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

### 8. branch protection の制約（07-23 に影響範囲を確定）
`integration/*` には `required_status_checks: ["ci"]` が設定されており、
Contents API による直接書き込みは **HTTP 409 で恒久的に拒否される**
（`Could not create file: Required status check "ci" is expected.`）。
API 経由の直接コミットは CI を走らせられないため、原理的に成立しない。

これは「ログが欠ける」だけの問題ではない。**ログを根拠にしていた防御層が
すべて機能停止する**（知見67 の因果連鎖）。対処は知見66。

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

### 27. cmd_start_night の投入判定（07-23 に全面改修）
~~turn1 ログの有無で投入判定（07-20 修正）~~ → **この実装は廃止**。

07-23 以降は **タスク単位・二重根拠**で判定する。

```python
already = merged_task_ids(branch) | launched_task_ids(m["night"])
for t in m["turn1"]:
    if t["id"] in already:
        skipped.append(...)   # 再投入を抑止
    else:
        launch.append(t)
```

- **PR状態（マージ済み）** が第一の根拠。ログが欠けても機能する
- **観測ログ（投入済み）** が第二の根拠。PR がまだ無い投入直後を埋める
- **ブランチの存在有無に依存しない**（旧実装の致命的欠陥。知見69）
- ログ書き込み失敗は `return 1` で異常終了（fail-closed。知見66）

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

### 64. turn ログの PUT 失敗（07-23 に解決。R5 / 知見8）

**状態: 解決済み**（知見66 で `ops/nightly-logs` に分離）。

#### この知見が7夜間ミスリードした経緯（重要）

当初この知見には「**フローは継続するため運用に支障はない**」と書かれていた。
この評価が誤りだった。実際には次の連鎖が起きていた（知見67）。

- T1 冪等性ガードが恒久的に無効化されていた（ログの存在を根拠にしていたため）
- `cmd_watch` が常に即 return し、検知層への入力が途絶していた（R12）

**原因（知見8）も対処方針も、この時点で既に正しく記録されていた。**
にもかかわらず7夜放置されたのは、原因が不明だったからではなく
「支障はない」と評価されていたためである。

**教訓: fail-silent な障害に「支障はない」と書いてはならない。**
何が壊れているかを確認するまで、影響範囲は不明として扱う。
この失敗の構造的分析と再発防止策は知見74。

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


### 66. 観測ログの保管先を ops/nightly-logs に分離（07-23 修正。R5 の解決）

#### 原因

`gh_put_file` は Contents API で `integration/nightly-*` に直接コミットするが、
同ブランチには `required_status_checks: ["ci"]` の保護がある（知見8）。
API 経由の直接コミットは CI を走らせられないため、**必ず 409 で拒否される**。
間欠障害ではなく構造的な恒久障害。

さらに `nightly.py` の `cmd_report` には既に回避策のコメントが書かれていた。

```python
# 統合ブランチには branch protection(ci必須)があり PUT が 409 で拒否されるため、
# レポートは main に直接書き込む(統合ブランチ側の変更は生成しない)。
gh_put_file("main", f".nightly/reports/morning-report-{m['night']}.md", ...)
```

**この回避策が cmd_report の1箇所にしか適用されていなかった**ことが、
「レポートは書けるがログは書けない」という状態を生んでいた。

#### 対処

保護のかからないデータ専用 orphan ブランチ `ops/nightly-logs` を作成し、全ログを集約。

- ログパスは `logs/<cycle>/<name>.json`（例: `logs/2026-07-24/turn2.json`）
- `ci.yml` は `integration/nightly-**` にのみ反応するため CI は起動しない
- `dispatch-after-merge` は PR closed が起点のためログ push では発火しない
- **branch protection を一切変更していない**（防御層を弱めない）

#### 検討したが採らなかった案

| 案 | 却下理由 |
|---|---|
| 必須チェックを外す | auto-merge が CI 未通過の PR をマージ可能になる。防御層の中核 |
| PAT で保護を迂回（`enforce_admins: false` のため技術的には可能） | 迂回経路を常設することになり fail-closed に反する |
| main に集約（cmd_report と同じ方式） | 実現可能だが main の履歴がログで埋まる。X-1 でサイクル数が増えると悪化 |

#### 実証

修正後に `turn-switch` を手動 dispatch し、以下を確認。

- `書き込みに失敗` の warning が出ない / `HTTP 409` が出ない
- `ops/nightly-logs` に `logs/2026-07-24/turn2.json` が実際に生成された

**07-16 以来はじめて観測ログが書き込まれた。**

#### X-1 への含意

ログパスからブランチ名への依存が消えたため、**役割D（ログ）と役割B（ブランチ命名）の
分離が完了している**。サイクル識別子の形式が変わってもディレクトリ名が変わるだけで、
コード構造は影響を受けない。


### 67. R5・R12・T1ガード停止は単一の因果連鎖だった（07-23 判明）

3つの独立したリスクとして管理していたものが、実際には1本の連鎖だった。

```
integration/* に ci 必須の branch protection（知見8）
  → gh_put_file が常に HTTP 409（R5 / 知見64）
  → turn1.json / turn2.json / sessions.json が永久に書けない
  ├→ cmd_start_night の T1 冪等性ガードが永久に無効（知見27・69）
  │    → ブランチ削除時に同一タスクが再投入されうる
  └→ cmd_watch が「起動ログがまだありません」で常に即 return
       → sessions.json も書けない → 検知層に入力ゼロ
          → ダッシュボードは終始緑（R12）
```

**R12「サイレント暴走・検知層が作動しない」の原因は、検知ロジックの不備ではなく
検知層に入力が届いていなかったこと**だった。

#### 教訓

- 観測データの欠損は「見えないだけ」ではない。**それを根拠にする判断がすべて狂う**
- リスク登録簿は独立項目として並べると因果関係が見えなくなる。
  R5 と R12 は別項目として管理されていたため、同一の根であることに気づけなかった


### 68. nightly.py にはテストが1件も存在しなかった（07-23 判明）

`tests/` には8本のテストファイルがあり67件が緑だったが、対象は
`app` / `build_prompt` / `config` / `create_alert_issue` / `dashboard_api` /
`parse_output` / `state_manager` / `validate_proposal` のみ。

**司令塔の中核である `nightly.py` だけがテストの空白地帯だった。**
これが R5（7夜）と turn-switch 無限ループ（2夜）が長期間見逃された一因である。
ガードが死んでいても、緑のテストは何も教えてくれなかった。

#### 原因

`.nightly/scripts/nightly.py` は**先頭がドットのディレクトリ**にあり、
`import .nightly.scripts.nightly` が構文上不可能（ドット始まりは識別子として不正）。
既存テストの流儀（`from commander.state_manager import ...`）を適用できなかった。

#### 対処

`tests/conftest.py` に `importlib.util.spec_from_file_location` でファイルパスから
直接ロードするフィクスチャを追加。本番の配置（ワークフロー6本が
`.nightly/scripts/nightly.py` を参照）を変更せずにテストできる。

フィクスチャは GitHub/Jules API を呼ぶ全関数を「呼ばれたら AssertionError」に
差し替える。テストが誤って本物の API を叩く事故を構造的に防ぐ。

**「テストが書きにくい配置」は、テストが書かれない理由になる。**
X-1 で構造を触る際、テスト容易性を設計要件に含めること。


### 69. ブランチの存在自体が冪等性ガードの一部になっていた（07-23 修正）

旧 `cmd_start_night` の構造:

```python
branch_existed = gh_branch_exists(branch)
if branch_existed:
    turn1_log = gh_get_json(...)        # ← ここでしかガードしない
    if turn1_log is not None:
        return 0
else:
    gh_create_branch_from_main(branch)  # ← ガードを通らず投入へ直行
```

**ブランチを削除すると、その夜の T1 冪等性ガードがリセットされる。**
ブランチが暗黙の状態（state）を持っていた。

#### 実務上の危険

保留中の「ブランチ定期整理の仕組み」は無害な掃除ではない。
現行は役割C（night 一致ゲート）が同時に効くため当夜以外は暴発しないが、
**X-1 でゲートCを外すと、整理スクリプトが再投入の引き金になる**。

#### 修正

ブランチ判定とガードを分離し、**ブランチの存在有無と無関係にガードを通る**ようにした。
判定根拠を PR状態と観測ログの二重にし、タスク単位に変更（T2 と対称。知見27）。
あわせてログ書き込み失敗を warning から **`::error::` + `return 1`** に格上げした。
投入したのにログが残らない状態は、次回の再投入を検知できなくなるため異常として扱う。


### 70. morning-report は時刻ズレで大半の夜に走っていなかった（07-23 判明）

main の `.nightly/reports/` には **07-15 / 07-19 / 07-21 の3本しかない**。
R5 とは無関係（main は非保護でレポートの PUT 自体は成功する）。

原因は `cmd_report` 冒頭のゲートC。

- morning-report の cron は **05:45 JST**
- `night_date_now()` は JST−12h なので、**05:45 に呼ぶと前日を返す**
- manifest night が当日なら不一致 → 即 return

同じ理由で **session-watchdog（00:00〜05:30 JST の30分毎）も毎回即 return していた**。
07-22 20:35 UTC の run で `## ⏭ 今夜のバッチはありません (manifest night=2026-07-23)`
を実データで確認。

#### 構造的な問題

`night_date_now()` は「夜に実行される」前提の日付規約だが、
approve.ps1 の導入により**実行が昼に移った**。両者が噛み合っていない。

**ゲートCは投入系では防波堤として働き、観測系では消音器として働いている。**
同じ条件式が正反対の役割を担っている。X-1 ではこの2つを分離する。


### 71. PowerShell 5.1 の Get-Content は UTF-8 を CP932 として読み、行数がずれる（07-23 発見。知見3/57 の系列）

`Get-Content` で日本語を含む UTF-8（BOM なし）ファイルを読むと、
文字化けするだけでなく**行が結合・分割されて行数が変わる**。

実例: `nightly.py` の同一のゲートを、`Select-String` は482行、
`Get-Content` は484行と報告した。オフセットが一定でないため単純なズレ補正もできない。

**行番号を根拠にする作業（差分の指示、レビュー、置換）は必ず Python 経由で行う。**

```powershell
& $Python -c "import io; L=io.open('path',encoding='utf-8').read().splitlines(); ..."
```

同じ理由で、**日本語を含む .ps1 を BOM なし UTF-8 で保存すると自壊する**
（PowerShell 5.1 は .ps1 を BOM がなければ CP932 として読む）。
スクリプトを渡す場合は ASCII のみで書くか、Python スクリプトにする方が安全。


### 72. テストは「壊したら落ちること」まで確認する（07-23 導入）

`nightly.py` に追加した冪等性ガードのテスト20件について、
**意図的にガードを壊して落ちることを確認した**（ミューテーションテスト）。

| 壊した内容 | 結果 |
|---|---|
| ブランチ存在時のみガードを効かせる（旧実装の欠陥） | 1 failed |
| ログ失敗を warning に戻す（旧実装の欠陥） | 1 failed |
| 依存判定に `already` を使う | 1 failed |
| ログパスを旧形式に戻す | 2 failed |

**テストが通ることは、テストが正しいことを意味しない。**
特にモックを多用するテストは、何も検証していなくても緑になりうる。
今後 nightly.py にテストを足す際は、同じ手順で実効性を確認すること。


### 73. 本番の turn-switch は常に FORCE_DATE 付きで起動される（07-23 判明）

`dispatch-after-merge.yml` はブランチ名からサイクル識別子を逆算し、
それを `force_date` として turn-switch に渡している。

```bash
digits="${BASE_REF#integration/nightly-}"   # integration/nightly-20260718 → 20260718
force_date="${digits:0:4}-${digits:4:2}-${digits:6:2}"
gh workflow run turn-switch.yml -f force_date="${force_date}"
```

このため `cmd_turn_switch` のゲートCは `force_date == m["night"]` の
**自明な比較**になり、実質的に何も検査していない。

- **役割B（ブランチ命名）と役割C（実行可否）がここで直結している**。
  命名がデータになっているため、ブランチ名を変えると必ず壊れる
- `NIGHTLY_FORCE_DATE` は「テスト用エスケープハッチ」とドキュメントされているが、
  **本番運用が常時これに依存している**
- 「ゲートCが暴走の最終防波堤」という理解は、turn-switch に関しては成り立っていなかった


## 知見運用そのものの知見（07-23 追加）

### 74. 知見が増えるほど知見同士が結びつかなくなる（07-23 の最大の教訓）

#### 何が起きたか

R5（turn ログの PUT 失敗）は7夜にわたり放置された。
07-23 のセッションで数時間かけて「調査・発見」したが、
**原因も対処方針も、既に lessons.md に正しく記録されていた**。

| 知見 | 章 | 内容 |
|---|---|---|
| 8 | GitHub / Jules 関連 | branch protection は API 直接書き込みを拒否（**原因**） |
| 27 | state_manager / commander 関連 | cmd_start_night は turn1 ログの有無で投入判定（**影響を受ける仕組み**） |
| 64 | 未解決事項の実証 | PUT が失敗し観測データが欠損（**症状**） |

**3つを並べれば「ガードが死んでいる」と導けたが、章が違うため並ばなかった。**

#### なぜ気づけなかったのか

**要因1: 原因・仕組み・症状が別々の章に分散していた**
知見は「どこで発見したか」で分類されており、「何に影響するか」では分類されていない。

**要因2: 知見64 に「運用に支障はない」という誤った評価が添えられていた**
この一文が7夜間の判断を固定した。実際には防御層2つが停止していた。
**fail-silent な障害の影響範囲を、確認せずに「支障なし」と書いてはならない。**

**要因3: 調査の出発点が引き継ぎサマリーだった**
サマリーは要約であり、既知の知見への参照が落ちている。
建築家は lessons.md を読まずに調査を始め、既知の事実を再発見した。

#### 再発防止策

**(1) リスク → 知見の逆引きを可能にする**

R5 に紐づく知見は 8・27・64・66・67 の5件あるが、これを一覧できる場所がない。
リスク登録簿に関連知見番号を書き、リスク側から知見を引けるようにする。

**(2) 「未解決」の知見には影響範囲の確認結果を必ず書く**

「支障はない」と書く場合は**何を確認してそう言えるのか**を併記する。
確認していないなら「影響範囲未確認」と書く。
これは fail-closed の原則をドキュメントに適用したもの。

**(3) セッション開始時に lessons.md を読む**

引き継ぎサマリーだけを出発点にしない。
特に既知の障害（R番号がついているもの）を扱う場合は該当知見を先に検索する。
`docs/lessons.md` は全文読んでも負担は小さい。

**(4) 検知層に「防御層が生きているか」の監視を入れる**

今回の本質は「防御層が死んでいることを誰も検知していなかった」ことにある。
ダッシュボードは「タスクが正常か」は見ているが、
**「ガードや検知層それ自体が機能しているか」は見ていない**。

X-1 で追加すべき監視項目:

- 直近サイクルで観測ログが書き込まれているか（書けていなければ赤）
- 同一タスクが N 回以上投入されていないか（知見65 の再発検知）
- session-watchdog が実際にセッションを記録できているか（即 return が続いていないか）

**「異常が起きたら赤」だけでなく「正常を確認できなければ赤」の設計にする。**
検知層が沈黙したとき緑のままになる構造を排除する。

#### 一般化

これは LLM ループエンジニアリング固有の問題ではなく、
**知識ベースを持つシステム全般の問題**である。

知見が10件なら人間が全部覚えていられる。65件を超えると
「関連する3件を思い出す」ことが構造的に不可能になる。
知見の**量**が増える局面では、知見の**索引と相互参照**に同等の投資が必要。

X-1（24時間稼働）では知見の生成速度も上がる。この問題は放置すると悪化する。


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

### 既知の障害（R番号）を扱うときの手順（知見74）
1. **先に lessons.md を検索する**。原因が既に記録されている可能性がある
2. 「支障はない」と書かれた知見は疑う。影響範囲が確認されているかを見る
3. 症状・原因・影響を受ける仕組みは別々の章にあることが多い。
   1つ見つけても打ち切らず、関連する知見を探す
4. 修正したら、その知見の**状態（解決済み/未解決）を更新する**

### 中核ファイル（nightly.py）を変更するときの手順（知見68/71/72）
1. 行番号を根拠にする作業は Python 経由で行う（Get-Content は行数がずれる。知見71）
2. 変更後は `pytest tests/ -q` で全件緑を確認する
3. **ガードや防御層を変更した場合は、意図的に壊して落ちることを確認する**（知見72）
4. テストの緑は「壊していない」の確認であり「直った」の証明ではない。
   実運用での動作実証を別途行う