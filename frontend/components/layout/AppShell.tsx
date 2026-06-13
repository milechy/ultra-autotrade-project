'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from "next/link";
import { useRouter } from "next/navigation";
import React, { useState } from "react";
import { useTranslations } from 'next-intl';
import { useAuth } from "../../lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout, isLoading, isAdmin, isPartner } = useAuth();
  const router = useRouter();
  const t = useTranslations('AppShell');
  const [menuOpen, setMenuOpen] = useState(false);

  const adminNavLinks = [
    { href: "/dashboard/automation", label: t('adminNav.automation') },
    { href: "/reports", label: t('adminNav.reports') },
    { href: "/knowledge", label: t('adminNav.knowledge') },
    { href: "/ai-decisions", label: t('adminNav.aiDecisions') },
    { href: "/ai-learning", label: t('adminNav.aiLearning') },
    { href: "/protocols", label: t('adminNav.protocols') },
    { href: "/events", label: t('adminNav.events') },
    { href: "/trades", label: t('adminNav.trades') },
    { href: "/proposals", label: t('adminNav.proposals') },
    { href: "/fee-management", label: t('adminNav.feeManagement') },
    { href: "/user/dashboard", label: t('adminNav.userApp'), highlight: true },
  ];

  const partnerNavLinks: Array<{ href: string; label: string; highlight?: boolean }> = [
    { href: "/partner/dashboard", label: t('partnerNav.dashboard') },
    { href: "/partner/referral", label: t('partnerNav.referral') },
    { href: "/partner/users", label: t('partnerNav.users') },
    { href: "/partner/proposals", label: t('partnerNav.proposals') },
    { href: "/partner/notifications", label: t('partnerNav.notifications') },
    { href: "/partner/settings", label: t('partnerNav.settings') },
  ];

  const activeNavLinks = isAdmin ? adminNavLinks : isPartner ? partnerNavLinks : [];

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
              <Link href="/dashboard" style={{ textDecoration: "none", color: "#666", fontSize: 12 }}>{t('operationsDashboard')}</Link>
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
                    <Link href="/settings/config" style={navLinkStyle}>{t('adminLinks.settings')}</Link>
                    <Link href="/users" style={navLinkStyle}>{t('adminLinks.userManagement')}</Link>
                    <Link href="/partner/dashboard" style={navLinkStyle}>{t('adminLinks.partnerDashboard')}</Link>
                    <Link href="/partner/users" style={navLinkStyle}>{t('adminLinks.testerManagement')}</Link>
                  </>
                )}
                <span style={{ color: "#666", fontSize: 12 }}>{user.username}</span>
                <button onClick={handleLogout} style={logoutButtonStyle}>{t('logout')}</button>
              </>
            )}
            {!isLoading && !user && (
              <Link href="/login" style={navLinkStyle}>{t('login')}</Link>
            )}
          </nav>

          {/* Hamburger button (mobile only) */}
          <button
            onClick={() => setMenuOpen(v => !v)}
            style={hamburgerButtonStyle}
            className="mobile-hamburger"
            aria-label={t('menuAriaLabel')}
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
                    <Link href="/settings/config" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>{t('adminLinks.settings')}</Link>
                    <Link href="/users" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>{t('adminLinks.userManagement')}</Link>
                    <Link href="/partner/dashboard" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>{t('adminLinks.partnerDashboard')}</Link>
                    <Link href="/partner/users" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>{t('adminLinks.testerManagement')}</Link>
                  </>
                )}
                <button onClick={handleLogout} style={mobileLogoutStyle}>{t('logout')}</button>
              </>
            )}
            {!isLoading && !user && (
              <Link href="/login" style={mobileNavLinkStyle} onClick={() => setMenuOpen(false)}>{t('login')}</Link>
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
