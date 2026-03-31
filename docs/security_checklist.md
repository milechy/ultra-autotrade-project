# Security Checklist

## GitHub Repository Security

- [ ] Repo visibility: **Unknown** — `gh repo view --json isPrivate` could not be executed (Bash tool unavailable in this session). Git remote URL confirms: `https://github.com/milechy/ultra-autotrade-project.git`. Visibility must be verified manually or via CI.
- [ ] main branch protection: **Unknown — action required**
  - Require PR review: not confirmed (CLAUDE.md rule 9 mandates: "main branch: no direct push, PR + review required")
  - No force push: not confirmed
  - No deletions: not confirmed
- [ ] dev branch protection: **Unknown — action required**
- [ ] GitHub Actions secrets: **Unknown** — `gh secret list` could not be executed. Expected secrets: `HETZNER_HOST`, `HETZNER_USER`, `HETZNER_SSH_KEY` (values must never be printed).

## Manual Actions Required

Because the Bash tool was denied in this session, the following `gh` CLI commands must be run manually (or via CI) by the repo owner:

### 1. Check repo visibility
```bash
cd /Users/hkobayashi/projects/ultra-autotrade
gh repo view --json isPrivate,name,url
```

### 2. Check existing branch protection
```bash
gh api repos/milechy/ultra-autotrade-project/branches/main/protection 2>&1 || echo "no protection set"
```

### 3. Enable branch protection on main
```bash
gh api repos/milechy/ultra-autotrade-project/branches/main/protection \
  --method PUT \
  --field required_status_checks=null \
  --field enforce_admins=false \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false
```

### 4. Enable branch protection on dev (no force push only)
```bash
gh api repos/milechy/ultra-autotrade-project/branches/dev/protection \
  --method PUT \
  --field required_status_checks=null \
  --field enforce_admins=false \
  --field required_pull_request_reviews=null \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false
```

### 5. Verify GitHub Actions secrets
```bash
gh secret list | head -20
# Expected: HETZNER_HOST, HETZNER_USER, HETZNER_SSH_KEY
```

### 6. Slack notification (send after completing steps above)
```bash
WEBHOOK=$(grep SLACK_WEBHOOK_URL /Users/hkobayashi/projects/ultra-autotrade/.env.staging | cut -d= -f2-)
curl -s -X POST "$WEBHOOK" -H "Content-Type: application/json" \
  -d '{"text": "✅ [github-security] 完了: GitHubセキュリティ設定\n結果: ブランチ保護設定、リポジトリ可視性確認\nファイル: docs/security_checklist.md"}'
```

## Application Security Status (from security_audit_report.md — 2026-03-11)

| Rule | Status | Notes |
|------|--------|-------|
| 1. No hardcoded secrets | PASS | All configs use `get_env()` |
| 2. Log masking | PASS | `[:6]...[-4:]` pattern implemented |
| 3. HF < 1.6 → HARD_STOP | PASS | Dual-layer implementation |
| 4. Emergency stop OR logic | PASS | `existing OR triggered` |
| 5. JWT weak key rejection | **WARN** | `validate_secret_key()` not called at startup in `main.py` |
| 6. LLM fail-closed | PASS | Parse failure → HOLD |
| 7. Decimal-only financials | PASS | All major financial fields use Decimal |
| 8. HARD_STOP blocking | PASS | 6-layer block implemented |
| 9. state.json atomic write | PASS | `chmod 600` implemented |

### Open Item: WARN-5
`backend/app/main.py` does not call `AuthService.validate_secret_key()` at startup.
A weak JWT secret key would not be rejected at boot in staging/production.
**Fix:** Add `AuthService.validate_secret_key()` to the `startup_database` event handler.

## Status

**Date:** 2026-03-20

**Summary:**
- Repo remote confirmed: `https://github.com/milechy/ultra-autotrade-project.git` (owner: `milechy`)
- Branch protection (main + dev) and repo visibility could NOT be set or confirmed in this session because the Bash tool was denied. All required `gh` CLI commands are documented above for manual execution.
- Application-level security audit (41 tests) shows 1 WARN (JWT startup validation) and 9 PASS items per the 2026-03-11 audit report.
- CLAUDE.md Security Rule 9 (no direct push to main, PR + review required) should be enforced via the branch protection commands listed above.

## Frontend Security

**Date:** 2026-03-20

- [x] productionBrowserSourceMaps: false — already set (was present before this task)
- [x] console.log stripped in production — configured (`compiler.removeConsole: { exclude: ['error'] }` added to `frontend/next.config.js`)
- [x] TypeScript errors: 0 — `npx tsc --noEmit` completed with no output (zero errors)
- [x] API routes reviewed: 2 — no issues found
  - `app/api/automation/[...path]/route.ts`: proxies to backend, catches errors and returns generic `"Failed to reach backend: <message>"` — error message includes `e.message` which may leak internal network hostnames in the 502 response body (low severity, backend-only detail)
  - `app/api/aave/[...path]/route.ts`: same pattern as above; also correctly forwards the `Authorization` header — same low-severity hostname leak in 502 body
  - Neither route logs sensitive data or exposes stack traces/DB errors
- [x] No sensitive env vars exposed client-side: PASS
  - `NEXT_PUBLIC_` vars in use: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_BACKEND_BASE_URL`, `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID`
  - All are public endpoint URLs or a WalletConnect project ID — no private keys, no secrets
  - `BACKEND_BASE_URL` (server-side, non-public) is correctly used only in API routes and never bundled client-side
