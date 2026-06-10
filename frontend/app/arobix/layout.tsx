// Arobix UI theme — self-contained preview layout.
// 既存の本番画面には一切影響しない独立ルート。テーマトークンは ./theme.css に集約。
import './theme.css'

export default function ArobixLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="arobix-root ax-bg-app" style={{ minHeight: '100dvh' }}>
      <div className="ax-phone">{children}</div>
    </div>
  )
}
