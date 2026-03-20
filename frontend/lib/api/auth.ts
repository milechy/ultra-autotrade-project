// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/auth.ts
/**
 * 認証 API クライアント。
 */

import { getJson, postJson } from "./http";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: number;
  email: string;
  username: string;
  role: "admin" | "editor" | "viewer";
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

/**
 * 初回管理者登録（ユーザーが存在しない場合のみ）
 */
export async function register(request: RegisterRequest): Promise<UserResponse> {
  return await postJson<UserResponse>("/auth/register", request);
}

/**
 * ログイン
 */
export async function login(request: LoginRequest): Promise<TokenResponse> {
  return await postJson<TokenResponse>("/auth/login", request);
}

/**
 * ログアウト
 */
export async function logout(token: string): Promise<void> {
  await postJson<void>("/auth/logout", {}, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

/**
 * 現在のユーザー情報取得
 */
export async function getMe(token: string): Promise<UserResponse> {
  return await getJson<UserResponse>("/auth/me", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

/**
 * パスワード変更
 */
export async function changePassword(
  token: string,
  request: PasswordChangeRequest
): Promise<void> {
  await postJson<void>("/auth/change-password", request, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}
