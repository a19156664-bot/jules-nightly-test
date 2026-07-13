# SETUP_GUIDE.md — 深夜バッチパイプライン導入手順書

「3時間×2ターン制・完全無人」の夜間バッチを安全に稼働させるためのGitHub設定と運用手順です。**所要時間は約30分。手順の順番どおりに実施してください**(特にブランチ保護より先にタスクを流さないこと)。

## 0. ファイル構成(このテンプレート一式)

```
AGENTS.md                                    # プロジェクト憲法(Julesが常時参照)
SETUP_GUIDE.md                               # 本書
.nightly/
  tasks.yml                                  # 夜の設計図(毎晩これだけ編集してコミット)
  ci.sh                                      # CI実体(プロジェクトに合わせ書き換え)
  scripts/nightly.py                         # オーケストレーター本体
  prompts/                                   # 長いタスク指示の置き場(prompt_file)
  logs/  reports/                            # 夜間ログと朝レポート(自動生成)
.github/workflows/
  turn-switch.yml                            # 夜間開始(push) + 02:30ターン切替(cron)
  auto-merge-to-integration.yml              # PRの無人マージゲート
  morning-report.yml                         # 05:45 朝レポート生成
  ci.yml                                     # 必須チェック(ブートストラップ対応)
```

---

## 1. ファイルの配置(5分)

1. 本テンプレート一式をリポジトリのルートに配置し、`AGENTS.md` の「★書き換える」箇所(プロジェクト概要・規約)を埋める。
2. `.nightly/ci.sh` をプロジェクトのテストコマンドに書き換える。**テスト未導入なら雛形のままでよい**(ブートストラップモードで動作し、初夜にJulesへテスト基盤構築を依頼する)。
3. `main` へコミットする。この時点では `tasks.yml` の `night:` が過去日付のため何も起動しない(誤発火防止のガードが効いている)。

## 2. Jules側の設定(5分)

1. [jules.google](https://jules.google) でGoogleアカウント連携し、対象リポジトリへのGitHubアクセスを許可する。
2. Julesの Settings から **APIキーを発行**する。
3. Jules API でソース名を確認する(形式: `sources/github/<owner>/<repo>`):
   ```bash
   curl 'https://jules.googleapis.com/v1alpha/sources' -H 'X-Goog-Api-Key: YOUR_KEY'
   ```
4. **並列枠の確認**: 10並列運用にはJulesの有償プラン(15並列以上の枠)が必要。無償枠(3並列)の場合は各ターン3件までに設計すること。

## 3. GitHubリポジトリの設定(15分)

### 3-1. Secrets / Variables(Settings → Secrets and variables → Actions)
| 種別 | 名前 | 値 |
|---|---|---|
| Secret | `JULES_API_KEY` | 手順2で発行したAPIキー |
| Variable | `JULES_SOURCE_NAME` | `sources/github/<owner>/<repo>` |
| Variable | `JULES_BOT_LOGINS` | JulesがPRを開くGitHubアカウント名(**手順5の試運転で実際のPR作者名を確認してから設定**。それまでゲートは全PRをブロックする=fail-closed) |

### 3-2. Actionsの権限(Settings → Actions → General)
- Workflow permissions: **Read and write permissions** を選択
- **Allow GitHub Actions to create and approve pull requests** は不要(本パイプラインはActionsでPRを作らない)

### 3-3. Auto-merge の有効化(Settings → General)
- **Allow auto-merge** にチェック(ゲート合格PRの「CI緑になり次第マージ」予約に必須)
- 併せて **Automatically delete head branches** も推奨(夜間ブランチの掃除)

### 3-4. ブランチ保護(Settings → Rules → Rulesets で2本作成)

**ルール①: main の完全保護(深夜事故の最終防壁)**
- 対象: `main`
- Require a pull request before merging(承認1名以上)
- Require status checks to pass: **`ci`** を必須に指定
- Block force pushes / Restrict deletions
- **Do not allow bypassing the above settings(管理者にも適用)** — 深夜の自動処理は理論上mainに触れないが、権限側でも二重に封じる

**ルール②: 統合ブランチの品質ゲート**
- 対象パターン: `integration/nightly-*`
- Require status checks to pass: **`ci`** を必須に指定(auto-mergeはこのチェックが緑になるまで実行されない)
- Block force pushes

### 3-5. ラベルの作成(Issues → Labels)
- `nightly-approved`(ゲート合格) / `nightly-blocked`(ゲート不合格・翌朝レビュー行き)

## 4. 運用ルール(統合ブランチの扱い)

- **統合ブランチは使い捨て。** 夜ごとに `integration/nightly-YYYYMMDD` が自動作成され、翌朝 main へマージするか、問題があれば**ブランチごと削除=完全ロールバック**。
- **mainへのマージは必ず人間が行う**(統合ブランチ→mainのPRを翌朝作成しレビュー・マージ)。ここをAIや自動化に委譲しない。
- `.nightly/logs/` と `.nightly/reports/` は統合ブランチ上に自動生成される。mainに取り込むかは任意(ナレッジログとして残す価値あり)。

## 5. 試運転(初回のみ・必須)

**いきなり夜に流さず、日中に1タスクで疎通確認をしてください。**

1. `tasks.yml` を「turn1に無害な1タスク(docs修正等)、turn2は空」に編集し、`night:` を今日の日付にして main にコミット
2. Actionsで `nightly-turn-switch` が走り、統合ブランチ作成とJulesセッション投入が成功することを確認(失敗したら Step Summary のエラーを確認。Jules APIはアルファ版のため、`nightly.py` の `jules_create_session` のフィールド名を[最新のAPIドキュメント](https://developers.google.com/jules/api)と突き合わせて修正する)
3. Julesの管理画面でセッションが起動し、計画→実装が進むことを確認
4. **JulesのPRが上がったら**: (a) PRのbaseが統合ブランチ宛てになっているか確認(mainに向いていたら、タスクプロンプト内のブランチ指定の効き方を確認して調整)。(b) **PR作者のアカウント名を控え、`JULES_BOT_LOGINS` に設定**
5. ゲートが動き、CI合格後に統合ブランチへ自動マージされることを確認
6. `workflow_dispatch` から `morning-report` を手動実行し、レポートが生成されることを確認
7. 統合ブランチを削除して試運転終了

## 6. 毎晩のルーチン(定常運用)

| 時刻 | 誰が | 何を |
|---|---|---|
| 就寝前(〜23:00) | 人間+Fable 5 | `tasks.yml` を作成(建築家に依頼→内容確認)し main にコミット。**これが夜の唯一の承認行為** |
| 23:00頃〜 | 自動 | 統合ブランチ作成 → T1投入 → CI+ゲート合格分を統合ブランチへ自動マージ |
| 02:30 | 自動 | T1マージ状況を確認し、依存充足のT2のみ投入(未充足はスキップ記録) |
| 05:45 | 自動 | 朝レポート生成(CI不合格/ゲート違反/スクリーニング対象を機械仕分け) |
| 翌朝 | 人間+Fable 5 | 朝レポート確認 → 一括スクリーニング(Fable 5へ1回依頼)→ 保留のみ個別レビュー → **人間が統合ブランチ→mainをマージ** |

## 7. 緊急停止(キルスイッチ)

1. **即時停止**: Actions → 各ワークフローを Disable(3本止めれば以後何も動かない)
2. **夜の成果の破棄**: 統合ブランチを削除(mainは無傷なので、これだけで完全ロールバック)
3. **Jules側の停止**: 進行中セッションをJules管理画面からキャンセル

## 8. 既知の制約と正直な注意点

1. **Jules APIはアルファ版**であり、リクエストスキーマは変更されえます。`nightly.py` のAPI呼び出しは失敗してもタスク単位で記録して他を続行するfail-closed設計ですが、初回導入時と月次で最新ドキュメントとの突き合わせを行ってください。
2. **PRタイトル規約 `[T1-01]` はJulesがプロンプト指示に従うことに依存**します。従わなかったPRは自動マージされず翌朝レビューに回るだけ(安全側)ですが、頻発する場合はプロンプト内の該当指示を強調する調整が必要です。
3. **scheduleトリガーは数十分遅延することがあります。** 02:30ちょうどの切替を保証しません。T1のタスクは2.5時間程度で終わる規模に抑えると安定します。
4. **ブートストラップモード(ci.sh未実体化)の間、CIは実質素通しです。** この期間の自動マージは「スコープ検査+テスト改変検査」のみで守られている状態なので、初夜〜数夜はテスト基盤構築を最優先タスクにし、リスクの低いタスクだけを流してください。
5. **立ち上げ期は各ターン3〜5件から。** 一発合格率が7割を超えてから増枠する(翌朝の検収能力がボトルネックです)。
