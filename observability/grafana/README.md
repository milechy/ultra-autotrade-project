# Grafana - Automation Operations Dashboard

This folder provides a **configuration template** to visualize the existing Operations APIs:

- `GET /api/automation/status` → `AutomationStatus`
- `GET /api/automation/dashboard?lookback_hours=1..24` → `DashboardSnapshot`
- `GET /api/automation/reports/latest` → `AutomationReportSummary`

## Principles (contract-safe)

- **No backend contract changes** are required.
- Panels are designed to be resilient when fields evolve (they fall back to JSON views when needed).
- This is **read-only visibility** for SRE/operations.

## Recommended datasource approach

Grafana needs a datasource capable of reading JSON over HTTP.

Two common approaches:

1. **Infinity datasource plugin** (recommended for quick setup)
2. **JSON API datasource plugin** (alternative)

This repository provides provisioning files assuming **Infinity**. If your environment prefers JSON API, keep the dashboard layout but adjust the datasource type accordingly.

## Local usage (example)

1. Run backend (FastAPI) on `http://localhost:8000`
2. Run Grafana (docker)
3. Install Infinity plugin in Grafana
4. Provision datasource + dashboards using the YAML files in `provisioning/`

## Dashboard scope

The included dashboard focuses on:

- Emergency pause state (`is_trading_paused`)
- Last health factor (`last_health_factor`)
- Last 24h portfolio change (`last_price_change_24h`)
- Last event level (`last_event_level`)
- Snapshot aggregates table (best-effort)
- Latest report JSON / highlights

This mirrors the operational guidance in `docs/19_operations_runbook.md` (§2.4 and related sections).
