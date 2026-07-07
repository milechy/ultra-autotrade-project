// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// e2e/duplicate-url-redirects.spec.ts
//
// Gate 4 E2E: 重複ページ (route group `(user)/` vs plain `user/`) の
// orphan URL → live URL リダイレクト回帰ガード (Asana 1216340622157717, Tier B)
//
// 背景:
//   Next.js App Router で `(user)/decisions`, `(user)/grid`,
//   `(user)/copy-trading` (route group につき URL は `/decisions` `/grid`
//   `/copy-trading`) が、実装が並行して重複した `user/decisions` `user/grid`
//   `user/copy-trading` (URL は `/user/decisions` `/user/grid`
//   `/user/copy-trading`) の orphan (どこからもリンクされていない) になって
//   いた。ナビ導線の実証:
//     - frontend/app/user/dashboard/_components/LatestDecision.tsx
//       → href="/user/decisions"
//     - frontend/components/user/UserHeader.tsx adminNavItems
//       → href="/user/grid", href="/user/copy-trading"
//   一方 `/decisions` `/grid` `/copy-trading` (route group 側) を指す
//   リンクはアプリ内に存在しない。削除はせず (URL 削除ポリシー: redirect
//   優先、page ファイルは消さない)、orphan page.tsx を
//   `router.replace(liveUrl)` するリダイレクトスタブに置き換えた。
//   本 spec は実ブラウザでその配線を確認する。
//
//   NOTE: /user/grid, /user/copy-trading は AuthGuard (adminOnly) 配下のため、
//   未認証環境では live URL 到達後にさらに /login?redirect=... へ連鎖する。
//   本 spec はフル Privy ログインに依存せず、「orphan URL → live URL (またはその
//   先の /login へのリダイレクトチェーン) に到達すること」を到達可否ベースで
//   検証する (e2e/gate4-privacy-link-404.spec.ts 等と同じ skip 許容パターン)。
//   /user/decisions は AuthGuard 無し (未認証時は 401 → /login に飛ぶのみ)。

import { test, expect } from '@playwright/test'

interface RedirectCase {
  name: string
  orphanUrl: string
  liveUrl: string
}

const CASES: RedirectCase[] = [
  { name: 'decisions', orphanUrl: '/decisions', liveUrl: '/user/decisions' },
  { name: 'grid', orphanUrl: '/grid', liveUrl: '/user/grid' },
  { name: 'copy-trading', orphanUrl: '/copy-trading', liveUrl: '/user/copy-trading' },
]

test.describe('Gate4 | duplicate URL cleanup — orphan → live redirects', () => {
  for (const { name, orphanUrl, liveUrl } of CASES) {
    test(`TC-${name}: ${orphanUrl} は ${liveUrl} (または認証ゲート先) へ redirect する`, async ({ page }) => {
      const res = await page.goto(orphanUrl, { waitUntil: 'domcontentloaded' })
      expect(res, 'navigation response should exist').not.toBeNull()
      expect(res!.status(), `${orphanUrl} は 404/5xx であってはならない`).toBeLessThan(400)

      // client-side router.replace() が発火し終わるまで待つ。
      // 認証ゲート付きの live URL は /login?redirect=... へさらに連鎖しうるため、
      // "orphan の URL から離脱した" ことを到達可否の一次条件にする。
      await page
        .waitForURL((url) => !url.pathname.startsWith(orphanUrl), { timeout: 10000 })
        .catch(() => {})

      const finalUrl = new URL(page.url())
      const reachedLive = finalUrl.pathname === liveUrl
      const bouncedToLogin =
        finalUrl.pathname === '/login' &&
        (finalUrl.searchParams.get('redirect') === liveUrl || finalUrl.search === '')

      expect(
        reachedLive || bouncedToLogin,
        `${orphanUrl} は ${liveUrl} 、または未認証時はその先の /login に到達すべき。` +
          `実際の到達先: ${finalUrl.pathname}${finalUrl.search}`
      ).toBe(true)

      // orphan URL 自体には留まっていないこと (redirect が発火した証拠)。
      expect(finalUrl.pathname, `${orphanUrl} からリダイレクトされていない`).not.toBe(orphanUrl)
    })
  }
})
