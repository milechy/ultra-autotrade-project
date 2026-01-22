import Link from "next/link";
import React from "react";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: "system-ui", color: "#111" }}>
      <header style={headerStyle}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
            <Link href="/" style={{ textDecoration: "none", color: "inherit" }}>
              <strong>Ultra AutoTrade</strong>
            </Link>
            <span style={{ color: "#666", fontSize: 12 }}>Operations</span>
          </div>
          <nav style={{ display: "flex", gap: 12, fontSize: 14 }}>
            <Link href="/dashboard/automation" style={navLinkStyle}>Automation</Link>
            <Link href="/dashboard/reports" style={navLinkStyle}>Reports</Link>
          </nav>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "16px" }}>{children}</main>

      <footer style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px", color: "#777", fontSize: 12 }}>
        Read-only dashboard. Backend base URL: <code>{process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "(not set)"}</code>
      </footer>
    </div>
  );
}

const headerStyle: React.CSSProperties = {
  position: "sticky",
  top: 0,
  background: "rgba(255,255,255,0.92)",
  borderBottom: "1px solid #eee",
  backdropFilter: "blur(6px)",
  zIndex: 10,
};

const navLinkStyle: React.CSSProperties = {
  textDecoration: "none",
  color: "#333",
};
