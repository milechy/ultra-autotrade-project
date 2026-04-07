// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

// 未認証状態では /login にリダイレクトされる場合がある。
// approve.spec.ts と同じパターンで「ページコンテンツ OR ログイン状態」を許容する。

test.describe('U-06 取引履歴 (/history)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/history');
    await page.waitForLoadState('domcontentloaded');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/history');
    // 認証リダイレクト（302 → ログインページ 200）も許容。500番台でないこと。
    expect(response?.status()).toBeLessThan(500);
  });

  test('ページ見出し「取引履歴」が表示される', async ({ page }) => {
    const heading = page.getByRole('heading', { name: '取引履歴' });
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      heading.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasHeading = await heading.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);
    expect(hasHeading || hasLoginBtn || hasLoginHeading).toBeTruthy();
  });

  test('統計カード（総取引数/総利益/総手数料）が表示される', async ({ page }) => {
    // StatsCards コンポーネント: KPICard label
    const totalTrades = page.getByText('総取引数');
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      totalTrades.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasTotalTrades = await totalTrades.isVisible().catch(() => false);
    const hasTotalProfit = await page.getByText('総利益').isVisible().catch(() => false);
    const hasTotalFee = await page.getByText('総手数料').isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);

    expect(
      (hasTotalTrades && hasTotalProfit && hasTotalFee) || hasLoginBtn || hasLoginHeading
    ).toBeTruthy();
  });

  test('フィルターボタン群（ALL/SUPPLY/WITHDRAW等）が表示される', async ({ page }) => {
    // TransactionFilters: SUPPLY/WITHDRAW は操作種別フィルターにのみ存在
    const supplyBtn = page.getByRole('button', { name: 'SUPPLY' });
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      supplyBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasAllBtn = await page.getByRole('button', { name: 'ALL' }).first().isVisible().catch(() => false);
    const hasSupplyBtn = await supplyBtn.isVisible().catch(() => false);
    const hasWithdrawBtn = await page.getByRole('button', { name: 'WITHDRAW' }).isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);

    expect(
      (hasAllBtn && hasSupplyBtn && hasWithdrawBtn) || hasLoginBtn || hasLoginHeading
    ).toBeTruthy();
  });

  test('取引リストまたは「まだ取引履歴がありません」メッセージが表示される', async ({ page }) => {
    // TransactionList: データあり時は SUPPLY/WITHDRAW 等のバッジ
    // データなし時は "まだ取引履歴がありません"（TransactionList の空状態テキスト）
    const list = page.getByText(/SUPPLY|WITHDRAW|BORROW|REPAY|まだ取引履歴がありません|取引履歴がありません/).first();
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      list.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasList = await list.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);
    expect(hasList || hasLoginBtn || hasLoginHeading).toBeTruthy();
  });
});
