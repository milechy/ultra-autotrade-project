# Staging UI Test Results

**Date:** 2026-03-20
**Tool:** agent-browser 0.21.2
**Target:** http://77.42.46.155:3000
**Tester:** Claude Code (automated)

---

## Summary

| # | Page | URL | Result | Notes |
|---|------|-----|--------|-------|
| 1 | Login | `/login` | ✅ PASS | Form rendered, login succeeded |
| 2 | Terms modal | (post-login overlay) | ✅ PASS | 4 checkboxes, accept button enabled after all checked |
| 3 | Data Feeds | `/data-feeds` | ✅ PASS | "AI Data Intelligence" heading present, signal data displayed |
| 4 | Risk Mode | `/settings/account` | ✅ PASS | 3 cards: 保守/バランス/積極 all visible |
| 5 | Onboarding | `/onboarding` | ✅ PASS | 4-step guide rendered (correct path: `/onboarding` not `/user/onboarding`) |
| 6 | Simulation | `/user/simulation` | ✅ PASS | 3 scenario cards: 今預けたら/全額引き出したら/何もしない |
| 7 | Performance | `/user/performance` | ⚠️ PARTIAL | Page renders, "月次レポートDL" button present, but "データを取得できませんでした" (API fetch failed) |

**Overall: 6 PASS, 1 PARTIAL, 0 FAIL**

---

## Detailed Results

### 1. Login — ✅ PASS
- **URL:** http://77.42.46.155:3000/login
- **Screenshot:** `test-results/01-login.png`
- Email field, password field, and "ログイン" button all rendered correctly
- Login with admin credentials succeeded → redirected to dashboard

### 2. Terms Modal — ✅ PASS
- **Screenshot:** `test-results/02-terms.png`
- Appeared automatically after first login
- 4 checkboxes present:
  1. 利用規約に同意します
  2. リスク開示書を理解し同意します
  3. プライバシーポリシーに同意します
  4. 18歳以上であることを確認します
- Accept button ("同意してサービスを利用する") correctly disabled until all checked
- After checking all → button enabled → click succeeded → modal dismissed

### 3. Data Feeds — ✅ PASS
- **URL:** http://77.42.46.155:3000/data-feeds
- **Screenshot:** `test-results/03-data-feeds.png`
- Heading "AI Data Intelligence" confirmed present
- Subtitle: "Phase 2 — Real-time market context for AI judgment"
- Signal displayed: NEUTRAL (28% confidence)
- INDICATOR AGENT, NEUTRAL (30%) visible

### 4. Risk Mode — ✅ PASS
- **URL:** http://77.42.46.155:3000/settings/account
- **Screenshot:** `test-results/04-risk-mode.png`
- "リスクモード設定" section present under account settings
- All 3 cards confirmed:
  - 🛡️ 保守（初心者向け） — max 60%, HF 2.0, confidence 80%
  - ⚖️ バランス（標準） — max 75%, HF 1.7, confidence 65%
  - 🚀 積極（経験者向け） — max 90%, HF 1.5, confidence 50%
- Current mode: バランス (marked "現在")

### 5. Onboarding — ✅ PASS
- **URL:** http://77.42.46.155:3000/onboarding (NOT `/user/onboarding`)
- **Screenshot:** `test-results/05-onboarding.png`
- "はじめに" heading and 4-step wallet guide rendered
- STEP 1: ウォレットを準備する (MetaMask setup)
- Note: route is at `/onboarding` due to Next.js route group `(user)` — `/user/onboarding` would 404

### 6. Simulation — ✅ PASS
- **URL:** http://77.42.46.155:3000/user/simulation
- **Screenshot:** `test-results/06-simulation.png`
- 3 scenario cards confirmed:
  1. 今預けたら → +45.21 USDC (+0.45%)
  2. 全額引き出したら → -2.00 USDC (-0.02%)
  3. 何もしない → ホールド
- Note: "シミュレーション中... (オフラインモード)" — backend `/api/transparency/simulation` unreachable, using fallback mock data

### 7. Performance — ⚠️ PARTIAL
- **URL:** http://77.42.46.155:3000/user/performance
- **Screenshot:** `test-results/07-performance.png`
- Page renders with "パフォーマンス" heading
- "月次レポートDL" download button present
- ⚠️ Body shows "データを取得できませんでした" — backend API returning error or unreachable
- **Action needed:** Check `GET /api/transparency/performance` endpoint and backend `/reports/monthly` endpoint on staging

---

## Issues Found

| Severity | Issue | Affected Page |
|----------|-------|---------------|
| LOW | Performance page shows "データを取得できませんでした" — backend API unreachable | `/user/performance` |
| INFO | Simulation uses fallback mock data (backend unreachable) | `/user/simulation` |
| INFO | Onboarding is at `/onboarding` not `/user/onboarding` — documented correctly | N/A |

---

## Screenshots

All saved to `docs/test-results/`:
- `01-login.png` — Login page
- `02-terms.png` — Terms modal (all checked)
- `03-data-feeds.png` — AI Data Intelligence
- `04-risk-mode.png` — Risk mode 3 cards
- `05-onboarding.png` — 4-step onboarding
- `06-simulation.png` — 3 scenario cards
- `07-performance.png` — Performance (partial)
