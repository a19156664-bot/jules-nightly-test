#!/usr/bin/env python3
"""
nightly.py — 深夜バッチ運用プロトコル(3時間×2ターン制)オーケストレーター
=============================================================================
GitHub Actions から呼び出される単一ファイルCLI。依存は PyYAML のみ。

サブコマンド:
  validate     tasks.yml の静的検証(ID重複・パス衝突・依存整合)
  start-night  統合ブランチ作成 + 第1ターンのJulesセッション投入
  turn-switch  02:30 JST: T1マージ状況を確認し、依存充足のT2のみ投入(fail-closed)
  gate         PRの自動マージゲート(スコープ/テスト改変/作者検査 → auto-merge有効化)
  watch        夜間: 起動済みセッションの状態を取得しログ化(PR自動作成の安全網。監視のみ)
  report       翌朝レポート生成(統合ブランチにコミット + Step Summary)

設計原則(fail-closed):
  - 疑わしい場合は「何もしない」に倒す。誤って走らせるより、空振りして翌朝報告する。
  - main には一切書き込まない。書き込み先は integration/nightly-* ブランチのみ。
  - Jules API はアルファ版。呼び出し失敗はタスク単位で握りつぶさず記録し、他タスクは続行。

必要な環境変数:
  GH_TOKEN            GitHub Actions の github.token
  GITHUB_REPOSITORY   owner/repo (Actionsが自動設定)
  JULES_API_KEY       Jules API キー (Secrets)
  JULES_SOURCE_NAME   例: sources/github/<owner>/<repo> (Variables)
  JULES_BOT_LOGINS    JulesがPRを開く際のGitHubログイン名(カンマ区切り, Variables)
"""

import argparse
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

try:
    import yaml
except ImportError:
    print("::error::PyYAML が必要です (pip install pyyaml)")
    sys.exit(1)

try:
    from zoneinfo import ZoneInfo
    JST = ZoneInfo("Asia/Tokyo")
except Exception:  # フォールバック(固定オフセット)
    JST = datetime.timezone(datetime.timedelta(hours=9))

MANIFEST_PATH = ".nightly/tasks.yml"
JULES_API = "https://jules.googleapis.com/v1alpha"
TASK_ID_RE = re.compile(r"^\[(T[12]-\d{2})\]")
# Jules に絶対に触らせないパス(マニフェストの protected_paths に加えて常時適用)
ALWAYS_PROTECTED = [".github/**", ".nightly/**", "AGENTS.md"]
LABEL_APPROVED = "nightly-approved"
LABEL_BLOCKED = "nightly-blocked"


# ---------------------------------------------------------------- 基盤ユーティリティ
def log(msg: str) -> None:
    print(msg, flush=True)


def add_summary(md: str) -> None:
    """GitHub Actions の Step Summary に追記(ローカル実行時はstdoutのみ)"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(md + "\n")
    log(md)


def sh(args: list, check: bool = True) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def gh_json(args: list):
    out = sh(["gh"] + args)
    return json.loads(out) if out else None


def repo() -> str:
    return os.environ["GITHUB_REPOSITORY"]


def night_date_now() -> str:
    """「夜の日付」= バッチが始まった夕方のJST日付。
    就寝前(~23時)にも深夜02:30にも翌朝05:45にも同じ日付を返すよう、
    現在JST時刻から12時間引いた日付を採用する。

    テスト用エスケープハッチ:
        環境変数 NIGHTLY_FORCE_DATE が設定されている場合、その値を返す。
        値は YYYY-MM-DD 形式でなければならない(形式不正時は ValueError)。
        本番運用ではこの環境変数を設定してはならない。日中テスト専用。
    """
    forced = os.environ.get("NIGHTLY_FORCE_DATE")
    if forced:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", forced):
            raise ValueError(
                f"NIGHTLY_FORCE_DATE must be YYYY-MM-DD format, got: {forced!r}"
            )
        return forced
    return (datetime.datetime.now(JST) - datetime.timedelta(hours=12)).date().isoformat()


def load_manifest(path: str = MANIFEST_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        m = yaml.safe_load(f)
    m["night"] = str(m.get("night", ""))  # YAMLのdate型を文字列に正規化
    for turn in ("turn1", "turn2"):
        m.setdefault(turn, [])
        m[turn] = m[turn] or []
    m.setdefault("protected_paths", [])
    m.setdefault("test_paths", [])
    return m


def branch_name(m: dict) -> str:
    return f"integration/nightly-{m['night'].replace('-', '')}"


def glob_match(path: str, pattern: str) -> bool:
    """`**`(区切り含む任意) と `*`(区切りを含まない) をサポートする簡易グロブ"""
    pat = re.escape(pattern)
    pat = pat.replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(pat, path) is not None


def matches_any(path: str, patterns: list) -> bool:
    return any(glob_match(path, p) for p in patterns)


def pattern_root(pattern: str) -> str:
    """衝突検査用: グロブの固定プレフィクス部分を取り出す"""
    return pattern.split("*", 1)[0].rstrip("/")


# ---------------------------------------------------------------- validate
def validate_manifest(m: dict) -> list:
    errors = []
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m["night"]):
        errors.append(f"night が YYYY-MM-DD 形式ではありません: '{m['night']}'")

    all_tasks = m["turn1"] + m["turn2"]
    ids = [t.get("id", "") for t in all_tasks]
    for i in ids:
        if not re.fullmatch(r"T[12]-\d{2}", i or ""):
            errors.append(f"タスクIDは T1-01 / T2-01 形式にしてください: '{i}'")
    if len(ids) != len(set(ids)):
        errors.append("タスクIDが重複しています")

    for t in all_tasks:
        tid = t.get("id", "?")
        if not (t.get("prompt") or t.get("prompt_file")):
            errors.append(f"{tid}: prompt または prompt_file が必要です")
        if t.get("prompt_file") and not os.path.exists(t["prompt_file"]):
            errors.append(f"{tid}: prompt_file が見つかりません: {t['prompt_file']}")
        if not t.get("paths"):
            errors.append(f"{tid}: paths(書き込み許可パス)が空です")

    for t in m["turn1"]:
        if t.get("depends_on"):
            errors.append(f"{t['id']}: 第1ターンのタスクは depends_on を持てません(ターン内依存の禁止)")

    t1_ids = {t["id"] for t in m["turn1"] if t.get("id")}
    for t in m["turn2"]:
        for dep in t.get("depends_on", []) or []:
            if dep not in t1_ids:
                errors.append(f"{t['id']}: 依存先 '{dep}' が第1ターンに存在しません(依存は1ホップ・T1→T2のみ)")

    # 同一ターン内のファイル所有権の衝突検査(保守的なプレフィクス判定)
    for turn in ("turn1", "turn2"):
        tasks = m[turn]
        for i in range(len(tasks)):
            for j in range(i + 1, len(tasks)):
                for pa in tasks[i].get("paths", []):
                    for pb in tasks[j].get("paths", []):
                        ra, rb = pattern_root(pa), pattern_root(pb)
                        if ra == rb or ra.startswith(rb + "/") or rb.startswith(ra + "/") or not ra or not rb:
                            errors.append(
                                f"{turn}: {tasks[i]['id']} と {tasks[j]['id']} の書き込みパスが"
                                f"重複の可能性 ('{pa}' vs '{pb}')。同一ターン内は互いに素にしてください")

    # 保護パスへの書き込み宣言を禁止
    for t in all_tasks:
        for p in t.get("paths", []):
            root = pattern_root(p)
            for prot in ALWAYS_PROTECTED + m["protected_paths"]:
                pr = pattern_root(prot)
                if pr and (root == pr or root.startswith(pr + "/")):
                    errors.append(f"{t['id']}: 保護パス '{prot}' 配下への書き込み宣言は禁止です ('{p}')")
    return errors


# ---------------------------------------------------------------- GitHub 操作
def gh_branch_exists(branch: str) -> bool:
    try:
        gh_json(["api", f"repos/{repo()}/git/ref/heads/{branch}"])
        return True
    except RuntimeError:
        return False


def gh_create_branch_from_main(branch: str) -> None:
    ref = gh_json(["api", f"repos/{repo()}/git/ref/heads/main"])
    sha = ref["object"]["sha"]
    sh(["gh", "api", "-X", "POST", f"repos/{repo()}/git/refs",
        "-f", f"ref=refs/heads/{branch}", "-f", f"sha={sha}"])


def gh_put_file(branch: str, path: str, content: str, message: str) -> None:
    """統合ブランチへログ/レポートをコミット(mainには使わないこと)"""
    sha = None
    try:
        cur = gh_json(["api", f"repos/{repo()}/contents/{path}?ref={branch}"])
        sha = cur.get("sha")
    except RuntimeError:
        pass
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    args = ["api", "-X", "PUT", f"repos/{repo()}/contents/{path}",
            "-f", f"message={message}", "-f", f"branch={branch}", "-f", f"content={b64}"]
    if sha:
        args += ["-f", f"sha={sha}"]
    sh(["gh"] + args)


def gh_get_file(branch: str, path: str):
    """統合ブランチから既存ファイルを取得(gh_put_file の逆操作)。
    存在しなければ None を返す。GitHub Contents API の base64 をデコードする。"""
    try:
        cur = gh_json(["api", f"repos/{repo()}/contents/{path}?ref={branch}"])
    except RuntimeError:
        return None
    if not cur or "content" not in cur:
        return None
    # 改行入り base64。b64decode は非アルファベット文字(改行)を無視する
    return base64.b64decode(cur["content"]).decode("utf-8")


def gh_get_json(branch: str, path: str):
    """gh_get_file の JSON 版。ファイル不在・JSON不正なら None(fail-closed)。"""
    raw = gh_get_file(branch, path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        log(f"::warning::{path} の JSON パースに失敗。無視して続行します。")
        return None


def list_prs(branch: str, state: str, with_checks: bool = True) -> list:
    """with_checks=False で statusCheckRollup を除外する。
    同フィールドの取得には checks:read でも足りず(checkSuite.workflowRun が
    Actions トークンから参照できない)、CI状態を使わない呼び出し元は False にする。"""
    fields = ("number,title,state,url,author,additions,deletions,"
              "mergedAt,isDraft")
    if with_checks:
        fields += ",statusCheckRollup"
    return gh_json(["pr", "list", "--repo", repo(), "--base", branch, "--state", state,
                    "--limit", "100", "--json", fields]) or []


def merged_task_ids(branch: str) -> set:
    ids = set()
    for pr in list_prs(branch, "merged", with_checks=False):
        mt = TASK_ID_RE.match(pr["title"] or "")
        if mt:
            ids.add(mt.group(1))
    return ids


def pr_files(number: int) -> list:
    """[{filename, status(added/modified/removed/renamed), previous_filename}]"""
    return gh_json(["api", f"repos/{repo()}/pulls/{number}/files", "--paginate"]) or []


# ---------------------------------------------------------------- Jules API
def jules_create_session(prompt: str, branch: str, title: str) -> dict:
    """Jules API (v1alpha) でセッションを作成する。
    注意: アルファ版APIのためフィールド名は変更されうる。初回導入時に
    https://developers.google.com/jules/api で最新スキーマを必ず確認すること。

    automationMode="AUTO_CREATE_PR": コード変更完了時にJulesがPRを自動公開する。
    これにより人間が Jules UI 上で「Publish PR」を手動で押す運用を廃止し、深夜
    無人運用を成立させる(requirePlanApproval は引き続き未設定=計画自動承認)。"""
    body = {
        "prompt": prompt,
        "title": title[:120],
        "sourceContext": {
            "source": os.environ["JULES_SOURCE_NAME"],
            "githubRepoContext": {"startingBranch": branch},
        },
        "automationMode": "AUTO_CREATE_PR",
    }
    req = urllib.request.Request(
        f"{JULES_API}/sessions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "X-Goog-Api-Key": os.environ["JULES_API_KEY"]},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read() or "{}")


def jules_get_session(name: str) -> dict:
    """Jules API (v1alpha) でセッションの現在状態を取得する(GET /sessions/{id})。
    `name` は起動ログに記録された "sessions/xxx" 形式。読み取り専用。"""
    req = urllib.request.Request(
        f"{JULES_API}/{name}",
        headers={"X-Goog-Api-Key": os.environ["JULES_API_KEY"]},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read() or "{}")


def jules_get_session_retry(name: str, attempts: int = 2) -> dict:
    """取得に失敗したら1回だけ再試行(=最大2回)。最終失敗は呼び出し側で握る。"""
    last = None
    for _ in range(max(1, attempts)):
        try:
            return jules_get_session(name)
        except Exception as e:  # noqa: BLE001 — 種別を問わず1回リトライ
            last = e
    raise last


# 停滞・要対応を示すセッション状態(朝レポート/監視で ⚠️ を付ける対象)
ATTENTION_STATES = {"FAILED", "AWAITING_USER_FEEDBACK",
                    "AWAITING_PLAN_APPROVAL", "PAUSED"}


def launched_sessions_from_logs(turn1_log, turn2_log) -> list:
    """turn1/turn2 の起動ログから status=='launched' のセッションを抽出(純粋関数)。
    turn1 ログは list、turn2 ログは {"results": [...]} 形式。未知/欠損は無視。"""
    entries = []

    def collect(items):
        for e in items or []:
            if isinstance(e, dict) and e.get("status") == "launched" and e.get("session"):
                entries.append({"task": e.get("id", "?"), "session": e["session"]})

    if isinstance(turn1_log, list):
        collect(turn1_log)
    if isinstance(turn2_log, dict):
        collect(turn2_log.get("results"))
    return entries


def session_record(task: str, name: str, resp: dict) -> dict:
    """Session レスポンスから sessions.json 用の1エントリを組み立てる(純粋関数)。
    未知フィールドは無視。pr_url / jules_url は取得できたときのみ付与する。"""
    rec = {"task": task, "session": name, "state": resp.get("state") or "UNKNOWN"}
    if resp.get("url"):
        rec["jules_url"] = resp["url"]
    for o in resp.get("outputs") or []:
        pr = (o or {}).get("pullRequest") or {}
        if pr.get("url"):
            rec["pr_url"] = pr["url"]
            break
    return rec


def session_note(sinfo) -> str:
    """朝レポートの『未提出』行に付けるセッション状態の注記(純粋関数)。
    sinfo が無ければ空文字を返す(=従来出力と完全一致・後方互換)。"""
    if not isinstance(sinfo, dict) or not sinfo.get("state"):
        return ""
    st = sinfo["state"]
    label = f"セッション: {st}"
    if st in ATTENTION_STATES or st == "API_ERROR":
        label += " — Jules URLを確認"
    ju = sinfo.get("jules_url")
    if ju:
        label = f"[{label}]({ju})"
    return f"(" + label + ")"


def watch_table(records: list, night: str, branch: str) -> str:
    """監視結果を Step Summary 用の表に整形する。"""
    lines = [f"## 👁 セッション監視 — {night} (branch: `{branch}`)", "",
             "| タスク | セッション | 状態 | PR | Jules |",
             "|---|---|---|---|---|"]
    attention = []
    for r in records:
        st = r.get("state", "?")
        flagged = st in ATTENTION_STATES or st == "API_ERROR"
        if flagged:
            attention.append(r)
        mark = "⚠️ " if flagged else ""
        pr = f"[PR]({r['pr_url']})" if r.get("pr_url") else "-"
        ju = f"[開く]({r['jules_url']})" if r.get("jules_url") else "-"
        lines.append(f"| {r.get('task', '?')} | `{r.get('session', '?')}` "
                     f"| {mark}{st} | {pr} | {ju} |")
    if not records:
        lines.append("| — | — | 監視対象のセッションはありません | - | - |")
    if attention:
        ids = ", ".join(r.get("task", "?") for r in attention)
        lines += ["", f"⚠️ 要対応のセッションがあります: {ids}。"
                  "朝レポートと Jules URL を確認してください(watch は監視のみ・自動介入はしません)。"]
    return "\n".join(lines)


def compose_prompt(m: dict, task: dict, branch: str) -> str:
    """tasks.yml のタスク定義から、Julesに渡す完全な指示文を組み立てる"""
    if task.get("prompt_file"):
        with open(task["prompt_file"], encoding="utf-8") as f:
            body = f.read()
    else:
        body = task["prompt"]
    paths = "\n".join(f"  - {p}" for p in task["paths"])
    protected = "\n".join(f"  - {p}" for p in ALWAYS_PROTECTED + m["protected_paths"])
    return f"""# タスク {task['id']}: {task.get('title', '')}

## 遵守事項(このリポジトリの AGENTS.md と併せて厳守すること)
- 作業ブランチの起点は `{branch}` です。Pull Request もこのブランチ宛てに作成してください。
- **PRのタイトルは必ず `[{task['id']}] ` で始めてください**(自動検収の識別子です。これがないとマージされません)。
- 変更してよいのは以下のパスのみです。これ以外のファイルへの変更(リフォーマット含む)を禁止します:
{paths}
- 以下のパスには絶対に触れないでください:
{protected}
- 既存のテストを削除・スキップ・期待値変更してはいけません。既存テストが失敗する場合は、修正せず失敗内容をPR説明文に報告してください。
- 障害で完了条件を満たせない場合、回避策を発明せず、できた部分で止めてPR説明文の「未確定事項」に記載して提出してください。
- PR説明文には「完了条件との対応表 / 変更ファイル一覧と理由 / テスト実行結果 / 未確定事項」を必ず含めてください。

## タスク内容
{body}
"""


def launch_tasks(m: dict, tasks: list, branch: str) -> list:
    results = []
    for t in tasks:
        try:
            prompt = compose_prompt(m, t, branch)
            res = jules_create_session(prompt, branch, f"[{t['id']}] {t.get('title', '')}")
            results.append({"id": t["id"], "status": "launched",
                            "session": res.get("name", "(unknown)")})
            log(f"launched {t['id']} -> {res.get('name')}")
        except Exception as e:  # fail-closed: 1件の失敗で夜全体を止めない。ただし必ず記録する
            results.append({"id": t["id"], "status": "launch_failed", "error": str(e)[:500]})
            log(f"::error::{t['id']} の投入に失敗: {e}")
    return results


def results_table(results: list) -> str:
    rows = ["| タスク | 状態 | 詳細 |", "|---|---|---|"]
    for r in results:
        rows.append(f"| {r['id']} | {r['status']} | {r.get('session') or r.get('error', '')} |")
    return "\n".join(rows)


# ---------------------------------------------------------------- コマンド実装
def cmd_validate(_args) -> int:
    m = load_manifest()
    errors = validate_manifest(m)
    if errors:
        for e in errors:
            log(f"::error::{e}")
        add_summary("## ❌ tasks.yml 検証失敗\n" + "\n".join(f"- {e}" for e in errors))
        return 1
    add_summary(f"## ✅ tasks.yml 検証OK (night={m['night']}, "
                f"T1={len(m['turn1'])}件, T2={len(m['turn2'])}件)")
    return 0


def cmd_start_night(_args) -> int:
    m = load_manifest()
    errors = validate_manifest(m)
    if errors:
        for e in errors:
            log(f"::error::{e}")
        add_summary("## ❌ 検証失敗のため夜間バッチを開始しません(fail-closed)\n"
                    + "\n".join(f"- {e}" for e in errors))
        return 1
    if m["night"] != night_date_now():
        add_summary(f"## ⏭ night={m['night']} は今夜({night_date_now()})ではないため開始しません。"
                    "古いマニフェストの誤発火防止です。")
        return 0
    branch = branch_name(m)
    if gh_branch_exists(branch):
        add_summary(f"## ⏭ {branch} は既に存在します。今夜は開始済みです。"
                    "やり直す場合はブランチを削除して tasks.yml を再コミットしてください。")
        return 0
    gh_create_branch_from_main(branch)
    log(f"created branch {branch}")
    results = launch_tasks(m, m["turn1"], branch)
    gh_put_file(branch, f".nightly/logs/{m['night']}-turn1.json",
                json.dumps(results, ensure_ascii=False, indent=2),
                f"nightly: turn1 launch log {m['night']}")
    failed = [r for r in results if r["status"] != "launched"]
    add_summary(f"## 🌙 第1ターン開始 (branch: `{branch}`)\n\n{results_table(results)}"
                + ("\n\n⚠️ 投入失敗があります。翌朝確認してください。" if failed else ""))
    return 0


def cmd_turn_switch(_args) -> int:
    m = load_manifest()
    if m["night"] != night_date_now():
        add_summary(f"## ⏭ 今夜のバッチはありません (manifest night={m['night']})")
        return 0
    branch = branch_name(m)
    if not gh_branch_exists(branch):
        add_summary(f"## ⏭ {branch} が存在しないためT2を投入しません(T1未開始?)")
        return 0

    merged = merged_task_ids(branch)
    launch, skipped = [], []
    for t in m["turn2"]:
        deps = set(t.get("depends_on", []) or [])
        missing = sorted(deps - merged)
        if missing:
            skipped.append({"id": t["id"], "status": "skipped",
                            "reason": f"依存未充足: {', '.join(missing)}"})
        else:
            launch.append(t)

    results = launch_tasks(m, launch, branch) + skipped
    gh_put_file(branch, f".nightly/logs/{m['night']}-turn2.json",
                json.dumps({"merged_t1": sorted(merged), "results": results},
                           ensure_ascii=False, indent=2),
                f"nightly: turn2 switch log {m['night']}")
    add_summary(f"## 🔄 ターン切替 (T1マージ済: {', '.join(sorted(merged)) or 'なし'})\n\n"
                + results_table(results))
    return 0


def gate_check(m: dict, pr: dict, files: list) -> list:
    """違反リストを返す。空なら合格。"""
    violations = []
    title = pr.get("title") or ""
    mt = TASK_ID_RE.match(title)
    if not mt:
        return [f"PRタイトルがタスクID形式 `[T1-01] ...` で始まっていません: '{title}'"]
    tid = mt.group(1)
    task = next((t for t in m["turn1"] + m["turn2"] if t.get("id") == tid), None)
    if task is None:
        return [f"タスク {tid} が tasks.yml に存在しません"]

    allowed_logins = [s.strip() for s in os.environ.get("JULES_BOT_LOGINS", "").split(",") if s.strip()]
    author = ((pr.get("user") or {}).get("login")) or ""
    if not allowed_logins:
        violations.append("リポジトリ変数 JULES_BOT_LOGINS が未設定です。"
                          f"このPRの作者は '{author}' でした。SETUP_GUIDE.md の手順で設定してください")
    elif author not in allowed_logins:
        violations.append(f"PR作者 '{author}' が許可リスト({', '.join(allowed_logins)})にありません")

    protected = ALWAYS_PROTECTED + m["protected_paths"]
    for f in files:
        name = f["filename"]
        status = f.get("status", "")
        if matches_any(name, protected):
            violations.append(f"保護パスへの変更: `{name}`")
        if not matches_any(name, task.get("paths", [])):
            violations.append(f"スコープ逸脱: `{name}` は {tid} の許可パス外です")
        if m["test_paths"] and matches_any(name, m["test_paths"]) and status != "added":
            violations.append(f"既存テストの改変({status}): `{name}` — テストは追加のみ許可")
        if status == "renamed" and f.get("previous_filename") and \
                m["test_paths"] and matches_any(f["previous_filename"], m["test_paths"]):
            violations.append(f"既存テストのリネーム: `{f['previous_filename']}`")
    return violations


def cmd_gate(args) -> int:
    m = load_manifest()
    n = args.pr
    pr = gh_json(["api", f"repos/{repo()}/pulls/{n}"])
    base = (pr.get("base") or {}).get("ref", "")
    if base != branch_name(m):
        log(f"skip: PR base '{base}' は今夜の統合ブランチではありません")
        return 0
    if ((pr.get("head") or {}).get("repo") or {}).get("full_name") != repo():
        sh(["gh", "pr", "comment", str(n), "--repo", repo(),
            "--body", "⛔ フォークからのPRは夜間パイプラインの対象外です。"], check=False)
        return 0
    if pr.get("draft"):
        log("skip: draft PR")
        return 0

    files = pr_files(n)
    violations = gate_check(m, pr, files)
    if violations:
        body = ("## 🌙 夜間ゲート: 自動マージ不可\n"
                + "\n".join(f"- {v}" for v in violations)
                + "\n\nこのPRは翌朝の人間+建築家レビューに回されます(fail-closed)。")
        sh(["gh", "pr", "edit", str(n), "--repo", repo(), "--add-label", LABEL_BLOCKED], check=False)
        sh(["gh", "pr", "comment", str(n), "--repo", repo(), "--body", body], check=False)
        add_summary(f"## ⛔ PR #{n} ブロック\n" + "\n".join(f"- {v}" for v in violations))
        return 0  # ジョブは緑のまま。状態はラベルとコメントで表現する

    sh(["gh", "pr", "edit", str(n), "--repo", repo(), "--add-label", LABEL_APPROVED], check=False)
    try:
        # 必須チェック(ci)が全て緑になった時点でGitHubがマージする。
        # auto-merge には「Allow auto-merge 有効化 + integration/nightly-** への必須チェック設定」が必要。
        sh(["gh", "pr", "merge", str(n), "--repo", repo(), "--squash", "--auto"])
        add_summary(f"## ✅ PR #{n} ゲート合格 → auto-merge 予約")
    except RuntimeError as e:
        sh(["gh", "pr", "comment", str(n), "--repo", repo(), "--body",
            "⚠️ ゲートは合格しましたが auto-merge を有効化できませんでした。"
            "リポジトリ設定(Allow auto-merge / ブランチ保護)を確認してください。"
            "CIを迂回した直接マージは行いません(fail-closed)。"], check=False)
        add_summary(f"## ⚠️ PR #{n} auto-merge 有効化失敗: {e}")
    return 0


def ci_state(pr: dict) -> str:
    checks = pr.get("statusCheckRollup") or []
    if not checks:
        return "no-checks"
    states = {(c.get("conclusion") or c.get("state") or "").upper() for c in checks}
    if states & {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}:
        return "fail"
    if states & {"", "PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED"}:
        return "pending"
    return "pass"


def cmd_watch(_args) -> int:
    """起動済みセッションの状態を Jules API で取得し、統合ブランチに記録する。
    読み取り+ログコミットのみ。sendMessage/approvePlan/delete/PR操作は一切しない。
    night不一致・ブランチ不在・ログ不在・API失敗のいずれでもクラッシュせず正常終了。"""
    m = load_manifest()
    if m["night"] != night_date_now():
        add_summary(f"## ⏭ 今夜のバッチはありません (manifest night={m['night']})")
        return 0
    branch = branch_name(m)
    if not gh_branch_exists(branch):
        add_summary(f"## ⏭ {branch} が存在しないため監視をスキップします")
        return 0

    turn1_log = gh_get_json(branch, f".nightly/logs/{m['night']}-turn1.json")
    turn2_log = gh_get_json(branch, f".nightly/logs/{m['night']}-turn2.json")
    if turn1_log is None and turn2_log is None:
        add_summary(f"## ⏭ 起動ログ({m['night']}-turn1/2.json)がまだありません。監視をスキップします。")
        return 0

    launched = launched_sessions_from_logs(turn1_log, turn2_log)
    records = []
    for item in launched:
        try:
            resp = jules_get_session_retry(item["session"])
            records.append(session_record(item["task"], item["session"], resp))
        except Exception as e:  # fail-closed: 1件の失敗で監視全体を止めない。必ず記録する
            records.append({"task": item["task"], "session": item["session"],
                            "state": "API_ERROR", "error": str(e)[:300]})
            log(f"::warning::{item['task']} ({item['session']}) の状態取得に失敗: {e}")

    payload = {"checked_at": datetime.datetime.now(JST).isoformat(),
               "sessions": records}
    gh_put_file(branch, f".nightly/logs/{m['night']}-sessions.json",
                json.dumps(payload, ensure_ascii=False, indent=2),
                f"nightly: session watch log {m['night']}")
    add_summary(watch_table(records, m["night"], branch))
    return 0


def cmd_report(_args) -> int:
    m = load_manifest()
    if m["night"] != night_date_now():
        add_summary(f"## ⏭ 今夜のバッチはありません (manifest night={m['night']})")
        return 0
    branch = branch_name(m)
    if not gh_branch_exists(branch):
        add_summary(f"## ⏭ {branch} が存在しません")
        return 0

    # 監視ログ(session-watchdog が生成)があれば読み込む。無ければ従来動作のまま。
    sessions_by_task = {}
    watch_log = gh_get_json(branch, f".nightly/logs/{m['night']}-sessions.json")
    if isinstance(watch_log, dict):
        for s in watch_log.get("sessions") or []:
            if isinstance(s, dict) and s.get("task"):
                sessions_by_task[s["task"]] = s

    prs = list_prs(branch, "all", with_checks=False)
    by_task = {}
    unmatched = []
    for pr in prs:
        mt = TASK_ID_RE.match(pr["title"] or "")
        if mt:
            by_task.setdefault(mt.group(1), []).append(pr)
        else:
            unmatched.append(pr)

    lines = [f"# 🌅 朝レポート — {m['night']} (branch: `{branch}`)", "",
             "| タスク | 依存 | PR | 状態 | CI | 差分 | ゲート違反 | 推奨仕分け |",
             "|---|---|---|---|---|---|---|---|"]
    for t in m["turn1"] + m["turn2"]:
        tid = t["id"]
        deps = ", ".join(t.get("depends_on", []) or []) or "-"
        plist = by_task.get(tid, [])
        if not plist:
            state_cell = "未提出/スキップ" + session_note(sessions_by_task.get(tid))
            lines.append(f"| {tid} | {deps} | なし | {state_cell} | - | - | - | ログ確認 |")
            continue
        for pr in plist:
            ci = ci_state(pr)
            state = "統合済" if pr["state"] == "MERGED" else pr["state"]
            flags = "-"
            verdict = "【一括スクリーニング】"
            if pr["state"] == "MERGED":
                verdict = "統合済(サンプル確認)"
            else:
                v = gate_check(m, {"title": pr["title"],
                                   "user": {"login": (pr.get("author") or {}).get("login", "")}},
                               pr_files(pr["number"]))
                flags = "; ".join(v) if v else "-"
                if ci == "fail":
                    verdict = "【要修正】CI不合格"
                elif v:
                    verdict = "【要人間確認】"
                elif ci == "pending":
                    verdict = "CI実行中(再確認)"
            lines.append(f"| {tid} | {deps} | [#{pr['number']}]({pr['url']}) | {state} | {ci} "
                         f"| +{pr['additions']}/-{pr['deletions']} | {flags} | {verdict} |")

    if unmatched:
        lines += ["", "## ⚠️ タスクID不明のPR(全件、人間確認)"]
        lines += [f"- [#{p['number']}]({p['url']}) {p['title']}" for p in unmatched]

    lines += ["", "## 次のアクション",
              "1. 【要修正】: CIログ要約をJulesに差し戻し(日中の再試行へ)",
              "2. 上表の【一括スクリーニング】対象のみ、Fable 5 の一括レビュープロンプトへ",
              "3. 検収完了後、人間が `" + branch + "` → `main` のPRを作成しマージ",
              "4. 横断所見をナレッジログへ(フライホイール)"]

    report = "\n".join(lines)
    # 統合ブランチには branch protection(ci必須)があり PUT が 409 で拒否されるため、
    # レポートは main に直接書き込む(統合ブランチ側の変更は生成しない)。
    gh_put_file("main", f".nightly/reports/morning-report-{m['night']}.md",
                report, f"nightly: morning report {m['night']}")
    add_summary(report)
    return 0


# ---------------------------------------------------------------- main
def main() -> int:
    p = argparse.ArgumentParser(description="nightly batch orchestrator")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sub.add_parser("start-night")
    sub.add_parser("turn-switch")
    g = sub.add_parser("gate")
    g.add_argument("--pr", type=int, required=True)
    sub.add_parser("watch")
    sub.add_parser("report")
    args = p.parse_args()
    return {"validate": cmd_validate, "start-night": cmd_start_night,
            "turn-switch": cmd_turn_switch, "gate": cmd_gate,
            "watch": cmd_watch, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
