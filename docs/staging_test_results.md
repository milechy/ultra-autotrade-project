# Staging Test Results
Generated: 2026-03-20
Backend: http://localhost:8000 | Frontend: http://localhost:3000

---

## Frontend Verification

| Page | HTTP Status | Expected | Result |
|------|-------------|----------|--------|
| / | 200 | 200 | ✅ |
| /login | 200 | 200 | ✅ |
| /data-feeds | 200 | 200 | ✅ |
| /user/onboarding | **404** | 200 | ❌ Path mismatch — actual path is `/onboarding` |
| /onboarding | 200 | — | ✅ (correct path) |
| /user/simulation | 200 | 200 | ✅ |
| /user/performance | 200 | 200 | ✅ |
| /user/settings | 200 | 200 | ✅ |
| /user/dashboard | 200 | 200 | ✅ |
| /admin/dashboard | **404** | 200 | ⚠️ Admin pages not accessible (may require auth) |

### Asset / Security Checks
| Check | Result | Notes |
|-------|--------|-------|
| Source maps (.js.map) | ✅ 404 | Not served |
| JS bundle loads | ✅ 200 | webpack chunk OK |
| Error patterns in HTML | ✅ None | Clean source |
| X-Frame-Options | ❌ Missing | Clickjacking risk |
| X-Content-Type-Options | ❌ Missing | MIME sniffing risk |
| **X-Powered-By** | ⚠️ `Next.js` | **Should remove** — add `poweredByHeader: false` |

**Frontend Score: 7/10**

---

## API Test Matrix

### Login
| User | Role | Status | Token |
|------|------|--------|-------|
| hkobayashi@ultra-autotrade.com | admin | ✅ 200 | eyJhbGciOiJIUzI1NiIs... |
| partner@ultra-autotrade.com | editor | ✅ 200 | eyJhbGciOiJIUzI1NiIs... |
| test@ultra-autotrade.com | viewer | ✅ 200 | eyJhbGciOiJIUzI1NiIs... |

### Data Feeds — GET (expect 200 all roles)
| Endpoint | Admin | Editor | Viewer | Result |
|----------|-------|--------|--------|--------|
| /api/data-feeds/geo-risk | 200 | 200 | 200 | ✅ |
| /api/data-feeds/news | 200 | 200 | 200 | ✅ |
| /api/data-feeds/finance | 200 | 200 | 200 | ✅ |
| /api/data-feeds/agents | 200 | 200 | 200 | ✅ |

### Refresh — POST (expect admin=200, editor/viewer=403)
| Endpoint | Admin | Editor | Viewer | Result |
|----------|-------|--------|--------|--------|
| /api/data-feeds/geo-risk/refresh | 200 | 403 | 403 | ✅ |
| /api/data-feeds/news/refresh | 200 | 403 | 403 | ✅ |
| /api/data-feeds/finance/refresh | 200 | 403 | 403 | ✅ |

### Terms Endpoints
| Endpoint | Method | Admin | Editor | Viewer | Result |
|----------|--------|-------|--------|--------|--------|
| /auth/terms/status | GET | 200 | 200 | 200 | ✅ |
| /auth/terms/accept | POST | 200* | 200* | 200* | ✅ |

> *Schema note: requires `{"accepted": true, "version": "v2"}` — not `{"accepted": true}` alone.

### Risk Mode
| Endpoint | Method | Admin | Editor | Viewer | Result |
|----------|--------|-------|--------|--------|--------|
| /auth/risk-mode | GET | 200 | 200 | 200 | ✅ |
| /auth/risk-mode | PUT | 200* | 200* | 200* | ✅ |

> *Schema note: field is `"mode"` not `"risk_mode"` — e.g. `{"mode": "balanced"}`.

### New Endpoints
| Endpoint | Admin | Viewer | Result |
|----------|-------|--------|--------|
| /api/reports/monthly | 200 | **403** | ✅ Admin-only enforced |
| /api/transparency/safety-score | 200 | 200 | ⚠️ See security issue below |

### Unauthenticated Access (expect 401)
| Endpoint | Status | Result |
|----------|--------|--------|
| /api/data-feeds/geo-risk | 401 | ✅ |
| /auth/terms/status | 401 | ✅ |
| /auth/risk-mode | 401 | ✅ |
| /api/reports/monthly | 401 | ✅ |
| **/api/transparency/safety-score** | **200** | ❌ Auth missing |

**API Score: 17/18**

---

## Security Verification

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| /docs hidden | 404 | **200** | ❌ Swagger UI exposed |
| /redoc hidden | 404 | **200** | ❌ ReDoc exposed |
| /openapi.json hidden | 404 | **200** | ❌ OpenAPI schema exposed |
| CORS blocks evil origin | No allow header | No header returned | ⚠️ CORS not configured (verify intent) |
| Stack traces in errors | CLEAN | CLEAN | ✅ |
| Server header hidden | Not present | `uvicorn` | ⚠️ Exposes server type |
| SQL injection safe | 422/401 | 422 | ✅ Pydantic blocks it |
| Rate limiting (5 bad logins) | 429 after N attempts | 401 × 5 (no 429) | ❌ No rate limiting |
| /api/transparency/safety-score auth | 401 | **200** | ❌ Publicly accessible |

**Security Score: 3/9** ⚠️

---

## Action Items (Priority Order)

### 🔴 Critical — Fix before production
1. **Swagger/Docs exposed** — Add `include_in_schema=False` or disable via env in FastAPI:
   ```python
   app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
   ```
2. **`/api/transparency/safety-score` unauthenticated** — Add `Depends(get_current_user)` to this endpoint

### 🟠 High — Fix before production
3. **No rate limiting on `/auth/login`** — Add `slowapi` or `fastapi-limiter` (e.g. 5 req/min per IP)
4. **`X-Powered-By: Next.js` exposed** — Add to `frontend/next.config.js`:
   ```js
   poweredByHeader: false,
   ```

### 🟡 Medium — Fix soon
5. **Server header exposes `uvicorn`** — Add reverse proxy header removal (nginx/Cloudflare)
6. **CORS not configured** — Verify `CORS_ORIGINS` env var is set; test with allowed origin returns `Access-Control-Allow-Origin`
7. **Frontend `/user/onboarding` path mismatch** — Either rename page to `app/user/onboarding/page.tsx` or update nav links to use `/onboarding`

### 🔵 Info
8. **Terms accept schema** — Document that `version` field is required (current default: `"v2"`)
9. **Risk mode PUT schema** — Document that field name is `"mode"` not `"risk_mode"`

---

## Summary

| Category | Score | Status |
|----------|-------|--------|
| Frontend pages | 7/10 | ⚠️ |
| API functionality | 17/18 | ✅ |
| Security hardening | 3/9 | ❌ |
| **Overall** | **27/37** | **⚠️ Not production-ready** |

**Blocker before production deploy:** Fix items 1–4 above.
