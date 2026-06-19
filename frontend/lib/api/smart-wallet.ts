// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/lib/api/smart-wallet.ts
// Smart Wallet (ERC-4337 SCW) アドレスを backend に登録する (slice4b)。

/**
 * 認証済みユーザーの SCW アドレスを backend に登録する。
 * POST /auth/wallet/smart-link（require_active_user）。冪等・unique 制約は backend 側。
 * submit-tx (slice3b) はこの登録アドレスを UserOp sender として検証する。
 */
export async function registerSmartWallet(
  address: string,
  token: string,
): Promise<Response> {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
  return fetch(`${API_BASE}/auth/wallet/smart-link`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ smart_wallet_address: address }),
  })
}
