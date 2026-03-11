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
