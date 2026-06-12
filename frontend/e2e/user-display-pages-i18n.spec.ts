// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [Gate 4] user display pages i18n E2E — feat/user-i18n-batch2 検証
//
// 検証範囲:
//   TC1-TC4: 各ページ疎通確認 (5xx でない)
//   TC5-TC8: ja デフォルト (locale=ja-JP) で日本語見出し表示 or 認証ゲート skip
//   TC9: NEXT_LOCALE=en cookie で英語見出し切替確認 (help ページ)
//
// 前提:
//   - locale は playwright.config.ts で ja-JP に設定済み
//   - app/user/ は通常フォルダ (route group なし) → URL は /user/<page>
//   - 認証ゲートにより redirect → / になる場合は設計通り skip し理由明記
//   - 認証ゲートがクライアントサイドレンダリング (CSR) の場合、URL は維持されたまま
//     body が空 / ログインフォームのみになる。両パターンを "auth gate" として扱う。
//
// baseURL: STAGING_URL 環境変数 or https://app.ultra-auto-trade.com

import { test, expect } from '@playwright/test'

// ─── 定数 ─────────────────────────────────────────────────────────────────────

const PAGES = [
  { path: '/user/help', jaTitleText: 'よくある質問' },
  { path: '/user/performance', jaTitleText: 'パフォーマンス' },
  { path: '/user/simulation', jaTitleText: 'シミュレーション' },
  { path: '/user/ai-feed', jaTitleText: 'AI判定フィード' },
] as const

const HELP_EN_TITLE = 'FAQ'
const HELP_JA_TITLE = 'よくある質問'

// ─── TC1-TC4: 疎通確認 (5xx でない) ─────────────────────────────────────────

for (const { path } of PAGES) {
  test(`TC: ${path} — 5xx でない (疎通確認)`, async ({ page }) => {
    const response = await page.goto(path, { waitUntil: 'domcontentloaded' })
    const status = response?.status() ?? 0
    // 200 / 301 / 302 / 307 / 308 (redirect to auth) は全て OK
    // 5xx のみ NG
    expect(status).toBeLessThan(500)
  })
}

// ─── TC5-TC8: ja デフォルトで日本語見出し or 認証ゲート skip ─────────────────

for (const { path, jaTitleText } of PAGES) {
  test(`TC: ${path} — ja デフォルトで日本語見出し or 認証ゲート`, async ({ page }) => {
    await page.goto(path, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(800)

    const finalUrl = page.url()
    const bodyText = await page.evaluate(
      () => (document.body as HTMLElement).innerText ?? '',
    )

    // 認証ゲート判定:
    //   1. URL がリダイレクト (path を含まない) した場合
    //   2. bodyText が空 (CSR ログインゲートが body を隠している場合)
    const redirectGated = !finalUrl.includes(path)
    const emptyBodyGated = bodyText.trim().length === 0

    if (redirectGated || emptyBodyGated) {
      const reason = redirectGated
        ? `URL リダイレクト: ${finalUrl}`
        : `bodyText 空 (CSR 認証ゲート): ${finalUrl}`
      console.log(`[SKIP] ${path} — 認証ゲート検出: ${reason}`)
      test.skip(true, `認証ゲートにより ${path} コンテンツ不可 — ${reason}`)
      return
    }

    // 認証済みで到達できた場合: 日本語見出しが含まれること
    expect(
      bodyText,
      `${path} で日本語見出し "${jaTitleText}" が見つからない`,
    ).toContain(jaTitleText)

    // 翻訳キーリテラルが画面に漏れていないこと (例: "Performance.pageTitle")
    const keyLiteralPattern = /[A-Z][a-zA-Z]+\.[a-z][a-zA-Z]+/
    const hasKeyLiteral = bodyText.split('\n').some((line) =>
      keyLiteralPattern.test(line) &&
      !line.includes('http') &&
      !line.includes('©') &&
      !line.includes('PM') &&
      !line.includes('AM'),
    )
    expect(
      hasKeyLiteral,
      `${path} で翻訳キーリテラルが画面に露出している可能性`,
    ).toBe(false)
  })
}

// ─── TC9: NEXT_LOCALE=en cookie で英語切替 (help ページ) ──────────────────────

test('TC: /user/help — NEXT_LOCALE=en cookie で英語見出し "FAQ" に切替', async ({
  page,
  context,
}) => {
  // NEXT_LOCALE cookie を en にセットしてからアクセス
  const baseURL = process.env.STAGING_URL ?? 'https://app.ultra-auto-trade.com'
  const origin = new URL(baseURL).origin
  const hostname = new URL(baseURL).hostname

  await context.addCookies([
    {
      name: 'NEXT_LOCALE',
      value: 'en',
      domain: hostname,
      path: '/',
    },
  ])

  await page.goto('/user/help', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(800)

  const finalUrl = page.url()
  const bodyText = await page.evaluate(
    () => (document.body as HTMLElement).innerText ?? '',
  )

  const redirectGated = !finalUrl.includes('/user/help')
  const emptyBodyGated = bodyText.trim().length === 0

  if (redirectGated || emptyBodyGated) {
    const reason = redirectGated
      ? `URL リダイレクト: ${finalUrl}`
      : `bodyText 空 (CSR 認証ゲート): ${finalUrl}`
    console.log(`[SKIP] /user/help (en) — 認証ゲート: ${reason}`)
    test.skip(
      true,
      `認証ゲートにより /user/help (en) コンテンツ不可 — ${reason}`,
    )
    return
  }

  // 英語版タイトル "FAQ" が表示されること
  expect(
    bodyText,
    `NEXT_LOCALE=en で /user/help に英語タイトル "${HELP_EN_TITLE}" が見つからない`,
  ).toContain(HELP_EN_TITLE)

  // 日本語タイトル "よくある質問" が混在しないこと
  expect(
    bodyText.includes(HELP_JA_TITLE),
    `NEXT_LOCALE=en にもかかわらず日本語タイトル "${HELP_JA_TITLE}" が残存`,
  ).toBe(false)

  // origin 変数は cookie 設定の確認用 (未使用 lint 対策)
  void origin
})
