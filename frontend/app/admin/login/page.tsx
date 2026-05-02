'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/admin/login/page.tsx
//
// 管理者専用ログインページ (/admin/login)。
// /login (汎用) からの分離。設計仕様書 §1.1「管理者=メール/PW、ユーザー=ウォレット」に準拠。
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, FormEvent, Suspense } from "react";
import Script from "next/script";
import { useAuth, AuthProvider } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, ShieldCheck } from "lucide-react";

const RECAPTCHA_SITE_KEY = process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY ?? "";

interface GrecaptchaWindow {
  grecaptcha?: {
    ready: (cb: () => void) => void;
    execute: (siteKey: string, options: { action: string }) => Promise<string>;
  };
}

function getSafeRedirect(redirect: string | null): string {
  const defaultPath = "/dashboard";
  if (!redirect) return defaultPath;
  if (redirect.startsWith("/") && !redirect.startsWith("//")) return redirect;
  return defaultPath;
}

async function getRecaptchaToken(): Promise<string | null> {
  if (!RECAPTCHA_SITE_KEY) return null;
  if (typeof window === "undefined") return null;
  const w = window as unknown as GrecaptchaWindow;
  if (!w.grecaptcha) return null;
  return new Promise<string | null>((resolve) => {
    w.grecaptcha!.ready(() => {
      w.grecaptcha!
        .execute(RECAPTCHA_SITE_KEY, { action: "admin_login" })
        .then((token) => resolve(token))
        .catch(() => resolve(null));
    });
  });
}

function AdminLoginForm() {
  const { login, logout, isAuthenticated, isLoading, isAdmin, user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const redirectParam = searchParams.get("redirect");

  useEffect(() => {
    if (isLoading) return;
    if (isAuthenticated && isAdmin) {
      const dest = redirectParam ? getSafeRedirect(redirectParam) : "/dashboard";
      router.replace(dest);
    }
  }, [isAuthenticated, isAdmin, isLoading, redirectParam, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      // reCAPTCHA v3 トークン取得 (サイトキー未設定時はスキップ)。
      // 取得した token はバックエンドが将来検証する想定 (現状は理論的足場)。
      await getRecaptchaToken();

      const loggedInUser = await login(email, password);

      if (loggedInUser.role !== "admin") {
        // 管理者以外でログインを試みた場合は即ログアウトしてエラー表示。
        await logout();
        setError("このページは管理者専用です。一般ユーザーはトップページからアクセスしてください。");
        return;
      }

      const dest = redirectParam ? getSafeRedirect(redirectParam) : "/dashboard";
      router.replace(dest);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "ログインに失敗しました";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">読み込み中...</p>
      </div>
    );
  }

  // 既に管理者でログイン済みなら useEffect でリダイレクト済み。
  // それ以外 (未ログイン or 非管理者) はフォームを表示する。
  if (isAuthenticated && isAdmin) {
    return null;
  }

  // 非管理者で既にログイン中の場合: フォーム上部に切り替え案内を表示。
  const wrongRoleNotice =
    isAuthenticated && user?.role && user.role !== "admin"
      ? `現在 ${user.role} ロールでログイン中です。管理者で再ログインするか、トップページに戻ってください。`
      : null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      {RECAPTCHA_SITE_KEY ? (
        <Script
          src={`https://www.google.com/recaptcha/api.js?render=${RECAPTCHA_SITE_KEY}`}
          strategy="afterInteractive"
        />
      ) : null}
      <Card className="w-full max-w-sm" data-testid="admin-login-card">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <ShieldCheck className="h-5 w-5 text-primary" />
          </div>
          <CardTitle className="text-2xl">管理者ログイン</CardTitle>
          <CardDescription>Ultra AutoTrade 運用ダッシュボード</CardDescription>
        </CardHeader>
        <CardContent>
          {wrongRoleNotice ? (
            <Alert className="mb-4" data-testid="admin-login-wrong-role">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{wrongRoleNotice}</AlertDescription>
            </Alert>
          ) : null}
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <Alert variant="destructive" data-testid="admin-login-error">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="admin-email">メールアドレス</Label>
              <Input
                id="admin-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                disabled={submitting}
                placeholder="admin@example.com"
                data-testid="admin-login-email"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="admin-password">パスワード</Label>
              <Input
                id="admin-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                disabled={submitting}
                data-testid="admin-login-password"
              />
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={submitting}
              data-testid="admin-login-submit"
            >
              {submitting ? "ログイン中..." : "管理者としてログイン"}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            このページは管理者専用です。一般ユーザーは{" "}
            <a href="/" className="underline">トップページ</a>
            {" "}からアクセスしてください。
          </p>
        </CardContent>
      </Card>
    </main>
  );
}

export default function AdminLoginPage() {
  return (
    <AuthProvider>
      <title>管理者ログイン - Ultra AutoTrade</title>
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center">
            <p className="text-muted-foreground">読み込み中...</p>
          </div>
        }
      >
        <AdminLoginForm />
      </Suspense>
    </AuthProvider>
  );
}
