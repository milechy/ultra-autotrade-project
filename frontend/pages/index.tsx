import Head from "next/head";
import Link from "next/link";

export default function Home() {
  return (
    <>
      <Head>
        <title>Ultra AutoTrade - Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 920, margin: "0 auto" }}>
        <h1 style={{ marginBottom: 8 }}>Ultra AutoTrade</h1>
        <p style={{ marginTop: 0, color: "#555" }}>
          運用ダッシュボード（読み取り専用）. Use this UI to confirm health and review the latest report.
        </p>

        <div style={{ display: "flex", gap: 12, marginTop: 20, flexWrap: "wrap" }}>
          <Link href="/dashboard/automation" style={cardStyle}>
            <strong>自動売買</strong>
            <div style={{ color: "#555", marginTop: 6 }}>
              Status, recent events, and snapshot panels.
            </div>
          </Link>

          <Link href="/dashboard/reports" style={cardStyle}>
            <strong>最新レポート</strong>
            <div style={{ color: "#555", marginTop: 6 }}>
              Most recent summary report (daily/weekly).
            </div>
          </Link>

          <a href="/dashboard" style={cardStyle}>
            <strong>ダッシュボード</strong>
            <div style={{ color: "#555", marginTop: 6 }}>
              Landing page for operations navigation.
            </div>
          </a>
        </div>

        <section style={{ marginTop: 28, color: "#555" }}>
          <h2 style={{ fontSize: 16 }}>Backend endpoint</h2>
          <p style={{ marginTop: 6 }}>
            Set <code>NEXT_PUBLIC_BACKEND_BASE_URL</code> to point to FastAPI (e.g.{" "}
            <code>http://localhost:8000</code>).
          </p>
        </section>
      </main>
    </>
  );
}

const cardStyle: React.CSSProperties = {
  display: "block",
  padding: 16,
  border: "1px solid #ddd",
  borderRadius: 12,
  width: 280,
  textDecoration: "none",
  color: "inherit",
  background: "#fff",
};
