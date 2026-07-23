"""pytest 共通設定。

`.nightly/scripts/nightly.py` は先頭がドットのディレクトリに置かれており、
`import .nightly.scripts.nightly` のような通常の import ができない
(ドットで始まる名前は Python の識別子として不正)。
そのためファイルパスから直接ロードするヘルパーを提供する。

本番の配置(ワークフロー6本が `.nightly/scripts/nightly.py` を参照)を
変更せずにテストできるようにするための措置。
"""

import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
NIGHTLY_PATH = REPO_ROOT / ".nightly" / "scripts" / "nightly.py"


def _load_nightly():
    spec = importlib.util.spec_from_file_location("nightly_under_test", NIGHTLY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"nightly.py をロードできません: {NIGHTLY_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def nightly(monkeypatch):
    """nightly.py をロードし、外部I/Oを無効化した状態で返す。

    GitHub API・Jules API・サマリー出力はすべて呼ばれたら失敗する
    ダミーに差し替える。各テストは必要なものだけを明示的に上書きする。
    これにより「テストが意図せず本物のAPIを叩く」事故を防ぐ。
    """
    mod = _load_nightly()

    def _forbidden(name):
        def _f(*a, **k):
            raise AssertionError(f"{name} が予期せず呼ばれました: args={a}")
        return _f

    for fn in ("sh", "gh_json", "gh_branch_exists", "gh_create_branch_from_main",
               "gh_put_file", "gh_get_file", "gh_get_json", "list_prs",
               "jules_create_session", "jules_get_session", "pr_files"):
        monkeypatch.setattr(mod, fn, _forbidden(fn), raising=True)

    # サマリーは副作用(ファイル追記)を持つので握りつぶし、内容だけ記録する
    mod._summaries = []
    monkeypatch.setattr(mod, "add_summary", lambda md: mod._summaries.append(md))
    monkeypatch.setattr(mod, "log", lambda msg: None)
    return mod
