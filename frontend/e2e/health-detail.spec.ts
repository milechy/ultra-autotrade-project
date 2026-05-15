// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// E2E for GET /health/detail (admin only, 5/14 DoD #6)
//
// Run with:
//   BACKEND_URL=http://127.0.0.1:8082 \
//   ADMIN_TOKEN=<jwt-of-admin-user> \
//   VIEWER_TOKEN=<jwt-of-non-admin-user> \
//   npx playwright test e2e/health-detail.spec.ts
//
// Token minting helper (run on Hetzner inside the backend container):
//   docker exec ultra-autotrade-backend-green-staging-new python -c \
//     "from app.auth.service import AuthService; \
//      t,_ = AuthService.create_access_token(user_id=1, email='admin@x.com', role='admin'); print(t)"

import { test, expect } from '@playwright/test'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'
const ADMIN_TOKEN = process.env.ADMIN_TOKEN ?? ''
const VIEWER_TOKEN = process.env.VIEWER_TOKEN ?? ''

test.describe('GET /health/detail (admin multi-layer health)', () => {
  test('admin → 200 + 4-component schema', async ({ request }) => {
    test.skip(
      !ADMIN_TOKEN,
      '理由: ADMIN_TOKEN 未設定。staging 環境変数注入が必要。詳細はファイル冒頭コメント参照'
    )
    const resp = await request.get(`${BACKEND_URL}/health/detail`, {
      headers: { Authorization: `Bearer ${ADMIN_TOKEN}` },
    })
    expect(resp.status()).toBe(200)
    const body = await resp.json()

    expect(['ok', 'degraded', 'down']).toContain(body.status)
    expect(body.components).toBeDefined()
    expect(body.components.scheduler.ok).toBeDefined()
    expect(body.components.quota.openai.reachable).toBeDefined()
    expect(body.components.quota.perplexity.reachable).toBeDefined()
    expect(body.components.cross_judgment.last_6h_total).toBeDefined()
    expect(body.components.safety.limiter_mode).toMatch(/^(strict|custom)$/)
    expect(Array.isArray(body.warnings)).toBe(true)
    expect(body.cached_at).toBeDefined()
  })

  test('viewer → 403 Admin access required', async ({ request }) => {
    test.skip(
      !VIEWER_TOKEN,
      '理由: VIEWER_TOKEN 未設定。staging 環境変数注入が必要。詳細はファイル冒頭コメント参照'
    )
    const resp = await request.get(`${BACKEND_URL}/health/detail`, {
      headers: { Authorization: `Bearer ${VIEWER_TOKEN}` },
    })
    expect(resp.status()).toBe(403)
    const body = await resp.json()
    expect(body.detail).toBe('Admin access required')
  })

  test('no token → 401 Not authenticated', async ({ request }) => {
    test.skip(
      !ADMIN_TOKEN,
      '理由: BACKEND_URL 経由のテスト。ADMIN_TOKEN 設定セッションでのみ実行'
    )
    const resp = await request.get(`${BACKEND_URL}/health/detail`)
    expect(resp.status()).toBe(401)
  })
})
