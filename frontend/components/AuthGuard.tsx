'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/components/AuthGuard.tsx
/**
 * Authentication guard component.
 *
 * Redirects to the login page when unauthenticated.
 * Blocks non-admin users when adminOnly is true.
 */

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "../lib/auth";

interface AuthGuardProps {
  children: React.ReactNode;
  adminOnly?: boolean;
}

export default function AuthGuard({ children, adminOnly = false }: AuthGuardProps) {
  const { isAuthenticated, isAdmin, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated) {
      // Redirect with current path in query string
      router.replace(`/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }

    if (adminOnly && !isAdmin) {
      // Non-admin user attempted to access an admin-only page
      router.replace("/dashboard");
      return;
    }
  }, [isAuthenticated, isAdmin, isLoading, adminOnly, router, pathname]);

  if (isLoading) {
    return (
      <div style={{ padding: 40, textAlign: "center" }}>
        <div>Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null; // Redirecting
  }

  if (adminOnly && !isAdmin) {
    return null; // Redirecting
  }

  return <>{children}</>;
}