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
## 状態管理 / エンコーディング関連（07-23 追加）

### 55. state.yml を PowerShell の Set-Content で書くと状態が全消失する（07-23 発見・最重要）
PowerShell の `Set-Content -Encoding UTF8` は **BOM 付き UTF-8** で保存する。`StateManager.load()` は
`open(path, encoding="utf-8")` で読むため BOM がパースエラーを起こし、以下の連鎖でサイレントに状態が消える。

```
Set-Content -Encoding UTF8 で state.yml を編集
  → 先頭に BOM (EF BB BF) が混入
  → load() の yaml.safe_load が例外
  → except: return get_default_state()   ← 例外を握りつぶす
  → 次の update()（record_wakeup 等）が save() を実行
  → デフォルト状態がファイルに上書きされる = current_night / turn / last_action が全消失
```

30分ごとのタスクスケジューラが `--record-wakeup` を呼ぶため、**編集した数分後に勝手に消える**。
エラーも警告も出ないため、原因の特定が極めて困難。

**運用ルール: `state.yml` は `StateManager.update()` 経由でのみ編集する。**

```powershell
# 正: 司令塔自身と同じ書き込み経路（yaml.dump / BOM なし）
python -c "from commander.state_manager import StateManager as S; S().update({'current_night':'2026-07-24'})"

# 誤: BOM が混入し、次の wakeup で状態が消える
(Get-Content commander\state.yml -Raw) -replace ... | Set-Content commander\state.yml -Encoding UTF8
```

### 56. load() の `except: return get_default_state()` は fail-silent（07-23 発見）
知見55 の根本原因。`state_manager.py` の `load()` は、パース失敗時に例外を握りつぶしてデフォルト状態を返す。
これは本システムの設計哲学である **fail-closed に反する fail-silent** であり、
「壊れた状態を検知して止まる」のではなく「壊れた事実を隠して正常なふりをする」挙動になっている。

X-1 での修正候補:
- `encoding="utf-8-sig"` にして BOM を許容する
- パース失敗時は例外を投げて停止する（あるいは stop_reason を立てる）
- `save()` の前に「読み込んだ state が空/デフォルトなら書き込まない」ガードを入れる

### 57. state の確認は必ず YAML パーサ経由で行う（07-23 発見。知見28 の強化）
`Select-String -Pattern "turn"` は `last_action.detail` の**本文テキストに含まれる文字列**まで拾う。
07-23 に、実際には `turn: null` だったにもかかわらず、detail 内の「turn=complete かつ翌夜…」という
報告文が引っかかり、`turn: complete` が存在すると誤認して調査が30分迷走した。

```powershell
# 正: パーサが解釈した実際の値を見る
python -c "import yaml; d=yaml.safe_load(open('commander/state.yml',encoding='utf-8')); print(repr(d.get('turn')))"

# 誤: 本文中の文字列を拾って誤認する
Get-Content commander\state.yml | Select-String -Pattern "turn"
```

トップレベルキーの一覧を見たい場合は `print(list(d.keys()))` が確実。

### 58. state.yml の turn フィールドに書き手が存在しない（07-23 発見）
`state.yml` の `turn` は読み手が3箇所（`--check-turn-due` / commander.ps1 の Stage 0 ゲート / ダッシュボード表示）
ある一方、**値を書き込むコードがリポジトリ内に存在しない**（`update({"turn": ...})` が一箇所もない）。
`nightly.py` に頻出する `turn1` / `turn2` は `.nightly/tasks.yml` のタスク区分であり、`state.yml` の `turn` とは別物。

現状は人間の手動更新に暗黙依存している。`--check-turn-due` は `turn == "turn1"` を期待しているが
誰も `turn1` を書かないため、**常に False を返す**（実質デッドコード）。
X-1 では turn のライフサイクル（誰がいつ何を書くか）を明示的に設計する必要がある。

### 59. commander.ps1 の Stage 0 ゲートは turn が空だと静かに空振りする（07-23 発見。知見52 の系列）
commander.ps1 の Stage 0 は次の複合条件で `no-work` として `exit 0` する。

```powershell
if ($openPRs -eq 0 -and $turnDue -like "False*" -and $turn -notlike "complete*")
```

`turn` が `null`（空文字列）だと `complete*` に一致しないため条件が成立し、
**LLM を呼ばずに正常終了する**。ログファイルも作られないため、コンソール表示だけでは
「動いたが仕事がなかった」のか「壊れて止まった」のか区別できない。

空振りの切り分け手順:
1. `commander\logs\commander-*.log` の最新タイムスタンプを見る（無ければ Stage 1 未到達）
2. `--can-call-llm` で予算ゲートを確認（`False|理由` が返る）
3. パーサ経由で `turn` / `stop_reason` / `error_count` を確認（知見57）

---

## 承認フロー関連（07-23 追加）

### 60. approve.ps1 の前に proposal のコミットが必要（07-23 発見）
司令塔が生成した `commander/proposals/<night>/` は untracked のまま残るため、
approve.ps1 の Phase 0（working tree clean 検査）で停止する。
Phase 0 は `*.bak-` / `*.obsolete` は除外するが、proposal ディレクトリは除外しない。

正しい順序:
```
1. commander.ps1 発火 → proposals/<night>/ 生成
2. git add <3ファイルを明示列挙> → commit   ← このステップが必要
3. approve.ps1 -Night <night>
```

approve.ps1 側で proposal コミットまで面倒を見るか、手順として明文化するかは要検討（X-1 候補）。

### 61. approve.ps1 は -ExecutionPolicy Bypass -File で呼ぶ（07-23 確認。知見32 の再確認）
`.\commander\approve.ps1 -Night ...` は実行ポリシー制限で `UnauthorizedAccess` になる。

```powershell
powershell -ExecutionPolicy Bypass -File commander\approve.ps1 -Night 2026-07-24
```

commander.ps1 と同じ呼び方。Phase 4 の y/n プロンプトもこの形式で正常に動作する。

### 62. approve.ps1 v4 初本番投入の結果（07-23）
11夜目（2026-07-24）で初めて本番投入し、Phase 0〜5 が設計どおり完走した。
- Phase 0 の fail-closed が proposal 未コミットを正しく検出（知見60）
- Phase 1 のバックアップは `.nightly\tasks.yml.bak-before-<night>-<timestamp>` 形式
- Phase 4 の night 不一致検出 → `force_date` 付き dispatch の提案が正しく機能
- 人間の作業は「y を1回入力」のみ。R3（人間がボトルネック）の緩和を実運用で確認

---

## 未解決事項の実証（07-23）

### 63. morning-report は integration → main のマージを行わない（07-23 実証。知見37 の確認）
10夜目完了の翌朝、main は前日の `c6fff24` のままで、`integration/nightly-20260723` の成果
（PR #29 / #30）は未反映だった。**morning-report は成果報告のみで実マージはしない**ことが確定。
課題F（integration → main の統合自動化）は未解決のまま。手動マージの手順:

```powershell
git fetch origin
git log --oneline origin/integration/nightly-YYYYMMDD..origin/main   # 分岐確認
git merge --no-ff origin/integration/nightly-YYYYMMDD -m "merge: Nth night into main"
git push origin main
```

main が先行している場合（approve.ps1 のコミット等）は ff-only では失敗するため `--no-ff` を使う。

### 64. turn1 ログの PUT 失敗は継続中（07-23 再観測。R5 / 知見8）
start-night 実行時、`.nightly/logs/<night>-turn1.json` への PUT が branch protection で失敗し、
`turn1 ログの書き込みに失敗しました(続行します)` の warning が出る。
フローは継続するため運用に支障はないが、**観測データが欠損する**。10夜目・11夜目とも同じ warning を確認。
X-1 で branch protection の除外設定、または PUT 先の変更が必要。

### 65. turn-switch の冪等性欠如による T2 無限再投入ループ（07-23 事故・最重要）

11夜目（2026-07-24）で、同一タスク T2-01 が **7回投入され、うち6回が auto-merge された**
（PR #32〜#37）。ダッシュボードは終始「正常運転中（緑）/ Error Count 0」で、
CI も pr_checker も全て通過していた。**検知層が一つも作動しないサイレントな暴走**。

#### ループの構造

```
T2 の PR が integration/nightly-* にマージ
  → dispatch-after-merge が発火（条件: base.ref が 'integration/nightly-' で始まる）
  → turn-switch を workflow_dispatch で起動（force_date を base ref から復元）
  → cmd_turn_switch が turn2 のタスクを投入
  → Jules が PR 作成 → auto-merge → 先頭に戻る
```

`dispatch-after-merge` の発火条件は「integration/nightly-* への PR がマージされたこと」だけで、
**T1 のマージも T2 のマージも区別しない**。つまり T2 のマージが次の T2 投入を呼ぶ自己再帰構造。

#### 真因: cmd_turn_switch に冪等性ガードが無い

修正前のコードは依存関係しか見ていなかった。

```python
merged = merged_task_ids(branch)
for t in m["turn2"]:
    deps = set(t.get("depends_on", []) or [])
    missing = sorted(deps - merged)
    if missing:
        skipped.append(...)      # 依存未充足 → スキップ
    else:
        launch.append(t)         # ← 「既に投入済み/マージ済み」の判定が無い
```

`cmd_start_night` は turn1 ログの有無で投入判定している（知見27）のに、
`cmd_turn_switch` には同等のガードが**実装されていなかった**。設計の非対称性。

#### 10夜目から潜在していた

turn-switch の実行履歴を確認したところ、**10夜目（07-22）も workflow_dispatch が3回**起動していた
（PR は #29 #30 の2つのみ）。3周目に Jules が PR を作らなかったため表面化しなかっただけで、
**ループ自体は10夜目から発生していた**。11夜目は Jules が毎回 PR を作ったため顕在化した。

「一度うまくいった」は「構造的に正しい」を意味しない。10夜目の完全連鎖成功は、
偶然ループが空回りしただけだった。

#### Jules の挙動が事故を可視化した

#33〜#37 のコミットメッセージが実態を語っている。

```
#36  Add trivial comments to generate a diff for already implemented T2-01
#35  Add paths limit validation to validate_proposal
#34  Add comment to validate_proposal.py to create diff
#33  Add comment for path length check
#32  [T2-01] Add paths count limit check to validate_proposal   ← 本来の実装
```

Jules は「既に実装済み」と認識していた。しかし投入され続けたため、
**空の差分では PR が作れないので、無意味なコメントを追加して形だけの PR を作った**。
R1（LLM同士の共謀的盲点）の実例。pr_checker も CI も、コメント追加は無害なので通してしまう。
**「無害だが無意味な変更」は既存の防御層をすり抜ける。**

#### 修正（3758e64）

`cmd_turn_switch` の turn2 ループ先頭に冪等性ガードを追加。

```python
for t in m["turn2"]:
    # 冪等性ガード: 既にマージ済みのタスクは再投入しない。
    if t["id"] in merged:
        skipped.append({"id": t["id"], "status": "skipped",
                        "reason": "既にマージ済み(再投入を抑止)"})
        continue
    deps = set(t.get("depends_on", []) or [])
```

`merged_task_ids(branch)` の戻り値をそのまま利用するため、新規 API 呼び出しは不要。
実証: 修正後に同じ workflow_dispatch を手動実行し、
`{"id": "T2-01", "status": "skipped", "reason": "既にマージ済み(再投入を抑止)"}` を確認。

#### 事故対応の手順（再発時のため）

1. `gh run list` で連鎖の構造を特定（EVENT 列が workflow_dispatch の連続に注目）
2. **輪を物理的に切る**: `gh workflow disable <auto-merge ID>` と `<dispatch-after-merge ID>`
3. Jules 管理画面の In progress で走行中セッションを Pause session
4. 原因確定 → 修正 → テスト → push
5. 修正の実証（無効化したまま手動 dispatch し、スキップされることを確認）
6. `gh workflow enable` で再有効化
7. 残った PR を close

#### X-1（24時間稼働）への含意

- **サイクルを24倍速にする前に、1周で正しく止まることの保証が必要**。暴走も24倍速になる
- ダッシュボードに「同一タスクが N 回以上投入されたら警告」の検知が無い。
  緑のまま暴走できる状態は、層1の観測設計の穴
- `dispatch-after-merge` の発火条件（integration/* への全マージ）は粗すぎる。
  T1 のマージのみを対象にするか、turn 状態を見る設計に変えるべき
- 冪等性は turn-switch だけの問題ではない。**全ての自動起動経路について
  「二度呼ばれても安全か」を点検する必要がある**


## 運用チェックリスト

### night 投入時の確認事項
1. tasks.yml の night 値が night_date_now() と一致するか
2. 同名の integration ブランチが既存でないか
3. プロンプトファイルが .nightly/prompts/ に配置されているか
4. push 後に Actions の start-night が成功したか（gh run list で確認）

### 夜間完了後の作業
1. ダッシュボードで信号機・エラーカウント確認
2. PR の精読（初回は全件、定着後は抜き打ち）
3. integration → main のマージ（手動。知見63）
4. 司令塔の Row 7 実行結果（proposals/ の生成）確認
5. proposal を git commit（ファイル明示列挙。知見60）
6. approve.ps1 -Night <night> で承認（知見61）

### state.yml を触るときの鉄則
1. 編集は StateManager.update() 経由のみ（Set-Content 禁止。知見55）
2. 確認は YAML パーサ経由（Select-String は誤認する。知見57）
3. 触る前にバックアップ（Copy-Item で退避）