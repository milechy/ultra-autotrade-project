'use client'

import Link from "next/link";
import { useRouter } from "next/navigation";
import React from "react";
import { useAuth } from "../../lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <div style={{ fontFamily: "system-ui", color: "#111" }}>
      <header style={headerStyle}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
            <Link href="/" style={{ textDecoration: "none", color: "inherit" }}>
              <strong>Ultra AutoTrade</strong>
            </Link>
            <span style={{ color: "#666", fontSize: 12 }}>運用ダッシュボード</span>
          </div>
          <nav style={{ display: "flex", gap: 12, fontSize: 14, alignItems: "center" }}>
            <Link href="/dashboard/automation" style={navLinkStyle}>自動売買</Link>
            <Link href="/dashboard/reports" style={navLinkStyle}>レポート</Link>
            <Link href="/knowledge" style={navLinkStyle}>ナレッジ</Link>
            {!isLoading && user && (
              <>
                <span style={{ color: "#999" }}>|</span>
                <Link href="/settings/account" style={navLinkStyle}>設定</Link>
                {user.role === "admin" && (
                  <Link href="/settings/users" style={navLinkStyle}>ユーザー管理</Link>
                )}
                <span style={{ color: "#666", fontSize: 12 }}>{user.username}</span>
                <button onClick={handleLogout} style={logoutButtonStyle}>ログアウト</button>
              </>
            )}
            {!isLoading && !user && (
              <Link href="/login" style={navLinkStyle}>ログイン</Link>
            )}
          </nav>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "16px" }}>{children}</main>

      <footer style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px", color: "#777", fontSize: 12 }}>
        読み取り専用ダッシュボード。バックエンドURL: <code>{process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "(未設定)"}</code>
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

const logoutButtonStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid #ddd",
  borderRadius: 6,
  padding: "4px 10px",
  fontSize: 12,
  cursor: "pointer",
  color: "#666",
};
