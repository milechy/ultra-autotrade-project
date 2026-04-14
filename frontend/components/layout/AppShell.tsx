'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from "next/link";
import { useRouter } from "next/navigation";
import React, { useState } from "react";
import { useAuth } from "../../lib/auth";

const adminNavLinks = [
  { href: "/dashboard/automation", label: "自動売買" },
  { href: "/reports", label: "レポート" },
  { href: "/knowledge", label: "ナレッジ" },
  { href: "/ai-decisions", label: "AI判定" },
  { href: "/ai-learning", label: "AI学習" },
  { href: "/protocols", label: "プロトコル" },
  { href: "/events", label: "データ" },
  { href: "/trades", label: "取引所管理" },
  { href: "/proposals", label: "提案管理" },
  { href: "/user/dashboard", label: "ユーザーアプリ →", highlight: true },
];

const partnerNavLinks: Array<{ href: string; label: string; highlight?: boolean }> = [
  { href: "/partner/dashboard", label: "ダッシュボード" },
  { href: "/partner/users", label: "テスター管理" },
  { href: "/partner/proposals", label: "AI提案" },
  { href: "/partner/notifications", label: "通知ログ" },
  { href: "/partner/settings", label: "設定" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout, isLoading, isAdmin, isPartner } = useAuth();
  const router = useRouter();

  const activeNavLinks = isAdmin ? adminNavLinks : isPartner ? partnerNavLinks : [];
  const [menuOpen, setMenuOpen] = useState(false);

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
            {isAdmin && (
              <Link href="/dashboard" style={{ textDecoration: "none", color: "#666", fontSize: 12 }}>運用ダッシュボード</Link>
            )}
          </div>

          {/* Desktop nav */}
          <nav style={{ display: "flex", gap: 12, fontSize: 14, alignItems: "center" }} className="mobile-hamburger-desktop-nav">
            {activeNavLinks.map(({ href, label, highlight }) => (
              <Link key={href} href={href} style={highlight ? { ...navLinkStyle, color: "#2563eb" } : navLinkStyle}>{label}</Link>
            ))}
            {!isLoading && user && (
              <>
                <span style={{ color: "#999" }}>|</span>
                {isAdmin && (
                  <>
                    <Link href="/settings/config" style={navLinkStyle}>設定</Link>
                    <Link href="/users" style={navLinkStyle}>ユーザー管理</Link>
                    <Link href="/partner/dashboard" style={navLinkStyle}>パートナーダッシュボード</Link>
                    <Link href="/partner/users" style={navLinkStyle}>テスター管理</Link>
                  </>
                )}
                <span style={{ color: "#666", fontSize: 12 }}>{user.username}</span>
                <button onClick={handleLogout} style={logoutButtonStyle}>ログアウト</button>
              </>
            )}
            {!isLoading && !user && (
              <Link href="/login" style={navLinkStyle}>ログイン</Link>
            )}
          </nav>

          {/* Hamburger button (mobile only) */}
          <button
            onClick={() => setMenuOpen(v => !v)}
            style={hamburgerButtonStyle}
            className="mobile-hamburger"
            aria-label="メニュー"
            aria-expanded={menuOpen}
          >
            <span style={hamburgerLineStyle} />
            <span style={hamburgerLineStyle} />
            <span style={hamburgerLineStyle} />
          </button>
        </div>

        {/* Mobile dropdown menu */}
        {menuOpen && (
          <nav style={mobileMenuStyle} className="mobile-hamburger-menu">
            {activeNavLinks.map(({ href, label, highlight }) => (
              <Link
                key={href}
                href={href}
                style={highlight ? { ...mobileNavLinkStyle, color: "#2563eb" } : mobileNavLinkStyle}
                onClick={() => setMenuOpen(false)}
              >
                {label}
              </Link>
            ))}
            {!isLoading && user && (
              <>
                {isAdmin && (
                  <>
                    <Link href="/settings/config" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>設定</Link>
                    <Link href="/users" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>ユーザー管理</Link>
                    <Link href="/partner/dashboard" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>パートナーダッシュボード</Link>
                    <Link href="/partner/users" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>テスター管理</Link>
                  </>
                )}
                <button onClick={handleLogout} style={mobileLogoutStyle}>ログアウト</button>
              </>
            )}
            {!isLoading && !user && (
              <Link href="/login" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>ログイン</Link>
            )}
          </nav>
        )}
      </header>

      <style>{`
        @media (min-width: 640px) {
          .mobile-hamburger { display: none !important; }
        }
        @media (max-width: 639px) {
          .mobile-hamburger-desktop-nav { display: none !important; }
        }
      `}</style>

      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "16px" }}>{children}</main>

      <footer style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px", color: "#777", fontSize: 12 }}>
        © Ultra AutoTrade
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

const hamburgerButtonStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  padding: 8,
  display: "flex",
  flexDirection: "column",
  gap: 5,
};

const hamburgerLineStyle: React.CSSProperties = {
  display: "block",
  width: 22,
  height: 2,
  background: "#333",
  borderRadius: 2,
};

const mobileMenuStyle: React.CSSProperties = {
  borderTop: "1px solid #eee",
  padding: "8px 16px 12px",
  display: "flex",
  flexDirection: "column",
  gap: 4,
  background: "rgba(255,255,255,0.98)",
};

const mobileNavLinkStyle: React.CSSProperties = {
  textDecoration: "none",
  color: "#333",
  padding: "10px 4px",
  fontSize: 14,
  borderBottom: "1px solid #f0f0f0",
};

const mobileLogoutStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid #ddd",
  borderRadius: 6,
  padding: "8px 10px",
  fontSize: 14,
  cursor: "pointer",
  color: "#666",
  textAlign: "left",
  marginTop: 4,
};