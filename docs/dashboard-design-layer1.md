# ダッシュボード設計書 — 層1（運転状況）

- 作成日: 2026-07-19
- 対象フェーズ: P5（UI統合）の仕様。実装は P3/P4 安定稼働後
- 目的: 非エンジニアを含む利用者と司令塔LLMが**同一のデータ**を見て運転状況を共有する

---

## 設計原則（人間とLLMの両方にやさしい構造）

### 1. Single Source of Truth
画面は独自の状態を一切持たない。表示内容はすべて以下の写像とする:
- `commander/state.yml`（司令塔の状態・予算）
- gh API（PR・Issue の実データ）
- `.nightly/tasks.yml`（今夜のタスク定義）

人間が見る数字と司令塔が判断に使う数字が構造的にズレない。

### 2. 対称API
画面の各セクションに対応する機械可読エンドポイントを必ず用意する。
司令塔自身がダッシュボードの「読者」になれることを保証する（P4 での自己参照に接続）。

| セクション | API | データ源 |
|---|---|---|
| 信号機・状態 | `GET /api/signal` | state.yml から3値を導出 |
| 状態全体 | `GET /api/state` | state.yml をそのまま JSON 化 |
| 予算メーター | `GET /api/budget` | state.yml の budget ブロック |
| 今夜のタスク | `GET /api/tasks` | .nightly/tasks.yml |
| 直近のPR | `GET /api/prs` | gh API（キャッシュ可） |

### 3. 用語の一対一対応（辞書）
画面ラベルと state.yml キーを厳密対応させる。人間とLLMが同じ語彙で会話するための辞書。

| 画面ラベル（日本語） | データキー |
|---|---|
| 今夜の対象 | `current_night` |
| ターン | `turn`（turn1 / turn2 / complete） |
| 承認待ち | `pending_reviews` |
| 保留タスク | `pending_tasks` |
| LLM呼び出し(日) | `budget.llm_calls_today` / `budget.max_llm_calls_per_day` |
| 5時間窓 | `budget.llm_calls_window` の件数 / `budget.max_llm_calls_per_window` |
| 停止理由 | `stop_reason` |
| エラー回数 | `error_count` |

### 4. 状態は3値の信号機に集約
非エンジニアが最初に見る情報を1ビットまで圧縮する。

| 信号 | 条件（優先順） | 表示 |
|---|---|---|
| 🔴 停止中 | `stop_reason != null` または `error_count >= 5` | stop_reason を表示 |
| 🟡 承認待ち | `pending_reviews` 非空 または `pending_tasks` 非空 | 件数と一覧へのリンク |
| 🟢 正常運転 | 上記いずれにも非該当 | turn / loop_status を補助表示 |

この3値は `GET /api/signal` でも同一ロジックで返す（画面とAPIで判定コードを共有する）。

---

## 画面構成（層1）

```
┌─────────────────────────────────────────────┐
│ ● 正常運転中   state: idle / turn: complete   最終更新 HH:MM │
├──────────┬──────────┬──────────┬──────────┤
│ 今夜の対象  │ LLM(日)   │ 5時間窓   │ 承認待ち   │  ← メトリクスカード×4
│ 2026-07-19│ 1/24 ▓░░░ │ 1/8 ▓░░░ │ 0 件      │
├─────────────────────────────────────────────┤
│ 🌙 今夜のタスク                                │
│  [T1-01] pr_checker.py …        21:00 開始予定 │
│  [T2-01] build_prompt.py …      T1 マージ後    │
├─────────────────────────────────────────────┤
│ ⎇ 直近のPR                                    │
│  #14 ROADMAP.md                       merged  │
│  #13 commander/config.py              merged  │
├─────────────────────────────────────────────┤
│ </> 機械可読ビュー — 司令塔と同一のデータソース      │
│  GET /api/state | /api/prs | /api/budget      │
└─────────────────────────────────────────────┘
```

- 更新方式: JS で30秒ごとに `/api/state` `/api/prs` を fetch（ポーリングで十分）
- テンプレート: 1枚（Flask render_template）
- 認証: ローカル運用のため当面なし（外部公開時に再設計）

---

## 3層構造における位置づけ

| 層 | 役割 | 利用頻度 | 状態 |
|---|---|---|---|
| 層1 ダッシュボード | 見るだけ（運転状況の共有） | 毎日 | **本書が仕様** |
| 層2 承認キュー | 判断する（承認/却下/修正指示） | 週数回 | 未設計 |
| 層3 憲法エディタ | 設計する（判断表の編集） | 月数回 | 未設計 |

層2・層3の設計時の不変条件:
- 司令塔の安全弁（矛盾検知→停止→人間エスカレーション）を UI が壊さないこと
- 「停止条件の自己緩和禁止」に関わる憲法条項は UI 上でロック表示し、
  変更には確認ダイアログ + 変更履歴を必須とすること

---

## 実装タスク分割案（Jules 夜間タスク粒度）

| タスク | 内容 | paths |
|---|---|---|
| T-A | `GET /api/state` `GET /api/budget` `GET /api/signal` を Flask に追加 + tests | webui/ tests/ |
| T-B | `GET /api/tasks` `GET /api/prs` を追加（gh API はサーバ側で叩く）+ tests | webui/ tests/ |
| T-C | ダッシュボード HTML テンプレート + 30秒ポーリング JS | webui/ |

注意: paths に `.nightly/` を含めないこと（ALWAYS_PROTECTED / 知見13）。
state.yml の読み取りは commander/state_manager.py の関数を再利用する
（webui から直接 YAML を再パースする実装を避け、判定ロジックの二重化を防ぐ）。

---

## 既知の依存・前提

- webui は GET /health, GET /tasks, PUT /tasks 実装済み（P0〜P2 で構築）
- webui/models.py の Task に prompt_file フィールドがない不整合は T-A/B 実装時に同時解消してよい
- 予算判定ロジックは state_manager.py に集約されている。API 側で再実装しない
