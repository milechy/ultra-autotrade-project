'use client'

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
          .catch(() => {
            // Clear auth if token is invalid
            clearAuth();
          })
          .finally(() => setIsLoading(false));
        return;
      }
      // Clear auth if token is expired
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
 * Retrieve stored token directly (not SSR-compatible)
 */
export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}
