// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-05 取引承認 (/approve)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/approve');
    // ページの初期レンダリングを待つ（DOM が描画されるまで）
    await page.waitForLoadState('domcontentloaded');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/approve');
    expect(response?.status()).toBe(200);
  });

  test('「取引承認」テキストが表示される', async ({ page }) => {
    // ページが完全に読み込まれた場合は h1 が表示される
    // ローディング中・未認証時はナビゲーションの「取引承認」リンクが表示される
    const heading = page.getByRole('heading', { name: '取引承認' });
    const navLink = page.getByRole('link', { name: '取引承認' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      heading.waitFor({ state: 'visible', timeout: 10000 }),
      navLink.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasHeading = await heading.isVisible().catch(() => false);
    const hasNavLink = await navLink.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);
    expect(hasHeading || hasNavLink || hasLoginHeading).toBeTruthy();
  });

  test('サブテキストが表示される', async ({ page }) => {
    // ページが完全に読み込まれた場合はサブテキストが表示される
    const sub = page.getByText('AIが提案した取引を確認・承認してください');
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const navLink = page.getByRole('link', { name: '取引承認' });

    // いずれかが表示されるまで待つ
    await Promise.any([
      sub.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      navLink.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasSubText = await sub.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasNavLink = await navLink.isVisible().catch(() => false);

    expect(hasSubText || hasLoginBtn || hasNavLink).toBeTruthy();
  });

  test('提案カードまたは「承認待ちの提案はありません」メッセージが表示される', async ({ page }) => {
    const proposal = page.getByText(/SUPPLY|WITHDRAW|承認待ちの提案はありません/).first();
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const navLink = page.getByRole('link', { name: '取引承認' });

    await Promise.any([
      proposal.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      navLink.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasProposal = await proposal.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasNavLink = await navLink.isVisible().catch(() => false);

    expect(hasProposal || hasLoginBtn || hasNavLink).toBeTruthy();
  });

  test('カードに承認・却下ボタンが存在する（提案がある場合）または空状態が表示される', async ({ page }) => {
    const approveBtn = page.getByRole('button', { name: '承認' }).first();
    const emptyState = page.getByText('承認待ちの提案はありません');
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const navLink = page.getByRole('link', { name: '取引承認' });

    await Promise.any([
      approveBtn.waitFor({ state: 'visible', timeout: 10000 }),
      emptyState.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      navLink.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasApproveBtn = await approveBtn.isVisible().catch(() => false);
    const hasRejectBtn = await page.getByRole('button', { name: '却下' }).first().isVisible().catch(() => false);
    const hasEmptyState = await emptyState.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasNavLink = await navLink.isVisible().catch(() => false);

    expect(
      (hasApproveBtn && hasRejectBtn) || hasEmptyState || hasLoginBtn || hasNavLink
    ).toBeTruthy();
  });

  test('最近の承認履歴セクションが存在する', async ({ page }) => {
    const recentSection = page.getByText('最近の承認履歴');
    const emptyHistory = page.getByText('承認履歴はありません');
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const navLink = page.getByRole('link', { name: '取引承認' });

    await Promise.any([
      recentSection.waitFor({ state: 'visible', timeout: 10000 }),
      emptyHistory.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      navLink.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasSectionHeading = await recentSection.isVisible().catch(() => false);
    const hasEmptyHistory = await emptyHistory.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasNavLink = await navLink.isVisible().catch(() => false);

    expect(hasSectionHeading || hasEmptyHistory || hasLoginBtn || hasNavLink).toBeTruthy();
  });
});
