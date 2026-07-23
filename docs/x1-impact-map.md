# Phase X-1 影響範囲マップ — 「夜」概念の解体

作成: 2026-07-23 夜（設計フェーズ前半）
目的: 「夜間限定」設計を24時間サイクルへ移行するにあたり、
      `night` 概念がどこにどう埋め込まれているかを事実ベースで洗い出す。
      **本ドキュメントは現状把握であり、変更方針の決定は含まない。**

---

## 0. 要約

`night` は単一の概念ではなく、**5つの異なる役割**を1つの文字列 `YYYY-MM-DD` が兼任している。
X-1 の本質は「時刻を変える」ことではなく、**この5役を分離すること**。

| # | 役割 | 現在の実体 | 24h化での扱い |
|---|---|---|---|
| A | **サイクル識別子** | `m["night"]` = tasks.yml の night | サイクルID（連番 or タイムスタンプ）へ |
| B | **ブランチ命名** | `integration/nightly-YYYYMMDD` | サイクルIDベースの命名へ |
| C | **実行可否ゲート** | `m["night"] != night_date_now()` → skip | **廃止 or 別条件へ**（最重要） |
| D | **ログ/レポートのファイル名** | `.nightly/logs/{night}-turn1.json` | サイクルIDベースへ |
| E | **人間向けの表示ラベル** | 朝レポートのタイトル等 | 日時表示として残せる |

**C が全ての詰まりの原因。** A/B/D/E は単なる命名で、機械的な置換で済む。
C だけが「時刻と進行を結合させている」箇所であり、
今日発生した「T1 は動くが T2 が繋がらない」問題の直接原因。

---

## 1. `night_date_now()` — 時刻ロジックの中核

**場所**: `.nightly/scripts/nightly.py:90`

```python
def night_date_now() -> str:
    """「夜の日付」= バッチが始まった夕方のJST日付。
    就寝前(~23時)にも深夜02:30にも翌朝05:45にも同じ日付を返すよう、
    現在JST時刻から12時間引いた日付を採用する。
    """
```

JST-12h。つまり **12:00 JST が日付の境界**。

- 07-23 の 11:59 → `2026-07-22`
- 07-23 の 12:00 → `2026-07-23`

この設計意図は明確で正しい: 「夕方に始まり翌朝に終わる一連の作業」を
同じ識別子で扱うため。**夜間運用としては合理的だった。**

24時間稼働では「一連の作業」が1日に何度も発生するため、
この前提そのものが成立しなくなる。

**エスケープハッチ**: 環境変数 `NIGHTLY_FORCE_DATE`（`-f force_date=` から設定）。
現状、日中の運用はほぼ全てこれに依存している = **本番運用が常時テストモードで走っている状態**。

---

## 2. 役割C（実行可否ゲート）の全出現箇所 — 最重要

`m["night"] != night_date_now()` による早期リターンが **4箇所**。
いずれも **exit 0 で静かにスキップ**（知見52）。

| 行 | 関数 | スキップ時の挙動 |
|---|---|---|
| 482 | `cmd_start_night` | `## ⏭ night=... は今夜(...)ではないため開始しません。` |
| 513 | `cmd_turn_switch` | `## ⏭ 今夜のバッチはありません` |
| 648 | `cmd_watch` | 同上 |
| 687 | `cmd_report` | 同上 |

### これが引き起こす問題（07-23 実観測）

1. **force_date なしでは日中に何も動かない**。approve.ps1 が Phase 4 で
   y/n を聞いて force_date を渡しているのは、この壁を越えるため
2. **cron との相性が悪い**。02:30 JST の turn-switch は `night_date_now()` が
   その時点の値になるため、tasks.yml の night が翌日日付だと不一致でスキップ
3. **サイクルを跨げない**。「今日の夕方に投入 → 明日の朝に完了」は表現できるが、
   「今から2時間で1サイクル」を1日に何度も回すことはできない

### 24h化での論点

ゲートを外すと「意図しないタイミングで走る」リスクが生まれる。
現在このゲートは**暴走の最終防波堤としても機能している**
（07-23 の無限ループでは、night 不一致なら止まっていた可能性がある）。
単純撤廃ではなく、**代替の安全弁が必要**。

候補: サイクル状態（pending/running/done）による制御、
明示的な起動フラグ、冪等性ガード（07-23 に turn-switch へ導入済み）の全経路展開。

---

## 3. 役割B（ブランチ命名）

**場所**: `.nightly/scripts/nightly.py:122`

```python
def branch_name(m: dict) -> str:
    return f"integration/nightly-{m['night'].replace('-', '')}"
```

**1行**。ここだけ変えれば命名は変わるが、依存が広い。

### 依存箇所

- `ci.yml`: `push: branches: ["integration/nightly-**"]`
- `dispatch-after-merge.yml`: base ref が `integration/nightly-` で始まるかを判定し、
  **ブランチ名から force_date を復元している**（= 命名がデータになっている）
- `auto-merge-to-integration.yml`: 同様のパターンマッチ想定
- branch protection: `integration/*` パターンで削除・直接pushを禁止
- Jules 作業ブランチ: `integration/nightly-YYYYMMDD-<session_id>` として派生

**重要**: `dispatch-after-merge.yml` がブランチ名から日付を逆算している構造は、
命名規則変更時に必ず壊れる。ここは X-1 の主要な改造点。

---

## 4. 役割D（ログ・レポートのファイル名）

| 行 | パス |
|---|---|
| 489, 500 | `.nightly/logs/{night}-turn1.json` |
| 542 | `.nightly/logs/{night}-turn2.json` |
| 656-657 | 上記2つの読み込み |
| 676 | `.nightly/logs/{night}-sessions.json` |
| 758 | `.nightly/reports/morning-report-{night}.md` |

**注意**: これらの PUT は branch protection により**現在も失敗している**（知見64 / R5）。
つまり **役割Dは既に半分機能していない**。
24h化では書き込み先の見直しが必須（そもそも成功していないので、
移行時の互換性懸念は小さい）。

---

## 5. 憲法（COMMANDER.md）の記述

| 行 | 内容 |
|---|---|
| 29 | Row 7: `turn == "complete"` かつ**翌夜の準備が未了** → 翌夜のタスク案を出力 |
| 53 | 「**翌夜の** tasks.yml を設計する際のルール」 |
| 59 | prompt_file を `.nightly/prompts/YYYY-MM-DD-Tx-01.md` に配置 |
| 94 | 「**翌夜の**タスク設計は commander/proposals/ に出力」 |
| 142 | 「YYYY-MM-DD は**翌夜の** night 日付」 |

### 07-23 に判明した重要事実

Row 7 の発動条件「翌夜の準備が未了」の判定は、
**`current_night + 1` ではなく `.nightly/tasks.yml` の反映状況**を見ている。

実観測（07-23 夕方）:
> `turn=complete` かつ `.nightly/tasks.yml` は翌夜(2026-07-24)分が反映済みで Row 7 も不該当

→ **知見47 は訂正が必要**。「Row 7 = current_night + 1」は誤り。

この曖昧さ自体が R8（自然言語ドメイン層の解釈ブレ）の実例。
24h化では「次サイクル」の定義を憲法上で厳密化する必要がある。

---

## 6. cron スケジュール（全て夜間前提）

| ワークフロー | cron (UTC) | JST | 役割 |
|---|---|---|---|
| `turn-switch.yml` | `30 17 * * *` | **02:30** | T1マージ確認 → T2投入 |
| `session-watchdog.yml` | `0,30 15-20 * * *` | **00:00〜05:30** の30分毎 | セッション監視 |
| `morning-report.yml` | `45 20 * * *` | **05:45** | 朝レポート生成 |

**3つとも深夜〜早朝に固定**。24h化では全て再設計対象。

`turn-switch.yml` はさらに `push: paths: [".nightly/tasks.yml"]` トリガーを持ち、
これが実質的な「サイクル開始」の合図になっている。

---

## 7. その他の依存

| ファイル | 依存内容 |
|---|---|
| `commander/approve.ps1` | 33箇所。`-Night YYYY-MM-DD` 引数、`night_date_now()` との比較、force_date 判定 |
| `commander/validate_proposal.py` | 11箇所。night の形式検査、ディレクトリ名との整合検査（10夜目 #29 で追加） |
| `commander/config.py` | 3箇所 |
| `webui/app.py`, `models.py` | 12箇所。ダッシュボードの Target Night 表示 |
| `commander/state.yml` | `current_night` フィールド |
| `tests/` | 26箇所以上。night 前提のテストが多数 |
| `AGENTS.md` | 3箇所 |

---

## 8. 変更の連鎖（依存グラフ）

```
night_date_now() の廃止/変更
  ├→ 役割C ゲート4箇所 …… 代替の安全弁が必要（最重要論点）
  ├→ approve.ps1 の Phase 4 …… force_date 判定が不要になる
  └→ NIGHTLY_FORCE_DATE …… エスケープハッチ自体が不要になる

branch_name() の変更
  ├→ ci.yml の push トリガーパターン
  ├→ dispatch-after-merge.yml の force_date 復元ロジック ★必ず壊れる
  ├→ auto-merge-to-integration.yml
  ├→ branch protection の設定パターン
  └→ 既存 integration/nightly-* 8本の扱い（移行時の互換性）

tasks.yml の night フィールドの意味変更
  ├→ validate_proposal.py の検査（night形式、ディレクトリ名整合）
  ├→ 憲法 Row 7 / タスク設計基準
  ├→ commander/proposals/<night>/ のディレクトリ命名
  ├→ prompt_file のパス命名規則
  └→ state.yml の current_night

cron の再設計
  ├→ turn-switch (02:30)
  ├→ session-watchdog (00:00-05:30)
  └→ morning-report (05:45) …… 「朝」レポートの概念自体を再定義
```

---

## 9. 未確定事項（明日の判断対象）

1. **役割Cのゲートを撤廃した場合の安全弁は何か**
   - 現在このゲートは暴走の防波堤も兼ねている
   - 冪等性ガード（07-23 導入）を全経路に展開すれば代替可能か?

2. **サイクル識別子の形式**
   - 連番（`cycle-001`）/ タイムスタンプ（`20260724-1430`）/ 日付+連番（`20260724-01`）
   - `dispatch-after-merge` がブランチ名から情報を復元している構造をどうするか

3. **1サイクルの構成**
   - 現行: T1 → T2 の2ターン直列
   - 07-22 の構想: 1サイクル1タスク × 24回/日
   - どちらにするかで turn-switch の存在意義が変わる

4. **移行方式**
   - 一括切替 / 並行稼働 / 段階移行
   - 既存の integration ブランチ8本と過去ログの扱い

5. **憲法 Row 7 の「次サイクル」の定義**
   - 現状「翌夜の準備が未了」は tasks.yml の反映状況で判定されている
   - 24h化では何をもって「次サイクルの準備が未了」とするか

6. **morning-report の位置づけ**
   - 「朝」の概念がなくなる。サイクル毎レポートにするか、1日1回のサマリーとして残すか

---

## 10. 所感（設計判断ではなく観察）

- **`night` の5役兼任が問題の本質**。時刻ロジックだけ直しても、
  命名・ゲート・ログ名が絡み合ったままでは同じ詰まりが再発する
- **役割C以外は機械的な置換で済む**。難しいのはCだけ
- **役割Dは既に壊れている**（PUT失敗）ので、移行の障害にはならない
- **`dispatch-after-merge` のブランチ名からの日付復元**が、
  命名とデータを結合させている最も危険な箇所
- 07-23 の無限ループで導入した**冪等性ガードは、24h化の前提条件**。
  ゲートCを外すなら、全ての自動起動経路に同等のガードが要る
