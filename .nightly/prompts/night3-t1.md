# タスク: PUT /tasks エンドポイント追加

## 対象ファイル
- `webui/app.py`（既存ファイルを編集）

## 要件
1. `PUT /tasks` エンドポイントを追加する
2. リクエストボディは JSON で、`webui/models.py` の `Manifest` スキーマに準拠すること
3. 受け取った JSON を Pydantic `Manifest` モデルでバリデーションする
4. バリデーション成功後、`.nightly/tasks.yml` に YAML 形式で書き戻す
5. 書き戻し時、既存の tasks.yml を上書きする
6. レスポンスは更新後の Manifest を JSON で返す（status 200）
7. バリデーション失敗時は 422 を返す（FastAPI デフォルト動作でOK）

## 実装の注意
- `yaml.dump` 時は `allow_unicode=True, default_flow_style=False` を指定
- tasks.yml のパスは環境変数 or デフォルト `.nightly/tasks.yml` で解決
- 既存の `GET /tasks` の YAML 読み込みロジックと共通化できる部分は関数抽出してよい
- `import` 追加が必要なら `webui/app.py` 先頭に追加

## やらないこと
- テストの作成（T2-01 で別途実施）
- HTML UI の作成
- 認証・認可の追加
