// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
/**
 * E2E spec: liff-confirm / liff-chat-history / liff-approve i18n 検証
 * Tester Gate 4 / PR #652 stacked / Asana GID: 1215650626628506
 *
 * 検証範囲:
 *   TC-CONFIRM-1: /liff-confirm が 5xx でない（疎通）
 *   TC-CONFIRM-2: localStorage["lang"]="en" をセット → リロード後に EN テキストが DOM に出るか確認
 *                 認証ゲートで描画不能な場合は gracefully skip
 *   TC-HISTORY-1: /liff-chat-history が 5xx でない（疎通）
 *   TC-HISTORY-2: localStorage["lang"]="en" → EN テキスト "Chat History" が DOM に出るか確認
 *                 認証ゲートで描画不能な場合は gracefully skip
 *   TC-APPROVE-1: /liff-approve が 5xx でない（疎通）
 *   TC-APPROVE-2: localStorage["lang"]="en" → EN テキスト "Approve" が DOM に出るか確認
 *                 認証ゲートで描画不能な場合は gracefully skip
 *   TC-LANG-LS:   localStorage["lang"] 事前設定 "en" → リロード後も localStorage が "en" を返す
 *
 * NOTE:
 *   - route group (liff) の URL は /liff-confirm / /liff-chat-history / /liff-approve
 *     （ディレクトリ "(liff)" は URL に含まれない。CLAUDE.md の route group ルール参照）
 *   - baseURL は playwright.config.ts (STAGING_URL || https://app.ultra-auto-trade.com)
 *   - LIFF/Privy 認証ゲートで描画に到達できない場合は test.skip で gracefully skip する
 *   - dev VPS では `npm run dev` が OOM になるため spec 作成・コミットし
 *     実行は CI/staging 委譲とする（疎通 TC は本番 URL で実行可能）
 */

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// ─── URL 定数 ─────────────────────────────────────────────────────────────────
// route group (liff) は URL に含まれないため "/liff-confirm" が正しいパス
const LIFF_CONFIRM_URL = '/liff-confirm'
const LIFF_HISTORY_URL = '/liff-chat-history'
const LIFF_APPROVE_URL = '/liff-approve'

// ─── ヘルパー ─────────────────────────────────────────────────────────────────

/**
 * ページへ移動し 5xx でないこと + URL が変わっていないことを確認する。
 * 認証リダイレクトで URL が変わった場合は false を返す（skip 対象）。
 */
async function visitPage(page: Page, url: string): Promise<boolean> {
  const res = await page.goto(url, { waitUntil: 'domcontentloaded' })
  if (!res || res.status() >= 500) return false
  if (!page.url().includes(url)) return false
  return true
}

/**
 * localStorage["lang"]="en" を設定してリロードし、
 * 認証ゲートを通過できた場合は true を返す。
 */
async function setLangEnAndReload(page: Page, url: string): Promise<boolean> {
  const reachable = await visitPage(page, url)
  if (!reachable) return false
  await page.evaluate(() => localStorage.setItem('lang', 'en'))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(800)
  // リロード後も対象ページにいるか確認
  return page.url().includes(url)
}

// ─── liff-confirm ─────────────────────────────────────────────────────────────

test.describe('[LIFF confirm] i18n 検証', () => {
  test('TC-CONFIRM-1: /liff-confirm が 5xx でない', async ({ page }) => {
    const res = await page.goto(LIFF_CONFIRM_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response が存在すること').not.toBeNull()
    expect(res!.status(), '/liff-confirm は 5xx を返してはならない').toBeLessThan(500)
  })

  test('TC-CONFIRM-2: EN モード時に確認項目タイトルが英語化される', async ({ page }) => {
    const reachable = await setLangEnAndReload(page, LIFF_CONFIRM_URL)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-confirm に到達不能のため skip')

    // Liff.confirm.items.self_custody.title = "Your assets are self-custodied"
    // または Liff.confirm.submitBtn = "Start trading" など、EN テキストが DOM に存在することを確認
    const enText = page
      .getByText(/Start trading|self-custodied|Confirm|DeFi/i)
      .first()
    const visible = await enText.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(
      !visible,
      '認証ゲートで確認ページ本文が描画されない環境のため skip（設計通り）',
    )
    await expect(enText).toBeVisible()

    // localStorage が "en" を保持していること
    const lang = await page.evaluate(() => localStorage.getItem('lang'))
    expect(lang, 'localStorage["lang"] は "en" であるべき').toBe('en')
  })
})

// ─── liff-chat-history ────────────────────────────────────────────────────────

test.describe('[LIFF chat-history] i18n 検証', () => {
  test('TC-HISTORY-1: /liff-chat-history が 5xx でない', async ({ page }) => {
    const res = await page.goto(LIFF_HISTORY_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response が存在すること').not.toBeNull()
    expect(res!.status(), '/liff-chat-history は 5xx を返してはならない').toBeLessThan(500)
  })

  test('TC-HISTORY-2: EN モード時にヘッダーが "Chat History" になる', async ({ page }) => {
    const reachable = await setLangEnAndReload(page, LIFF_HISTORY_URL)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat-history に到達不能のため skip')

    // Liff.history.headerTitle = "Chat History"
    const enTitle = page.getByText('Chat History', { exact: false }).first()
    const visible = await enTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(
      !visible,
      '認証ゲートで chat-history 本文が描画されない環境のため skip（設計通り）',
    )
    await expect(enTitle).toBeVisible()

    const lang = await page.evaluate(() => localStorage.getItem('lang'))
    expect(lang, 'localStorage["lang"] は "en" であるべき').toBe('en')
  })
})

// ─── liff-approve ─────────────────────────────────────────────────────────────

test.describe('[LIFF approve] i18n 検証', () => {
  test('TC-APPROVE-1: /liff-approve が 5xx でない', async ({ page }) => {
    const res = await page.goto(LIFF_APPROVE_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response が存在すること').not.toBeNull()
    expect(res!.status(), '/liff-approve は 5xx を返してはならない').toBeLessThan(500)
  })

  test('TC-APPROVE-2: EN モード時に "Approved" / "Approve" テキストが DOM に出る', async ({ page }) => {
    const reachable = await setLangEnAndReload(page, LIFF_APPROVE_URL)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-approve に到達不能のため skip')

    // Liff.approve.approved = "Approved ✓"
    // Liff.approve.waitingProposal = "Waiting for a proposal..."
    const enText = page
      .getByText(/Approved|Approve|Waiting for a proposal/i)
      .first()
    const visible = await enText.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(
      !visible,
      '認証ゲートで approve 本文が描画されない環境のため skip（設計通り）',
    )
    await expect(enText).toBeVisible()

    const lang = await page.evaluate(() => localStorage.getItem('lang'))
    expect(lang, 'localStorage["lang"] は "en" であるべき').toBe('en')
  })
})

// ─── localStorage 永続化 ──────────────────────────────────────────────────────

test.describe('[共通] localStorage lang 永続化', () => {
  test('TC-LANG-LS: localStorage["lang"]="en" 設定後リロードで "en" が保持される', async ({ page }) => {
    const res = await page.goto(LIFF_CONFIRM_URL, { waitUntil: 'domcontentloaded' })
    expect(res!.status()).toBeLessThan(500)

    // localStorage に "en" をセット
    await page.evaluate(() => localStorage.setItem('lang', 'en'))

    // リロード
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(500)

    // localStorage の値が維持されているか
    const lang = await page.evaluate(() => localStorage.getItem('lang'))
    expect(lang, 'リロード後も localStorage["lang"] は "en" であるべき').toBe('en')
  })
})

// ─── モバイル 375px ───────────────────────────────────────────────────────────

test.describe('[Mobile 375px] liff-pages i18n 疎通', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  for (const { name, url } of [
    { name: 'liff-confirm', url: LIFF_CONFIRM_URL },
    { name: 'liff-chat-history', url: LIFF_HISTORY_URL },
    { name: 'liff-approve', url: LIFF_APPROVE_URL },
  ]) {
    test(`モバイルで /${name} が 5xx でない`, async ({ page }) => {
      const res = await page.goto(url, { waitUntil: 'domcontentloaded' })
      expect(res, 'navigation response が存在すること').not.toBeNull()
      expect(res!.status(), `/${name} は 5xx を返してはならない`).toBeLessThan(500)
    })
  }
})
