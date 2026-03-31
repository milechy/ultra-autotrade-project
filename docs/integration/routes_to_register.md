# Transparency Router — Registration Instructions

Add the following lines to `backend/app/main.py` inside the `create_app()` function,
alongside the other `app.include_router(...)` calls:

```python
from app.aave.transparency_router import router as transparency_router

app.include_router(transparency_router)  # Transparency (Wave 2)
```

## Endpoints exposed after registration

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/transparency/safety-score | Safety score (0-100) with breakdown |
| GET | /api/transparency/explanation/{decision_id} | 5-step natural-language explanation |
| GET | /api/transparency/signal | Market weather signal (sunny/cloudy/stormy) |
| GET | /api/transparency/impact | Gain/loss impact for a deposit action |
| GET | /api/transparency/simulation | supply / withdraw / hold scenario projection |
| GET | /api/transparency/performance | Mock 30-day performance summary |
| GET | /api/transparency/risk-profile | All three risk profiles (list) |
| GET | /api/transparency/risk-profile/{mode} | Single risk profile by mode |

## Query parameters

`GET /api/transparency/impact`

| Parameter | Type | Default | Constraint |
|-----------|------|---------|------------|
| current_amount | float | 1000.0 | — |
| action_amount | float | 500.0 | must be > 0 (else 422) |

---

## Billing Module

Router: `from app.billing.router import router as billing_router`
Registration: `app.include_router(billing_router)`
Prefix: `/api/billing`
Tags: `["billing"]`

### Endpoints exposed after registration

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/billing/fees | viewer | ユーザーの手数料履歴（?user_id=, ?period= オプション） |
| GET | /api/billing/summary | viewer | ユーザーの手数料累計サマリー（?user_id=） |
| POST | /api/billing/batch/daily | admin | 日次手数料バッチ実行（body: {"uid": "aum"} JSON） |
| GET | /api/billing/config | viewer | 現在の手数料設定 |

---

## Knowledge Hub — Search Test & Workflow Trigger (already registered via knowledge router)

The following endpoints are added to the existing knowledge router (already registered in `main.py`).
No additional `app.include_router(...)` calls are needed.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/knowledge/search/test | editor+ | Admin RAG search test with query params |
| POST | /api/knowledge/workflow/trigger | admin | Trigger full pipeline for pending items |
