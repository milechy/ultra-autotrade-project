// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/client.ts
// Auth-aware API client.
// Thin wrappers around http.ts that automatically inject the stored JWT token.
// Usage: import { apiFetch, apiPost, apiPut } from '@/lib/api/client'

import { getStoredToken } from '../auth'
import { getJson, postJson, putJson } from './http'

function authHeaders(): Record<string, string> {
  const token = getStoredToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  return getJson<T>(path, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  })
}

export async function apiPost<T>(path: string, data: unknown, options?: RequestInit): Promise<T> {
  return postJson<T>(path, data, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  })
}

export async function apiPut<T>(path: string, data: unknown, options?: RequestInit): Promise<T> {
  return putJson<T>(path, data, {
    ...options,
    headers: { ...authHeaders(), ...options?.headers },
  })
}
