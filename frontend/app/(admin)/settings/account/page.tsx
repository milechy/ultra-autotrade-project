'use client'

// frontend/app/(admin)/settings/account/page.tsx
import React, { useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { changePassword } from "@/lib/api/auth";
import RiskModeSelector from "@/components/settings/RiskModeSelector";

export default function AccountSettingsPage() {
  return (
    <AuthGuard>
      <AccountSettingsContent />
    </AuthGuard>
  );
}

function AccountSettingsContent() {
  const { user, token } = useAuth();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (newPassword !== confirmPassword) {
      setError("新しいパスワードが一致しません");
      return;
    }

    if (newPassword.length < 8) {
      setError("新しいパスワードは8文字以上必要です");
      return;
    }

    if (!token) {
      setError("認証されていません");
      return;
    }

    setIsSubmitting(true);
    try {
      await changePassword(token, {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setSuccess("パスワードを変更しました");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setError(err?.message || "パスワード変更に失敗しました");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!user) {
    return null;
  }

  return (
    <>
      <title>アカウント設定 - Ultra AutoTrade</title>

      <h1 style={{ marginBottom: 6 }}>アカウント設定</h1>
      <p style={{ marginTop: 0, color: "#555" }}>
        プロフィール情報の確認とパスワード変更ができます。
      </p>

      {/* Profile Section */}
      <section style={sectionStyle}>
        <h2 style={{ margin: 0, fontSize: 16 }}>プロフィール情報</h2>
        <div style={{ marginTop: 16 }}>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>メールアドレス</span>
            <span style={valueStyle}>{user.email}</span>
          </div>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>ユーザー名</span>
            <span style={valueStyle}>{user.username}</span>
          </div>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>ロール</span>
            <span style={valueStyle}>
              <span style={{
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 12,
                background: user.role === "admin" ? "#e8f5e9" : "#e3f2fd",
                color: user.role === "admin" ? "#2e7d32" : "#1565c0",
              }}>
                {user.role === "admin" ? "管理者" : "閲覧者"}
              </span>
            </span>
          </div>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>ステータス</span>
            <span style={valueStyle}>
              <span style={{
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 12,
                background: user.is_active ? "#e8f5e9" : "#ffebee",
                color: user.is_active ? "#2e7d32" : "#c62828",
              }}>
                {user.is_active ? "有効" : "無効"}
              </span>
            </span>
          </div>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>作成日時</span>
            <span style={valueStyle}>{new Date(user.created_at).toLocaleString()}</span>
          </div>
        </div>
      </section>

      {/* Password Change Section */}
      <section style={sectionStyle}>
        <h2 style={{ margin: 0, fontSize: 16 }}>パスワード変更</h2>
        <form onSubmit={handleChangePassword} style={{ marginTop: 16 }}>
          {error && (
            <div style={errorStyle}>{error}</div>
          )}
          {success && (
            <div style={successStyle}>{success}</div>
          )}

          <div style={{ marginBottom: 12 }}>
            <label style={inputLabelStyle}>現在のパスワード</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              style={inputStyle}
              required
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={inputLabelStyle}>新しいパスワード</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              style={inputStyle}
              required
              minLength={8}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={inputLabelStyle}>新しいパスワード（確認）</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              style={inputStyle}
              required
              minLength={8}
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            style={buttonStyle}
          >
            {isSubmitting ? "変更中..." : "パスワードを変更"}
          </button>
        </form>
      </section>

      <section className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/60 p-6">
        <RiskModeSelector />
      </section>
    </>
  );
}

const sectionStyle: React.CSSProperties = {
  marginTop: 24,
  padding: 20,
  border: "1px solid #eee",
  borderRadius: 12,
  background: "#fff",
};

const fieldRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  padding: "8px 0",
  borderBottom: "1px solid #f5f5f5",
};

const labelStyle: React.CSSProperties = {
  width: 120,
  color: "#666",
  fontSize: 14,
};

const valueStyle: React.CSSProperties = {
  flex: 1,
  fontSize: 14,
};

const inputLabelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: 4,
  fontSize: 14,
  color: "#333",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: 300,
  padding: "8px 12px",
  border: "1px solid #ddd",
  borderRadius: 8,
  fontSize: 14,
};

const buttonStyle: React.CSSProperties = {
  padding: "10px 20px",
  background: "#1976d2",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  fontSize: 14,
  cursor: "pointer",
};

const errorStyle: React.CSSProperties = {
  marginBottom: 12,
  padding: 12,
  border: "1px solid #f1c0c0",
  background: "#fff5f5",
  borderRadius: 8,
  color: "#c62828",
  fontSize: 14,
};

const successStyle: React.CSSProperties = {
  marginBottom: 12,
  padding: 12,
  border: "1px solid #c8e6c9",
  background: "#e8f5e9",
  borderRadius: 8,
  color: "#2e7d32",
  fontSize: 14,
};
