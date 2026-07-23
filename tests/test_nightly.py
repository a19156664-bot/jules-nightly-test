"""nightly.py の冪等性ガードと fail-closed 挙動の回帰テスト。

背景(2026-07-23 の事故):
  1. turn-switch に冪等性ガードが無く、同一タスク T2-01 が7回投入された。
     ダッシュボードは終始「正常運転中」で、検知層が一つも作動しなかった。
  2. 統合ブランチの branch protection により観測ログの PUT が HTTP 409 で
     恒久的に失敗しており、ログの存在を根拠にしていた T1 側のガードが
     無効化されていた(約7夜にわたり発覚せず)。

このファイルは上記2件の再発を機械的に検出することを目的とする。
「ガードが効くこと」ではなく「ガードが効かなくなったら落ちること」を書く。
"""

import json

import pytest


# ---------------------------------------------------------------- 補助
def make_manifest(night="2026-07-24", turn1=None, turn2=None):
    """validate_manifest を通過する最小のマニフェスト。"""
    def task(tid, path, deps=None):
        t = {"id": tid, "prompt": "do something", "paths": [path]}
        if deps:
            t["depends_on"] = deps
        return t

    return {
        "night": night,
        "turn1": turn1 if turn1 is not None else [task("T1-01", "src/a/**")],
        "turn2": turn2 if turn2 is not None else [task("T2-01", "src/b/**")],
        "protected_paths": [],
    }


@pytest.fixture
def wired(nightly, monkeypatch):
    """start_night / turn_switch を実行できる最小構成に配線する。

    launch_tasks は「何が投入されたか」を記録するだけのスパイに差し替える。
    実際に Jules を呼ばないので、ガードが破れた場合はここに現れる。
    """
    state = {"launched": [], "put": [], "branch_exists": True,
             "merged": set(), "logs": {}}

    def fake_launch_tasks(m, tasks, branch):
        state["launched"].extend(t["id"] for t in tasks)
        return [{"id": t["id"], "status": "launched", "session": "sessions/x"}
                for t in tasks]

    def fake_put(branch, path, content, message):
        state["put"].append((branch, path))

    def fake_get_json(branch, path):
        return state["logs"].get(path)

    monkeypatch.setattr(nightly, "load_manifest", lambda *a, **k: state["manifest"])
    monkeypatch.setattr(nightly, "night_date_now", lambda: state["manifest"]["night"])
    monkeypatch.setattr(nightly, "launch_tasks", fake_launch_tasks)
    monkeypatch.setattr(nightly, "gh_put_file", fake_put)
    monkeypatch.setattr(nightly, "gh_get_json", fake_get_json)
    monkeypatch.setattr(nightly, "gh_branch_exists", lambda b: state["branch_exists"])
    monkeypatch.setattr(nightly, "gh_create_branch_from_main", lambda b: None)
    monkeypatch.setattr(nightly, "merged_task_ids", lambda b: state["merged"])
    state["manifest"] = make_manifest()
    return nightly, state


# ---------------------------------------------------------------- launched_task_ids
def test_launched_task_ids_ログが無ければ空集合(nightly, monkeypatch):
    monkeypatch.setattr(nightly, "gh_get_json", lambda b, p: None)
    assert nightly.launched_task_ids("2026-07-24") == set()


def test_launched_task_ids_turn1形式はリスト(nightly, monkeypatch):
    logs = {
        nightly.log_path("2026-07-24", "turn1.json"): [
            {"id": "T1-01", "status": "launched", "session": "s/1"},
            {"id": "T1-02", "status": "error"},
        ],
        nightly.log_path("2026-07-24", "turn2.json"): None,
    }
    monkeypatch.setattr(nightly, "gh_get_json", lambda b, p: logs.get(p))
    # error のものは投入済みに含めない(再投入されるべき)
    assert nightly.launched_task_ids("2026-07-24") == {"T1-01"}


def test_launched_task_ids_turn2形式は辞書(nightly, monkeypatch):
    logs = {
        nightly.log_path("2026-07-24", "turn1.json"): None,
        nightly.log_path("2026-07-24", "turn2.json"): {
            "merged_t1": ["T1-01"],
            "results": [
                {"id": "T2-01", "status": "launched", "session": "s/2"},
                {"id": "T2-02", "status": "skipped", "reason": "既にマージ済み"},
            ],
        },
    }
    monkeypatch.setattr(nightly, "gh_get_json", lambda b, p: logs.get(p))
    assert nightly.launched_task_ids("2026-07-24") == {"T2-01"}


def test_launched_task_ids_壊れたログでも例外を投げない(nightly, monkeypatch):
    logs = {
        nightly.log_path("2026-07-24", "turn1.json"): ["文字列", None, 42, {}],
        nightly.log_path("2026-07-24", "turn2.json"): {"results": "not a list"},
    }
    monkeypatch.setattr(nightly, "gh_get_json", lambda b, p: logs.get(p))
    assert nightly.launched_task_ids("2026-07-24") == set()


def test_launched_task_ids_はログ専用ブランチを読む(nightly, monkeypatch):
    """統合ブランチではなく ops/nightly-logs を読むこと(R5対策)。"""
    seen = []
    monkeypatch.setattr(nightly, "gh_get_json",
                        lambda b, p: seen.append(b) or None)
    nightly.launched_task_ids("2026-07-24")
    assert seen and all(b == nightly.LOGS_BRANCH for b in seen)


# ---------------------------------------------------------------- T1 冪等性ガード
def test_T1_未投入なら投入される(wired):
    n, st = wired
    assert n.cmd_start_night(None) == 0
    assert st["launched"] == ["T1-01"]


def test_T1_マージ済みなら再投入しない(wired):
    n, st = wired
    st["merged"] = {"T1-01"}
    assert n.cmd_start_night(None) == 0
    assert st["launched"] == []


def test_T1_ログ上投入済みなら再投入しない(wired):
    """PR がまだ無い時間帯をログで埋める(レースウィンドウ対策)。"""
    n, st = wired
    st["logs"][n.log_path("2026-07-24", "turn1.json")] = [
        {"id": "T1-01", "status": "launched", "session": "s/1"}]
    assert n.cmd_start_night(None) == 0
    assert st["launched"] == []


def test_T1_ブランチが無くてもガードが効く(wired):
    """07-23 の事故と同型の退行を検出する。

    旧実装はブランチが存在するときしかガードを通らなかったため、
    ブランチを削除すると同一タスクが再投入された。
    ブランチ整理スクリプトが暴走の引き金になりうる。
    """
    n, st = wired
    st["branch_exists"] = False
    st["merged"] = {"T1-01"}
    assert n.cmd_start_night(None) == 0
    assert st["launched"] == [], "ブランチ不在時にガードが素通りしている"


def test_T1_タスク単位で判定される(wired):
    """一部だけ投入済みなら、残りだけを投入する(夜単位ではない)。"""
    n, st = wired
    st["manifest"] = make_manifest(turn1=[
        {"id": "T1-01", "prompt": "x", "paths": ["src/a/**"]},
        {"id": "T1-02", "prompt": "y", "paths": ["src/c/**"]},
    ])
    st["merged"] = {"T1-01"}
    assert n.cmd_start_night(None) == 0
    assert st["launched"] == ["T1-02"]


def test_T1_全て投入済みならログも書かない(wired):
    n, st = wired
    st["merged"] = {"T1-01"}
    n.cmd_start_night(None)
    assert st["put"] == []


# ---------------------------------------------------------------- fail-closed
def test_T1_ログ書き込み失敗は異常終了(wired, monkeypatch):
    """投入したのにログが残らない状態を成功扱いにしない(R5対策)。

    旧実装は warning を出して return 0 していたため、
    ガードの根拠が欠落したまま7夜にわたり誰も気づかなかった。
    """
    n, st = wired

    def boom(*a, **k):
        raise RuntimeError("HTTP 409")

    monkeypatch.setattr(n, "gh_put_file", boom)
    assert n.cmd_start_night(None) == 1, "ログ書き込み失敗が成功扱いになっている"


def test_T2_ログ書き込み失敗は異常終了(wired, monkeypatch):
    n, st = wired

    def boom(*a, **k):
        raise RuntimeError("HTTP 409")

    monkeypatch.setattr(n, "gh_put_file", boom)
    assert n.cmd_turn_switch(None) == 1


# ---------------------------------------------------------------- T2 冪等性ガード
def test_T2_マージ済みなら再投入しない(wired):
    """07-23 に実際に発生した無限ループの直接の回帰テスト。"""
    n, st = wired
    st["merged"] = {"T1-01", "T2-01"}
    assert n.cmd_turn_switch(None) == 0
    assert st["launched"] == [], "T2 が再投入されている(無限ループの再発)"


def test_T2_ログ上投入済みなら再投入しない(wired):
    n, st = wired
    st["merged"] = {"T1-01"}
    st["logs"][n.log_path("2026-07-24", "turn2.json")] = {
        "results": [{"id": "T2-01", "status": "launched", "session": "s/2"}]}
    assert n.cmd_turn_switch(None) == 0
    assert st["launched"] == []


def test_T2_依存未充足なら投入しない(wired):
    n, st = wired
    st["manifest"] = make_manifest(turn2=[
        {"id": "T2-01", "prompt": "x", "paths": ["src/b/**"],
         "depends_on": ["T1-01"]}])
    st["merged"] = set()
    assert n.cmd_turn_switch(None) == 0
    assert st["launched"] == []


def test_T2_依存判定はマージ済みのみを見る(wired):
    """依存充足の根拠に「投入済み」を混ぜてはならない。

    投入されただけで未マージの依存タスクを充足扱いにすると、
    成果物が存在しないまま後続タスクが走る。
    再投入抑止(already)と依存判定(merged)は根拠が異なる。
    """
    n, st = wired
    st["manifest"] = make_manifest(turn2=[
        {"id": "T2-01", "prompt": "x", "paths": ["src/b/**"],
         "depends_on": ["T1-01"]}])
    st["merged"] = set()
    # T1-01 は投入済みだが未マージ
    st["logs"][n.log_path("2026-07-24", "turn1.json")] = [
        {"id": "T1-01", "status": "launched", "session": "s/1"}]
    assert n.cmd_turn_switch(None) == 0
    assert st["launched"] == [], "未マージの依存を充足扱いにしている"


def test_T2_依存充足なら投入される(wired):
    n, st = wired
    st["manifest"] = make_manifest(turn2=[
        {"id": "T2-01", "prompt": "x", "paths": ["src/b/**"],
         "depends_on": ["T1-01"]}])
    st["merged"] = {"T1-01"}
    assert n.cmd_turn_switch(None) == 0
    assert st["launched"] == ["T2-01"]


# ---------------------------------------------------------------- ログ配置
def test_ログはログ専用ブランチに書かれる(wired):
    """統合ブランチに書くと branch protection で 409 になる(R5)。"""
    n, st = wired
    n.cmd_start_night(None)
    assert st["put"], "ログが書かれていない"
    for branch, path in st["put"]:
        assert branch == n.LOGS_BRANCH
        assert not path.startswith(".nightly/logs/"), "旧パスが残っている"


def test_log_path_はサイクル識別子をディレクトリに分離する(nightly):
    """X-1 で識別子の形式が変わってもコード構造が影響を受けないこと。"""
    assert nightly.log_path("2026-07-24", "turn1.json") == "logs/2026-07-24/turn1.json"
    assert nightly.log_path("cycle-0042", "turn1.json") == "logs/cycle-0042/turn1.json"
