// frontend/components/DemoBanner.tsx
// Shown only when NEXT_PUBLIC_MOCK_MODE=true. Warns users this is a demo environment.

import { getTranslations } from 'next-intl/server'

export async function DemoBanner() {
  if (process.env.NEXT_PUBLIC_MOCK_MODE !== "true") return null;
  const t = await getTranslations('DemoBanner');
  return (
    <div
      role="banner"
      aria-label="デモ環境通知"
      style={{
        background: "#FEF08A",
        borderBottom: "2px solid #EF4444",
        color: "#7F1D1D",
        textAlign: "center",
        padding: "8px 16px",
        fontSize: "14px",
        fontWeight: 700,
        letterSpacing: "0.02em",
        position: "sticky",
        top: 0,
        zIndex: 9999,
      }}
    >
      {t('notice')}
    </div>
  );
}
