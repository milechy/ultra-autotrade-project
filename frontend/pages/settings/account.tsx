// frontend/pages/settings/account.tsx
/**
 * アカウント設定ページ。
 *
 * - プロフィール情報表示
 * - パスワード変更
 */

import Head from "next/head";
import React, { useState } from "react";
import AppShell from "../../components/layout/AppShell";
import AuthGuard from "../../components/AuthGuard";
import { useAuth } from "../../lib/auth";
import { changePassword } from "../../lib/api/auth";

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
      setError("New passwords do not match");
      return;
    }

    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters");
      return;
    }

    if (!token) {
      setError("Not authenticated");
      return;
    }

    setIsSubmitting(true);
    try {
      await changePassword(token, {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setSuccess("Password changed successfully");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setError(err?.message || "Failed to change password");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!user) {
    return null;
  }

  return (
    <AppShell>
      <Head>
        <title>Account Settings - Ultra AutoTrade</title>
      </Head>

      <h1 style={{ marginBottom: 6 }}>Account Settings</h1>
      <p style={{ marginTop: 0, color: "#555" }}>
        View your profile and change your password.
      </p>

      {/* Profile Section */}
      <section style={sectionStyle}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Profile Information</h2>
        <div style={{ marginTop: 16 }}>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>Email</span>
            <span style={valueStyle}>{user.email}</span>
          </div>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>Username</span>
            <span style={valueStyle}>{user.username}</span>
          </div>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>Role</span>
            <span style={valueStyle}>
              <span style={{
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 12,
                background: user.role === "admin" ? "#e8f5e9" : "#e3f2fd",
                color: user.role === "admin" ? "#2e7d32" : "#1565c0",
              }}>
                {user.role}
              </span>
            </span>
          </div>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>Status</span>
            <span style={valueStyle}>
              <span style={{
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 12,
                background: user.is_active ? "#e8f5e9" : "#ffebee",
                color: user.is_active ? "#2e7d32" : "#c62828",
              }}>
                {user.is_active ? "Active" : "Inactive"}
              </span>
            </span>
          </div>
          <div style={fieldRowStyle}>
            <span style={labelStyle}>Created</span>
            <span style={valueStyle}>{new Date(user.created_at).toLocaleString()}</span>
          </div>
        </div>
      </section>

      {/* Password Change Section */}
      <section style={sectionStyle}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Change Password</h2>
        <form onSubmit={handleChangePassword} style={{ marginTop: 16 }}>
          {error && (
            <div style={errorStyle}>{error}</div>
          )}
          {success && (
            <div style={successStyle}>{success}</div>
          )}

          <div style={{ marginBottom: 12 }}>
            <label style={inputLabelStyle}>Current Password</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              style={inputStyle}
              required
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={inputLabelStyle}>New Password</label>
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
            <label style={inputLabelStyle}>Confirm New Password</label>
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
            {isSubmitting ? "Changing..." : "Change Password"}
          </button>
        </form>
      </section>
    </AppShell>
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
