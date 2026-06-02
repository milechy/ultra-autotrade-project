// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-approve/page.tsx
// LIFF内 Privy 署名 non-custodial 承認フロー
//
// フロー:
//   1. GET /api/proposals/pending → 最新 pending 提案を表示
//      URL param ?proposal_id=X で個別指定も可 (LINE 通知リンク用)
//   2. 承認ボタン押下 → GET /api/proposals/{id}/build-tx で未署名 tx 取得
//   3. Privy embedded wallet で approve_tx → supply_tx を順次署名・送信
//      秘密鍵はブラウザ内 Privy SDK に閉じる。サーバーに渡らない。
//   4. supply tx_hash を POST /api/proposals/{id}/submit-tx に提出
//      サーバーが on-chain receipt を検証して proposal.status = "executed" に遷移
//
// 前提:
//   - Privy App ID: NEXT_PUBLIC_PRIVY_APP_ID (cmnv54q5f03ex0cjley894xrp)
//   - embeddedWallets.createOnLogin = "users-without-wallets" (PrivyRootClient.tsx)
//     → Privy ログイン済みユーザーには embedded wallet が自動作成される
//   - 外部 wallet 接続中の場合も利用可 (walletClientType !== "privy" の場合は UI に明記)
//
// Note on useSearchParams:
//   Next.js では useSearchParams を使うコンポーネントを <Suspense> でラップ必須。
//   LiffApproveContent (内部) が useSearchParams を持ち、
//   LiffApprovePage (default export) が Suspense ラッパーになる。
"use client"

import { Suspense, useEffect, useRef, useState } from "react"
import { usePrivy, useWallets } from "@privy-io/react-auth"
import { useSearchParams } from "next/navigation"
import { useLiff } from "@/hooks/useLiff"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

// Base Sepolia = 84532, Base Mainnet = 8453 (build-time env)
const DEFAULT_CHAIN_ID = parseInt(process.env.NEXT_PUBLIC_DEFAULT_CHAIN_ID ?? "8453")
const BASESCAN_BASE =
  DEFAULT_CHAIN_ID === 84532
    ? "https://sepolia.basescan.org/tx/"
    : "https://basescan.org/tx/"

// --- Backend schema types ---

type Proposal = {
  id: number
  status: string
  operation: string
  asset: string
  amount_usd: number
  reason: string
  expires_at: string
  created_at: string
  tx_hash: string | null
}

// response_model_by_alias=True → JSON フィールド名は Field(alias=...) の値を使う
type UnsignedTx = {
  to: string
  data: string
  from: string       // Field(alias="from")
  chainId: number    // Field(alias="chainId")
  value: string
}

type PartnerUnsignedTxs = {
  proposal_id: number
  operation: string
  wallet_address: string
  approve_tx?: UnsignedTx   // SUPPLY のみ
  supply_tx?: UnsignedTx    // SUPPLY のみ
  withdraw_tx?: UnsignedTx  // WITHDRAW のみ
}

type FlowStep =
  | "idle"
  | "building"
  | "approving"   // USDC approve tx Privy 署名中
  | "supplying"   // supply/withdraw tx Privy 署名中
  | "submitting"  // POST /submit-tx 中
  | "done"
  | "error"

// ---------------------------------------------------------------------------
// Inner component (uses useSearchParams → must be inside <Suspense>)
// ---------------------------------------------------------------------------

function LiffApproveContent() {
  const { isReady, isLoggedIn, error: liffError } = useLiff()
  const { ready: privyReady, authenticated, login } = usePrivy()
  const { wallets } = useWallets()
  const searchParams = useSearchParams()
  const proposalIdParam = searchParams.get("proposal_id")

  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [flowStep, setFlowStep] = useState<FlowStep>("idle")
  const [stepDetail, setStepDetail] = useState("")
  const [supplyTxHash, setSupplyTxHash] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // 二重送信防止: React state は非同期なので ref で即時ロック
  const isSubmittingRef = useRef(false)

  const token =
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null

  // --- Proposal fetch ---
  useEffect(() => {
    if (!isReady || !isLoggedIn || !token) return

    setLoading(true)
    setFetchError(null)
    setProposal(null)

    const url = proposalIdParam
      ? `${API_BASE}/api/proposals/${proposalIdParam}`
      : `${API_BASE}/api/proposals/pending`

    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<Proposal | { items: Proposal[]; total: number }>
      })
      .then((data) => {
        // /pending は ProposalListResponse { items, total }
        // /{id} は ProposalResponse (single object)
        if ("items" in data) {
          setProposal(data.items[0] ?? null)
        } else {
          setProposal(data)
        }
      })
      .catch((e: unknown) =>
        setFetchError(e instanceof Error ? e.message : "提案の取得に失敗しました"),
      )
      .finally(() => setLoading(false))
  }, [isReady, isLoggedIn, token, proposalIdParam, reloadKey])

  // --- handleReject ---
  async function handleReject() {
    if (!proposal || !token || isSubmittingRef.current) return
    isSubmittingRef.current = true
    setFlowStep("submitting")
    setStepDetail("提案を拒否中...")
    setErrorMsg(null)

    try {
      const res = await fetch(`${API_BASE}/api/proposals/${proposal.id}/reject`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`reject 失敗 (${res.status}): ${body}`)
      }
      setFlowStep("done")
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : String(e))
      setFlowStep("error")
    } finally {
      isSubmittingRef.current = false
    }
  }

  // --- handleApprove: Privy 署名 non-custodial フロー ---
  async function handleApprove() {
    if (!proposal || !token || isSubmittingRef.current) return
    isSubmittingRef.current = true
    setFlowStep("building")
    setStepDetail("")
    setErrorMsg(null)
    setSupplyTxHash(null)

    try {
      // Privy embedded wallet を優先。なければ接続済み外部 wallet を使用。
      const signerWallet =
        wallets.find((w) => w.walletClientType === "privy") ?? wallets[0]
      if (!signerWallet) {
        throw new Error(
          "署名可能な wallet が見つかりません。\n" +
            "「Privy でログイン」ボタンでログインして embedded wallet を作成するか、\n" +
            "MetaMask 等の外部 wallet を接続してください。",
        )
      }

      // Step 1: build-tx — 未署名 approve_tx + supply_tx を取得
      setStepDetail("未署名 tx をサーバーから取得中...")
      const buildRes = await fetch(
        `${API_BASE}/api/proposals/${proposal.id}/build-tx`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (!buildRes.ok) {
        const body = await buildRes.text()
        throw new Error(`build-tx 失敗 (${buildRes.status}): ${body}`)
      }
      const txData = (await buildRes.json()) as PartnerUnsignedTxs
      const eip1193 = await signerWallet.getEthereumProvider()

      // Step 2: approve_tx (SUPPLY のみ — Pool が USDC を transferFrom するための allowance)
      if (txData.approve_tx) {
        setFlowStep("approving")
        setStepDetail(
          "Privy が USDC approve の署名を要求します。確認画面で承認してください。",
        )
        const a = txData.approve_tx
        // eth_sendTransaction params に chainId は含めない (Privy が wallet 設定から解決)
        await (eip1193.request({
          method: "eth_sendTransaction",
          params: [{ to: a.to, data: a.data, from: a.from, value: a.value ?? "0x0" }],
        }) as Promise<string>)
        // approve tx hash は submit-tx に不要 (サーバーは supply tx hash のみ receipt 検証)
      }

      // Step 3: supply_tx (SUPPLY) または withdraw_tx (WITHDRAW)
      const mainTx = txData.supply_tx ?? txData.withdraw_tx
      if (!mainTx) {
        throw new Error(
          "supply_tx / withdraw_tx が build-tx レスポンスにありません。" +
            `operation=${txData.operation}`,
        )
      }

      setFlowStep("supplying")
      const opLabel = txData.operation === "SUPPLY" ? "supply" : "withdraw"
      setStepDetail(
        `Privy が ${opLabel} の署名を要求します。確認画面で承認してください。`,
      )

      const txHash = (await eip1193.request({
        method: "eth_sendTransaction",
        params: [
          {
            to: mainTx.to,
            data: mainTx.data,
            from: mainTx.from,
            value: mainTx.value ?? "0x0",
          },
        ],
      })) as string
      setSupplyTxHash(txHash)

      // Step 4: submit-tx — supply tx_hash をサーバーに提出
      // サーバー側が on-chain receipt を検証して proposal.status = "executed" に遷移
      setFlowStep("submitting")
      setStepDetail("supply tx_hash をサーバーに提出中...")

      const submitRes = await fetch(
        `${API_BASE}/api/proposals/${proposal.id}/submit-tx`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            tx_hash: txHash,
            wallet_address: signerWallet.address,
          }),
        },
      )

      if (!submitRes.ok) {
        const body = await submitRes.text()
        // supply は既に on-chain に送信済み。tx_hash を保持し手動リカバリを促す。
        throw new Error(
          `submit-tx 失敗 (${submitRes.status}): ${body}\n\n` +
            `⚠ supply tx は送信済みです。tx_hash を管理者に連絡してください:\n${txHash}`,
        )
      }

      setFlowStep("done")
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      // ユーザーキャンセルは error 扱いにせず idle に戻す
      if (
        msg.includes("User rejected") ||
        msg.includes("user rejected") ||
        msg.includes("User cancelled") ||
        msg.includes("user cancelled")
      ) {
        setFlowStep("idle")
        setStepDetail("")
      } else {
        setErrorMsg(msg)
        setFlowStep("error")
      }
    } finally {
      isSubmittingRef.current = false
    }
  }

  // ---------------------------------------------------------------------------
  // Guard views
  // ---------------------------------------------------------------------------

  if (!isReady) {
    return (
      <Centered>
        <p className="text-zinc-400 text-sm">読み込み中...</p>
      </Centered>
    )
  }
  if (liffError) {
    return (
      <Centered>
        <p className="text-red-400 text-sm">LIFF初期化エラー: {liffError}</p>
      </Centered>
    )
  }
  if (!isLoggedIn) {
    return (
      <Centered>
        <p className="text-zinc-400 text-sm">LINEアプリから開いてください</p>
      </Centered>
    )
  }
  if (!token) {
    if (typeof window !== "undefined") window.location.replace("/liff-login")
    return (
      <Centered>
        <p className="text-zinc-400 text-sm">再認証中...</p>
      </Centered>
    )
  }

  // ---------------------------------------------------------------------------
  // Done view
  // ---------------------------------------------------------------------------

  if (flowStep === "done") {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-8 max-w-md mx-auto">
        <div className="text-center space-y-4">
          <p className="text-green-400 text-2xl font-bold">✅ 承認完了</p>
          <p className="text-zinc-400 text-sm">
            {supplyTxHash
              ? "supply tx が送信され、提案が executed になりました"
              : "提案が処理されました"}
          </p>
          {supplyTxHash && (
            <div className="bg-zinc-900 rounded-lg p-4 text-left space-y-2">
              <p className="text-zinc-500 text-xs font-medium">supply tx_hash</p>
              <p className="text-blue-400 font-mono text-xs break-all">{supplyTxHash}</p>
              <a
                href={`${BASESCAN_BASE}${supplyTxHash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block text-indigo-400 text-xs underline"
              >
                Basescan で確認 →
              </a>
            </div>
          )}
          <button
            onClick={() => {
              setFlowStep("idle")
              setSupplyTxHash(null)
              setReloadKey((k) => k + 1)
            }}
            className="text-zinc-400 text-sm underline"
          >
            次の提案を確認
          </button>
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Main view
  // ---------------------------------------------------------------------------

  const isBusy =
    flowStep !== "idle" && flowStep !== "error" && flowStep !== "done"
  const canApprove = !isBusy && authenticated && !!proposal

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-6 max-w-md mx-auto">
      <h1 className="text-xl font-bold mb-2 text-center">取引承認</h1>
      <p className="text-zinc-500 text-xs text-center mb-5">
        Privy embedded wallet で署名 — 秘密鍵はサーバーに渡りません
      </p>

      {/* Privy wallet status */}
      {privyReady && !authenticated && (
        <div className="mb-4 space-y-2">
          <p className="text-yellow-400 text-xs">
            署名には Privy ログインが必要です
          </p>
          <button
            onClick={() => login()}
            className="w-full bg-violet-700 hover:bg-violet-600 text-white font-semibold py-2.5 rounded-lg text-sm"
          >
            Privy でログイン
          </button>
        </div>
      )}

      {authenticated && wallets.length > 0 && (
        <WalletBadge wallets={wallets} />
      )}

      {/* Proposal fetch state */}
      {loading && (
        <p className="text-zinc-400 text-sm text-center py-6">提案を取得中...</p>
      )}
      {fetchError && (
        <p className="text-red-400 text-sm text-center py-6">{fetchError}</p>
      )}
      {!loading && !fetchError && proposal === null && (
        <p className="text-zinc-400 text-sm text-center py-6">
          承認待ちの提案はありません
        </p>
      )}

      {proposal && (
        <div className="space-y-4">
          {/* Proposal card */}
          <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800 space-y-3">
            <div className="flex items-center justify-between text-xs text-zinc-500">
              <span>提案 #{proposal.id}</span>
              <span>{new Date(proposal.created_at).toLocaleString("ja-JP")}</span>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`text-2xl font-bold ${
                  proposal.operation === "SUPPLY" ? "text-green-400" : "text-red-400"
                }`}
              >
                {proposal.operation}
              </span>
              <span className="text-zinc-100 text-lg font-semibold">
                ${Number(proposal.amount_usd).toFixed(2)}{" "}
                <span className="text-zinc-400 text-base font-normal">
                  {proposal.asset}
                </span>
              </span>
            </div>
            {proposal.reason && (
              <p className="text-zinc-300 text-sm leading-relaxed">
                {proposal.reason}
              </p>
            )}
            <p className="text-zinc-600 text-xs">
              期限: {new Date(proposal.expires_at).toLocaleString("ja-JP")}
            </p>
          </div>

          {/* Flow progress */}
          {(isBusy || flowStep === "error") && (
            <FlowProgress step={flowStep} detail={stepDetail} />
          )}

          {/* Error detail */}
          {flowStep === "error" && errorMsg && (
            <div className="bg-red-950 border border-red-800 rounded-lg p-3 text-xs text-red-300 whitespace-pre-wrap break-words">
              {errorMsg}
            </div>
          )}

          {/* Partial tx_hash (submit-tx 失敗時のリカバリ用) */}
          {flowStep === "error" && supplyTxHash && (
            <div className="bg-zinc-900 rounded-lg p-3 text-xs space-y-1">
              <p className="text-yellow-400 font-medium">⚠ supply tx は送信済みです</p>
              <p className="text-zinc-400 font-mono break-all">{supplyTxHash}</p>
            </div>
          )}

          {/* Action buttons */}
          <div className="grid grid-cols-2 gap-3 pt-1">
            <button
              onClick={() => void handleApprove()}
              disabled={!canApprove}
              className="bg-green-600 hover:bg-green-500 disabled:opacity-40 disabled:cursor-not-allowed
                         text-white font-semibold py-3 rounded-lg transition-colors text-sm"
            >
              {flowStep === "building"
                ? "tx 構築中..."
                : flowStep === "approving"
                  ? "approve 署名中..."
                  : flowStep === "supplying"
                    ? "supply 署名中..."
                    : flowStep === "submitting"
                      ? "提出中..."
                      : "Privy で承認する"}
            </button>

            <button
              onClick={() => void handleReject()}
              disabled={isBusy || !proposal}
              className="bg-red-700 hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed
                         text-white font-semibold py-3 rounded-lg transition-colors text-sm"
            >
              却下する
            </button>
          </div>

          {flowStep === "error" && (
            <button
              onClick={() => {
                setFlowStep("idle")
                setErrorMsg(null)
              }}
              className="w-full text-zinc-500 text-xs underline"
            >
              リセットして再試行
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Default export — Suspense ラッパー (useSearchParams 必須)
// ---------------------------------------------------------------------------

export default function LiffApprovePage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen bg-zinc-950">
          <p className="text-zinc-400 text-sm">読み込み中...</p>
        </div>
      }
    >
      <LiffApproveContent />
    </Suspense>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
      {children}
    </div>
  )
}

type Wallet = { walletClientType: string; address: string }

function WalletBadge({ wallets }: { wallets: Wallet[] }) {
  const w = wallets.find((x) => x.walletClientType === "privy") ?? wallets[0]
  const isEmbedded = w.walletClientType === "privy"
  return (
    <div className="bg-zinc-900 rounded-lg p-3 mb-4 text-xs space-y-1">
      <p className="text-zinc-500 font-medium">署名 wallet</p>
      <p className="text-blue-400 font-mono">
        {w.address.slice(0, 10)}...{w.address.slice(-6)}
      </p>
      <p className="text-zinc-500">
        {isEmbedded
          ? "Privy embedded wallet (推奨)"
          : `外部 wallet: ${w.walletClientType}`}
      </p>
      {!isEmbedded && (
        <p className="text-yellow-400">
          ⚠ embedded wallet が見つかりません。Privy ダッシュボードで有効化されているか確認してください。
        </p>
      )}
    </div>
  )
}

const FLOW_STEPS: Array<{ key: FlowStep; label: string }> = [
  { key: "building", label: "build-tx (未署名 tx 取得)" },
  { key: "approving", label: "USDC approve 署名 (Privy)" },
  { key: "supplying", label: "supply 署名 (Privy)" },
  { key: "submitting", label: "submit-tx (サーバー提出)" },
]

function FlowProgress({ step, detail }: { step: FlowStep; detail: string }) {
  const currentIdx = FLOW_STEPS.findIndex((s) => s.key === step)
  const isError = step === "error"
  return (
    <div className="bg-zinc-900 rounded-lg p-3 space-y-2">
      <p className="text-zinc-400 text-xs font-medium mb-1">処理進捗</p>
      {FLOW_STEPS.map((s, i) => {
        const done = i < currentIdx || step === "done"
        const active = s.key === step
        const failed = active && isError
        return (
          <div key={s.key} className="flex items-center gap-2">
            <span className="text-base leading-tight">
              {failed ? "❌" : done ? "✅" : active ? "⏳" : "⬜"}
            </span>
            <span
              className={`text-xs ${
                failed
                  ? "text-red-400"
                  : active
                    ? "text-yellow-400"
                    : done
                      ? "text-green-400"
                      : "text-zinc-600"
              }`}
            >
              {s.label}
            </span>
          </div>
        )
      })}
      {detail && (
        <p className="text-zinc-500 text-xs mt-1 pl-6">{detail}</p>
      )}
    </div>
  )
}
