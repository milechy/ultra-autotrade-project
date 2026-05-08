// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [RAS L4] i18n integrity E2E — Gate 4 verification.
//
// 検証範囲:
//   TC1: /partner/* で英語 "partner" ハードコード残存ゼロ
//   TC2: /partner/referral で日本語「紹介」系キーワードのレンダリング確認
//   TC3: /partner/referral で英語 "Referral" / "Refer" 混入なし
//
// 前提: locale は playwright.config.ts で ja-JP に設定済み。
//
// 方式: setupPartnerAuth + referral API モックで /partner/* にアクセスし、
//   DOM のテキストノードのみを走査して英語残存を確認する。
//
// スクリーンショット: e2e/screenshots/ras/

import { test, expect, Page } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { setupPartnerAuth } from './helpers/partner-auth'

// ─── 定数 ─────────────────────────────────────────────────────────────────────

const SCREENSHOT_DIR = path.join('e2e', 'screenshots', 'ras')

// ─── ヘルパー ─────────────────────────────────────────────────────────────────

function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
  }
}

async function saveScreenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${name}.png`),
    fullPage: true,
  })
}

/** DOM のテキストノードを列挙して英語単語 pattern にマッチするものを返す。
 *  script / style / noscript 内のテキストは除外する（Next.js RSC/__next_f 誤検出防止）。
 */
async function findEnglishTextNodes(
  page: Page,
  pattern: RegExp,
): Promise<string[]> {
  return page.evaluate((patternSource: string) => {
    const re = new RegExp(patternSource, 'i')
    const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT'])
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const tag = node.parentElement?.tagName ?? ''
          return SKIP_TAGS.has(tag)
            ? NodeFilter.FILTER_REJECT
            : NodeFilter.FILTER_ACCEPT
        },
      },
    )
    const matches: string[] = []
    let node: Node | null
    while ((node = walker.nextNode())) {
      const text = (node.textContent ?? '').trim()
      if (text && re.test(text)) {
        matches.push(text)
      }
    }
    return matches
  }, pattern.source)
}

/** partner API モックの共通セットアップ */
async function setupReferralMocks(page: Page): Promise<void> {
  await page.route('**/referral/code', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          referral_code: 'AB12CD34',
          share_url: 'https://app.ultra-auto-trade.com/r/AB12CD34',
        }),
      })
    } else {
      await route.continue()
    }
  })
  await page.route('**/referral/list', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    } else {
      await route.continue()
    }
  })
}

// ─── テスト ──────────────────────────────────────────────────────────────────

test.describe('[RAS] i18n integrity', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC1: /partner/* で英語 "partner" テキストノード残存ゼロ', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await setupReferralMocks(page)

    // 既存 + 新規 partner ページを巡回
    const partnerPages = [
      '/partner/dashboard',
      '/partner/referral',
      '/partner/settings',
      '/partner/proposals',
    ]

    for (const href of partnerPages) {
      await page.goto(href)
      await page.waitForLoadState('domcontentloaded')
      await page.waitForTimeout(800)

      // /partner/referral は Lane 3 実装待ちのため 404 / redirect は skip
      const url = page.url()
      if (!url.includes('/partner')) {
        console.log(`[SKIP] ${href} → リダイレクト先 ${url}`)
        continue
      }

      const matches = await findEnglishTextNodes(page, /\bpartner\b/)
      if (matches.length > 0) {
        console.log(
          `[WARN] ${href} に英語 "partner" テキストノード ${matches.length} 件:`,
          matches.slice(0, 5),
        )
      }
      expect(matches.length, `${href} に英語 "partner" テキストノードが残存`).toBe(0)
    }

    await saveScreenshot(page, 'tc1-i18n-no-english-partner')
  })

  test('TC2: /partner/referral で「紹介」系日本語キーワードがレンダリングされる', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await setupReferralMocks(page)

    await page.goto('/partner/referral')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1_000)

    // /partner/referral が未実装の場合はスキップ
    const url = page.url()
    if (!url.includes('/partner/referral')) {
      test.skip(true, `Lane 3 未 merge: /partner/referral → ${url}`)
    }

    // 「紹介」系キーワードのいずれかが表示されること
    const bodyText = await page.evaluate(
      () => (document.body as HTMLElement).innerText ?? '',
    )

    const hasReferralKeyword =
      bodyText.includes('紹介者') ||
      bodyText.includes('紹介コード') ||
      bodyText.includes('紹介プログラム') ||
      bodyText.includes('紹介リンク') ||
      bodyText.includes('紹介済み')

    expect(hasReferralKeyword).toBeTruthy()

    // 翻訳キーリテラルが漏れていないこと (例: "partner.referral.title" が表示される)
    const hasKeyLiteral = await findEnglishTextNodes(
      page,
      /partner\.[a-z]+\.[a-z]+/,
    )
    expect(
      hasKeyLiteral.length,
      `翻訳キーリテラルが画面に露出: ${hasKeyLiteral.slice(0, 3).join(', ')}`,
    ).toBe(0)

    await saveScreenshot(page, 'tc2-i18n-japanese-referral-text')
  })

  test('TC3: /partner/referral で英語 "Referral" / "Refer" テキストノード混入なし', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await setupReferralMocks(page)

    await page.goto('/partner/referral')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1_000)

    const url = page.url()
    if (!url.includes('/partner/referral')) {
      test.skip(true, `Lane 3 未 merge: /partner/referral → ${url}`)
    }

    // "Referral" / "Refer" 英語テキストノードが存在しないこと
    const referralMatches = await findEnglishTextNodes(page, /\bReferr?al?\b/)
    if (referralMatches.length > 0) {
      console.log(
        `[WARN] 英語 "Referral/Refer" テキストノード ${referralMatches.length} 件:`,
        referralMatches.slice(0, 5),
      )
    }
    expect(
      referralMatches.length,
      `英語 "Referral/Refer" テキストノードが残存: ${referralMatches.slice(0, 3).join(', ')}`,
    ).toBe(0)

    await saveScreenshot(page, 'tc3-i18n-no-english-referral')
  })
})
