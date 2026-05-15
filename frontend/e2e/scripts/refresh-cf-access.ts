// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// CF Access Cookie リフレッシュスクリプト
//
// 使用方法:
//   npx ts-node e2e/scripts/refresh-cf-access.ts
//
// または Playwright コードでの実行:
//   npx playwright codegen https://staging.ultra-auto-trade.com \
//     --save-storage=.auth/cf-access.json
//
// 手順:
//   1. このスクリプトを実行するとブラウザが開く
//   2. Cloudflare Access の OTP 画面で hkobayashi@mooores.com にメールを送信
//   3. メールに届いたコードを入力して認証
//   4. staging.ultra-auto-trade.com が表示されたら Enter を押す
//   5. .auth/cf-access.json が更新される

import { chromium } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import * as readline from 'readline'

const STAGING_URL = process.env.STAGING_URL ?? 'https://staging.ultra-auto-trade.com'
const AUTH_PATH = path.join(process.cwd(), 'e2e', '.auth', 'cf-access.json')

async function main() {
  console.log('[CF Access Refresh] ブラウザを起動して CF Access 認証を行います...')
  console.log(`[CF Access Refresh] Target: ${STAGING_URL}`)

  const browser = await chromium.launch({ headless: false })
  const context = await browser.newContext()
  const page = await context.newPage()

  await page.goto(STAGING_URL)

  console.log('\n[CF Access Refresh] CF Access OTP 認証を完了してください:')
  console.log('  1. hkobayashi@mooores.com にコードを送信')
  console.log('  2. 届いたコードを入力して認証')
  console.log('  3. staging サイトが表示されたら Enter を押す\n')

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout })
  await new Promise<void>((resolve) => {
    rl.question('staging サイトが表示されたら Enter を押してください...', () => {
      rl.close()
      resolve()
    })
  })

  // Cookie を保存
  const storageState = await context.storageState()
  const dir = path.dirname(AUTH_PATH)
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(AUTH_PATH, JSON.stringify(storageState, null, 2))

  const cfCookie = storageState.cookies.find((c) => c.name === 'CF_Authorization')
  if (cfCookie) {
    console.log(`\n[CF Access Refresh] ✅ CF_Authorization cookie を保存しました`)
    console.log(`[CF Access Refresh] 保存先: ${AUTH_PATH}`)
  } else {
    console.warn('\n[CF Access Refresh] ⚠️  CF_Authorization cookie が見つかりません。認証が完了しているか確認してください。')
  }

  await browser.close()
}

main().catch((e) => {
  console.error('[CF Access Refresh] エラー:', e)
  process.exit(1)
})
