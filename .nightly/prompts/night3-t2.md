# タスク: smoke test 作成

## 対象ファイル
- `tests/__init__.py`（新規作成、空ファイル）
- `tests/test_app.py`（新規作成）

## 要件
1. FastAPI の `TestClient`（`from starlette.testclient import TestClient`）を使う
2. 以下のテストケースを実装:
   - `test_health`: GET /health が 200 を返し、レスポンスに status キーがあること
   - `test_get_tasks`: GET /tasks が 200 を返し、レスポンスが Manifest スキーマに準拠すること
   - `test_put_tasks_valid`: PUT /tasks に有効な Manifest JSON を送り、200 が返ること
   - `test_put_tasks_invalid`: PUT /tasks に不正な JSON を送り、422 が返ること
3. テスト実行コマンド: `python -m pytest tests/ -v`

## 実装の注意
- `httpx` は使わない（`starlette.testclient` の `TestClient` のみ）
- テスト用の tasks.yml は `tmp_path` fixture で一時ファイルを作り、環境変数等でパスを差し替える
  - GET /tasks と PUT /tasks が `.nightly/tasks.yml` をハードコードしている場合は、
    app.py 側でパスを設定可能にするリファクタリングを行ってよい
- `pyproject.toml` に `pytest` を dev dependency として追加（`[project.optional-dependencies]` の `dev` グループ）

## やらないこと
- CI ワークフローの変更（ci.sh は建築家側で対応済み）
- HTML UI のテスト
- 認証・認可のテスト
