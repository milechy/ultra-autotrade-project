// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/client.ts
// Auth-aware API client.
// Thin wrappers around http.ts that automatically inject the stored JWT token.
// Usage: import { apiFetch, apiPost, apiPut } from '@/lib/api/client'

import { getStoredToken } from '../auth'
import { authReadyPromise } from '../auth-state'
import { getJson, postJson, putJson } from './http'
import type { HttpError } from './http'

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
  '/api/invitations/',
]

function isAuthSkipPath(path: string): boolean {
  return AUTH_SKIP_PATHS.some((skip) => path.startsWith(skip))
}

function authHeaders(): Record<string, string> {
  const token = getStoredToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/**
 * On 401, redirect to /login (client-side only).
 * This prevents unhandled HttpError from propagating up and crashing React.
 */
function handle401(err: unknown): never {
  const httpErr = err as HttpError
  if (httpErr?.status === 401 && typeof window !== 'undefined') {
    window.location.href = '/login'
  }
  throw err
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  if (!isAuthSkipPath(path)) {
    await authReadyPromise
  }
  try {
    return await getJson<T>(path, {
      ...options,
      headers: { ...authHeaders(), ...options?.headers },
    })
  } catch (err) {
    return handle401(err)
  }
}

export async function apiPost<T>(path: string, data: unknown, options?: RequestInit): Promise<T> {
  if (!isAuthSkipPath(path)) {
    await authReadyPromise
  }
  try {
    return await postJson<T>(path, data, {
      ...options,
      headers: { ...authHeaders(), ...options?.headers },
    })
  } catch (err) {
    return handle401(err)
  }
}

export async function apiPut<T>(path: string, data: unknown, options?: RequestInit): Promise<T> {
  if (!isAuthSkipPath(path)) {
    await authReadyPromise
  }
  try {
    return await putJson<T>(path, data, {
      ...options,
      headers: { ...authHeaders(), ...options?.headers },
    })
  } catch (err) {
    return handle401(err)
  }
}
