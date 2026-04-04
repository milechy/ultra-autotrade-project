// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/lib/auth-state.ts
/**
 * Shared auth initialization state.
 *
 * Extracted from auth.ts to avoid circular imports:
 *   auth.ts  → api/auth.ts  (login, getMe, ...)
 *   client.ts → auth.ts     (getStoredToken)
 *   client.ts → auth-state.ts (authReadyPromise)  ← no cycle
 *
 * authReadyPromise resolves once AuthProvider has finished restoring
 * the token from localStorage. It resolves immediately on subsequent
 * awaits (standard Promise behaviour), so there is no ongoing overhead.
 */

let _resolveAuthReady: (() => void) | undefined

/**
 * A Promise that resolves when the AuthProvider has completed its
 * initial auth check (isLoading transitions from true → false).
 *
 * API clients await this before sending requests so that they never
 * fire with a stale / missing token during the startup race.
 */
export const authReadyPromise: Promise<void> = new Promise<void>((resolve) => {
  _resolveAuthReady = resolve
})

/**
 * Called by AuthProvider once auth initialisation is complete.
 * Must be called exactly once; subsequent calls are no-ops.
 */
export function resolveAuthReady(): void {
  if (_resolveAuthReady) {
    _resolveAuthReady()
    _resolveAuthReady = undefined // prevent double-resolve
  }
}
