// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/lib/wallet/userop.ts
// Smart Wallet (ERC-4337 AA) 署名経路の共有ヘルパー (slice4c)。

import type { UnsignedTx } from "@/lib/api/admin-proposals"

/** build-tx の UnsignedTx を Smart Wallet UserOp の call (to/data/value) に変換する。
 *  approve/supply/withdraw はいずれも 0 ETH value。from は SCW client が自動付与するため不要。 */
export function toUserOpCall(tx: UnsignedTx): {
  to: `0x${string}`
  data: `0x${string}`
  value: bigint
} {
  return {
    to: tx.to as `0x${string}`,
    data: tx.data as `0x${string}`,
    value: 0n,
  }
}
