// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

// ----------------------------------------------------------------
// liff-chat 通知設定パネル (NotificationPanel)
// ----------------------------------------------------------------
// 対象: app/(liff)/liff-chat/_components/panels/NotificationPanel.tsx
// 検証観点:
//   1. /liff-chat ページが 200 で読み込まれる。
//   2. 通知設定タブを開くと NotificationPanel の要素が描画される。
//   3. 「緊急停止通知」行が disabled + ON 固定 (role=switch, aria-checked=true,
//      かつ操作不可) で「変更不可」バッジ付きで描画される (CSS バグ修正の回帰防止)。
//   4. 通常の通知トグル (例: AI 提案通知) は操作可能で状態が切り替わる。
//
// 注意: baseURL は playwright.config.ts 準拠 (STAGING_URL or app.ultra-auto-trade.com)。
//       未認証環境では LIFF ログイン画面へリダイレクトされうるため、各検証は
//       「該当 UI が出る or ログイン画面が出る」を許容する防御的アサーションにする。
// ----------------------------------------------------------------

const NOTIF_TAB_LABEL = '通知設定';

test.describe('liff-chat 通知設定パネル', () => {
  test('/liff-chat が読み込まれる', async ({ page }) => {
    const response = await page.goto('/liff-chat');
    // 200 もしくはログインへのリダイレクト後 200 を許容
    expect(response?.status()).toBeLessThan(400);
  });

  test('通知設定タブを開くと NotificationPanel が描画される', async ({ page }) => {
    await page.goto('/liff-chat');
    await page.waitForLoadState('domcontentloaded');

    // 通知設定タブ / メニュー項目をクリック (存在すれば)
    const notifTab = page.getByText(NOTIF_TAB_LABEL, { exact: false }).first();
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    // ログイン画面 or 通知タブのどちらかが現れることを許容
    await Promise.any([
      notifTab.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    if (await notifTab.isVisible().catch(() => false)) {
      await notifTab.click().catch(() => {});
      await page.waitForLoadState('domcontentloaded');

      // パネル内のセクション/ラベルのいずれかが見えること
      const channelHeader = page.getByText('通知チャネル', { exact: false });
      const emergencyLabel = page.getByText('緊急停止通知', { exact: false });
      const visible =
        (await channelHeader.isVisible().catch(() => false)) ||
        (await emergencyLabel.isVisible().catch(() => false));
      expect(visible).toBeTruthy();
    } else {
      // 未認証: ログイン画面に到達していれば妥当
      expect(await loginHeading.isVisible().catch(() => false)).toBeTruthy();
    }
  });

  test('緊急停止通知トグルは disabled + ON 固定 + 変更不可バッジ', async ({ page }) => {
    await page.goto('/liff-chat');
    await page.waitForLoadState('domcontentloaded');

    const notifTab = page.getByText(NOTIF_TAB_LABEL, { exact: false }).first();
    if (!(await notifTab.isVisible().catch(() => false))) {
      test.skip(true, '未認証環境: 通知設定タブに到達できないためスキップ');
      return;
    }
    await notifTab.click().catch(() => {});
    await page.waitForLoadState('domcontentloaded');

    const emergencyRow = page
      .locator('div', { hasText: '緊急停止通知' })
      .filter({ has: page.getByRole('switch') })
      .first();

    // 「変更不可」バッジが同行に存在
    await expect(emergencyRow.getByText('変更不可')).toBeVisible();

    // 行内の switch は ON (aria-checked=true) かつ disabled
    const emergencySwitch = emergencyRow.getByRole('switch').first();
    await expect(emergencySwitch).toHaveAttribute('aria-checked', 'true');
    await expect(emergencySwitch).toBeDisabled();

    // ノブが右側 (ON) に寄っていること = translate-x-5 クラスを持つ span が存在
    const knobOn = emergencySwitch.locator('span.translate-x-5');
    await expect(knobOn).toHaveCount(1);
  });

  test('通常トグル (AI 提案通知) は操作可能', async ({ page }) => {
    await page.goto('/liff-chat');
    await page.waitForLoadState('domcontentloaded');

    const notifTab = page.getByText(NOTIF_TAB_LABEL, { exact: false }).first();
    if (!(await notifTab.isVisible().catch(() => false))) {
      test.skip(true, '未認証環境: 通知設定タブに到達できないためスキップ');
      return;
    }
    await notifTab.click().catch(() => {});
    await page.waitForLoadState('domcontentloaded');

    const aiRow = page
      .locator('div', { hasText: 'AI 提案通知' })
      .filter({ has: page.getByRole('switch') })
      .first();
    const aiSwitch = aiRow.getByRole('switch').first();

    await expect(aiSwitch).toBeEnabled();
    const before = await aiSwitch.getAttribute('aria-checked');
    await aiSwitch.click();
    const after = await aiSwitch.getAttribute('aria-checked');
    expect(after).not.toBe(before);
  });
});
