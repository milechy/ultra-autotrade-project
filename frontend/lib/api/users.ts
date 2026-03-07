// frontend/lib/api/users.ts
/**
 * ユーザー管理 API クライアント。
 */

import { getJson, postJson, putJson, deleteJson } from "./http";
import type { UserResponse } from "./auth";

export interface CreateUserRequest {
  email: string;
  username: string;
  password: string;
  role?: "admin" | "editor" | "viewer";
}

export interface UpdateUserRequest {
  email?: string;
  username?: string;
  password?: string;
  role?: "admin" | "editor" | "viewer";
  is_active?: boolean;
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

/**
 * ユーザー一覧取得（admin のみ）
 */
export async function listUsers(token: string): Promise<UserResponse[]> {
  return await getJson<UserResponse[]>("/users", {
    headers: authHeaders(token),
  });
}

/**
 * ユーザー作成（admin のみ）
 */
export async function createUser(
  token: string,
  request: CreateUserRequest
): Promise<UserResponse> {
  return await postJson<UserResponse>("/users", request, {
    headers: authHeaders(token),
  });
}

/**
 * ユーザー詳細取得（自分または admin）
 */
export async function getUser(token: string, userId: number): Promise<UserResponse> {
  return await getJson<UserResponse>(`/users/${userId}`, {
    headers: authHeaders(token),
  });
}

/**
 * ユーザー更新（自分または admin）
 */
export async function updateUser(
  token: string,
  userId: number,
  request: UpdateUserRequest
): Promise<UserResponse> {
  return await putJson<UserResponse>(`/users/${userId}`, request, {
    headers: authHeaders(token),
  });
}

/**
 * ユーザー削除（admin のみ）
 */
export async function deleteUser(token: string, userId: number): Promise<void> {
  await deleteJson<void>(`/users/${userId}`, {
    headers: authHeaders(token),
  });
}
