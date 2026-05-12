// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// /partner/dashboard 手数料体系セクションの tier 別表示検証 (P0 hotfix 2026-05-12)
//
// 背景:
//   2026-05-12 production の test-partner-001 (tier=LOWER) で
//   - 2 枚目の MIDDLE カードが「一般」と誤表示
//   - UPPER カードが常時オレンジ枠ハイライト (ユーザー tier 無関係)
//   - 「あなたのティア」インジケータが存在しない
//   の 3 連バグが発覚。frontend hotfix 適用後の回帰検証。
//
// 検証方針:
//   /auth/me を 3 通り (LOWER / MIDDLE / UPPER) で mock し、
//   - fee-card-{TIER} に data-current="true" が立つこと
//   - 他 2 枚は data-current="false" であること
//   - tier-badge-{TIER} のテキストが TIER_LABELS と一致すること
//   - 「あなたのティア」ラベルが該当カードにだけ出ること
//
// 実行:
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/partner-dashboard-tier.spec.ts
//
// 認証: DB に依存しない (全 API mock)。E2E_PARTNER_EMAIL/PASSWORD 不要。

import { test, expect, Page } from '@playwright/test'

const FEE_SCHEDULE = {
  schedule: [
    {
      tier: 'LOWER',
      label: '一般',
      min_rate: '0.03',
      max_rate: '0.10',
      min_rate_pct: '3',
      max_rate_pct: '10',
      description: 'デポジット 100 万円以下のティア',
    },
    {
      tier: 'MIDDLE',
      label: 'ミドル',
      min_rate: '0.08',
      max_rate: '0.18',
      min_rate_pct: '8',
      max_rate_pct: '18',
      description: 'デポジット 100 万〜1000 万円のティア',
    },
    {
      tier: 'UPPER',
      label: 'アッパー',
      min_rate: '0.15',
      max_rate: '0.25',
      min_rate_pct: '15',
      max_rate_pct: '25',
      description: 'デポジット 1000 万円以上のティア',
    },
  ],
  note: '手数料率は実利益に対して適用されます',
}

async function setupAuth(page: Page, tier: string): Promise<void> {
  await page.addInitScript(
    (args) => {
      localStorage.setItem(args.tokenKey, args.token)
      localStorage.setItem(args.expiresKey, String(args.expires))
    },
    {
      tokenKey: 'ultra_auth_token',
      token: 'mock-tier-display-token',
      expiresKey: 'ultra_auth_expires',
      expires: Date.now() + 24 * 60 * 60 * 1000,
    },
  )

  await page.route('**/auth/me', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue()
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 16,
        email: 'test-partner-tier@ultra-autotrade.com',
        username: 'test-partner-tier',
        role: 'partner',
        is_active: true,
        created_at: '2026-01-01T00:00:00+00:00',
        updated_at: '2026-01-01T00:00:00+00:00',
        tier,
        risk_mode: 'conservative',
        risk_mode_label: 'ローリスク',
      }),
    })
  })

  // /partner/dashboard をレンダリングするのに最低限必要な API を mock
  const mocks: Array<[string, unknown]> = [
    ['**/users/fee-schedule', FEE_SCHEDULE],
    [
      '**/api/partner/stats',
      {
        total_aum: 0,
        yesterday_aum: 0,
        month_return_pct: 0,
        yesterday_return_pct: 0,
        user_count: 0,
      },
    ],
    ['**/api/partner/monthly', []],
    ['**/api/partner/allocations', []],
    [
      '**/api/partner/performance',
      {
        total_allocated_usd: 0,
        total_supply_usd: 0,
        health_factor: null,
        testers: [],
      },
    ],
    [
      '**/ai/accuracy',
      {
        total_decisions: 0,
        correct_count: 0,
        accuracy_pct: 0,
        last_30d_accuracy_pct: 0,
      },
    ],
    ['**/users', { items: [] }],
  ]
  for (const [pattern, body] of mocks) {
    await page.route(pattern, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(body),
        })
      } else {
        await route.continue()
      }
    })
  }
}

const TIER_LABELS: Record<string, string> = {
  LOWER: '一般',
  MIDDLE: 'ミドル',
  UPPER: 'アッパー',
  GENERAL: '一般',
}

async function assertTierHighlight(
  page: Page,
  currentTier: 'LOWER' | 'MIDDLE' | 'UPPER',
): Promise<void> {
  // 手数料体系セクション全体が描画されるまで待つ
  await expect(page.getByText('手数料体系', { exact: true })).toBeVisible({
    timeout: 15_000,
  })

  // 3 枚のカードが全て描画される (LOWER / MIDDLE / UPPER)
  for (const tier of ['LOWER', 'MIDDLE', 'UPPER'] as const) {
    await expect(page.getByTestId(`fee-card-${tier}`)).toBeVisible({
      timeout: 10_000,
    })
  }

  // 各 tier の badge ラベルが TIER_LABELS と一致
  // (MIDDLE が「一般」と表示される旧バグの回帰防止)
  for (const tier of ['LOWER', 'MIDDLE', 'UPPER'] as const) {
    const badge = page.getByTestId(`fee-card-${tier}`).getByTestId(`tier-badge-${tier}`)
    await expect(badge).toHaveText(TIER_LABELS[tier])
  }

  // 現在ユーザーの tier のカードだけ data-current="true"
  // (UPPER 固定ハイライト旧バグの回帰防止)
  for (const tier of ['LOWER', 'MIDDLE', 'UPPER'] as const) {
    const card = page.getByTestId(`fee-card-${tier}`)
    const expected = tier === currentTier ? 'true' : 'false'
    await expect(card).toHaveAttribute('data-current', expected)
  }

  // 「あなたのティア」ラベルは currentTier のカードに 1 つだけ
  const currentLabel = page
    .getByTestId(`fee-card-${currentTier}`)
    .getByTestId('current-tier-label')
  await expect(currentLabel).toBeVisible()
  await expect(currentLabel).toHaveText('あなたのティア')

  // 他 2 枚にラベルが付いていないこと
  const otherTiers = (['LOWER', 'MIDDLE', 'UPPER'] as const).filter(
    (t) => t !== currentTier,
  )
  for (const tier of otherTiers) {
    await expect(
      page.getByTestId(`fee-card-${tier}`).getByTestId('current-tier-label'),
    ).toHaveCount(0)
  }
}

test.describe('Tier 表示バグ hotfix (P0 2026-05-12)', () => {
  test('tier=LOWER ユーザー → LOWER カードがハイライトされる + 3 枚全て正しいラベル', async ({
    page,
  }) => {
    await setupAuth(page, 'LOWER')
    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    await assertTierHighlight(page, 'LOWER')
  })

  test('tier=MIDDLE ユーザー → MIDDLE カードがハイライトされる + バッジが「ミドル」', async ({
    page,
  }) => {
    await setupAuth(page, 'MIDDLE')
    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    await assertTierHighlight(page, 'MIDDLE')
  })

  test('tier=UPPER ユーザー → UPPER カードがハイライトされる + バッジが「アッパー」', async ({
    page,
  }) => {
    await setupAuth(page, 'UPPER')
    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    await assertTierHighlight(page, 'UPPER')
  })

  test('tier=GENERAL (v9 互換) ユーザー → LOWER カードがハイライトされる', async ({
    page,
  }) => {
    await setupAuth(page, 'GENERAL')
    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    // GENERAL は LOWER 同義として扱う
    await assertTierHighlight(page, 'LOWER')
  })
})
