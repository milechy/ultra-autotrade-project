// Copyright (c) Ultra AutoTrade. All rights reserved.
// スクリーンショット取得スクリプト (山本さんテスターガイド用)
//
// 使い方:
//   cd frontend
//   npx tsx e2e/scripts/yamamoto-guide-shots.ts
//
// 出力: /tmp/uata-shots/*.png (7枚)
// 注意: 取引操作(BUY/SELL/deposit/withdraw)は絶対に行わないこと

import { chromium, devices } from '@playwright/test';
import fs from 'fs';
import readline from 'readline';

const OUT = '/tmp/uata-shots';
fs.mkdirSync(OUT, { recursive: true });
const BASE = 'https://app.ultra-auto-trade.com';

function wait(msg: string): Promise<void> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve =>
    rl.question(`\n\x1b[33m[HUMAN] ${msg}\n完了したら Enter を押してください > \x1b[0m`, () => {
      rl.close();
      resolve();
    })
  );
}

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 100 });

  // ===== デスクトップ撮影 =====
  const desktop = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    locale: 'ja-JP',
    colorScheme: 'dark',
  });
  const page = await desktop.newPage();

  // 01. ランディング(未ログイン)
  console.log('\n[SHOT] 01_landing');
  await page.goto(BASE);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${OUT}/01_landing.png`, fullPage: false });
  console.log('  → saved: 01_landing.png');

  // 02. Privyログインモーダル(開いたところ)
  console.log('\n[SHOT] 02_login_privy');
  // ログインボタンを探してクリック(複数の表現に対応)
  const loginClicked = await page
    .getByRole('button', { name: /ログイン|Login|はじめる|Start|接続|Connect/i })
    .first()
    .click()
    .then(() => true)
    .catch(() => false);

  if (!loginClicked) {
    await page
      .getByRole('link', { name: /ログイン|Login/ })
      .first()
      .click()
      .catch(() => console.log('  [WARN] ログインボタンが見つかりませんでした。手動でクリックしてください。'));
  }

  await page.waitForTimeout(3000); // Privy モーダル起動待ち
  await page.screenshot({ path: `${OUT}/02_login_privy.png` });
  console.log('  → saved: 02_login_privy.png');

  // ===== 手動ログイン (デスクトップ) =====
  await wait(
    'ブラウザでPrivyログインを完了してください（メール入力→コード入力）。\n' +
    'ダッシュボード (/user/dashboard) が表示されたら Enter を。'
  );

  // 03. ダッシュボード上部
  console.log('\n[SHOT] 03_dashboard_top');
  await page.goto(`${BASE}/user/dashboard`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}/03_dashboard_top.png` });
  console.log('  → saved: 03_dashboard_top.png');

  // 04. AI判定セクション(スクロール後)
  console.log('\n[SHOT] 04_dashboard_ai_decision');
  // AI判定フィードページで最新判定を撮影
  await page.goto(`${BASE}/user/ai-feed`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}/04_dashboard_ai_decision.png` });
  console.log('  → saved: 04_dashboard_ai_decision.png');

  // 06. 緊急停止ボタン非表示確認(ダッシュボード全体)
  console.log('\n[SHOT] 06_no_emergency_stop');
  await page.goto(`${BASE}/user/dashboard`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${OUT}/06_no_emergency_stop.png`, fullPage: true });
  console.log('  → saved: 06_no_emergency_stop.png');
  console.log('  ℹ️  右下に赤い緊急停止ボタンがないことを目視確認してください');

  // 07. 設定アクセス拒否(viewer → loginリダイレクト or 表示制限)
  console.log('\n[SHOT] 07_settings_blocked');
  await page.goto(`${BASE}/user/settings`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2500);
  const finalUrl = page.url();
  console.log(`  → リダイレクト先: ${finalUrl}`);
  await page.screenshot({ path: `${OUT}/07_settings_blocked.png` });
  console.log('  → saved: 07_settings_blocked.png');

  await desktop.close();
  console.log('\n✅ デスクトップ撮影完了 (6枚)');

  // ===== モバイル撮影 =====
  console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('[MOBILE] iPhone 13 サイズで撮影します');
  const mobile = await browser.newContext({
    ...devices['iPhone 13'],
    locale: 'ja-JP',
    colorScheme: 'dark',
  });
  const mpage = await mobile.newPage();

  await mpage.goto(BASE);
  await mpage.waitForLoadState('networkidle');

  await wait(
    'モバイル画面でもPrivyログインしてください。\n' +
    'ダッシュボード (/user/dashboard) 表示後に Enter を。\n' +
    '※デスクトップと同じアカウントで OK です。'
  );

  // 05. モバイル BottomNav (viewer ナビ: ホーム/AI判定/ヘルプ のみ)
  console.log('\n[SHOT] 05_bottom_nav');
  await mpage.goto(`${BASE}/user/dashboard`);
  await mpage.waitForLoadState('networkidle');
  await mpage.waitForTimeout(2000);
  // 画面下部のナビが見えるよう下にスクロール
  await mpage.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await mpage.waitForTimeout(500);
  await mpage.screenshot({ path: `${OUT}/05_bottom_nav.png`, fullPage: false });
  console.log('  → saved: 05_bottom_nav.png');
  console.log('  ℹ️  BottomNavに「承認」「設定」リンクがないことを確認してください');

  await mobile.close();
  await browser.close();

  // ===== サマリー =====
  console.log('\n\x1b[32m✅ 全撮影完了\x1b[0m');
  console.log(`出力先: ${OUT}`);
  const files = fs.readdirSync(OUT).filter(f => f.endsWith('.png'));
  files.sort();
  let totalBytes = 0;
  for (const f of files) {
    const stat = fs.statSync(`${OUT}/${f}`);
    totalBytes += stat.size;
    const kb = Math.round(stat.size / 1024);
    console.log(`  ${f.padEnd(35)} ${kb.toString().padStart(5)} KB`);
  }
  console.log(`\n  合計: ${files.length}枚  ${Math.round(totalBytes / 1024)}KB`);
  console.log('\n次のアクション: 7枚を claude.ai にアップロード → Word埋め込み');
})();
