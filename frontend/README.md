# Ultra AutoTrade - Operations Dashboard (Web)

Read-only operations UI aligned with `docs/19_operations_runbook.md`.

## Requirements

- Node.js 18+
- Backend FastAPI running

## Run (local)

1) Start backend (example):
- `uvicorn app.main:app --reload --port 8000`

2) Start UI:

```bash
cd frontend
npm install
BACKEND_BASE_URL=http://localhost:8000 npm run dev
```

Then open:
- http://localhost:3000/dashboard/automation
- http://localhost:3000/dashboard/reports

## Notes

- By default the UI calls **same-origin** `/api/automation/*`, which is proxied by Next.js to `BACKEND_BASE_URL`.
- If you prefer calling backend directly from the browser, set:
  - `NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:8000`
  - (Backend CORS may be required.)
