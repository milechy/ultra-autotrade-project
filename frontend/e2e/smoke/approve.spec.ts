// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-05 取引承認 (/approve)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/approve');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/approve');
    expect(response?.status()).toBe(200);
  });

  test('「取引承認」テキストが表示される', async ({ page }) => {
    const heading = page.getByRole('heading', { name: '取引承認' });
    await expect(heading).toBeVisible();
  });

  test('サブテキストが表示される', async ({ page }) => {
    const sub = page.getByText('AIが提案した取引を確認・承認してください');
    await expect(sub).toBeVisible();
  });

  test('提案カードまたは「承認待ちの提案はありません」メッセージが表示される', async ({ page }) => {
    // MOCK_PROPOSALS があるので提案カードが表示されるはず
    const proposal = page.getByText(/SUPPLY|WITHDRAW|承認待ちの提案はありません/).first();
    await expect(proposal).toBeVisible();
  });

  test('提案カードに承認・却下ボタンが存在する（モックデータあり）', async ({ page }) => {
    // ProposalCard には承認ボタン（status=pending 時）がある
    const approveBtn = page.getByRole('button', { name: '承認' }).first();
    await expect(approveBtn).toBeVisible();
    const rejectBtn = page.getByRole('button', { name: '却下' }).first();
    await expect(rejectBtn).toBeVisible();
  });

  test('最近の承認履歴セクションが存在する', async ({ page }) => {
    // RecentApprovals コンポーネント: "最近の承認履歴"
    const recentSection = page.getByText('最近の承認履歴');
    await expect(recentSection).toBeVisible();
  });
});
