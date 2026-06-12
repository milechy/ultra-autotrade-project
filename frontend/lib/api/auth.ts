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

export interface OpenRegisterRequest {
  email: string;
  username: string;
  password: string;
  terms_consent: boolean;
}

/**
 * 一般登録（open registration）レスポンス。
 * backend RegisterResponse = UserResponse + access_token + expires_in に対応。
 */
export interface OpenRegisterResponse {
  id: number;
  email: string;
  username: string;
  role: string;
  is_active: boolean;
  access_token: string;
  token_type: string;
  expires_in: number;
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
  role: "admin" | "partner" | "editor" | "viewer";
  is_active: boolean;
  created_at: string;
  updated_at: string;
  invited_by?: number | null;
  tier?: "LOWER" | "MIDDLE" | "UPPER" | "GENERAL";
  risk_mode?: "conservative" | "balanced" | "aggressive";
  risk_mode_label?: string;
  execution_policy?: "auto_execute" | "require_approval" | "proposal_only";
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
 * 一般登録（partner 招待不要の自己申請 / POST /auth/register-open）。
 *
 * terms_consent === true が必須（backend 側で 422 になる）。成功時は
 * RegisterResponse（ユーザー情報 + access_token + expires_in）を返す。
 * フロント側の到達経路は isPublicRegistrationEnabled() フラグで gate する。
 */
export async function registerOpen(
  request: OpenRegisterRequest
): Promise<OpenRegisterResponse> {
  return await postJson<OpenRegisterResponse>("/auth/register-open", request);
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
 * 現在のユーザー情報取得。
 *
 * 8 秒の AbortSignal.timeout を付与する。バックエンドが応答不能な瞬間でも
 * AuthProvider の初期化が 8 秒で解決し、画面が真っ暗なまま無限ブロックする
 * (2026-04-24 の山本さんインシデント) のを防ぐ。
 * timeoutMs に override を渡せば Playwright 等で調整可能。
 */
const DEFAULT_GET_ME_TIMEOUT_MS = 8000;

export async function getMe(
  token: string,
  options?: { timeoutMs?: number }
): Promise<UserResponse> {
  const timeoutMs = options?.timeoutMs ?? DEFAULT_GET_ME_TIMEOUT_MS;
  return await getJson<UserResponse>("/auth/me", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal: AbortSignal.timeout(timeoutMs),
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

export interface WalletConnectRequest {
  wallet_address: string;
  message: string;
  signature: string;
}

export interface WalletConnectResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  is_new_user: boolean;
  needs_terms_acceptance: boolean;
}

/**
 * ウォレット署名認証（POST /auth/wallet/connect）
 */
export async function walletConnect(request: WalletConnectRequest): Promise<WalletConnectResponse> {
  return await postJson<WalletConnectResponse>("/auth/wallet/connect", request);
}

export interface TermsStatusResponse {
  accepted: boolean;
  terms_version: string | null;
  terms_accepted_at: string | null;
  current_version: string;
  needs_acceptance: boolean;
}

/**
 * 利用規約の同意状態を取得（GET /auth/terms/status）
 */
export async function getTermsStatus(token: string): Promise<TermsStatusResponse> {
  return await getJson<TermsStatusResponse>("/auth/terms/status", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

/**
 * 利用規約に同意を記録（POST /auth/terms/accept）
 * @param token   JWT アクセストークン
 * @param version 同意バージョン文字列（例: "2.0"）
 */
export async function acceptTerms(token: string, version: string): Promise<TermsStatusResponse> {
  return await postJson<TermsStatusResponse>(
    "/auth/terms/accept",
    { version },
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );
}
