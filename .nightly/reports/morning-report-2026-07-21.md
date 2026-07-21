# 🌅 朝レポート — 2026-07-21 (branch: `integration/nightly-20260721`)

| タスク | 依存 | PR | 状態 | CI | 差分 | ゲート違反 | 推奨仕分け |
|---|---|---|---|---|---|---|---|
| T1-01 | - | [#27](https://github.com/a19156664-bot/jules-nightly-test/pull/27) | 統合済 | no-checks | +249/-0 | - | 統合済(サンプル確認) |
| T1-01 | - | [#26](https://github.com/a19156664-bot/jules-nightly-test/pull/26) | OPEN | no-checks | +45/-156 | 保護パスへの変更: `.nightly/COMMANDER.md`; スコープ逸脱: `.nightly/COMMANDER.md` は T1-01 の許可パス外です; 保護パスへの変更: `.nightly/prompts/2026-07-21-T1-01.md`; スコープ逸脱: `.nightly/prompts/2026-07-21-T1-01.md` は T1-01 の許可パス外です; 保護パスへの変更: `.nightly/prompts/2026-07-21-T2-01.md`; スコープ逸脱: `.nightly/prompts/2026-07-21-T2-01.md` は T1-01 の許可パス外です; 保護パスへの変更: `.nightly/tasks.yml`; スコープ逸脱: `.nightly/tasks.yml` は T1-01 の許可パス外です; スコープ逸脱: `commander/commander.ps1` は T1-01 の許可パス外です | 【要人間確認】 |
| T1-01 | - | [#24](https://github.com/a19156664-bot/jules-nightly-test/pull/24) | 統合済 | no-checks | +159/-0 | - | 統合済(サンプル確認) |
| T2-01 | - | [#28](https://github.com/a19156664-bot/jules-nightly-test/pull/28) | 統合済 | no-checks | +34/-1 | - | 統合済(サンプル確認) |
| T2-01 | - | [#25](https://github.com/a19156664-bot/jules-nightly-test/pull/25) | 統合済 | no-checks | +2/-1 | - | 統合済(サンプル確認) |

## 次のアクション
1. 【要修正】: CIログ要約をJulesに差し戻し(日中の再試行へ)
2. 上表の【一括スクリーニング】対象のみ、Fable 5 の一括レビュープロンプトへ
3. 検収完了後、人間が `integration/nightly-20260721` → `main` のPRを作成しマージ
4. 横断所見をナレッジログへ(フライホイール)