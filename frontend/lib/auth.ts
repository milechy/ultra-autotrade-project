'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/lib/auth.ts
/**
 * Authentication state management.
 *
 * - Stores token in localStorage
 * - Exposes auth state via useAuth hook
 * - Wrap component tree with AuthProvider to use
 *
 * Security note:
 * - Using localStorage is vulnerable to XSS attacks.
 * - For production, one of the following is recommended:
 *   1. HttpOnly Cookie + SameSite=Strict
 *   2. In-Memory Token + Refresh Token (HttpOnly Cookie)
 * - Currently, XSS risk is mitigated via CSP (Content Security Policy).
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { login as apiLogin, getMe, logout as apiLogout, walletConnect, type UserResponse, type TokenResponse } from "./api/auth";
import { resolveAuthReady } from "./auth-state";
import { recordLastSeen } from "./auth/session-monitor";

const TOKEN_KEY = "ultra_auth_token";
const TOKEN_EXPIRES_KEY = "ultra_auth_expires";

/** ethers.Signer の signMessage だけを使う duck-typed interface */
interface WalletSigner {
  signMessage: (message: string | Uint8Array) => Promise<string>;
}

interface AuthContextType {
  user: UserResponse | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isPartner: boolean;
  /**
   * 初期化時の getMe() が timeout / ネットワーク失敗した場合に設定される。
   * 画面上部にバナーを表示して再読み込みを促す用途。401/403 は認証期限切れと
   * みなして null のまま (通常のログイン画面に誘導される)。
   */
  authInitError: string | null;
  login: (email: string, password: string) => Promise<UserResponse>;
  loginWithWallet: (address: string, signer: WalletSigner) => Promise<UserResponse>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

const AUTH_INIT_ERROR_MESSAGE = "接続に失敗しました。再読み込みしてください。";

function isAbortError(err: unknown): boolean {
  if (!err || typeof err !== "object") return false;
  const name = (err as { name?: unknown }).name;
  return name === "AbortError" || name === "TimeoutError";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authInitError, setAuthInitError] = useState<string | null>(null);

  // Restore token on initialization
  useEffect(() => {
    // ITP wipe 検知用の last_seen を更新 (token の有無に関わらず常に記録)。
    // 7日 ITP wipe で token が消えていても last_seen が残っていれば wipe を検知できる。
    recordLastSeen();

    const storedToken = localStorage.getItem(TOKEN_KEY);
    const expiresStr = localStorage.getItem(TOKEN_EXPIRES_KEY);

    if (storedToken && expiresStr) {
      const expires = parseInt(expiresStr, 10);
      if (Date.now() < expires) {
        setToken(storedToken);
        // Fetch user information (getMe には AbortSignal.timeout(8s) が付与済み)
        getMe(storedToken)
          .then((u) => {
            setUser(u);
            setAuthInitError(null);
          })
          .catch((err: unknown) => {
            const status = (err as { status?: number }).status;
            if (status === 401 || status === 403) {
              clearAuth();
            } else if (isAbortError(err) || typeof status === "undefined") {
              // 8s タイムアウト or ネットワーク層の失敗。
              // トークンは保持したまま、ユーザーに再読み込みを促す。
              setAuthInitError(AUTH_INIT_ERROR_MESSAGE);
            }
          })
          .finally(() => {
            resolveAuthReady();
            setIsLoading(false);
          });
        return;
      }
      // Clear auth if token is expired
      clearAuth();
    }
    resolveAuthReady();
    setIsLoading(false);
  }, []);

  const clearAuth = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_EXPIRES_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response: TokenResponse = await apiLogin({ email, password });
    const expiresAt = Date.now() + response.expires_in * 1000;

    // Temporarily hold token (confirmed after getMe succeeds)
    const newToken = response.access_token;

    try {
      // Fetch user info (also validates the token)
      const userInfo = await getMe(newToken);

      // Only save to localStorage on success
      localStorage.setItem(TOKEN_KEY, newToken);
      localStorage.setItem(TOKEN_EXPIRES_KEY, String(expiresAt));
      recordLastSeen();
      setToken(newToken);
      setUser(userInfo);
      return userInfo;
    } catch (error) {
      // Do not save token if getMe fails
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_EXPIRES_KEY);
      throw error;
    }
  }, []);

  const loginWithWallet = useCallback(async (address: string, signer: WalletSigner) => {
    const message = `Sign in to Ultra AutoTrade\nAddress: ${address}`;
    const signature = await signer.signMessage(message);
    const response = await walletConnect({ wallet_address: address, message, signature });
    const expiresAt = Date.now() + response.expires_in * 1000;
    const newToken = response.access_token;

    try {
      const userInfo = await getMe(newToken);
      localStorage.setItem(TOKEN_KEY, newToken);
      localStorage.setItem(TOKEN_EXPIRES_KEY, String(expiresAt));
      recordLastSeen();
      setToken(newToken);
      setUser(userInfo);
      return userInfo;
    } catch (error) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_EXPIRES_KEY);
      throw error;
    }
  }, []);

  const logout = useCallback(async () => {
    if (token) {
      try {
        await apiLogout(token);
      } catch {
        // Clear local auth even if logout API call fails
      }
    }
    clearAuth();
  }, [token, clearAuth]);

  const refresh = useCallback(async () => {
    if (token) {
      try {
        const userInfo = await getMe(token);
        setUser(userInfo);
      } catch (err: unknown) {
        const status = (err as { status?: number }).status;
        // 401/403 のみ実際のトークン無効化として扱う。
        // timeout / ネットワーク失敗 (status undefined) で勝手にログアウトしない。
        if (status === 401 || status === 403) {
          clearAuth();
        }
      }
    }
  }, [token, clearAuth]);

  const value: AuthContextType = {
    user,
    token,
    isLoading,
    isAuthenticated: !!(user || token),
    isAdmin: user?.role === "admin",
    isPartner: (user?.role as string | undefined) === "partner" || user?.role === "admin",
    authInitError,
    login,
    loginWithWallet,
    logout,
    refresh,
  };

  // Timeout 発生時の再読み込み誘導バナー。
  // children と並列に描画してレイアウトに侵入しないよう position: fixed で固定する。
  const banner = authInitError
    ? React.createElement(
        "div",
        {
          role: "alert",
          "data-testid": "auth-init-error-banner",
          style: {
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            zIndex: 9999,
            background: "#dc2626",
            color: "#fff",
            padding: "10px 16px",
            fontSize: 14,
            textAlign: "center",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 12,
            boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
          },
        },
        React.createElement("span", null, authInitError),
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => {
              if (typeof window !== "undefined") window.location.reload();
            },
            style: {
              background: "#fff",
              color: "#dc2626",
              border: "none",
              borderRadius: 4,
              padding: "4px 10px",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            },
          },
          "再読み込み",
        ),
      )
    : null;

  return React.createElement(
    AuthContext.Provider,
    { value },
    banner,
    children,
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

/**
 * Retrieve stored token directly (not SSR-compatible)
 */
export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}