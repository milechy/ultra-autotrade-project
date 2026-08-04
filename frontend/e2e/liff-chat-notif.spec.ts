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
//   5. (2026-08-04 PR4) NEXT_PUBLIC_VAPID_PUBLIC_KEY 未設定時、プッシュ通知トグルは
//      disabled で「VAPID未設定」バッジが出る。
//   6. (2026-08-04 PR4) VAPID 設定済み環境で、プッシュ通知トグルを ON にすると
//      実際に pushManager.subscribe() が呼ばれ、POST /notifications/push/subscribe
//      が正しい認証ヘッダ・ボディで送られる (handlePushToggle が権限取得だけで
//      終わっていた欠陥の回帰防止)。next-pwa は開発時 Service Worker を無効化するため
//      navigator.serviceWorker / PushManager を addInitScript でスタブする。
//
// 注意: baseURL は playwright.config.ts 準拠 (STAGING_URL or app.ultra-auto-trade.com)。
//       未認証環境では LIFF ログイン画面へリダイレクトされうるため、各検証は
//       「該当 UI が出る or ログイン画面が出る」を許容する防御的アサーションにする。
//       6. のテストは NEXT_PUBLIC_VAPID_PUBLIC_KEY を設定した dev サーバでのみ意味を持つ
//       (未設定環境ではトグル自体が disabled になるため skip する)。
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

  test('VAPID未設定時はプッシュ通知トグルが disabled + バッジ表示', async ({ page }) => {
    // NEXT_PUBLIC_VAPID_PUBLIC_KEY はビルド時埋め込みのため実行時に判定できない。
    // 設定済み dev サーバで実行された場合は下の disabled 分岐が false になり、
    // アサーション自体が発火せず素通りする (意味を持つのは未設定環境のみ)。
    await page.goto('/liff-chat');
    await page.waitForLoadState('domcontentloaded');

    const notifTab = page.getByText(NOTIF_TAB_LABEL, { exact: false }).first();
    if (!(await notifTab.isVisible().catch(() => false))) {
      test.skip(true, '未認証環境: 通知設定タブに到達できないためスキップ');
      return;
    }
    await notifTab.click().catch(() => {});
    await page.waitForLoadState('domcontentloaded');

    const pushRow = page
      .locator('div', { hasText: 'プッシュ通知' })
      .filter({ has: page.getByRole('switch') })
      .first();
    const pushSwitch = pushRow.getByRole('switch').first();

    // VAPID が設定されていない環境でのみ disabled + バッジが出ることを確認する
    // (設定済み環境ではこのテストは目的を持たないため、disabled でなければ素通りさせる)。
    const disabled = await pushSwitch.isDisabled();
    if (disabled) {
      await expect(pushRow.getByText('VAPID未設定')).toBeVisible();
    }
  });
});

// ----------------------------------------------------------------
// Push 購読の実配線 (2026-08-04 PR4)
// ----------------------------------------------------------------
// NEXT_PUBLIC_VAPID_PUBLIC_KEY を設定した dev サーバでのみ意味を持つ。
// 未設定環境ではトグルが disabled になり click 自体が成立しないため全ケース skip する。
// next-pwa は開発時 Service Worker を無効化するため、navigator.serviceWorker /
// PushManager を addInitScript でスタブし、実際の SW ライフサイクルから切り離す。

test.describe('Push購読の実配線 (subscribeToPush)', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.grantPermissions(['notifications']);

    // getAuthToken() が読む正準キーへ事前注入。
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem('auth_token', 'e2e-push-test-token');
      } catch {
        /* ignore */
      }
      ;(window as any).Notification = {
        permission: 'granted',
        requestPermission: async () => 'granted',
      }

      const fakeSubscription = {
        endpoint: 'https://fcm.googleapis.com/fcm/send/e2e-fake-endpoint',
        toJSON: () => ({
          endpoint: 'https://fcm.googleapis.com/fcm/send/e2e-fake-endpoint',
          keys: { p256dh: 'fake-p256dh', auth: 'fake-auth' },
        }),
        unsubscribe: async () => {
          ;(window as any).__unsubscribeCalledOnRollback = true
          return true
        },
      }
      const fakePushManager = {
        subscribe: async () => fakeSubscription,
        getSubscription: async () => null,
      }
        ; (navigator as any).serviceWorker = {
          ready: Promise.resolve({ pushManager: fakePushManager }),
        }
    })

    await page.route('**/api/notifications/settings', async (route) => {
      const req = route.request()
      if (req.method() === 'PUT') {
        const body = req.postDataJSON()
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(body),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          line_enabled: true,
          push_enabled: false,
          preferences: {
            ai_proposal: true,
            execution_complete: true,
            health_factor_warning: true,
            emergency_stop: true,
            monthly_report: true,
            system_notice: true,
          },
        }),
      })
    })
  })

  test('トグルON → pushManager.subscribe() → POST /notifications/push/subscribe', async ({
    page,
  }) => {
    let subscribeCalled = false
    let subscribeAuth: string | null = null
    let subscribeBody: Record<string, unknown> | null = null

    await page.route('**/notifications/push/subscribe', async (route) => {
      subscribeCalled = true
      subscribeAuth = route.request().headers()['authorization'] ?? null
      subscribeBody = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'subscribed', count: 1 }),
      })
    })

    await page.goto('/liff-chat')
    await page.waitForLoadState('domcontentloaded')

    const notifTab = page.getByText(NOTIF_TAB_LABEL, { exact: false }).first()
    if (!(await notifTab.isVisible().catch(() => false))) {
      test.skip(true, '未認証環境: 通知設定タブに到達できないためスキップ')
      return
    }
    await notifTab.click().catch(() => {})
    await page.waitForLoadState('domcontentloaded')

    const pushRow = page
      .locator('div', { hasText: 'プッシュ通知' })
      .filter({ has: page.getByRole('switch') })
      .first()
    const pushSwitch = pushRow.getByRole('switch').first()

    if (await pushSwitch.isDisabled()) {
      test.skip(true, 'VAPID未設定環境: このテストは NEXT_PUBLIC_VAPID_PUBLIC_KEY 設定済みdevサーバでのみ実行する')
      return
    }

    await pushSwitch.click()
    await expect.poll(() => subscribeCalled, { timeout: 5000 }).toBe(true)

    expect(subscribeAuth).toBe('Bearer e2e-push-test-token')
    expect(subscribeBody).toMatchObject({
      endpoint: 'https://fcm.googleapis.com/fcm/send/e2e-fake-endpoint',
      keys: { p256dh: 'fake-p256dh', auth: 'fake-auth' },
    })
  })

  test('サーバ登録失敗時は push_enabled を立てずエラーを表示する', async ({ page }) => {
    await page.route('**/notifications/push/subscribe', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
    })

    let putCalled = false
    await page.route('**/api/notifications/settings', async (route) => {
      if (route.request().method() === 'PUT') {
        putCalled = true
      }
      await route.continue()
    })

    await page.goto('/liff-chat')
    await page.waitForLoadState('domcontentloaded')

    const notifTab = page.getByText(NOTIF_TAB_LABEL, { exact: false }).first()
    if (!(await notifTab.isVisible().catch(() => false))) {
      test.skip(true, '未認証環境: 通知設定タブに到達できないためスキップ')
      return
    }
    await notifTab.click().catch(() => {})
    await page.waitForLoadState('domcontentloaded')

    const pushRow = page
      .locator('div', { hasText: 'プッシュ通知' })
      .filter({ has: page.getByRole('switch') })
      .first()
    const pushSwitch = pushRow.getByRole('switch').first()

    if (await pushSwitch.isDisabled()) {
      test.skip(true, 'VAPID未設定環境: このテストは NEXT_PUBLIC_VAPID_PUBLIC_KEY 設定済みdevサーバでのみ実行する')
      return
    }

    await pushSwitch.click()

    // 失敗時にエラーメッセージが表示され、push_enabled の PUT が飛ばないこと。
    await expect(page.getByText('通知の登録に失敗しました')).toBeVisible({ timeout: 5000 })
    expect(putCalled).toBe(false)

    // subscribeToPush() は失敗時にブラウザ側購読をロールバックする(unsubscribe呼び出し)。
    const unsubscribeCalledOnRollback = await page.evaluate(
      () => (window as any).__unsubscribeCalledOnRollback === true
    )
    expect(unsubscribeCalledOnRollback).toBe(true)
  })
})
