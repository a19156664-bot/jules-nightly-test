# 技術的知見 (Lessons Learned)

ループエンジニアリングシステムの運用を通じて蓄積された知見。
新しい知見はこのファイルに追記し、git 管理下で維持する。

将来的には：
- プロンプト注入（build_prompt.py のコンテキストに含める）
- ゲート項目（pr_checker の検査項目に変換）
への2段変換を行う。

---

## GitHub / Jules 関連

### 1. Jules のアカウント構成
Jules は `a19156664-bot` で PR 作成、`google-labs-jules[bot]` はコメント担当。

### 2. night_date_now() の計算
`night_date_now()` は JST-12h の日付を返す。`NIGHTLY_FORCE_DATE` / `-f force_date=` で上書き可能。

### 4. statusCheckRollup の制約
`statusCheckRollup` は Actions トークン不可 → `with_checks=False` で運用。

### 5. tasks.yml の prompt 指定
tasks.yml の prompt はファイル経由（`.nightly/prompts/*.md` + prompt_file）。

### 6. タスクID命名規則
タスクIDは毎夜 T1-01 / T2-01 リセット（`T[12]-\d{2}` のみ有効）。

### 7. nightly.py サブコマンド
ローカル実行可能な nightly.py サブコマンドは `validate` のみ。

### 8. branch protection の制約
branch protection は API 直接書き込みも拒否（turn ログ PUT が HTTP 409。R5 参照）。

### 9. Run workflow vs Re-run jobs
「Run workflow」= 最新コードで新規実行 / 「Re-run jobs」= 古いコードで再実行。

### 10. 直列投入パターン
1夜1タスク×2ターンの直列が勝ちパターン。

### 11. Jules の .egg-info
Jules は .egg-info を作ることがある（ゲート検知→自己修正の実績あり）。

### 14. GITHUB_TOKEN と PR イベント
GITHUB_TOKEN でマージされた PR は closed イベントを発火しない → PAT で対策済み（実地検証済み）。

### 24. integration ブランチの削除制限
integration/* ブランチは branch protection で削除不可。Allow deletions を一時有効化して対処。

### 25. tasks.yml の残存事故
tasks.yml の残存事故に注意（差し替え忘れ）。

### 29. T1/T2 の直列投入
T1/T2 は直列投入（start-night が T1、turn-switch が T2）。

---

## Windows / PowerShell 関連

### 3. PowerShell 5.1 と文字コード
Windows PowerShell 5.1 は cp932 → `PYTHONIOENCODING=utf-8` 必須。

### 15. パイプ渡しのハング
PowerShell で `$prompt | claude -p` のパイプ渡しはハングする。ファイル経由を使う。

### 16. ダウンロードファイルのサフィックス
ブラウザのダウンロードで同名ファイルは `_1` サフィックス。ps1 の受け渡しは zip 圧縮が確実（直DLだと開けない場合あり）。

### 17. gh auth login の有効期限
gh auth login はデバイスフロー中にワンタイムコードの有効期限が切れやすい。

### 18. タスクスケジューラの PATH
タスクスケジューラ環境では PATH 不足 → フルパス変数で指定。

### 19. PowerShell の日本語とインデント
PowerShell 5.1 の here-string 日本語化けとメモ帳貼り付けのインデント欠落に注意。ファイル全置換（zip渡し→展開→Copy-Item -Force）が最も安全。

### 20. 複数行 python -c
PowerShell の複数行 `python -c "..."` は ScriptBlock エラーになる場合がある。

### 32. 実行ポリシー制限
スクリプト実行ポリシー制限時は `powershell -ExecutionPolicy Bypass -File "..."` で起動。

### 34. $Python 変数の未定義
PowerShell で `& $Python -m ...` を対話実行する場合、$Python 変数が未定義だと BadExpression。フルパス直書きが安全。

---

## state_manager / commander 関連

### 12. Claude Code の自動承認
Claude Code の自動承認済み: git *, python3 -c *, validate系, git update-index *, git fetch *。

### 13. ALWAYS_PROTECTED
nightly.py の ALWAYS_PROTECTED = [".github/**", ".nightly/**", "AGENTS.md"] はハードコード。司令塔部品は commander/ に置く。

### 21. state_manager.py の exit code
state_manager.py の CLI は exit code 常に 0。stdout を `-like "True*"` / `-like "False*"` でパース。

### 22. 定数の二重管理
~~定数の二重管理~~ 解消済み（07-20, PR #18）。ただし知見30の副作用を生んだ。

### 23. should-stop の出力形式
should-stop の出力形式は `True|理由` / `False`。

### 26. subprocess.run の日本語
subprocess.run で gh CLI の日本語出力は `encoding="utf-8"` を明示。

### 27. cmd_start_night の投入判定
cmd_start_night は turn1 ログの有無で投入判定（07-20 修正）。

### 28. state.yml の日本語
state.yml の日本語は正常 UTF-8。PS5.1 表示化けは実害なし。確認は Python 経由。

---

## 設計・アーキテクチャ関連

### 30. パッケージ形式 import の罠（R1/R7 実例第1号）
パッケージ形式 import（`from commander.config import ...`）は `-m` 実行でのみ解決可能。`$PSScriptRoot\*.py` 直接実行は ModuleNotFoundError。CI（ルート起点の pytest）では通るため発見が遅れる。**「テストが通る」と「実行環境で動く」は別**。

### 31. 司令塔のファイル書き込み能力
司令塔（claude -p）はテキスト応答のみでファイル書き込み能力を持たない。ファイル生成は parse_output.py 側の責務。PR #24 で PROPOSAL_FILE ブロックのパース＆書き出し機能を実装済み。

### 33. メモ帳保存と git diff
メモ帳保存の COMMANDER.md は git diff で差分が出ないことがある（エンコーディング/EOL 差）。変更確認は `Select-String -Pattern` で実体を見る。

### 35. tasks.yml の night 値と night_date_now() の整合（07-21 発見）
tasks.yml の `night` フィールドは night_date_now()（JST-12h の日付）と一致させる必要がある。「7月20日の夜に実行したいタスク」の night は `2026-07-20`。push トリガーのタイミングが12時JST前後で night_date_now() が変わるため、**push は12時JST以降に行うか、night を push 時の night_date_now() に合わせる**のが安全。

### 36. commander.ps1 と start-night の分離（07-21 発見）
commander.ps1 には start-night（夜の切り替え）ロジックがない。夜の起動は GitHub Actions（turn-switch.yml の push トリガー）が担う。commander.ps1 は「既に始まった夜の中での司令塔業務」のみ。turn=complete 時に Row 7 へ進むパスは PR #25 で追加済み。

### 37. integration ブランチから main への反映（07-21 発見）
integration ブランチの成果（Jules の PR マージ先）は自動では main に反映されない。夜の完了後に手動で `git merge origin/integration/nightly-YYYYMMDD` → main push が必要。

---

## 運用チェックリスト

### night 投入時の確認事項
1. tasks.yml の night 値が night_date_now() と一致するか
2. 同名の integration ブランチが既存でないか
3. プロンプトファイルが .nightly/prompts/ に配置されているか
4. push 後に Actions の start-night が成功したか（gh run list で確認）

### 夜間完了後の作業
1. ダッシュボードで信号機・エラーカウント確認
2. PR の精読（初回は全件、定着後は抜き打ち）
3. integration → main のマージ
4. 司令塔の Row 7 実行結果（proposals/ の生成）確認
5. proposals/ の承認 → .nightly/ への反映
