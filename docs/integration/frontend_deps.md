# Frontend 依存ライブラリ追加ログ

## recharts ^2.13.3

- **追加日:** 2026-03-12
- **追加者:** Stream S (AI判定の信頼度トレンド可視化)
- **用途:** AI判定の信頼度トレンドチャート、アクション分布チャート、精度チャート
- **使用コンポーネント:**
  - `frontend/components/charts/ConfidenceTrendChart.tsx`
  - `frontend/components/charts/ActionDistributionChart.tsx`
  - `frontend/components/charts/AccuracyChart.tsx`
- **選定理由:** React向けのデファクトチャートライブラリ。SVGベースでSSR互換。

## next-intl ^3.26.5

- **追加日:** 2026-03-12
- **追加者:** Stream W (多言語対応 JA/EN)
- **用途:** 日本語/英語の切り替え（i18n）
- **設定ファイル:**
  - `frontend/lib/i18n.ts` — next-intl サーバー設定（cookies でロケール読み取り）
  - `frontend/middleware.ts` — Accept-Language ヘッダーからロケール検出、cookie セット
  - `frontend/messages/ja.json` — 日本語翻訳
  - `frontend/messages/en.json` — 英語翻訳
- **使用コンポーネント:**
  - `frontend/components/user/LanguageToggle.tsx` — JA/EN 切替ボタン
  - `frontend/app/(user)/copy-trading/layout.tsx` — `NextIntlClientProvider` を設置
- **設定方法 (settings/page.tsx への統合):**
  1. `frontend/app/(user)/settings/` に layout.tsx を作成し `NextIntlClientProvider` でラップ
  2. settings/page.tsx で `import { LanguageToggle } from '@/components/user/LanguageToggle'` 追加
  3. UI に `<LanguageToggle />` を配置（例: ヘッダー右側）
  4. settings/page.tsx を `'use client'` のまま維持し、翻訳は `useTranslations()` で取得
- **選定理由:** Next.js App Router に最適化されたi18nライブラリ。SSR互換、URLルーティング不要モードあり。
