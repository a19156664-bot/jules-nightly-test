# 実装指示書: Publish PR 自動化(深夜完全無人化の最終ピース)

- 発行者: Fable 5(建築家)
- 実装者: Claude Code
- 対象リポジトリ: このリポジトリ(a19156664-bot/jules-nightly-test)のローカルクローン
- 作業ID: AUTO-PR-01

---

## 0. あなた(Claude Code)への依頼の全体像

このリポジトリは「Google Jules を使った深夜完全無人バッチ開発パイプライン」のテンプレートである。まず `AGENTS.md` と `.nightly/scripts/nightly.py` と `.github/workflows/` 配下を読み、既存の設計(fail-closed、統合ブランチ方式、mainへの不可侵)を把握してから作業に入ること。

**背景**: 昨日の日中試運転で、Jules はタスク実装完了後「Ready for review」状態で停止し、人間が Jules UI 上で「Publish PR」ボタンを押すまで GitHub に PR を作成しないことが判明した。これは深夜無人運用の致命的なギャップである。

**根本原因(建築家が特定済み)**: 現行の `nightly.py` の `jules_create_session()` が、セッション作成時に `automationMode` フィールドを渡していないため。Jules API 公式リファレンス(https://jules.google/docs/api/reference/sessions/)に以下が明記されている:

> `automationMode` (string): Automation mode. Use 'AUTO_CREATE_PR' to automatically create pull requests when code changes are ready.

**依頼内容**: 以下のタスク1〜4を実装する。タスク1が本丸、タスク2〜4は「PRが自動作成されなかった夜に、翌朝原因が分かる」ための安全網である。

---

## 1. 検証済みの Jules API 仕様(外部知識・この通りに実装してよい)

ベースURL: `https://jules.googleapis.com/v1alpha`
認証: HTTPヘッダ `X-Goog-Api-Key: <APIキー>`(既存実装と同じ)

### 1-1. セッション作成(既存実装の拡張対象)
`POST /sessions`
リクエストボディの関連フィールド:
- `prompt` (string, 必須)
- `title` (string)
- `sourceContext.source` / `sourceContext.githubRepoContext.startingBranch`(既存実装通り)
- `requirePlanApproval` (boolean): 未設定なら計画は自動承認される(現行の未設定を維持すること。夜間無人運用の意図的な設計)
- **`automationMode` (string): `"AUTO_CREATE_PR"` を指定すると、コード変更完了時に自動でPRを作成する** ← 今回追加するもの

### 1-2. セッション取得(タスク2で新規利用)
`GET /sessions/{sessionId}`
レスポンス(Session オブジェクト)の関連フィールド:
- `name`: "sessions/1234567" 形式(既存の起動ログに記録済みの値と同形式)
- `state`: 次の8状態のいずれか — `QUEUED` / `PLANNING` / `AWAITING_PLAN_APPROVAL` / `AWAITING_USER_FEEDBACK` / `IN_PROGRESS` / `PAUSED` / `COMPLETED` / `FAILED`
- `outputs[]`: 完了後に存在。`outputs[].pullRequest.url` / `.title` / `.description` にPR情報が入る
- `url`: Jules UI 上のセッションURL(朝レポートに載せると人間が調査しやすい)

### 1-3. 注意事項
- APIはアルファ版。HTTPエラー時はエラー本文をログに残し、**リトライは1回まで、失敗しても他セッションの処理は続行**(既存の fail-closed 方針と同じ)
- レスポンスに未知のフィールドがあっても無視して壊れない実装にすること

---

## 2. 実装タスク

### タスク1(必須・本丸): automationMode の追加

`.nightly/scripts/nightly.py` の `jules_create_session()` 内、セッション作成のリクエストボディに以下を追加する:

```python
"automationMode": "AUTO_CREATE_PR",
```

- 既存のフィールド(prompt / title / sourceContext)は変更しない
- `requirePlanApproval` は引き続き**設定しない**(自動承認が意図)
- 関数コメントに「AUTO_CREATE_PR: 完了時にPRを自動公開(Publish PR手動押下の廃止)」の趣旨を追記

### タスク2(必須): `watch` サブコマンドの新設

`nightly.py` に5つの既存サブコマンド(validate / start-night / turn-switch / gate / report)と同じ流儀で、6つ目のサブコマンド `watch` を追加する。

**処理内容**:
1. マニフェスト(`.nightly/tasks.yml`、mainからcheckout済みの作業ディレクトリのもの)を読み、`night` が今夜(既存の `night_date_now()` 基準)でなければ `⏭` サマリーを出して正常終了(既存の turn-switch と同じガード)
2. 統合ブランチが存在しなければ同様に正常終了
3. 統合ブランチ上の起動ログ `.nightly/logs/{night}-turn1.json` と `{night}-turn2.json` を `gh api` の contents 取得(既存の `gh_put_file` の逆操作。base64デコードが必要)で読み込む。turn2ログが未生成(ターン切替前)なら turn1 のみで続行
4. 起動ログ内の `status == "launched"` の各エントリからセッション名(`sessions/xxx`)を取り出し、`GET /sessions/{id}` で状態を取得
5. 結果を `.nightly/logs/{night}-sessions.json` として統合ブランチにコミット(既存の `gh_put_file` を利用)。形式:
   ```json
   {"checked_at": "<ISO8601 JST>", "sessions": [
     {"task": "T1-01", "session": "sessions/123", "state": "COMPLETED",
      "pr_url": "https://github.com/.../pull/1", "jules_url": "https://jules.google.com/session/..."}
   ]}
   ```
   (pr_url / jules_url は取得できた場合のみ。stateの取得に失敗したら `"state": "API_ERROR"` とエラー要旨を記録)
6. Step Summary に表形式で出力。`FAILED` / `AWAITING_USER_FEEDBACK` / `AWAITING_PLAN_APPROVAL` / `PAUSED` のセッションがあれば `⚠️` を付けて目立たせる

**禁止事項**: watch は読み取りとログコミットのみ。セッションへの sendMessage / approvePlan / delete、PRの操作は一切行わない(監視に徹する)。

### タスク3(必須): 夜間監視ワークフローの新設

`.github/workflows/session-watchdog.yml` を新規作成する。既存ワークフロー(特に morning-report.yml)の構成・コメントスタイルを踏襲すること。

- name: `nightly-session-watchdog`
- トリガー:
  - `schedule`: cron `"0,30 15-20 * * *"`(UTC。= JST 0:00〜5:30 の間、30分おき)
  - `workflow_dispatch`(手動リカバリ用)
- permissions: `contents: write`(ログコミット用)、`pull-requests: read`
- concurrency: `nightly-session-watchdog` / cancel-in-progress: false
- 手順: checkout main → pip install pyyaml → Guard(JULES_API_KEY / JULES_SOURCE_NAME 未設定なら即エラー終了。turn-switch.yml と同じ)→ `python3 .nightly/scripts/nightly.py watch`
- 冒頭コメントに役割(「PR自動作成の安全網。夜間にセッション状態を記録し、FAILED/停滞を朝レポートで可視化する」)を記載

### タスク4(必須・小): 朝レポートの強化

`nightly.py` の `cmd_report()` を最小限に拡張する:

1. `.nightly/logs/{night}-sessions.json` が統合ブランチに存在すれば読み込む(存在しなければ従来動作のまま。**後方互換を壊さない**)
2. 「PRなし(未提出/スキップ)」と表示していたタスク行に、セッション状態があれば追記する。例: `未提出(セッション: FAILED)` / `未提出(セッション: AWAITING_USER_FEEDBACK — Jules URLを確認)`
3. sessions.json に jules_url があれば、該当行からリンクできるようにする

既存の表の列構成・推奨仕分けロジック(`【要修正】` 等)は**変更しない**。追記のみ。

### タスク5(任意・時間があれば): ドキュメント更新

`SETUP_GUIDE.md` の「既知の制約と正直な注意点」にある Publish PR 関連の記述状況を確認し、必要なら「automationMode: AUTO_CREATE_PR により自動公開される。session-watchdog が夜間の安全網」の趣旨に更新する。大幅な書き換えはしない。

---

## 3. ガードレール(絶対遵守)

1. **変更してよいファイル**: `.nightly/scripts/nightly.py`、`.github/workflows/session-watchdog.yml`(新規)、`SETUP_GUIDE.md`(タスク5のみ)。**これ以外への変更を禁止する**
2. 既存の `gate_check()` / `cmd_gate()` / `validate_manifest()` / 既存4ワークフローのロジックを**変更しない**(watch と report 追記のための共通関数の追加は可。既存関数のシグネチャ変更は不可)
3. main ブランチへの書き込み処理を新設しない(新コードの書き込み先は統合ブランチのログのみ)
4. APIキー・シークレットをコード・ログ・コメントに書かない。ローカルから Jules API を**実呼び出ししない**(実地検証は後述のActionsドライランで行う。あなたのローカル環境にAPIキーは存在しない前提)
5. 新規の外部依存パッケージを追加しない(標準ライブラリ + PyYAML のまま)
6. fail-closed: 判断に迷う仕様の曖昧さを見つけたら、推測で実装せず「未確定事項」として報告に含める

## 4. テスト方針(ローカルで実施すること)

1. `python3 -c "import ast; ast.parse(open('.nightly/scripts/nightly.py').read())"` で構文検証
2. 新規/変更した純粋関数(起動ログのパース、sessions.json の組み立て、レポート行の追記ロジック)について、`gh` や Jules API を**モック/スタブ化した**簡易ユニットテストを一時スクリプトで実行し、結果を報告に含める(テストファイル自体はコミットしない。実行して消す)
3. `session-watchdog.yml` は `python3 -c "import yaml; yaml.safe_load(open(...))"` で構文検証
4. Jules API・GitHub API への実通信テストは行わない(次回の日中試運転第2弾で、Actions 経由で実地検証する)

## 5. 完了条件(Definition of Done)

- [ ] `jules_create_session()` のボディに `automationMode: "AUTO_CREATE_PR"` が追加されている
- [ ] `nightly.py watch` が新設され、起動ログ→セッション状態取得→sessions.json コミット→Step Summary 出力の流れが実装されている
- [ ] watch は night 不一致・ブランチ不在・ログ不在・API失敗のいずれでもクラッシュせず、fail-closed に正常終了する
- [ ] `.github/workflows/session-watchdog.yml` が既存ワークフローと同じ流儀で作成されている
- [ ] `cmd_report()` が sessions.json 存在時のみ情報を追記し、不在時は従来と完全に同一の出力をする
- [ ] ガードレール1の3ファイル以外に差分がない(`git status` / `git diff --stat` で確認)
- [ ] 構文検証・モックテストが全て通っている

## 6. 報告様式(作業完了時にこの形式で報告すること)

1. 変更サマリー(タスク1〜5それぞれの実施状況)
2. 変更ファイル一覧と各変更の理由(`git diff --stat` を含む)
3. テスト実行結果(実行したコマンドと出力の要旨)
4. 未確定事項・建築家(Fable 5)に確認したい事項(なければ「なし」)
5. **コミット・プッシュはまだ行わない。** 差分を提示し、人間と建築家のレビュー承認を待つこと
