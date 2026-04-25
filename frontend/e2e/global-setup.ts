// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Playwright global setup: log in once and cache the JWT for all tests.
// Prevents rate-limit hits (5/min) when 24+ tests each call /auth/login.
//
// Output: e2e/.auth/partner.json  { token, expiresAt, email }

import fs from 'fs'
import path from 'path'

export default async function globalSetup(): Promise<void> {
  const email = process.env.E2E_PARTNER_EMAIL
  const password = process.env.E2E_PARTNER_PASSWORD
  if (!email || !password) {
    console.log('[global-setup] Credentials not set — auth cache skipped')
    return
  }

  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? 'https://api.ultra-auto-trade.com'

  const res = await fetch(`${backendUrl}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!res.ok) {
    console.warn(`[global-setup] /auth/login failed: ${res.status} — tests will attempt login individually`)
    return
  }

  const data = (await res.json()) as { access_token: string; expires_in: number }
  const expiresAt = Date.now() + data.expires_in * 1000

  const authDir = path.join(process.cwd(), 'e2e', '.auth')
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true })

  fs.writeFileSync(
    path.join(authDir, 'partner.json'),
    JSON.stringify({ token: data.access_token, expiresAt, email }),
  )
  console.log('[global-setup] Partner auth state cached (token valid 24 h)')
}
