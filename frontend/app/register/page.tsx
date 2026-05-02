'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/register/page.tsx
// 招待コード付きユーザー登録ページ（認証不要）
// B方式: URLにcodeがある場合はプリフィル+読み取り専用、ない場合は手動入力
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, FormEvent, Suspense } from "react";
import { apiFetch, apiPost } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, CheckCircle2, Loader2, Wallet } from "lucide-react";

interface InvitationResponse {
  valid: boolean;
  partner_id?: number;
  expires_at?: string;
  uses_remaining?: number;
}

interface RegisterResponse {
  id: number;
  email: string;
  username: string;
  role: string;
  is_active: boolean;
  access_token: string;
  token_type: string;
  expires_in: number;
}

type CodeStatus = "idle" | "checking" | "valid" | "invalid";

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlCode = searchParams.get("code"); // URL から取得したコード（変更不可）

  // 招待コード: URL からプリフィル、ない場合は手動入力
  const [invitationCode, setInvitationCode] = useState(urlCode ?? "");
  const [codeStatus, setCodeStatus] = useState<CodeStatus>(urlCode ? "checking" : "idle");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // URLコードが存在する場合は自動検証
  useEffect(() => {
    if (!urlCode) return;
    setCodeStatus("checking");
    apiFetch<InvitationResponse>(`/api/invitations/${encodeURIComponent(urlCode)}`)
      .then((inv) => setCodeStatus(inv.valid ? "valid" : "invalid"))
      .catch(() => setCodeStatus("invalid"));
  }, [urlCode]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const code = invitationCode.trim();
    if (!code) {
      setError("招待コードを入力してください");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const result = await apiPost<RegisterResponse>("/auth/register", {
        email,
        username: displayName,
        password,
        invitation_code: code,
      });
      // 登録完了 → トークンを保存して自動ログイン
      localStorage.setItem("ultra_auth_token", result.access_token);
      localStorage.setItem("ultra_auth_expires", String(Date.now() + result.expires_in * 1000));
      router.replace("/user/dashboard");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "登録に失敗しました";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  // URLコードが無効の場合はサブミットを無効化
  const submitDisabled =
    submitting ||
    codeStatus === "checking" ||
    (Boolean(urlCode) && codeStatus === "invalid");

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-muted/40 p-4">
      {/* Deprecation banner: 一般ユーザーは /connect (Privy) に誘導、管理者専用 */}
      <div
        role="status"
        aria-label="メール登録は管理者専用です"
        data-testid="register-deprecation-banner"
        className="w-full max-w-sm mb-4 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
      >
        <p className="font-semibold flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          メール登録は管理者専用です
        </p>
        <p className="mt-1 text-xs">
          一般ユーザーの方は<a href="/connect" className="font-semibold underline underline-offset-2 mx-1">ウォレット接続</a>で開始してください。
        </p>
        <a
          href="/connect"
          className="mt-2 inline-flex items-center gap-1.5 rounded border border-amber-400 bg-white px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100 dark:bg-amber-900 dark:text-amber-50 dark:hover:bg-amber-800"
          data-testid="register-banner-connect-link"
        >
          <Wallet className="h-3.5 w-3.5" />
          ウォレットで始める
        </a>
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Ultra AutoTrade</CardTitle>
          <CardDescription>アカウント登録（管理者用）</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* 招待コード */}
            <div className="space-y-1.5">
              <Label htmlFor="invitationCode">招待コード</Label>
              {urlCode ? (
                // URL からプリフィル: 読み取り専用表示
                <div className={`flex items-center gap-2 rounded-md border px-3 py-2 bg-muted text-sm font-mono ${
                  codeStatus === "invalid" ? "border-destructive" : "border-input"
                }`}>
                  <span className="flex-1 truncate text-foreground">{invitationCode}</span>
                  {codeStatus === "checking" && (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
                  )}
                  {codeStatus === "valid" && (
                    <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
                  )}
                  {codeStatus === "invalid" && (
                    <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
                  )}
                </div>
              ) : (
                // 手動入力
                <Input
                  id="invitationCode"
                  type="text"
                  value={invitationCode}
                  onChange={(e) => setInvitationCode(e.target.value)}
                  required
                  placeholder="招待コードを入力してください"
                  disabled={submitting}
                  autoComplete="off"
                />
              )}
              {codeStatus === "invalid" && urlCode && (
                <p className="text-xs text-destructive">
                  招待コードが無効または期限切れです。担当者にお問い合わせください。
                </p>
              )}
              {codeStatus === "valid" && (
                <p className="text-xs text-green-600">招待コードが確認されました</p>
              )}
            </div>

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
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="displayName">表示名</Label>
              <Input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
                autoComplete="username"
                disabled={submitting}
                placeholder="山田太郎"
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
                autoComplete="new-password"
                disabled={submitting}
              />
            </div>

            <Button type="submit" className="w-full" disabled={submitDisabled}>
              {submitting ? "登録中..." : "アカウントを作成"}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            すでにアカウントをお持ちの方は
            <a href="/login" className="underline underline-offset-4 hover:text-primary ml-1">
              ログイン
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}

export default function RegisterPage() {
  return (
    <>
      <title>アカウント登録 - Ultra AutoTrade</title>
      <Suspense fallback={
        <div className="flex min-h-screen items-center justify-center">
          <p className="text-muted-foreground">読み込み中...</p>
        </div>
      }>
        <RegisterForm />
      </Suspense>
    </>
  );
}
