// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
import { test, expect } from '@playwright/test'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

test.describe('API Health Check Tests', () => {
  test('GET /health が200を返す', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/health`)
    expect(response.status()).toBe(200)
  })

  test('GET /api/automation/status が認証なしで401を返す', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/automation/status`)
    expect(response.status()).toBe(401)
  })
})
