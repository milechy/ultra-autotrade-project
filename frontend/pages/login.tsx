// frontend/pages/login.tsx
/**
 * ログインページ。
 */

import Head from "next/head";
import { useRouter } from "next/router";
import { useState, useEffect, FormEvent } from "react";
import { useAuth } from "../lib/auth";

/**
 * リダイレクト先を検証し、安全なパスのみ許可する。
 * Open Redirect 攻撃を防ぐため、同一オリジンのパスのみ許可。
 */
function getSafeRedirect(redirect: string | undefined): string {
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

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // router.query.redirect は string | string[] | undefined のため正規化
  const rawRedirect = router.query.redirect;
  const redirect = getSafeRedirect(
    Array.isArray(rawRedirect) ? rawRedirect[0] : rawRedirect
  );

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace(redirect);
    }
  }, [isAuthenticated, isLoading, redirect, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await login(email, password);
      router.replace(redirect);
    } catch (err: any) {
      setError(err?.message || "ログインに失敗しました");
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <div style={{ padding: 40, textAlign: "center" }}>
        <div>読み込み中...</div>
      </div>
    );
  }

  if (isAuthenticated) {
    return null; // リダイレクト中
  }

  return (
    <>
      <Head>
        <title>ログイン - Ultra AutoTrade</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <main style={mainStyle}>
        <div style={cardStyle}>
          <h1 style={{ margin: 0, marginBottom: 8 }}>Ultra AutoTrade</h1>
          <p style={{ margin: 0, marginBottom: 24, color: "#666" }}>
            運用ダッシュボード
          </p>

          <form onSubmit={handleSubmit}>
            {error && (
              <div style={errorStyle}>
                {error}
              </div>
            )}

            <div style={fieldStyle}>
              <label style={labelStyle}>メールアドレス</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                style={inputStyle}
                disabled={submitting}
              />
            </div>

            <div style={fieldStyle}>
              <label style={labelStyle}>パスワード</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                style={inputStyle}
                disabled={submitting}
              />
            </div>

            <button
              type="submit"
              style={buttonStyle}
              disabled={submitting}
            >
              {submitting ? "ログイン中..." : "ログイン"}
            </button>
          </form>

          <p style={{ marginTop: 24, fontSize: 12, color: "#999", textAlign: "center" }}>
            初期設定が必要な場合は管理者にお問い合わせください。
          </p>
        </div>
      </main>
    </>
  );
}

const mainStyle: React.CSSProperties = {
  fontFamily: "system-ui, sans-serif",
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "#f5f5f5",
  padding: 20,
};

const cardStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: 12,
  padding: 32,
  width: "100%",
  maxWidth: 400,
  boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
};

const fieldStyle: React.CSSProperties = {
  marginBottom: 16,
};

const labelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: 6,
  fontSize: 14,
  fontWeight: 500,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  fontSize: 14,
  border: "1px solid #ddd",
  borderRadius: 8,
  boxSizing: "border-box",
};

const buttonStyle: React.CSSProperties = {
  width: "100%",
  padding: "12px 16px",
  fontSize: 14,
  fontWeight: 600,
  color: "#fff",
  background: "#333",
  border: "none",
  borderRadius: 8,
  cursor: "pointer",
  marginTop: 8,
};

const errorStyle: React.CSSProperties = {
  marginBottom: 16,
  padding: 12,
  background: "#fff5f5",
  border: "1px solid #f1c0c0",
  borderRadius: 8,
  color: "#c00",
  fontSize: 14,
};
