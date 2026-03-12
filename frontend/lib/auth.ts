'use client'

// frontend/lib/auth.ts
/**
 * 認証状態管理。
 *
 * - localStorage にトークンを保存
 * - useAuth フックで認証状態を取得
 * - AuthProvider でラップして使用
 *
 * セキュリティノート：
 * - localStorage を使用しているため XSS 攻撃に脆弱
 * - 本番環境では以下のいずれかを推奨：
 *   1. HttpOnly Cookie + SameSite=Strict
 *   2. In-Memory Token + Refresh Token (HttpOnly Cookie)
 * - 現状は CSP (Content Security Policy) で XSS リスクを緩和
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { login as apiLogin, getMe, logout as apiLogout, type UserResponse, type TokenResponse } from "./api/auth";

const TOKEN_KEY = "ultra_auth_token";
const TOKEN_EXPIRES_KEY = "ultra_auth_expires";

interface AuthContextType {
  user: UserResponse | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<UserResponse>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 初期化時にトークンを復元
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    const expiresStr = localStorage.getItem(TOKEN_EXPIRES_KEY);

    if (storedToken && expiresStr) {
      const expires = parseInt(expiresStr, 10);
      if (Date.now() < expires) {
        setToken(storedToken);
        // ユーザー情報を取得
        getMe(storedToken)
          .then(setUser)
          .catch(() => {
            // トークンが無効な場合はクリア
            clearAuth();
          })
          .finally(() => setIsLoading(false));
        return;
      }
      // 期限切れの場合はクリア
      clearAuth();
    }
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

    // トークンを一時保存（getMe 成功後に確定）
    const newToken = response.access_token;

    try {
      // ユーザー情報を取得（トークン検証を兼ねる）
      const userInfo = await getMe(newToken);

      // 成功した場合のみ localStorage に保存
      localStorage.setItem(TOKEN_KEY, newToken);
      localStorage.setItem(TOKEN_EXPIRES_KEY, String(expiresAt));
      setToken(newToken);
      setUser(userInfo);
      return userInfo;
    } catch (error) {
      // getMe 失敗時はトークンを保存しない
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
        // ログアウト API が失敗してもローカルはクリア
      }
    }
    clearAuth();
  }, [token, clearAuth]);

  const refresh = useCallback(async () => {
    if (token) {
      try {
        const userInfo = await getMe(token);
        setUser(userInfo);
      } catch {
        clearAuth();
      }
    }
  }, [token, clearAuth]);

  const value: AuthContextType = {
    user,
    token,
    isLoading,
    isAuthenticated: !!user,
    isAdmin: user?.role === "admin",
    login,
    logout,
    refresh,
  };

  return React.createElement(AuthContext.Provider, { value }, children);
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

/**
 * トークンを直接取得（SSR 非対応）
 */
export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}
