'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/(admin)/settings/users/page.tsx
import React, { useState, useEffect, useCallback } from "react";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("AdminSettingsUsers");
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
      const msg = err instanceof Error ? err.message : t("errorLoadUsers");
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [token, t]);

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
      const msg = err instanceof Error ? err.message : t("errorGeneric");
      setError(msg);
    }
  };

  const handleQuickRoleChange = async (user: UserResponse, newRole: "admin" | "partner" | "editor" | "viewer") => {
    if (!token) return;
    try {
      await updateUser(token, user.id, { role: newRole });
      loadUsers();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("errorRoleChange");
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
      <title>{t("pageTitle")}</title>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>{t("heading")}</h1>
          <p style={{ marginTop: 0, color: "#555" }}>
            {t("description")}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="outline" size="sm" onClick={() => setShowInviteModal(true)}>
            {t("inviteButton")}
          </Button>
          <Button size="sm" onClick={() => setShowCreateModal(true)}>
            {t("createButton")}
          </Button>
        </div>
      </div>

      {error && <div style={errorStyle}>{error}</div>}

      {isLoading ? (
        <div style={{ padding: 40, textAlign: "center", color: "#666" }}>{t("loading")}</div>
      ) : (
        <section style={tableContainerStyle}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>ID</th>
                <th style={thStyle}>{t("colEmail")}</th>
                <th style={thStyle}>{t("colUsername")}</th>
                <th style={thStyle}>{t("colRole")}</th>
                <th style={thStyle}>{t("colStatus")}</th>
                <th style={thStyle}>{t("colLastLogin")}</th>
                <th style={thStyle}>{t("colActions")}</th>
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
                        {t("youBadge")}
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
                            handleQuickRoleChange(user, e.target.value as "admin" | "partner" | "editor" | "viewer")
                          }
                          style={roleSelectStyle}
                          title={t("roleChangeTitle")}
                        >
                          <option value="viewer">{t("roles.viewer")}</option>
                          <option value="editor">{t("roles.editor")}</option>
                          <option value="partner">{t("roles.partner")}</option>
                          <option value="admin">{t("roles.admin")}</option>
                        </select>
                      </div>
                    )}
                  </td>
                  <td style={tdStyle}>
                    <StatusBadge isActive={user.is_active} />
                  </td>
                  <td style={{ ...tdStyle, color: "#999", fontSize: 13 }}>{t("lastLoginUnknown")}</td>
                  <td style={tdStyle}>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingUser(user)}
                      >
                        {t("editButton")}
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
                          {user.is_active ? t("disableButton") : t("enableButton")}
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
          title={t("createModalTitle")}
          onSubmit={(data) => handleCreateUser(data as CreateUserRequest)}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {/* Edit User Modal */}
      {editingUser && (
        <UserFormModal
          title={t("editModalTitle")}
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
function RoleBadge({ role }: { role: "admin" | "partner" | "editor" | "viewer" }) {
  const t = useTranslations("AdminSettingsUsers");
  const variantMap: Record<"admin" | "partner" | "editor" | "viewer", "destructive" | "default" | "secondary"> = {
    admin: "destructive",
    partner: "default",
    editor: "default",
    viewer: "secondary",
  };
  const variant = variantMap[role] ?? variantMap.viewer;
  return <Badge variant={variant}>{t(`roles.${role}`)}</Badge>;
}

// Status Badge Component
function StatusBadge({ isActive }: { isActive: boolean }) {
  const t = useTranslations("AdminSettingsUsers");
  return (
    <Badge variant={isActive ? "default" : "outline"}>
      {isActive ? t("statusActive") : t("statusInactive")}
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
  const t = useTranslations("AdminSettingsUsers");
  const [email, setEmail] = useState(user?.email ?? "");
  const [username, setUsername] = useState(user?.username ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "partner" | "editor" | "viewer">(user?.role ?? "viewer");
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
          setError(t("errorPasswordLength"));
          setIsSubmitting(false);
          return;
        }
        await onSubmit({ email, username, password, role });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("errorGeneric");
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
            <label style={inputLabelStyle}>{t("fieldEmail")}</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
              required
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={inputLabelStyle}>{t("fieldUsername")}</label>
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
              {isEditing ? t("fieldPasswordEdit") : t("fieldPassword")}
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
                <label style={inputLabelStyle}>{t("fieldRole")}</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as "admin" | "partner" | "editor" | "viewer")}
                  style={inputStyle}
                >
                  <option value="viewer">{t("roles.viewer")}</option>
                  <option value="editor">{t("roles.editor")}</option>
                  <option value="partner">{t("roles.partner")}</option>
                  <option value="admin">{t("roles.admin")}</option>
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
                    <span style={{ fontSize: 14 }}>{t("fieldActive")}</span>
                  </label>
                </div>
              )}
            </>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? t("saving") : t("save")}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("cancel")}
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
  const t = useTranslations("AdminSettingsUsers");
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setIsProcessing(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("errorGeneric");
      setError(msg);
      setIsProcessing(false);
    }
  };

  return (
    <div style={modalOverlayStyle} onClick={onClose}>
      <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>{t("disableModalTitle")}</h2>

        <p>
          {t("disableConfirmText", { username: user.username, email: user.email })}
        </p>
        <p style={{ color: "#c62828", fontSize: 14 }}>
          {t("disableWarning")}
        </p>

        {error && <div style={errorStyle}>{error}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <Button variant="destructive" onClick={handleConfirm} disabled={isProcessing}>
            {isProcessing ? t("processing") : t("disableButton")}
          </Button>
          <Button variant="outline" onClick={onClose}>
            {t("cancel")}
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
  const t = useTranslations("AdminSettingsUsers");
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
      const msg = err instanceof Error ? err.message : t("errorInvite");
      setError(msg);
      setIsSubmitting(false);
    }
  };

  return (
    <div style={modalOverlayStyle} onClick={onClose}>
      <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>{t("inviteModalTitle")}</h2>
        <p style={{ color: "#555", fontSize: 14, marginTop: 0 }}>
          {t("inviteModalDescription")}
        </p>

        <form onSubmit={handleSubmit}>
          {error && <div style={errorStyle}>{error}</div>}

          <div style={{ marginBottom: 16 }}>
            <label style={inputLabelStyle}>{t("fieldEmail")}</label>
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
              {isSubmitting ? t("inviting") : t("inviteSubmit")}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("cancel")}
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
  const t = useTranslations("AdminSettingsUsers");
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
        <h2 style={{ marginTop: 0 }}>{t("inviteResultTitle")}</h2>
        <p style={{ fontSize: 14, color: "#333" }}>
          {t("inviteResultText", { email })}
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
            {copied ? t("copiedButton") : t("copyButton")}
          </Button>
        </div>

        <p style={{ fontSize: 12, color: "#c62828", margin: "0 0 16px" }}>
          {t("passwordWarning")}
        </p>

        <Button onClick={onClose}>{t("closeButton")}</Button>
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
