// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

/**
 * Production landing page chain text consistency check
 *
 * 2026-05-02 incident: frontend/app/page.tsx had hardcoded "Base Sepolia" text
 * that was not detected by existing E2E tests during 5/1 mainnet switch.
 *
 * This test prevents recurrence by verifying the landing page does NOT show
 * testnet text and DOES show mainnet text.
 *
 * Asana: GID 1214462619161978
 */
test.describe('ランディングページ チェーン表記一貫性チェック (mainnet)', () => {
  test('Sepolia / テストネット 表記が含まれていない', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const html = await page.content();

    expect(html, 'Landing page should not contain "Sepolia" text').not.toMatch(/Sepolia/i);
    expect(html, 'Landing page should not contain "テストネット" text').not.toContain('テストネット');
  });

  test('メインネット / Mainnet 表記が含まれている', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const html = await page.content();

    expect(
      html,
      'Landing page should contain "メインネット" or "Mainnet" text'
    ).toMatch(/メインネット|Mainnet/i);
  });

  test('FAQ セクション: チェーン関連の表記に Sepolia がない', async ({ page }) => {
    await page.goto('/');

    const faqTrigger = page.getByRole('button', {
      name: /対応チェーン|プロトコル/i,
    });

    if (await faqTrigger.isVisible()) {
      await faqTrigger.click();

      const faqContent = await page.locator('[role="region"]').textContent();
      expect(faqContent, 'FAQ chain content should not mention Sepolia').not.toMatch(/Sepolia/i);
    }
  });
});
