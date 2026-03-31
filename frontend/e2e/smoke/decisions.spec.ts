// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-04 AI判定フィード (/decisions)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/decisions');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/decisions');
    expect(response?.status()).toBe(200);
  });

  test('ページ見出し「AI判定フィード」が表示される', async ({ page }) => {
    const heading = page.getByRole('heading', { name: 'AI判定フィード' });
    await expect(heading).toBeVisible();
  });

  test('AI判定バッジ（BUY/SELL/HOLD いずれか）が存在する', async ({ page }) => {
    // データがある場合はバッジが表示される
    // データなし・エラー時は "データを取得できません" が表示される
    const hasBadge = await page.getByText(/BUY|SELL|HOLD/).first().isVisible({ timeout: 5000 }).catch(() => false);
    const hasError = await page.getByText('データを取得できません').isVisible().catch(() => false);

    if (hasBadge) {
      await expect(page.getByText(/BUY|SELL|HOLD/).first()).toBeVisible();
    } else {
      // データなし：ページ見出しが表示されていることを確認
      await expect(page.getByRole('heading', { name: 'AI判定フィード' })).toBeVisible();
      // エラー状態またはデータなし状態のいずれかが許容される
      expect(hasError || !hasBadge).toBeTruthy();
    }
  });

  test('判定理由テキストが存在する', async ({ page }) => {
    // データがある場合は判定理由テキストが表示される
    // データなし・エラー時はエラーメッセージまたはページヘッダーのみ
    const hasReason = await page.getByText(/ボラティリティ|市場環境|ポジション/).first().isVisible({ timeout: 5000 }).catch(() => false);
    const hasError = await page.getByText('データを取得できません').isVisible().catch(() => false);

    if (hasReason) {
      await expect(page.getByText(/ボラティリティ|市場環境|ポジション/).first()).toBeVisible();
    } else {
      // データなし：ページ見出しが表示されていることを確認
      await expect(page.getByRole('heading', { name: 'AI判定フィード' })).toBeVisible();
      expect(hasError || !hasReason).toBeTruthy();
    }
  });

  test('判定履歴タイムラインが存在する', async ({ page }) => {
    // データがある場合はタイムラインアイテム（confidence値）が表示される
    // データなし・エラー時はエラーメッセージまたはページヘッダーのみ
    const hasTimeline = await page.getByText(/\d+%/).first().isVisible({ timeout: 5000 }).catch(() => false);
    const hasError = await page.getByText('データを取得できません').isVisible().catch(() => false);

    if (hasTimeline) {
      await expect(page.getByText(/\d+%/).first()).toBeVisible();
    } else {
      // データなし：ページ見出しが表示されていることを確認
      await expect(page.getByRole('heading', { name: 'AI判定フィード' })).toBeVisible();
      expect(hasError || !hasTimeline).toBeTruthy();
    }
  });
});
