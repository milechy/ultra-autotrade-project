'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/login/page.tsx
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, FormEvent, Suspense } from "react";
import { useAuth, AuthProvider } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";

/**
 * リダイレクト先を検証し、安全なパスのみ許可する。
 * Open Redirect 攻撃を防ぐため、同一オリジンのパスのみ許可。
 */
function getSafeRedirect(redirect: string | null): string {
  const defaultPath = "/dashboard";

  if (!redirect) {
    return defaultPath;
  }

  // 同一オリジンのパスのみ許可（/ で始まり、// を含まない）
  if (redirect.startsWith("/") && !redirect.startsWith("//")) {
    return redirect;
  }

  return defaultPath;
}

function getRoleDefaultPath(role: string | undefined): string {
  if (role === "admin") return "/dashboard";
  if (role === "partner") return "/partner/dashboard";
  return "/user/dashboard";
}

function LoginForm() {
  const { login, isAuthenticated, isLoading, user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const redirectParam = searchParams.get("redirect");

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      const dest = redirectParam
        ? getSafeRedirect(redirectParam)
        : getRoleDefaultPath(user?.role);
      router.replace(dest);
    }
  }, [isAuthenticated, isLoading, redirectParam, router, user?.role]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const loggedInUser = await login(email, password);
      const dest = redirectParam
        ? getSafeRedirect(redirectParam)
        : getRoleDefaultPath(loggedInUser.role);
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

  if (isAuthenticated) {
    return null;
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Ultra AutoTrade</CardTitle>
          <CardDescription>運用ダッシュボード</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">メールアドレス</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                disabled={submitting}
                placeholder="admin@example.com"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">パスワード</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                disabled={submitting}
              />
            </div>

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "ログイン中..." : "ログイン"}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            初期設定が必要な場合は管理者にお問い合わせください。
          </p>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            <a
              href="/admin/login"
              className="underline hover:text-foreground"
              data-testid="login-admin-link"
            >
              管理者の方はこちら
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}

export default function LoginPage() {
  return (
    <AuthProvider>
      <title>ログイン - Ultra AutoTrade</title>
      <Suspense fallback={
        <div className="flex min-h-screen items-center justify-center">
          <p className="text-muted-foreground">読み込み中...</p>
        </div>
      }>
        <LoginForm />
      </Suspense>
    </AuthProvider>
  );
}
