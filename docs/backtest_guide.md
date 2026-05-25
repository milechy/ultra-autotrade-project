# Backtest Guide (Placeholder)

> **Status: 2026-05-25 — synthetic mock backtest を撤去。本物の backtest harness は別 epic として §17 フル公開前に着手予定。**

## 経緯

旧 `scripts/backtest_weekly.py` は `random.gauss()` ベースの synthetic mock で、production 判定パス (`backend/app/automation/workflow.py` / `backend/app/aave/risk_limiter.py` 等) を一切実行していなかった。固定 seed=42 のため毎週同一の `HF Violations 3 / MaxDD 25.1%` を Slack に出し続け、本番リスクシグナルではない phantom WARN を生んでいた。誤解を断つため、6/1 限定公開前に script + CI workflow + test を削除した。

撤去対象:

- `scripts/backtest_weekly.py`
- `scripts/tests/test_backtest_weekly.py`
- `.github/workflows/backtest.yml`

CI 健全性確認は `scripts/verify.sh` および他 workflow で既に担保されており、backtest workflow を単独で残す価値は無いと判断。

## production HF 安全機構(参考、本ドキュメント撤去で失われないこと)

旧 mock 由来の WARN とは独立して、本番側の HF 保護は多層化されている:

| Layer | コード | 効果 |
|---|---|---|
| Rule engine 事前 gate | `backend/app/automation/workflow.py:316-318` | `last_health_factor < 1.6` で `can_trade=False, reason='hf_below_threshold'` を返し LLM 呼び出しを skip |
| HF emergency override | `backend/app/automation/workflow.py:580-584` | `hf < 1.6` で `execution_policy` を `auto_execute` に強制しポジション解消側に倒す |
| Risk limiter | `backend/app/aave/risk_limiter.py` | `HF_STRICT_DEFAULT=1.6`、絶対 floor `HF_HARD_MIN=1.2` は env override 不可 |
| LINE 通知 | `backend/app/notifications/line_notifier.py:176-225` | HF<1.6 で EMERGENCY、<1.8 で WARNING を送信 |

## 次の一手(本物の backtest harness)

別 epic「Tier: A / 本物の backtest harness 構築」(Asana 起票済、§17 フル公開前) で実装予定:

- データソース: Aave V3 Base の historical reserves(The Graph subgraph)
- 実行: `workflow.process_pending_knowledge` を historical HF / APY / 価格に対して回す
- LLM 部分: recorded fixture または deterministic mock LLM
- メトリクス: production code が trip した `hf_below_threshold` 回数、emergency override 発火数、実 MaxDD、Sharpe、proposal 生成数
- 出力: backtest_results.json + Grafana dashboard 用 CSV

それまでは backtest による回顧的検証は実施しない(production を実環境で観察する方が定量的)。
