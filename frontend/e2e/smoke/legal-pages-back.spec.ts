// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

// 法的文書ページ（利用規約 / プライバシーポリシー / リスク開示）の「戻る」挙動。
//
// 旧実装は遷移先がハードコードされていた（terms・risk → /connect、privacy → '/'）ため、
// /signup など /connect 以外から開くと無関係なウォレット接続画面に飛ばされていた。
// useSmartBack 導入後は「来訪元に戻る」(router.back) が基本で、履歴が無い場合
// （別タブ target="_blank" / ブックマーク）のみ fallback（トップ '/' → 未認証は /login）。
test.describe('法的文書ページの「戻る」挙動 (useSmartBack)', () => {
  // 同一タブ遷移では来訪元に戻る（遷移先ハードコードではない）ことを、
  // 旧挙動と区別できる入口で検証する。
  //   - 旧: /terms 戻る → /connect 固定 / /privacy-policy 戻る → '/' 固定
  //   - 新: いずれも「来訪元」へ
  const cases = [
    { referrer: '/risk-disclosure', open: '/terms' },          // 旧なら /connect に飛んでいた
    { referrer: '/risk-disclosure', open: '/privacy-policy' },  // 旧なら '/'(→/login) に飛んでいた
    { referrer: '/terms', open: '/risk-disclosure' },           // 旧なら /connect に飛んでいた
  ];

  for (const { referrer, open } of cases) {
    test(`${referrer} から ${open} を開いて「戻る」→ 来訪元 ${referrer} に戻る`, async ({ page }) => {
      await page.goto(referrer);
      await page.goto(open); // 同一タブ遷移（履歴あり）

      await page.getByRole('button', { name: '戻る' }).click();

      await page.waitForURL(`**${referrer}`, { timeout: 8000 });
      expect(page.url()).toContain(referrer);
      expect(page.url()).not.toContain('/connect');
    });
  }

  // 本番のリンクは target="_blank"（別タブ）。別タブは履歴が無いため、
  // 「戻る」は来訪元に戻れず fallback（トップ '/' → 未認証は /login）へ遷移する。
  test('別タブ(target="_blank")で開いた場合は履歴が無く fallback (→/login) へ', async ({ page, context }) => {
    await page.goto('/login');
    const base = new URL(page.url()).origin;
    await page.setContent(
      `<a id="legal" href="${base}/terms" target="_blank" rel="noopener noreferrer">利用規約</a>`
    );

    const [popup] = await Promise.all([
      context.waitForEvent('page'),
      page.click('#legal'),
    ]);
    await popup.waitForLoadState('domcontentloaded');

    // 別タブは新規コンテキストでクライアントバンドルがコールドのため、
    // React hydration 前に click すると onClick 未装着で無反応になりうる。
    // ナビゲートが成立するまで再試行する（hydration 完了待ち）。
    await expect(async () => {
      await popup.getByRole('button', { name: '戻る' }).click();
      await popup.waitForURL('**/login', { timeout: 3000 });
    }).toPass({ timeout: 20000 });
    expect(popup.url()).toContain('/login');
  });
});
