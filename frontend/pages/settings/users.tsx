// frontend/pages/settings/users.tsx
/**
 * ユーザー管理ページ（管理者専用）。
 *
 * - ユーザー一覧表示
 * - ユーザー作成
 * - ユーザー編集
 * - ユーザー削除
 */

import Head from "next/head";
import React, { useState, useEffect, useCallback } from "react";
import AppShell from "../../components/layout/AppShell";
import AuthGuard from "../../components/AuthGuard";
import { useAuth } from "../../lib/auth";
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  type CreateUserRequest,
  type UpdateUserRequest,
} from "../../lib/api/users";
import type { UserResponse } from "../../lib/api/auth";

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
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<UserResponse | null>(null);

  const loadUsers = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await listUsers(token);
      setUsers(data);
    } catch (err: any) {
      setError(err?.message || "ユーザーの読み込みに失敗しました");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleCreateUser = async (data: CreateUserRequest) => {
    if (!token) return;
    try {
      await createUser(token, data);
      setShowCreateModal(false);
      loadUsers();
    } catch (err: any) {
      throw err;
    }
  };

  const handleUpdateUser = async (userId: number, data: UpdateUserRequest) => {
    if (!token) return;
    try {
      await updateUser(token, userId, data);
      setEditingUser(null);
      loadUsers();
    } catch (err: any) {
      throw err;
    }
  };

  const handleDeleteUser = async (userId: number) => {
    if (!token) return;
    try {
      await deleteUser(token, userId);
      setDeleteConfirm(null);
      loadUsers();
    } catch (err: any) {
      throw err;
    }
  };

  if (!currentUser) {
    return null;
  }

  return (
    <AppShell>
      <Head>
        <title>ユーザー管理 - Ultra AutoTrade</title>
      </Head>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>ユーザー管理</h1>
          <p style={{ marginTop: 0, color: "#555" }}>
            ユーザーアカウントと権限を管理します。
          </p>
        </div>
        <button onClick={() => setShowCreateModal(true)} style={primaryButtonStyle}>
          + ユーザー作成
        </button>
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
                <th style={thStyle}>作成日</th>
                <th style={thStyle}>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} style={user.id === currentUser.id ? currentUserRowStyle : undefined}>
                  <td style={tdStyle}>{user.id}</td>
                  <td style={tdStyle}>{user.email}</td>
                  <td style={tdStyle}>{user.username}</td>
                  <td style={tdStyle}>
                    <RoleBadge role={user.role} />
                  </td>
                  <td style={tdStyle}>
                    <span style={{
                      padding: "2px 8px",
                      borderRadius: 4,
                      fontSize: 12,
                      background: user.is_active ? "#e8f5e9" : "#ffebee",
                      color: user.is_active ? "#2e7d32" : "#c62828",
                    }}>
                      {user.is_active ? "有効" : "無効"}
                    </span>
                  </td>
                  <td style={tdStyle}>{new Date(user.created_at).toLocaleDateString()}</td>
                  <td style={tdStyle}>
                    <button
                      onClick={() => setEditingUser(user)}
                      style={actionButtonStyle}
                    >
                      編集
                    </button>
                    {user.id !== currentUser.id && (
                      <button
                        onClick={() => setDeleteConfirm(user)}
                        style={{ ...actionButtonStyle, color: "#c62828" }}
                      >
                        削除
                      </button>
                    )}
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

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <DeleteConfirmModal
          user={deleteConfirm}
          onConfirm={() => handleDeleteUser(deleteConfirm.id)}
          onClose={() => setDeleteConfirm(null)}
        />
      )}
    </AppShell>
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
  const [email, setEmail] = useState(user?.email || "");
  const [username, setUsername] = useState(user?.username || "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "editor" | "viewer">(user?.role || "viewer");
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
    } catch (err: any) {
      setError(err?.message || "操作に失敗しました");
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
            <button type="submit" disabled={isSubmitting} style={primaryButtonStyle}>
              {isSubmitting ? "保存中..." : "保存"}
            </button>
            <button type="button" onClick={onClose} style={secondaryButtonStyle}>
              キャンセル
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Role Badge Component
function RoleBadge({ role }: { role: "admin" | "editor" | "viewer" }) {
  const styles: Record<string, { background: string; color: string; label: string }> = {
    admin: { background: "#ffebee", color: "#c62828", label: "管理者" },
    editor: { background: "#e3f2fd", color: "#1565c0", label: "編集者" },
    viewer: { background: "#f5f5f5", color: "#616161", label: "閲覧者" },
  };
  const s = styles[role] ?? styles.viewer;
  return (
    <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 12, background: s.background, color: s.color }}>
      {s.label}
    </span>
  );
}

// Delete Confirmation Modal
interface DeleteConfirmModalProps {
  user: UserResponse;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}

function DeleteConfirmModal({ user, onConfirm, onClose }: DeleteConfirmModalProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setIsDeleting(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err: any) {
      setError(err?.message || "ユーザーの削除に失敗しました");
      setIsDeleting(false);
    }
  };

  return (
    <div style={modalOverlayStyle} onClick={onClose}>
      <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>ユーザー削除</h2>

        <p>ユーザー <strong>{user.username}</strong>（{user.email}）を削除しますか？</p>
        <p style={{ color: "#c62828" }}>この操作は取り消せません。</p>

        {error && <div style={errorStyle}>{error}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <button
            onClick={handleConfirm}
            disabled={isDeleting}
            style={{ ...primaryButtonStyle, background: "#c62828" }}
          >
            {isDeleting ? "削除中..." : "削除"}
          </button>
          <button onClick={onClose} style={secondaryButtonStyle}>
            キャンセル
          </button>
        </div>
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
  background: "#f5f5f5",
};

const actionButtonStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#1976d2",
  cursor: "pointer",
  padding: "4px 8px",
  fontSize: 13,
};

const primaryButtonStyle: React.CSSProperties = {
  padding: "10px 20px",
  background: "#1976d2",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  fontSize: 14,
  cursor: "pointer",
};

const secondaryButtonStyle: React.CSSProperties = {
  padding: "10px 20px",
  background: "#fff",
  color: "#333",
  border: "1px solid #ddd",
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
  maxWidth: 400,
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
