// Copyright (c) Ultra AutoTrade. All rights reserved.
/**
 * E2E tests for the unified AI judgment / proposal / wallet balance box on /liff-chat.
 * (Asana 1216284377506806: AI判定+提案+ウォレット残高の統合ボックス)
 *
 * 検証対象:
 *  1. 保留中の提案が無い(HOLD)場合は従来の汎用 AI 判定ボックスを表示する
 *  2. 保留中の提案がある場合、汎用 AI 判定ボックスは非表示化され、統合ボックスに
 *     銘柄・金額・確信度(直近AI判定由来の注記付き)・理由・ウォレット残高・承認/見送るボタンが集約される
 *  3. 入金待ち(awaiting_funds)状態では必要額/現在残高/不足額+SBI VC送金案内+入金ボタンが
 *     ボックス内にインライン表示される(別パネルへの画面遷移が前提でないこと)
 *
 * NOTE:
 *  - /api/* は page.route() でモックするため、実バックエンド・実ウォレット接続は不要。
 *  - Privy ウォレット未接続のためウォレット残高(useUsdcBalance)は常に null（"—"表示）。
 *    残高不足プレ承認状態(オンチェーン残高が必要額を下回るケース)はウォレット接続のモックが
 *    別途必要なためこのファイルではカバーしない(手動 / staging-v4 実機確認で担保)。
 */

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const AUTH_TOKEN = 'e2e-unified-card-token'

interface ChatProposalMock {
  id: number
  operation: string
  asset: string
  amount: string
  amount_usd: string
  reason: string
  protocol?: string
  expected_hf_after: string | null
  estimated_gas_usd: string | null
  status: string
  created_at: string
}

async function mockLiffChatApis(
  page: Page,
  opts: {
    aiJudgment?: { action: string; confidence: number; reason?: string } | null
    proposals?: ChatProposalMock[]
  },
) {
  // terms_version は (liff)/layout.tsx の useLiffTermsGate が同意状態判定に使う。
  // 省略すると "not-accepted" 扱いで /liff-confirm へリダイレクトされ children が描画されない。
  await page.route('**/api/user/settings', (route) =>
    route.fulfill({ json: { is_active: true, terms_version: 'liff-v4' } }),
  )
  await page.route('**/api/portfolio/current', (route) =>
    route.fulfill({
      json: { positions_json: [], has_data: false, total_value_usd: '0', weighted_avg_apy: '0' },
    }),
  )
  await page.route('**/api/user/dividends', (route) =>
    route.fulfill({ json: { dividends: [] } }),
  )
  await page.route('**/api/ai/decisions**', (route) =>
    route.fulfill({ json: { items: opts.aiJudgment ? [opts.aiJudgment] : [] } }),
  )
  await page.route('**/api/proposals/pending', (route) =>
    route.fulfill({ json: { items: opts.proposals ?? [] } }),
  )
}

test.describe('[LIFF Chat] AI判定+提案+ウォレット残高の統合ボックス', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((token) => {
      window.localStorage.setItem('auth_token', token)
    }, AUTH_TOKEN)
  })

  test('保留中の提案が無い(HOLD)場合は従来のAI判定ボックスを表示する', async ({ page }) => {
    await mockLiffChatApis(page, {
      aiJudgment: { action: 'HOLD', confidence: 42, reason: 'レンジ相場のため様子見' },
      proposals: [],
    })
    await page.goto('/liff-chat', { waitUntil: 'domcontentloaded' })

    await expect(page.getByText('AI JUDGMENT')).toBeVisible()
    // 「なぜHOLD？」ボタンも部分一致するため exact: true で行動表示自体に絞る
    await expect(page.getByText('HOLD', { exact: true })).toBeVisible()
  })

  test('保留中の提案(残高十分)は統合ボックスに銘柄・金額・確信度・残高・承認/見送るを表示する', async ({
    page,
  }) => {
    await mockLiffChatApis(page, {
      aiJudgment: { action: 'BUY', confidence: 78, reason: 'Aave 金利上昇' },
      proposals: [
        {
          id: 1,
          operation: 'SUPPLY',
          asset: 'USDC',
          amount: '1000',
          amount_usd: '1000',
          reason: 'テスト用の提案理由',
          protocol: 'aave',
          expected_hf_after: null,
          estimated_gas_usd: null,
          status: 'pending',
          created_at: '2026-07-06T00:00:00Z',
        },
      ],
    })
    await page.goto('/liff-chat', { waitUntil: 'domcontentloaded' })

    // 汎用 AI 判定ボックス(銘柄・金額なし)は統合ボックスに置き換わり非表示化される
    await expect(page.getByText('AI JUDGMENT')).not.toBeVisible()

    await expect(page.getByText('入金 (Supply)')).toBeVisible()
    await expect(page.getByText('テスト用の提案理由')).toBeVisible()
    await expect(page.getByText('信頼度')).toBeVisible()
    await expect(page.getByText('直近のAI判定').first()).toBeVisible()
    await expect(page.getByText('ウォレット残高')).toBeVisible()
    await expect(page.getByRole('button', { name: '承認する' })).toBeVisible()
    await expect(page.getByRole('button', { name: '見送る' })).toBeVisible()
  })

  test('入金待ち(awaiting_funds)は必要額/残高/不足額+入金導線をボックス内にインライン表示する', async ({
    page,
  }) => {
    await mockLiffChatApis(page, {
      aiJudgment: { action: 'BUY', confidence: 80 },
      proposals: [
        {
          id: 2,
          operation: 'SUPPLY',
          asset: 'USDC',
          amount: '1000',
          amount_usd: '1000',
          reason: 'テスト理由2',
          protocol: 'aave',
          expected_hf_after: null,
          estimated_gas_usd: null,
          status: 'awaiting_funds',
          created_at: '2026-07-06T00:00:00Z',
        },
      ],
    })
    await page.goto('/liff-chat', { waitUntil: 'domcontentloaded' })

    await expect(page.getByText('入金待ち')).toBeVisible()
    await expect(page.getByText('必要額')).toBeVisible()
    await expect(page.getByText('不足額')).toBeVisible()
    // Liff.awaitingFunds.guide の SBI VC 送金案内文がボックス内にインラインで出る
    await expect(page.getByText('SBI VCトレード', { exact: false })).toBeVisible()
    await expect(page.getByRole('button', { name: '入金する' })).toBeVisible()
    await expect(page.getByRole('button', { name: '見送る' })).toBeVisible()
  })
})
