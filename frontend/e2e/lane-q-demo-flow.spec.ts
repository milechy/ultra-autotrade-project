// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Lane Q — デモ通し E2E spec (6/1 デモ運用向け)
//
// 対象導線:
//   1. Privy ログイン画面表示          (Lane H / PR #423 — `/user/wallet`)
//   2. Manual UI (display-only) 表示   (Lane K / PR #392 — `/user/approve`)
//   3. AI 提案閲覧 + RAG 根拠展開      (Lane K / PR #392 — ProposalCard)
//   4. ToS active consent submit       (Lane J / PR #425 — DemoConsentModal)
//
// 設計方針:
//   - 本 spec は PR #423 / #392 / #425 の merge 前に先行作成される。
//     対象画面が未 deploy の staging で実走すると 404 / selector miss で fail するため、
//     各 test は「対象 selector が存在しなければ skip + 理由出力」で構成する。
//   - 実走 (Gate 4) は 4 PR merge + staging deploy 完了後の別タスクで行う想定。
//   - baseURL は playwright.config.ts の `STAGING_URL || https://app.ultra-auto-trade.com`。
//
// 関連:
//   - 既存パターン: e2e/yamamoto-partner-flow.spec.ts (proposals mock)
//   - 既存パターン: e2e/helpers/partner-auth.ts (JWT inject + /auth/me mock)
//   - 既存パターン: e2e/itp-wipe-reauth.spec.ts (Lane I — addInitScript で seed)

import { test, expect, type Page, type Route } from '@playwright/test'
import { setupPartnerAuth, PARTNER_MOCK_USER } from './helpers/partner-auth'

// ─── Fixtures ──────────────────────────────────────────────────────────────

const MOCK_PROPOSAL = {
  id: 9001,
  user_id: PARTNER_MOCK_USER.id,
  operation: 'SUPPLY',
  asset: 'USDC',
  amount: '100.000000',
  amount_usd: '100.00',
  reason: 'AI判定: 市場ボラ低下 + Aave 利回り上昇。SUPPLY で利回り獲得を提案。',
  expected_hf_after: '2.85',
  estimated_gas_usd: '0.12',
  status: 'pending',
  tx_hash: null,
  expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
  created_at: new Date().toISOString(),
  rag_context_json: {
    market_signal: 'low_vol',
    macro_signal: 'risk_on',
    sources: ['gdelt:2026-05-26', 'aave:supply_apy_3.4'],
  },
}

/** /api/proposals/pending と /api/proposals/history を mock する。 */
async function mockProposalsAPI(
  page: Page,
  opts: { pending: unknown[]; history: unknown[] } = { pending: [MOCK_PROPOSAL], history: [] },
): Promise<void> {
  await page.route('**/api/proposals/pending', async (route: Route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: opts.pending, total: opts.pending.length }),
      })
    } else {
      await route.continue()
    }
  })
  await page.route('**/api/proposals/history*', async (route: Route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: opts.history, total: opts.history.length }),
      })
    } else {
      await route.continue()
    }
  })
  // user_actions ログ送信 (manual click) は背景で投げられる best-effort 経路。
  // POST 経路を 201 で受け止め、UI 検証に副作用を残さない。
  await page.route('**/api/users/actions', async (route: Route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, action_type: 'manual_approve_click', created_at: new Date().toISOString() }),
      })
    } else {
      await route.continue()
    }
  })
}

/** ToS consent endpoint を 201 で受ける mock。 */
async function mockToSConsentAPI(page: Page): Promise<void> {
  await page.route('**/api/v1/tos/consent', async (route: Route) => {
    const method = route.request().method()
    if (method === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          tos_version: 'demo-1.0',
          user_id: PARTNER_MOCK_USER.id,
          created_at: new Date().toISOString(),
        }),
      })
    } else if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ consent: null }),
      })
    } else {
      await route.continue()
    }
  })
}

/** 対象セレクタが timeout 内に出現しなければ skip + 理由ログを残す。 */
async function skipIfMissing(
  page: Page,
  testId: string,
  reason: string,
  timeoutMs = 5000,
): Promise<boolean> {
  const locator = page.getByTestId(testId)
  try {
    await locator.first().waitFor({ state: 'visible', timeout: timeoutMs })
    return true
  } catch {
    test.skip(true, `${reason} (data-testid="${testId}" not visible within ${timeoutMs}ms)`)
    return false
  }
}

// ─── Tests ─────────────────────────────────────────────────────────────────

test.describe('Lane Q: デモ通し E2E (Privy → Manual UI → AI提案閲覧 → ToS consent)', () => {
  test.beforeEach(async ({ page }) => {
    // すべての test で partner JWT + /auth/me mock を共通で注入する。
    await setupPartnerAuth(page)
  })

  // ── Step 1: Privy ログイン画面 (Lane H / PR #423) ────────────────────────
  test('Step 1: /user/wallet で Privy 埋込ウォレットカードが表示される', async ({ page }) => {
    await page.goto('/user/wallet', { waitUntil: 'domcontentloaded' })

    // 4xx / 5xx で descriptor が返ったら fail させたいので、URL が wallet 配下に留まっていることを確認。
    // 認証失敗で /login へ飛ばされていないことが最低限の合格条件。
    expect(page.url()).not.toContain('/login')

    // Lane H mount チェック: WalletPage は外側に "ウォレット接続" 見出しを持ち、
    // PrivyEmbeddedWalletInfo は CardTitle として「埋込ウォレット」を含むテキストを描画する。
    // staging に Lane H が未 deploy なら見出しは出ない → skip。
    const heading = page.getByRole('heading', { name: 'ウォレット接続' })
    try {
      await heading.waitFor({ state: 'visible', timeout: 5000 })
    } catch {
      test.skip(true, 'Lane H (#423) 未 merge / 未 deploy: /user/wallet に PrivyEmbeddedWalletInfo が無い')
      return
    }

    // Privy SDK が unconfigured / unauthenticated / ready のいずれの分岐でも
    // CardTitle に「埋込ウォレット」を含むテキストが現れる。state に依らずスモーク確認する。
    const privyCard = page.locator('text=/埋込ウォレット/')
    await expect(privyCard.first()).toBeVisible({ timeout: 5000 })
  })

  // ── Step 2: Manual UI (display-only) 表示 (Lane K / PR #392) ─────────────
  test('Step 2: /user/approve で LegalGate + display-only banner が表示される', async ({ page }) => {
    await mockProposalsAPI(page, { pending: [], history: [] })
    await page.goto('/user/approve', { waitUntil: 'domcontentloaded' })

    expect(page.url()).not.toContain('/login')

    // Lane K の display-only banner。data-testid="display-only-banner"
    const ok = await skipIfMissing(
      page,
      'display-only-banner',
      'Lane K (#392) 未 merge / 未 deploy: /user/approve に display-only banner が無い',
    )
    if (!ok) return

    await expect(page.getByTestId('display-only-banner')).toContainText(/機能説明用|display-only/)

    // LegalGate banner: NEXT_PUBLIC_LEGAL_SIGN_OFF_DONE !== "true" のとき表示される。
    // 法務 sign-off 完了 (launch gate 通過) なら banner が消える設計のため、
    // 「存在すれば content を確認」「無ければ launch gate 通過状態」と扱う。
    const legalGate = page.getByTestId('legal-gate-banner')
    if ((await legalGate.count()) > 0) {
      await expect(legalGate.first()).toContainText(/ノンカストディアル|機能説明用|preview/)
    } else {
      test.info().annotations.push({
        type: 'note',
        description: 'LegalGate banner 不在 — NEXT_PUBLIC_LEGAL_SIGN_OFF_DONE=true (launch gate 通過後)',
      })
    }

    // 詳細トグル: 「全自動の仕組みを見る」を押すと内訳が展開される。
    const toggle = page.getByTestId('display-only-banner-toggle')
    await toggle.click()
    await expect(page.getByText('・スケジューラ (ai_judgment_scheduler) が定期的に AI 判定を実行')).toBeVisible()
  })

  // ── Step 3: AI 提案閲覧 + RAG 根拠展開 (Lane K / PR #392) ────────────────
  test('Step 3: /user/approve で AI 提案カードが表示され RAG 根拠が展開できる', async ({ page }) => {
    await mockProposalsAPI(page, { pending: [MOCK_PROPOSAL], history: [] })
    await page.goto('/user/approve', { waitUntil: 'domcontentloaded' })

    expect(page.url()).not.toContain('/login')

    // approve ボタン (display-only) が proposal カードに出ること = カードが描画されていること
    const ok = await skipIfMissing(
      page,
      'proposal-approve-button',
      'Lane K (#392) 未 merge / 未 deploy: ProposalCard が描画されない',
    )
    if (!ok) return

    // proposal 描画内容を smoke 検証 (mock の値が画面に出ていること)
    await expect(page.getByText('USDC').first()).toBeVisible()
    await expect(page.getByText(/SUPPLY/)).toBeVisible()

    // RAG 根拠トグルが存在すれば展開 → rag_context_json の中身 (sources / market_signal) が描画される
    const ragToggle = page.getByTestId('proposal-rag-toggle')
    if ((await ragToggle.count()) > 0) {
      await ragToggle.first().click()
      await expect(page.getByTestId('proposal-rag-content').first()).toBeVisible()
      // mock データ由来の文字列の少なくとも一部が見えること
      await expect(
        page.locator('[data-testid="proposal-rag-content"]').first(),
      ).toContainText(/market_signal|sources|gdelt|low_vol/)
    } else {
      test.info().annotations.push({
        type: 'note',
        description: 'proposal-rag-toggle 不在 — RAG context 未配線または rag_context_json=null',
      })
    }

    // display-only: approve ボタンを押しても /api/proposals/:id/approve は呼ばれない契約。
    // POST が飛んだら fail させる guard を貼る。
    let realApproveCalled = false
    await page.route('**/api/proposals/*/approve', async (route: Route) => {
      if (route.request().method() === 'POST') {
        realApproveCalled = true
      }
      await route.continue()
    })

    await page.getByTestId('proposal-approve-button').first().click()
    await page.waitForTimeout(500)
    expect(realApproveCalled).toBe(false)
  })

  // ── Step 4: ToS active consent submit (Lane J / PR #425) ─────────────────
  test('Step 4: ToS consent モーダルを全文読了 → checkbox → submit する', async ({ page }) => {
    await mockToSConsentAPI(page)
    await mockProposalsAPI(page, { pending: [], history: [] })

    // DemoConsentModal は現状どのページにも mount されていない (Lane J が component 単独 PR)。
    // mount 先候補:
    //   - /user/approve  (Lane K Manual UI 統合後の onboarding gate)
    //   - /user/onboarding (Lane K onboarding flow)
    //   - /demo (将来の demo entry page)
    // mount 先が確定したら本 spec を更新する。当面は両方を試行して、いずれかに modal が出れば走らせる。
    const candidates = ['/user/approve', '/user/onboarding', '/demo']
    let modalFound = false
    for (const path of candidates) {
      await page.goto(path, { waitUntil: 'domcontentloaded' }).catch(() => undefined)
      if (page.url().includes('/login')) continue
      const scroll = page.getByTestId('tos-scroll-area')
      try {
        await scroll.waitFor({ state: 'visible', timeout: 3000 })
        modalFound = true
        break
      } catch {
        // try next
      }
    }
    if (!modalFound) {
      test.skip(
        true,
        'Lane J (#425) 未 merge / mount 先未確定: DemoConsentModal がどの導線にも出現しない',
      )
      return
    }

    // ── ここから DemoConsentModal の挙動検証 ─────────────────────────────
    const submit = page.getByTestId('consent-submit')
    const demoAck = page.getByTestId('consent-demo-ack')
    const feeAck = page.getByTestId('consent-fee-ack')

    // 初期状態: checkbox は disable / submit も disable
    await expect(demoAck).toBeDisabled()
    await expect(feeAck).toBeDisabled()
    await expect(submit).toBeDisabled()

    // 規約スクロール領域を最下部までスクロール → hasReadAll = true
    await page.getByTestId('tos-scroll-area').evaluate((el: HTMLElement) => {
      el.scrollTop = el.scrollHeight
      el.dispatchEvent(new Event('scroll'))
    })

    // checkbox が有効化されるまで待ち、両方チェック
    await expect(demoAck).toBeEnabled({ timeout: 3000 })
    await expect(feeAck).toBeEnabled({ timeout: 3000 })
    await demoAck.check()
    await feeAck.check()

    // POST /api/v1/tos/consent が飛ぶことを確認
    const consentReq = page.waitForRequest(
      (req) =>
        req.url().includes('/api/v1/tos/consent') && req.method() === 'POST',
      { timeout: 5000 },
    )
    await expect(submit).toBeEnabled()
    await submit.click()
    const req = await consentReq
    const body = JSON.parse(req.postData() ?? '{}')
    expect(body).toMatchObject({
      tos_version: 'demo-1.0',
      is_demo_ack: true,
      fully_read: true,
    })
  })
})
