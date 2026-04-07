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
  login: (email: string, password: string) => Promise<UserResponse>;
  loginWithWallet: (address: string, signer: WalletSigner) => Promise<UserResponse>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore token on initialization
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    const expiresStr = localStorage.getItem(TOKEN_EXPIRES_KEY);

    if (storedToken && expiresStr) {
      const expires = parseInt(expiresStr, 10);
      if (Date.now() < expires) {
        setToken(storedToken);
        // Fetch user information
        getMe(storedToken)
          .then(setUser)
          .catch((err: unknown) => {
            const status = (err as { status?: number }).status
            if (status === 401 || status === 403) {
              clearAuth()
            }
            // Network error: keep token — user may still be authenticated
          })
          .finally(() => {
            resolveAuthReady()
            setIsLoading(false)
          });
        return;
      }
      // Clear auth if token is expired
      clearAuth();
    }
    resolveAuthReady()
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
      } catch {
        clearAuth();
      }
    }
  }, [token, clearAuth]);

  const value: AuthContextType = {
    user,
    token,
    isLoading,
    isAuthenticated: !!(user || token),
    isAdmin: user?.role === "admin",
    isPartner: user?.role === "partner",
    login,
    loginWithWallet,
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
 * Retrieve stored token directly (not SSR-compatible)
 */
export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}