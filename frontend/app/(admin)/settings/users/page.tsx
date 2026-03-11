'use client'

// frontend/app/(admin)/settings/users/page.tsx
import React, { useState, useEffect, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  listUsers,
  createUser,
  updateUser,
  type CreateUserRequest,
  type UpdateUserRequest,
} from "@/lib/api/users";
import type { UserResponse } from "@/lib/api/auth";

export default function UsersManagementPage() {
  return (
    <AuthGuard adminOnly>
      <UsersManagementContent />
    </AuthGuard>
  );
}

function UsersManagementContent() {
  const { user: currentUser, token } = useAuth();

  const [users, setUsers] = useState<UserResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null);
  const [disableConfirm, setDisableConfirm] = useState<UserResponse | null>(null);
  const [inviteResult, setInviteResult] = useState<{ email: string; tempPassword: string } | null>(null);

  const loadUsers = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await listUsers(token);
      setUsers(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "ユーザーの読み込みに失敗しました";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleCreateUser = async (data: CreateUserRequest) => {
    if (!token) return;
    await createUser(token, data);
    setShowCreateModal(false);
    loadUsers();
  };

  const handleUpdateUser = async (userId: number, data: UpdateUserRequest) => {
    if (!token) return;
    await updateUser(token, userId, data);
    setEditingUser(null);
    loadUsers();
  };

  const handleToggleActive = async (user: UserResponse) => {
    if (!token) return;
    try {
      await updateUser(token, user.id, { is_active: !user.is_active });
      loadUsers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "操作に失敗しました";
      setError(msg);
    }
  };

  const handleQuickRoleChange = async (user: UserResponse, newRole: "admin" | "editor" | "viewer") => {
    if (!token) return;
    try {
      await updateUser(token, user.id, { role: newRole });
      loadUsers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "ロール変更に失敗しました";
      setError(msg);
    }
  };

  const handleInviteUser = async (email: string) => {
    if (!token) return;
    // Generate a random temp password (16 chars, alphanumeric + symbols)
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%";
    const tempPassword = Array.from({ length: 16 }, () =>
      chars[Math.floor(Math.random() * chars.length)]
    ).join("");

    // Derive username from email local part
    const username = email.split("@")[0].replace(/[^a-zA-Z0-9_]/g, "_").slice(0, 30) || "user";

    await createUser(token, { email, username, password: tempPassword, role: "viewer" });
    setShowInviteModal(false);
    setInviteResult({ email, tempPassword });
    loadUsers();
  };

  if (!currentUser) {
    return null;
  }

  return (
    <>
      <title>ユーザー管理 - Ultra AutoTrade</title>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>ユーザー管理</h1>
          <p style={{ marginTop: 0, color: "#555" }}>
            ユーザーアカウントと権限を管理します。
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="outline" size="sm" onClick={() => setShowInviteModal(true)}>
            招待
          </Button>
          <Button size="sm" onClick={() => setShowCreateModal(true)}>
            + ユーザー作成
          </Button>
        </div>
      </div>

      {error && <div style={errorStyle}>{error}</div>}

      {isLoading ? (
        <div style={{ padding: 40, textAlign: "center", color: "#666" }}>読み込み中...</div>
      ) : (
        <section style={tableContainerStyle}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>ID</th>
                <th style={thStyle}>メールアドレス</th>
                <th style={thStyle}>ユーザー名</th>
                <th style={thStyle}>ロール</th>
                <th style={thStyle}>ステータス</th>
                <th style={thStyle}>最終ログイン</th>
                <th style={thStyle}>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr
                  key={user.id}
                  style={user.id === currentUser.id ? currentUserRowStyle : undefined}
                >
                  <td style={tdStyle}>{user.id}</td>
                  <td style={tdStyle}>
                    {user.email}
                    {user.id === currentUser.id && (
                      <Badge variant="outline" className="ml-2" style={{ fontSize: 10 }}>
                        あなた
                      </Badge>
                    )}
                  </td>
                  <td style={tdStyle}>{user.username}</td>
                  <td style={tdStyle}>
                    {user.id === currentUser.id ? (
                      <RoleBadge role={user.role} />
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <RoleBadge role={user.role} />
                        <select
                          value={user.role}
                          onChange={(e) =>
                            handleQuickRoleChange(user, e.target.value as "admin" | "editor" | "viewer")
                          }
                          style={roleSelectStyle}
                          title="ロールを変更"
                        >
                          <option value="viewer">閲覧者</option>
                          <option value="editor">編集者</option>
                          <option value="admin">管理者</option>
                        </select>
                      </div>
                    )}
                  </td>
                  <td style={tdStyle}>
                    <StatusBadge isActive={user.is_active} />
                  </td>
                  <td style={{ ...tdStyle, color: "#999", fontSize: 13 }}>不明</td>
                  <td style={tdStyle}>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingUser(user)}
                      >
                        編集
                      </Button>
                      {user.id !== currentUser.id && (
                        <Button
                          variant={user.is_active ? "destructive" : "outline"}
                          size="sm"
                          onClick={() =>
                            user.is_active
                              ? setDisableConfirm(user)
                              : handleToggleActive(user)
                          }
                        >
                          {user.is_active ? "無効化" : "有効化"}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Create User Modal */}
      {showCreateModal && (
        <UserFormModal
          title="新規ユーザー作成"
          onSubmit={(data) => handleCreateUser(data as CreateUserRequest)}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {/* Edit User Modal */}
      {editingUser && (
        <UserFormModal
          title="ユーザー編集"
          user={editingUser}
          isCurrentUser={editingUser.id === currentUser.id}
          onSubmit={(data) => handleUpdateUser(editingUser.id, data as UpdateUserRequest)}
          onClose={() => setEditingUser(null)}
        />
      )}

      {/* Disable Confirmation Modal */}
      {disableConfirm && (
        <DisableConfirmModal
          user={disableConfirm}
          onConfirm={() => handleToggleActive(disableConfirm).then(() => setDisableConfirm(null))}
          onClose={() => setDisableConfirm(null)}
        />
      )}

      {/* Invite User Modal */}
      {showInviteModal && (
        <InviteUserModal
          onSubmit={handleInviteUser}
          onClose={() => setShowInviteModal(false)}
        />
      )}

      {/* Invite Result Modal */}
      {inviteResult && (
        <InviteResultModal
          email={inviteResult.email}
          tempPassword={inviteResult.tempPassword}
          onClose={() => setInviteResult(null)}
        />
      )}
    </>
  );
}

// Role Badge Component
function RoleBadge({ role }: { role: "admin" | "editor" | "viewer" }) {
  const config: Record<"admin" | "editor" | "viewer", { variant: "destructive" | "default" | "secondary"; label: string }> = {
    admin: { variant: "destructive", label: "管理者" },
    editor: { variant: "default", label: "編集者" },
    viewer: { variant: "secondary", label: "閲覧者" },
  };
  const { variant, label } = config[role] ?? config.viewer;
  return <Badge variant={variant}>{label}</Badge>;
}

// Status Badge Component
function StatusBadge({ isActive }: { isActive: boolean }) {
  return (
    <Badge variant={isActive ? "default" : "outline"}>
      {isActive ? "有効" : "無効"}
    </Badge>
  );
}

// Create/Edit Modal
interface UserFormModalProps {
  title: string;
  user?: UserResponse;
  isCurrentUser?: boolean;
  onSubmit: (data: CreateUserRequest | UpdateUserRequest) => Promise<void>;
  onClose: () => void;
}

function UserFormModal({ title, user, isCurrentUser, onSubmit, onClose }: UserFormModalProps) {
  const [email, setEmail] = useState(user?.email ?? "");
  const [username, setUsername] = useState(user?.username ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "editor" | "viewer">(user?.role ?? "viewer");
  const [isActive, setIsActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isEditing = !!user;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      if (isEditing) {
        const data: UpdateUserRequest = {};
        if (email !== user.email) data.email = email;
        if (username !== user.username) data.username = username;
        if (password) data.password = password;
        if (!isCurrentUser) {
          if (role !== user.role) data.role = role;
          if (isActive !== user.is_active) data.is_active = isActive;
        }
        await onSubmit(data);
      } else {
        if (!password || password.length < 8) {
          setError("パスワードは8文字以上必要です");
          setIsSubmitting(false);
          return;
        }
        await onSubmit({ email, username, password, role });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "操作に失敗しました";
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={modalOverlayStyle} onClick={onClose}>
      <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>{title}</h2>

        <form onSubmit={handleSubmit}>
          {error && <div style={errorStyle}>{error}</div>}

          <div style={{ marginBottom: 12 }}>
            <label style={inputLabelStyle}>メールアドレス</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
              required
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={inputLabelStyle}>ユーザー名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={inputStyle}
              required
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={inputLabelStyle}>
              {isEditing ? "新しいパスワード（変更しない場合は空欄）" : "パスワード"}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
              required={!isEditing}
              minLength={8}
            />
          </div>

          {!isCurrentUser && (
            <>
              <div style={{ marginBottom: 12 }}>
                <label style={inputLabelStyle}>ロール</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as "admin" | "editor" | "viewer")}
                  style={inputStyle}
                >
                  <option value="viewer">閲覧者</option>
                  <option value="editor">編集者</option>
                  <option value="admin">管理者</option>
                </select>
              </div>

              {isEditing && (
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={isActive}
                      onChange={(e) => setIsActive(e.target.checked)}
                    />
                    <span style={{ fontSize: 14 }}>有効</span>
                  </label>
                </div>
              )}
            </>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "保存中..." : "保存"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              キャンセル
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Disable Confirmation Modal
interface DisableConfirmModalProps {
  user: UserResponse;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}

function DisableConfirmModal({ user, onConfirm, onClose }: DisableConfirmModalProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setIsProcessing(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "操作に失敗しました";
      setError(msg);
      setIsProcessing(false);
    }
  };

  return (
    <div style={modalOverlayStyle} onClick={onClose}>
      <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>ユーザー無効化</h2>

        <p>
          ユーザー <strong>{user.username}</strong>（{user.email}）を無効化しますか？
        </p>
        <p style={{ color: "#c62828", fontSize: 14 }}>
          無効化されたユーザーはログインできなくなります。後から有効化することも可能です。
        </p>

        {error && <div style={errorStyle}>{error}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <Button variant="destructive" onClick={handleConfirm} disabled={isProcessing}>
            {isProcessing ? "処理中..." : "無効化"}
          </Button>
          <Button variant="outline" onClick={onClose}>
            キャンセル
          </Button>
        </div>
      </div>
    </div>
  );
}

// Invite User Modal
interface InviteUserModalProps {
  onSubmit: (email: string) => Promise<void>;
  onClose: () => void;
}

function InviteUserModal({ onSubmit, onClose }: InviteUserModalProps) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await onSubmit(email);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "招待に失敗しました";
      setError(msg);
      setIsSubmitting(false);
    }
  };

  return (
    <div style={modalOverlayStyle} onClick={onClose}>
      <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>ユーザー招待</h2>
        <p style={{ color: "#555", fontSize: 14, marginTop: 0 }}>
          メールアドレスを入力してください。一時パスワードが自動生成されます。
        </p>

        <form onSubmit={handleSubmit}>
          {error && <div style={errorStyle}>{error}</div>}

          <div style={{ marginBottom: 16 }}>
            <label style={inputLabelStyle}>メールアドレス</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
              placeholder="user@example.com"
              required
              autoFocus
            />
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "招待中..." : "招待する"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              キャンセル
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Invite Result Modal (shows temp password)
interface InviteResultModalProps {
  email: string;
  tempPassword: string;
  onClose: () => void;
}

function InviteResultModal({ email, tempPassword, onClose }: InviteResultModalProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(tempPassword);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard not available — ignore
    }
  };

  return (
    <div style={modalOverlayStyle} onClick={onClose}>
      <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>招待完了</h2>
        <p style={{ fontSize: 14, color: "#333" }}>
          <strong>{email}</strong> のアカウントを作成しました。
          以下の一時パスワードをユーザーに共有してください。
        </p>

        <div style={{
          background: "#f5f5f5",
          border: "1px solid #ddd",
          borderRadius: 8,
          padding: "12px 16px",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}>
          <code style={{ fontSize: 16, letterSpacing: 1, fontFamily: "monospace", wordBreak: "break-all" }}>
            {tempPassword}
          </code>
          <Button variant="ghost" size="sm" onClick={handleCopy} style={{ flexShrink: 0 }}>
            {copied ? "コピー済" : "コピー"}
          </Button>
        </div>

        <p style={{ fontSize: 12, color: "#c62828", margin: "0 0 16px" }}>
          このパスワードは再表示できません。今すぐ控えてください。
        </p>

        <Button onClick={onClose}>閉じる</Button>
      </div>
    </div>
  );
}

// Styles
const tableContainerStyle: React.CSSProperties = {
  marginTop: 20,
  overflowX: "auto",
  border: "1px solid #eee",
  borderRadius: 12,
  background: "#fff",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 14,
};

const thStyle: React.CSSProperties = {
  padding: "12px 16px",
  textAlign: "left",
  borderBottom: "1px solid #eee",
  background: "#f9f9f9",
  fontWeight: 500,
};

const tdStyle: React.CSSProperties = {
  padding: "12px 16px",
  borderBottom: "1px solid #f5f5f5",
};

const currentUserRowStyle: React.CSSProperties = {
  background: "#f0f4ff",
};

const roleSelectStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "2px 4px",
  border: "1px solid #ddd",
  borderRadius: 4,
  background: "#fff",
  cursor: "pointer",
  color: "#555",
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

const modalOverlayStyle: React.CSSProperties = {
  position: "fixed",
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: "rgba(0,0,0,0.5)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
};

const modalContentStyle: React.CSSProperties = {
  background: "#fff",
  padding: 24,
  borderRadius: 12,
  width: "100%",
  maxWidth: 420,
  maxHeight: "90vh",
  overflowY: "auto",
};

const inputLabelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: 4,
  fontSize: 14,
  color: "#333",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid #ddd",
  borderRadius: 8,
  fontSize: 14,
  boxSizing: "border-box",
};
