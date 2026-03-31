# Anonymization Report
Generated: 2026-03-20

---

## 1. Japanese Text Found

Japanese text (hiragana, katakana, kanji) is present in a large number of files across the project. Below is a summary by file type, followed by selected representative files. The full set of matches is very large (hundreds of occurrences); only the file-level inventory is practical to enumerate here.

### Python files with Japanese text (183 files total — selected notable ones)

| File | Notes |
|------|-------|
| `backend/app/main.py` | Japanese comments |
| `backend/app/ai/service.py` | Japanese comments and docstrings |
| `backend/app/ai/prompts.py` | Japanese text in LLM prompts |
| `backend/app/aave/rebalance_service.py` | Japanese comments |
| `backend/app/aave/service.py` | Japanese comments |
| `backend/app/aave/client.py` | Japanese comments |
| `backend/app/auth/router.py` | Japanese comments |
| `backend/app/auth/schemas.py` | Japanese comments |
| `backend/app/auth/models.py` | Japanese comments |
| `backend/app/automation/workflow.py` | Japanese comments |
| `backend/app/knowledge/service.py` | Japanese comments |
| `backend/app/exchange/service.py` | Japanese comments |
| `scripts/aave_borrow_test.py` | Japanese docstrings and inline comments |
| `scripts/aave_withdraw_test.py` | Japanese comments |
| `scripts/aave_hf_monitor_test.py` | Japanese comments |
| `.claude/hooks/slack_notify.py` | Japanese text |
| `.claude/hooks/slack_permission.py` | Japanese text |
| (+ 166 more Python files) | |

### TypeScript/TSX/JS files with Japanese text (71 files total — selected notable ones)

| File | Notes |
|------|-------|
| `frontend/components/AuthGuard.tsx` | Japanese comments |
| `frontend/lib/auth.ts` | Japanese security notes in comments |
| `frontend/app/login/page.tsx` | Japanese UI text |
| `frontend/app/user/dashboard/page.tsx` | Japanese UI text |
| `frontend/app/(admin)/dashboard/page.tsx` | Japanese UI text |
| `frontend/app/(admin)/settings/users/page.tsx` | Japanese UI text |
| `frontend/tests/smoke.spec.ts` | Japanese test descriptions |
| `frontend/lib/api/automation.ts` | Japanese comments |
| (+ 63 more TS/TSX/JS files) | |

### YAML/TOML files with Japanese text (6 files)

| File | Notes |
|------|-------|
| `docker-compose.staging.yml` | Japanese comments |
| `docker-compose.production.yml` | Japanese comments |
| `.github/workflows/claude-review.yml` | Japanese review criteria in workflow prompts |
| `.github/workflows/path-check.yml` | Japanese messages in workflow scripts |
| `.github/workflows/auto-review.yml` | Japanese comments |
| `backend/ruff.toml` | Japanese comments |

### Markdown files with Japanese text (55 files total — selected notable ones)

| File | Notes |
|------|-------|
| `CLAUDE.md` | Japanese throughout (development guide) |
| `README.md` | Japanese sections |
| `QUICKSTART_SLACK.md` | Japanese instructions |
| `docs/00_overview.md` through `docs/27_asana_operations.md` | All docs heavily in Japanese |
| `.skills/aave-development.md` | Japanese throughout |
| `.skills/ultra-autotrade-context.md` | Japanese + contains IP address |
| `.claude/skills/ultra-staging-deploy/SKILL.md` | Japanese + IP address |
| `.claude/commands/verify.md` | Japanese |
| `.claude/commands/plan-review.md` | Japanese |
| `tasks/lessons.md` | Japanese |
| `tasks/anti-slop.md` | Japanese |

---

## 2. Personal Identifiers Found

| File | Line | Type | Content |
|------|------|------|---------|
| `scripts/seed_staging_users.py` | 39 | Username + email | `"email": "hkobayashi@ultra-autotrade.com"` |
| `scripts/seed_staging_users.py` | 40 | Username | `"username": "hkobayashi"` |
| `docs/deploy_staging.md` | 3 | Username | `対象: hkobayashi による Hetzner VPS への手動デプロイ` |
| `.claude/settings.json` | 4,10,36,45,67,68,84,133,134 | Local filesystem path | Multiple refs to `/Users/hkobayashi/projects/...` |
| `docs/DEPLOY_GUIDE.md` | 18 | GitHub username | `github.com/milechy/ultra-autotrade-project` |
| `docs/DEPLOY_GUIDE.md` | 25 | GitHub username | `github.com/milechy/ultra-autotrade-project.git` |

**No matches for "小林" (kanji name) were found.**

---

## 3. Hardcoded URLs/IPs Found

### Hetzner IP address (77.42.46.155)

| File | Line(s) | Content |
|------|---------|---------|
| `.skills/ultra-autotrade-context.md` | 18–20, 111 | `77.42.46.155` (staging IP, frontend/backend URLs, SSH) |
| `.claude/skills/ultra-staging-deploy/SKILL.md` | 46 | `ssh ultra@77.42.46.155` |
| `scripts/test_octobot_flow.sh` | 10, 22 | `http://77.42.46.155:8000` (default API URL) |
| `frontend/.env.local.example` | 18, 23, 30, 31 | `http://77.42.46.155:8000` |
| `QUICKSTART_SLACK.md` | 67 | `ssh root@77.42.46.155` |
| `docs/26_slack_automation_guide.md` | 83, 105 | `https://77.42.46.155:5000/slack/interactions`, `ssh root@77.42.46.155` |
| `docs/23_partner_test_guide.md` | 3 | `http://77.42.46.155:3000`, `http://77.42.46.155:8000` |
| `docs/04_api_design.md` | 19 | `http://77.42.46.155:8000` |
| `docs/24_octobot_manual_test.md` | 4 | `77.42.46.155 (Hetzner staging)` |
| `docs/24_partner_test_guide.md` | 29–31, 144, 146, 155, 191, 213, 220, 249 | Multiple `http://77.42.46.155:...` references |
| `docs/deploy_staging.md` | 21 | `ssh root@77.42.46.155` |
| `.env.staging.example` | 87 | `CORS_ORIGINS=http://localhost:3000,http://77.42.46.155:3000` |

### Hardcoded domain: ultra-auto-trade.com

| File | Line | Content |
|------|------|---------|
| `scripts/slack-approval-hook.sh` | 18 | `API_BASE="${HOOKS_API_BASE:-https://api.ultra-auto-trade.com}"` |
| `backend/app/main.py` | 69 | `_default_origins = "https://app.ultra-auto-trade.com,http://localhost:3000"` |
| `docker-compose.staging.yml` | 113, 115 | `NEXT_PUBLIC_BACKEND_BASE_URL: ${...:-https://api.ultra-auto-trade.com}` |
| `frontend/tests/smoke.spec.ts` | 14 | `request.get('https://api.ultra-auto-trade.com/health')` |
| `frontend/app/user/simulation/page.tsx` | 10 | `process.env.NEXT_PUBLIC_API_URL \|\| 'https://api.ultra-auto-trade.com'` |
| `frontend/app/user/trade/page.tsx` | 19 | `process.env.NEXT_PUBLIC_API_URL \|\| 'https://api.ultra-auto-trade.com'` |
| `frontend/app/user/settings/page.tsx` | 20 | `process.env.NEXT_PUBLIC_API_URL \|\| 'https://api.ultra-auto-trade.com'` |
| `frontend/app/user/ai-feed/page.tsx` | 13 | `process.env.NEXT_PUBLIC_API_URL \|\| 'https://api.ultra-auto-trade.com'` |
| `frontend/app/user/dashboard/page.tsx` | 21 | `process.env.NEXT_PUBLIC_API_URL \|\| 'https://api.ultra-auto-trade.com'` |
| `frontend/app/user/performance/page.tsx` | 21 | `process.env.NEXT_PUBLIC_API_URL \|\| 'https://api.ultra-auto-trade.com'` |

### Hetzner references in code/config (provider name)

| File | Notes |
|------|-------|
| `CLAUDE.md` | "Hetzner VPS" in architecture section |
| `README.md` | "Hetzner VPS" in stack table |
| `docs/deploy_staging.md` | "Hetzner VPS" in title |
| `docs/DEPLOY_GUIDE.md` | "Hetzner VPS" throughout |
| `docs/16_infra_deployment_guide.md` | "Hetzner Cloud Ubuntu" |
| `.github/workflows/deploy-staging.yml` | secrets named `HETZNER_HOST`, `HETZNER_USER`, `HETZNER_SSH_KEY` (safe — uses secrets) |
| `.github/workflows/staging-deploy.yml` | Same secrets pattern (safe) |
| `scripts/hetzner_setup.sh` | Script name and internal references |
| `scripts/slack_handler.py` | Comment mentions Hetzner staging server |
| `frontend/lib/api/automation.ts` | Comment mentions Hetzner Staging |

---

## 4. .gitignore Status

The `.gitignore` at project root uses the pattern `.env.*` (with `!.env.example` and `!.env.*.example` exceptions), which **covers** `.env.staging` and `.env.production` by wildcard.

**Status: PASS** — `.env.staging` and `.env.production` are excluded from version control via `.env.*` wildcard rule.

However, the following example files **are** committed and contain the hardcoded IP `77.42.46.155`:
- `.env.staging.example` (line 87: `CORS_ORIGINS=http://localhost:3000,http://77.42.46.155:3000`)
- `frontend/.env.local.example` (lines 18, 23, 30, 31: hardcoded staging IP)

---

## 5. Summary: Files Requiring Changes

The following files contain personal identifiers or hardcoded infrastructure details that should be anonymized before public release or sharing:

### High Priority (personal identifiers)
1. `scripts/seed_staging_users.py` — contains `hkobayashi` username and email `hkobayashi@ultra-autotrade.com`
2. `docs/deploy_staging.md` — contains `hkobayashi` in header
3. `docs/DEPLOY_GUIDE.md` — contains GitHub username `milechy`
4. `.claude/settings.json` — contains absolute paths with `hkobayashi` home directory (local config, should not be in repo)

### High Priority (hardcoded IP)
5. `scripts/test_octobot_flow.sh` — hardcoded IP `77.42.46.155` as default
6. `frontend/.env.local.example` — hardcoded IP `77.42.46.155` (example file committed to repo)
7. `.env.staging.example` — hardcoded IP `77.42.46.155`
8. `.skills/ultra-autotrade-context.md` — hardcoded IP + SSH commands
9. `.claude/skills/ultra-staging-deploy/SKILL.md` — hardcoded IP
10. `QUICKSTART_SLACK.md` — `ssh root@77.42.46.155`
11. `docs/26_slack_automation_guide.md` — hardcoded IP in Request URL and SSH command
12. `docs/23_partner_test_guide.md` — multiple hardcoded IP references
13. `docs/24_partner_test_guide.md` — many hardcoded IP references in curl examples
14. `docs/24_octobot_manual_test.md` — hardcoded IP
15. `docs/04_api_design.md` — hardcoded IP in table
16. `docs/deploy_staging.md` — hardcoded IP in SSH command

### Medium Priority (hardcoded domain in source code)
17. `backend/app/main.py` — `ultra-auto-trade.com` as hardcoded CORS default
18. `frontend/app/user/simulation/page.tsx` — hardcoded API URL fallback
19. `frontend/app/user/trade/page.tsx` — hardcoded API URL fallback
20. `frontend/app/user/settings/page.tsx` — hardcoded API URL fallback
21. `frontend/app/user/ai-feed/page.tsx` — hardcoded API URL fallback
22. `frontend/app/user/dashboard/page.tsx` — hardcoded API URL fallback
23. `frontend/app/user/performance/page.tsx` — hardcoded API URL fallback
24. `scripts/slack-approval-hook.sh` — hardcoded domain in API base default
25. `frontend/tests/smoke.spec.ts` — hardcoded domain in E2E test URL
26. `docker-compose.staging.yml` — hardcoded domain as env var default

### Low Priority (provider name "Hetzner" — informational, not a secret)
- `CLAUDE.md`, `README.md`, multiple `docs/` files, `.github/workflows/deploy-staging.yml`, `scripts/hetzner_setup.sh` — these reference "Hetzner" as the cloud provider name. Safe to keep if the project is shared publicly with infrastructure provider disclosed; otherwise replace with a generic placeholder like "VPS_PROVIDER".

### Japanese text
- 183 Python files, 71 TS/TSX/JS files, 6 YAML/TOML files, 55 Markdown files contain Japanese text. This is intentional (development language is Japanese) but must be considered if the project is to be shared with non-Japanese audiences or passed through tools that may not handle multibyte characters correctly.
