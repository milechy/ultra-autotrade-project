// frontend/components/AuthGuard.tsx
/**
 * 認証ガードコンポーネント。
 *
 * 未認証の場合はログインページにリダイレクト。
 * adminOnly の場合は管理者以外をブロック。
 */

import { useEffect } from "react";
import { useRouter } from "next/router";
import { useAuth } from "../lib/auth";

interface AuthGuardProps {
  children: React.ReactNode;
  adminOnly?: boolean;
}

export default function AuthGuard({ children, adminOnly = false }: AuthGuardProps) {
  const { isAuthenticated, isAdmin, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated) {
      // 現在のパスをクエリに含めてリダイレクト
      router.replace(`/login?redirect=${encodeURIComponent(router.asPath)}`);
      return;
    }

    if (adminOnly && !isAdmin) {
      // 管理者専用ページに非管理者がアクセスした場合
      router.replace("/dashboard");
      return;
    }
  }, [isAuthenticated, isAdmin, isLoading, adminOnly, router]);

  if (isLoading) {
    return (
      <div style={{ padding: 40, textAlign: "center" }}>
        <div>Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null; // リダイレクト中
  }

  if (adminOnly && !isAdmin) {
    return null; // リダイレクト中
  }

  return <>{children}</>;
}
