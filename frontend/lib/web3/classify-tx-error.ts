// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/lib/web3/classify-tx-error.ts
// 提案 build-tx/submit-tx・Privy/ethers 署名のエラーを分類する。
// build-tx の残高不足 (422)・ユーザー拒否 (4001)・on-chain revert を出し分け、
// liff-chat 署名シートで適切な文言・入金導線を出すために使う。

export type TxErrorKind = "insufficient" | "rejected" | "revert" | "unknown"

/**
 * tx 系エラーを分類する。
 *
 * 対応するエラー形:
 * - `HttpError` ({ status, message, detail } / lib/api/http.ts) — `instanceof Error` ではない。
 *   build-tx の残高不足 422 / 402 を `insufficient` に分類。
 * - Privy / ethers の EIP-1193 エラー (code 4001 = user rejected)。
 * - submit-tx の revert 400 (detail に "revert") / EOA approve revert メッセージ。
 */
export function classifyTxError(err: unknown): TxErrorKind {
  const status =
    err && typeof err === "object" && "status" in err
      ? Number((err as { status?: unknown }).status)
      : undefined
  // 残高不足は build-tx (B1) が 402/422 で返す。最優先で分類。
  if (status === 402 || status === 422) return "insufficient"

  const code =
    err && typeof err === "object" && "code" in err
      ? (err as { code?: number | string }).code
      : undefined
  const raw =
    err instanceof Error
      ? err.message
      : typeof err === "string"
        ? err
        : err && typeof err === "object" && "message" in err
          ? String((err as { message?: unknown }).message ?? "")
          : ""
  const lower = raw.toLowerCase()

  if (code === 4001 || lower.includes("rejected") || lower.includes("denied")) {
    return "rejected"
  }
  if (
    raw.includes("残高不足") ||
    lower.includes("insufficient funds") ||
    lower.includes("insufficient balance") ||
    lower.includes("exceeds balance")
  ) {
    return "insufficient"
  }
  if (lower.includes("revert")) return "revert"
  return "unknown"
}
