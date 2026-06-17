// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/scripts/poc/paymaster-poc.mjs
//
// スライス7 PoC — Privy Smart Wallet AA/ERC-4337 + Paymaster 設計 doc
//   (docs/privy-aa-paymaster-design.md / Asana 1215697060370824)
//
// 目的: paymaster ベンダー(Pimlico)で sponsored UserOp が Base Sepolia 上で
//       status=1 を返し、getUserOperationReceipt から actualGasCost を取得できるかを
//       headless に検証する。これは設計 doc の核心リスク2/3(receipt 検証経路 /
//       UserOpHash ベース)を de-risk し、スライス4 承認ゲートの前提(status=1 確認)を満たす。
//
// 新規依存ゼロ: 既存の viem(^2.47, `viem/account-abstraction` 同梱)のみを使用する。
//   → package.json を触らない(スライス5=Tier S を回避)。本 PoC は新規ファイルのみ。
//
// 【このPoCが検証すること】
//   1. Base Sepolia 上で Coinbase Smart Account(SCW) を counterfactual 生成
//   2. paymaster(Pimlico)経由で sponsored UserOp を送信(SCW owner=throwaway EOA が署名)
//   3. bundler から userOpHash を取得
//   4. waitForUserOperationReceipt で success=true と actualGasCost を確認
//      (actualGasCost は F-9 expense 再設計・案A の per-UserOp 実費ソース)
//
// 【このPoCが検証しないこと(スライス4 で実施)】
//   - Privy embedded EOA を SCW owner にする本番署名経路の配線(client-side, SmartWalletsProvider)
//   - 既存 build-tx / verify_supply_onbehalf / submit-tx の onBehalfOf=SCW 対応
//
// ── 実行方法 ──────────────────────────────────────────────
//   cd frontend
//   PIMLICO_API_KEY=pim_xxx node scripts/poc/paymaster-poc.mjs
//
//   必須 env(小林さん外部セットアップ):
//     PIMLICO_API_KEY            … Pimlico ダッシュボードの API キー(Base Sepolia)
//   任意 env:
//     PIMLICO_BUNDLER_URL        … 上記の代わりに完全な bundler URL を直接指定
//     PIMLICO_SPONSORSHIP_POLICY_ID … verifying paymaster のスポンサーポリシー id(必要な場合)
//     BASE_SEPOLIA_RPC_URL       … chain 読み取り用 RPC(既定: https://sepolia.base.org)
//     POC_OWNER_PRIVATE_KEY      … SCW owner の EOA 秘密鍵(既定: 毎回ランダム生成)
//
//   キー未設定時は SKIP(exit 0)。小林さんが Pimlico key を用意し次第、staging で実行する。
// ──────────────────────────────────────────────────────────

import { createPublicClient, http, formatEther } from "viem"
import { baseSepolia } from "viem/chains"
import { privateKeyToAccount, generatePrivateKey } from "viem/accounts"
import {
  createBundlerClient,
  toCoinbaseSmartAccount,
} from "viem/account-abstraction"

function mask(s) {
  if (!s) return "(unset)"
  return s.length <= 10 ? "******" : `${s.slice(0, 6)}...${s.slice(-4)}`
}

async function main() {
  const apiKey = process.env.PIMLICO_API_KEY
  const bundlerUrl =
    process.env.PIMLICO_BUNDLER_URL ||
    (apiKey
      ? `https://api.pimlico.io/v2/base-sepolia/rpc?apikey=${apiKey}`
      : null)

  if (!bundlerUrl) {
    console.log("⏭️  SKIP: PIMLICO_API_KEY / PIMLICO_BUNDLER_URL 未設定。")
    console.log("   小林さん外部セットアップ後に実行:")
    console.log("     1) Pimlico ダッシュボードで Base Sepolia の API キーを発行")
    console.log("     2) (必要なら) verifying paymaster の sponsorship policy を作成")
    console.log("     3) PIMLICO_API_KEY=pim_xxx node scripts/poc/paymaster-poc.mjs")
    process.exit(0)
  }

  const rpcUrl = process.env.BASE_SEPOLIA_RPC_URL || "https://sepolia.base.org"
  const ownerKey = process.env.POC_OWNER_PRIVATE_KEY || generatePrivateKey()
  const policyId = process.env.PIMLICO_SPONSORSHIP_POLICY_ID

  console.log("── Paymaster PoC (Base Sepolia / Pimlico) ──")
  console.log("  chain        : base-sepolia (84532)")
  console.log("  rpc          :", rpcUrl)
  console.log("  bundler      :", bundlerUrl.replace(apiKey ?? "__none__", mask(apiKey)))
  console.log("  owner EOA key:", mask(ownerKey), process.env.POC_OWNER_PRIVATE_KEY ? "(env)" : "(generated)")
  console.log("  policy id    :", policyId ? mask(policyId) : "(none)")

  const publicClient = createPublicClient({
    chain: baseSepolia,
    transport: http(rpcUrl),
  })

  const owner = privateKeyToAccount(ownerKey)

  // 非カストディアル不変条件: owner = ユーザー EOA(本 PoC では throwaway)。
  // UATa サーバー鍵は owner にしない(本番では Privy embedded EOA が owner)。
  const account = await toCoinbaseSmartAccount({
    client: publicClient,
    owners: [owner],
    version: "1.1",
  })
  console.log("  SCW address  :", account.address, "(counterfactual)")

  const bundlerClient = createBundlerClient({
    account,
    client: publicClient,
    transport: http(bundlerUrl),
    // Pimlico の v2 エンドポイントは bundler + paymaster(ERC-7677 pm_*)を兼ねる。
    paymaster: true,
    ...(policyId
      ? { paymasterContext: { sponsorshipPolicyId: policyId } }
      : {}),
  })

  // 最小の sponsored UserOp: SCW 自身への 0 value / 空 data 呼び出し。
  // 初回 UserOp で SCW がデプロイされる(ガスは paymaster が肩代わり → owner ETH 不要)。
  console.log("\n→ sponsored UserOp を送信中...")
  const t0 = Date.now()
  const userOpHash = await bundlerClient.sendUserOperation({
    calls: [{ to: account.address, value: 0n, data: "0x" }],
  })
  console.log("  userOpHash   :", userOpHash)

  console.log("→ getUserOperationReceipt を待機中...")
  const receipt = await bundlerClient.waitForUserOperationReceipt({
    hash: userOpHash,
  })
  const elapsed = ((Date.now() - t0) / 1000).toFixed(1)

  const gasWei = receipt.actualGasCost ?? 0n
  console.log("\n── 結果 ──")
  console.log("  success      :", receipt.success)
  console.log("  txHash       :", receipt.receipt?.transactionHash)
  console.log("  actualGasCost:", gasWei.toString(), "wei (", formatEther(gasWei), "ETH )")
  console.log("  elapsed      :", elapsed, "s")
  console.log(
    "  → actualGasCost は F-9 expense 再設計(案A)の per-UserOp 実費ソース",
  )

  if (receipt.success !== true) {
    console.error("\n❌ FAIL: UserOp receipt.success !== true")
    process.exit(1)
  }
  console.log("\n✅ PASS: sponsored UserOp が status=1 で確定。paymaster 経路 OK。")
  process.exit(0)
}

main().catch((err) => {
  console.error("\n❌ PoC エラー:")
  console.error(err?.shortMessage || err?.message || err)
  if (err?.details) console.error("  details:", err.details)
  process.exit(1)
})
