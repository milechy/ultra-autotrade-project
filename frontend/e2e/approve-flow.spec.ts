// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-05 取引承認フロー 詳細テスト (/approve)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/approve');
  });

  test('提案カードの詳細コンテンツ（バッジ・資産・金額・理由・メトリクス）が表示される', async ({ page }) => {
    // 操作バッジ: "SUPPLY" が表示されること
    const supplyBadge = page.getByText('SUPPLY').first();
    await expect(supplyBadge).toBeVisible();

    // 資産名が表示されること
    const assetName = page.getByText('USDC').first();
    await expect(assetName).toBeVisible();

    // 金額が表示されること（1,500 USDC 形式）
    const amount = page.getByText(/1,500/).first();
    await expect(amount).toBeVisible();

    // AI判定理由テキストが表示されること
    const reasonSection = page.getByText(/ヘルスファクター|推定ガス代|reason|理由/).first();
    await expect(reasonSection).toBeVisible();

    // メトリクス: ヘルスファクター変化
    const healthFactor = page.getByText('ヘルスファクター変化');
    await expect(healthFactor).toBeVisible();

    // メトリクス: 推定ガス代
    const gasEstimate = page.getByText('推定ガス代');
    await expect(gasEstimate).toBeVisible();
  });

  test('待ち件数バッジ「2件待ち」が表示される', async ({ page }) => {
    const badge = page.getByText('2件待ち');
    await expect(badge).toBeVisible();
  });

  test('承認フロー: ボタンクリックから完了まで状態遷移が正しく表示される', async ({ page }) => {
    // 最初の承認ボタンをクリック
    const approveBtn = page.getByRole('button', { name: '承認' }).first();
    await expect(approveBtn).toBeVisible();
    await approveBtn.click();

    // 処理中... に変化する
    const processingBtn = page.getByRole('button', { name: '処理中...' }).first();
    await expect(processingBtn).toBeVisible({ timeout: 2000 });

    // 承認中: "署名をリクエスト中..." が表示される
    const signingText = page.getByText('署名をリクエスト中...');
    await expect(signingText).toBeVisible({ timeout: 3000 });

    // 確認中: "確認待ち..." が表示される
    const confirmingText = page.getByText('確認待ち...');
    await expect(confirmingText).toBeVisible({ timeout: 4000 });

    // 完了: "トランザクション完了" が表示される
    const successText = page.getByText('トランザクション完了');
    await expect(successText).toBeVisible({ timeout: 5000 });

    // TxHash リンク: "0x" で始まるテキストが表示される
    const txHashLink = page.getByText(/^0x/);
    await expect(txHashLink).toBeVisible({ timeout: 5000 });

    // 承認後に承認・却下ボタンが消える（該当カードのボタン）
    // 完了後はそのカードのボタン群が非表示になる
    await expect(processingBtn).not.toBeVisible({ timeout: 5000 });
  });

  test('拒否フロー: 却下ボタンクリックでそのカードが消える', async ({ page }) => {
    // prop-001 カード（SUPPLY USDC 1500）が表示されていることを確認
    const firstCard = page.getByText('1,500').first();
    await expect(firstCard).toBeVisible();

    // 最初の却下ボタンをクリック
    const rejectBtn = page.getByRole('button', { name: '却下' }).first();
    await expect(rejectBtn).toBeVisible();
    await rejectBtn.click();

    // 該当カードの金額テキストが消える（カードが除去される）
    await expect(firstCard).not.toBeVisible({ timeout: 3000 });
  });

  test('全提案を却下した後「承認待ちの提案はありません」が表示される', async ({ page }) => {
    // 1件目を却下
    const firstRejectBtn = page.getByRole('button', { name: '却下' }).first();
    await expect(firstRejectBtn).toBeVisible();
    await firstRejectBtn.click();

    // 2件目を却下（1件目が消えたあと、残ったカードの却下ボタンをクリック）
    const secondRejectBtn = page.getByRole('button', { name: '却下' }).first();
    await expect(secondRejectBtn).toBeVisible({ timeout: 3000 });
    await secondRejectBtn.click();

    // 空の状態メッセージが表示される
    const emptyMessage = page.getByText('承認待ちの提案はありません');
    await expect(emptyMessage).toBeVisible({ timeout: 3000 });
  });

  test('最近の承認履歴コンテンツ（SUPPLY・2,000 USDC・成功バッジ）が表示される', async ({ page }) => {
    // セクションタイトル
    const sectionTitle = page.getByText('最近の承認履歴');
    await expect(sectionTitle).toBeVisible();

    // past-1: SUPPLY USDC 2000 成功 の内容確認
    const supplyHistory = page.getByText('SUPPLY').nth(1);
    await expect(supplyHistory).toBeVisible();

    const amount2000 = page.getByText(/2,000/);
    await expect(amount2000).toBeVisible();

    // "成功" バッジが表示される
    const successBadge = page.getByText('成功').first();
    await expect(successBadge).toBeVisible();
  });

  test('「全履歴を見る →」リンクが /history を指す', async ({ page }) => {
    const historyLink = page.getByText('全履歴を見る →');
    await expect(historyLink).toBeVisible();

    // href が /history であることを確認
    const href = await historyLink.getAttribute('href');
    expect(href).toContain('/history');
  });
});

// モバイル固有テスト（375px）
test.describe('U-05 取引承認 モバイルビューポート (375px)', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test.beforeEach(async ({ page }) => {
    await page.goto('/approve');
  });

  test('モバイルで「取引承認」ヘッダーと提案カードが表示される', async ({ page }) => {
    const heading = page.getByRole('heading', { name: '取引承認' });
    await expect(heading).toBeVisible();

    // 提案カードが表示される
    const approveBtn = page.getByRole('button', { name: '承認' }).first();
    await expect(approveBtn).toBeVisible();
  });

  test('モバイルで待ち件数バッジが表示される', async ({ page }) => {
    const badge = page.getByText('2件待ち');
    await expect(badge).toBeVisible();
  });

  test('モバイルで「最近の承認履歴」セクションが表示される', async ({ page }) => {
    const recentSection = page.getByText('最近の承認履歴');
    await expect(recentSection).toBeVisible();
  });
});
