# chaos test 実行結果

`scripts/chaos_test_3day_runner.sh` が自動生成する Markdown ファイルの格納先。
ローンチ条件 2 (chaos test 3 日連続失敗ゼロ) のエビデンス。

## ファイル命名規約

```
YYYY-MM-DD_runN.md
```

例: `2026-05-29_run1.md` / `2026-05-30_run2.md` / `2026-05-31_run3.md`

## ファイル構造

`template.md` を参照。各ファイルには以下が記録される:

1. メタ情報 (実行時刻 / DRY_RUN / chaos_rc / 経過秒)
2. PASS 判定 4 軸テーブル
3. docker events (staging-new コンテナの die/start)
4. chaos_test_staging.sh log (tail 50)
5. 最終判定 (PASS / FAIL / DRY_RUN)

## 関連 doc

- `docs/launch/chaos_test_3day_plan.md` — 5/29-31 実行スケジュール
- `docs/launch_decision_criteria_v2.md` §2 — 条件 2 PASS 判定基準
- `scripts/chaos_test_3day_runner.sh` — runner 本体
- `scripts/chaos_test_staging.sh` — kill 実装
