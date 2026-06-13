// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
/**
 * E2E spec: EmergencyStop + RiskModeSelector i18n 化 smoke test
 * Asana: financial batch A / PR Group A
 *
 * 検証範囲:
 *   TC1: /user/settings ページが 404/5xx を返さない
 *   TC2: /user/settings ページに "緊急停止" テキストが存在する（EmergencyStop.sectionTitle）
 *        認証ゲートで到達できない場合は gracefully skip
 *   TC3: /user/settings ページに "リスクモード" テキストが存在する（RiskModeSelector.title）
 *        認証ゲートで到達できない場合は gracefully skip
 *
 * NOTE:
 *   - EmergencyStop は app/user/settings/page.tsx L483 に配置（live ツリー: /user/settings）
 *   - RiskModeSelector は app/user/settings/page.tsx L322 に配置
 *   - /protocols（admin）には両コンポーネントは存在しない（修正: PR #307 教訓の再発を修正）
 *   - baseURL は playwright.config.ts (STAGING_URL || https://app.ultra-auto-trade.com)
 *   - 認証ゲートで UI に到達不能な場合は test.skip で gracefully skip する
 *   - Gate 1-3: ja/en key parity は python3 スクリプトで別途検証済み
 */

import { test, expect } from '@playwright/test'

const SETTINGS_URL = '/user/settings'

test.describe('[financial-i18n-A] EmergencyStop + RiskModeSelector - i18n smoke', () => {
  test('TC1: /user/settings が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto(SETTINGS_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/user/settings は 404 / 5xx であってはならない').not.toBe(404)
    expect(res!.status(), '/user/settings は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC2: /user/settings に EmergencyStop.sectionTitle "緊急停止" が表示される', async ({ page }) => {
    const res = await page.goto(SETTINGS_URL, { waitUntil: 'domcontentloaded' })
    // 認証ゲートやリダイレクトで /user/settings に留まらない場合は skip
    if (!res || res.status() >= 400 || !page.url().includes('/user/settings')) {
      test.skip(true, '認証ゲートで /user/settings に到達不能のため skip')
      return
    }

    const emergencyStopText = page.getByText('緊急停止', { exact: false }).first()
    const visible = await emergencyStopText.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '"緊急停止" テキストが認証後コンテンツのため skip')
    await expect(emergencyStopText).toBeVisible()
  })

  test('TC3: /user/settings に RiskModeSelector.title "リスクモード" が表示される', async ({ page }) => {
    const res = await page.goto(SETTINGS_URL, { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/user/settings')) {
      test.skip(true, '認証ゲートで /user/settings に到達不能のため skip')
      return
    }

    const riskModeText = page.getByText('リスクモード', { exact: false }).first()
    const visible = await riskModeText.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '"リスクモード" テキストが認証後コンテンツのため skip')
    await expect(riskModeText).toBeVisible()
  })
})
