# Backtest Guide & Log Aggregation Reference

## Table of Contents

1. [Running the Backtest Locally](#1-running-the-backtest-locally)
2. [Interpreting Results](#2-interpreting-results)
3. [Pass / Fail Thresholds](#3-pass--fail-thresholds)
4. [Weekly CI Pipeline](#4-weekly-ci-pipeline)
5. [Loki / Promtail Log Aggregation](#5-loki--promtail-log-aggregation)

---

## 1. Running the Backtest Locally

### Prerequisites

```bash
pip install requests
```

### Run

```bash
# From the repo root
python scripts/backtest_weekly.py
```

The script generates 90 days of simulated trading data (no real API calls), computes key metrics, writes `backtest_results.json` in the current directory, and sends a Slack report if `SLACK_WEBHOOK_URL` is set.

### Run without Slack (dry-run)

If `SLACK_WEBHOOK_URL` is not set, the metrics are printed to stdout and the script exits with code 1 (Slack delivery failure). To suppress the error and review metrics only, redirect stderr:

```bash
python scripts/backtest_weekly.py 2>/dev/null; echo "exit $?"
```

Or set a dummy value:

```bash
SLACK_WEBHOOK_URL=http://localhost/noop python scripts/backtest_weekly.py || true
```

### Output files

| File | Description |
|------|-------------|
| `backtest_results.json` | Full metrics in JSON, uploaded as a GitHub Actions artifact |

---

## 2. Interpreting Results

### Win Rate

Fraction of trades where PnL >= 0.

```
Win Rate = winning trades / total trades
```

A win rate of 50% is break-even before fees. Targets above 55% are realistic for a momentum strategy with tight stops.

### Sharpe Ratio

Risk-adjusted return, annualised.

```
Sharpe = (mean_return - risk_free_rate) / std_return * sqrt(252)
```

Where `risk_free_rate = 0.02 / 252` (2% annualised).

| Range | Interpretation |
|-------|----------------|
| < 0   | Strategy loses money on a risk-adjusted basis |
| 0–1   | Mediocre — acceptable in crypto bull markets only |
| 1–2   | Good |
| > 2   | Excellent |

### Max Drawdown

Largest peak-to-trough decline in portfolio value over the simulation window.

```
Max Drawdown = (peak_value - trough_value) / peak_value
```

Expressed as a percentage (e.g. 15% = 0.15). High drawdown signals the strategy cannot survive a sustained losing streak.

### HF Violations

Count of calendar days where the simulated Aave Health Factor dropped below the hard safety threshold of **1.6**.

Per the security rules (`docs/13_security_design.md`), a HF below 1.6 triggers an automatic HARD_STOP. Any violations in the simulation indicate the strategy may be over-leveraged under adverse market conditions.

---

## 3. Pass / Fail Thresholds

| Metric | PASS | WARN | FAIL |
|--------|------|------|------|
| Sharpe Ratio | > 1.0 | 0.5 – 1.0 | < 0.5 |
| Max Drawdown | < 20% | 20% – 30% | > 30% |
| HF Violations | 0 days | 1–3 days | > 3 days |

Status is **PASS** only when all three PASS conditions are met simultaneously. A single FAIL condition marks the entire report as FAIL regardless of other metrics.

---

## 4. Weekly CI Pipeline

The backtest runs automatically every Monday at 00:00 UTC via `.github/workflows/backtest.yml`.

### Trigger

```yaml
on:
  schedule:
    - cron: '0 0 * * 1'
  workflow_dispatch:   # manual trigger via GitHub UI
```

### Steps

1. **Checkout** — pinned SHA (`actions/checkout@11bd71901...`)
2. **Setup Python 3.11** — pinned SHA (`actions/setup-python@a26af69...`)
3. **Install requests** — only external dependency
4. **Run backtest** — `python scripts/backtest_weekly.py`
   - Slack report is sent using `SLACK_WEBHOOK_URL` secret
5. **Upload artifact** — `backtest_results.json` is uploaded as `backtest-results`

### Adding the Slack secret

In the repository settings: **Settings → Secrets and variables → Actions → New repository secret**

- Name: `SLACK_WEBHOOK_URL`
- Value: your Slack incoming webhook URL

### Viewing results

1. Open the Actions tab in GitHub
2. Select the `Weekly Backtest` workflow
3. Click the run → download the `backtest-results` artifact

---

## 5. Loki / Promtail Log Aggregation

The staging stack (`docker-compose.staging.yml`) ships two additional services for centralised log collection.

### Architecture

```
[postgres / backend / frontend containers]
        |  (Loki Docker logging driver)
        v
[Loki :3100]  ←─  [Promtail]  scrapes /var/lib/docker/containers
        |
        v
[Grafana (optional, not included in compose)]
```

### Host-side prerequisite

The Loki Docker logging driver must be installed **once** on the Hetzner VPS before starting the stack:

```bash
docker plugin install grafana/loki-docker-driver:latest \
  --alias loki \
  --grant-all-permissions

# Verify
docker plugin ls
```

### Starting the stack

```bash
docker compose -f docker-compose.staging.yml up -d
```

Loki starts first (no dependencies), then Promtail waits for Loki before scraping.

### Querying logs (LogQL)

Connect to Loki directly:

```bash
# All backend logs in the last hour
curl -G http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={service="backend"}' \
  --data-urlencode 'start=-1h'
```

Common LogQL queries for Grafana dashboards:

```logql
# All error-level logs across services
{env="staging"} |= "ERROR"

# Backend request logs
{service="backend"} | json | line_format "{{.log}}"

# HF warnings
{service="backend"} |= "health_factor" |= "HARD_STOP"
```

### Retention

Logs are retained for **7 days** (168 hours) as configured in `docker/loki/loki-config.yaml`. Adjust `retention_period` and redeploy if a longer window is needed.

### Storage

Log chunks are stored in the `loki-data` Docker named volume (`/loki/chunks` inside the container). On the Hetzner VPS this maps to `/var/lib/docker/volumes/ultra-autotrade-loki-data/`.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Services fail to start with logging driver error | Loki plugin not installed | Run `docker plugin install ...` above |
| Promtail shows no streams | Docker socket not mounted | Check `/var/run/docker.sock` mount in compose |
| Loki OOM on VPS | Ingestion rate too high | Lower `ingestion_rate_mb` in `loki-config.yaml` |
| Logs missing after restart | Volume removed | Do not use `docker compose down -v` |
