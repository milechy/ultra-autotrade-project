// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/client.ts
// Auth-aware API client.
// Thin wrappers around http.ts that automatically inject the stored JWT token.
// Usage: import { apiFetch, apiPost, apiPut } from '@/lib/api/client'

import { getStoredToken } from '../auth'
import { authReadyPromise } from '../auth-state'
import { getJson, postJson, putJson } from './http'

/**
 * Paths that do not require an authenticated token.
 * These are allowed to bypass the authReadyPromise guard to prevent
 * infinite loops (e.g. the login call itself triggering a wait for auth).
 */
const AUTH_SKIP_PATHS = [
  '/api/health',
  '/health',
  '/auth/login',
  '/auth/register',
  '/auth/wallet/connect',
]

function isAuthSkipPath(path: string): boolean {
  return AUTH_SKIP_PATHS.some((skip) => path === skip || path.startsWith(skip + '?'))
}

function authHeaders(): Record<string, string> {
  const token = getStoredToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  if (!isAuthSkipPath(path)) {
    await authReadyPromise
  }
  return getJson<T>(path, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  })
}

export async function apiPost<T>(path: string, data: unknown, options?: RequestInit): Promise<T> {
  if (!isAuthSkipPath(path)) {
    await authReadyPromise
  }
  return postJson<T>(path, data, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  })
}

export async function apiPut<T>(path: string, data: unknown, options?: RequestInit): Promise<T> {
  if (!isAuthSkipPath(path)) {
    await authReadyPromise
  }
  return putJson<T>(path, data, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  })
}
