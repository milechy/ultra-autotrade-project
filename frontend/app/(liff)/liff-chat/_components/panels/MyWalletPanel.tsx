// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useState, useCallback, useEffect, useRef } from "react"
import QRCode from "qrcode"
import {
  Copy,
  QrCode,
  ExternalLink,
  ShieldCheck,
  Shield,
  Wallet,
  AlertTriangle,
  RefreshCw,
  Loader2,
} from "lucide-react"
import { usePrivy } from "@privy-io/react-auth"
import { useWallet } from "@/hooks/useWallet"
import { useLinkedWalletAddress } from "@/hooks/useLinkedWalletAddress"

// アドレス解決の状態。
//  - loading : Privy 初期化中 / API 取得中
//  - ready   : address 取得済み
//  - empty   : 認証済みだがウォレット未接続（アドレス無し）
//  - error   : 取得に失敗（リトライ可能）
type FetchState = "loading" | "ready" | "empty" | "error"

export function MyWalletPanel() {
  const { ready: privyReady, login } = usePrivy()

  // live wallet（injected / Privy embedded）は useWallet に集約済み。
  // settings 画面など他の消費者と同一の単一情報源を共有する。
  const { address: liveAddress } = useWallet()

  // live wallet が取れないときだけ、バックエンド記録アドレスをフォールバック取得。
  // （別デバイスで連携済み等。表示専用で署名はできない。）
  const linked = useLinkedWalletAddress(privyReady && !liveAddress)

  const address = liveAddress ?? linked.address

  // 表示状態を派生。Privy 初期化前は loading を維持（永久固まり回避）。
  const fetchState: FetchState = !privyReady
    ? "loading"
    : address
      ? "ready"
      : linked.state === "loading" || linked.state === "idle"
        ? "loading"
        : linked.state === "error"
          ? "error"
          : "empty"

  const [qrExpanded, setQrExpanded] = useState(false)
  const [toastMsg, setToastMsg] = useState("")
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!qrExpanded || !address || !canvasRef.current) return
    void QRCode.toCanvas(canvasRef.current, address, { width: 200, margin: 2 })
  }, [qrExpanded, address])

  // 「ウォレットに接続する」: Privy login をトリガ。
  // login 後は useWallet().address が更新され再描画される。
  const handleConnect = useCallback(async () => {
    try {
      await login()
    } catch {
      // 失敗時は接続誘導 UI のまま（Privy 側がモーダルでエラー提示）
    }
  }, [login])

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setTimeout(() => setToastMsg(""), 2000)
  }

  const handleCopy = async () => {
    if (!address) return
    try {
      await navigator.clipboard.writeText(address)
      showToast("アドレスをコピーしました ✓")
    } catch {
      showToast("コピーに失敗しました")
    }
  }

  const handleBasescan = () => {
    if (!address) return
    window.open(`https://basescan.org/address/${address}`, "_blank", "noopener,noreferrer")
  }

  // アドレスの先頭4文字・末尾4文字をハイライト表示
  function renderAddress(addr: string) {
    if (addr.length <= 8) return <span className="text-[#4ade9a]">{addr}</span>
    const start = addr.slice(0, 4)
    const mid = addr.slice(4, addr.length - 4)
    const end = addr.slice(-4)
    return (
      <>
        <span className="text-[#4ade9a]">{start}</span>
        <span className="text-zinc-300">{mid}</span>
        <span className="text-[#4ade9a]">{end}</span>
      </>
    )
  }

  return (
    <div className="space-y-4">
      {/* ウォレットカード */}
      <div className="bg-[#1a3d2e] rounded-2xl p-4 space-y-3">
        {/* Non-Custodial バッジ + Base Mainnet */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-[#4ade9a]" />
            <span className="text-[#4ade9a] text-xs font-semibold">Non-Custodial</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#1D9E75] inline-block" />
            <span className="text-zinc-300 text-xs">Base Mainnet</span>
          </div>
        </div>

        {/* ウォレットアドレス / 各種状態 */}
        {address ? (
          <div className="font-mono text-xs break-all leading-relaxed">
            {renderAddress(address)}
          </div>
        ) : fetchState === "loading" ? (
          <div className="flex items-center gap-2 text-zinc-500 text-xs">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-[#4ade9a]" />
            <span>ウォレットアドレスを読み込み中...</span>
          </div>
        ) : fetchState === "error" ? (
          // fail-visible: 永久ローディングにせずエラー + リトライ
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-[#e24b4a] flex-shrink-0 mt-0.5" />
              <p className="text-[#e24b4a] text-xs leading-relaxed">
                ウォレットアドレスの取得に失敗しました。通信環境をご確認のうえ再試行してください。
              </p>
            </div>
            <button
              onClick={() => linked.refetch()}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl
                         bg-zinc-800/60 hover:bg-zinc-700/60 active:bg-zinc-600/60
                         transition-colors text-xs text-zinc-200"
            >
              <RefreshCw className="w-3.5 h-3.5 text-[#4ade9a]" />
              再試行
            </button>
          </div>
        ) : (
          // empty: 認証済みだがウォレット未接続 → 接続誘導 UI
          <div className="space-y-3 py-1">
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-11 h-11 rounded-full bg-zinc-800/60 flex items-center justify-center">
                <Wallet className="w-5 h-5 text-[#4ade9a]" />
              </div>
              <p className="text-zinc-200 text-sm font-medium">
                ウォレットが未接続です
              </p>
              <p className="text-zinc-500 text-xs leading-relaxed">
                ウォレットに接続すると、受取用アドレスや QR コードが表示されます。
              </p>
            </div>
            <button
              onClick={() => void handleConnect()}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl
                         bg-[#1D9E75] hover:bg-[#178a65] active:bg-[#147a5a]
                         transition-colors text-sm font-semibold text-white"
            >
              <Wallet className="w-4 h-4" />
              ウォレットに接続する
            </button>
            {/* Privy 初期化前など login が使えない場合のフォールバック再試行 */}
            <button
              onClick={() => linked.refetch()}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl
                         bg-zinc-800/40 hover:bg-zinc-700/50 active:bg-zinc-600/50
                         transition-colors text-xs text-zinc-400"
            >
              <RefreshCw className="w-3.5 h-3.5 text-zinc-400" />
              再読み込み
            </button>
          </div>
        )}

        {/* 3つのアクションボタン */}
        <div className="flex gap-2 pt-1">
          <button
            onClick={handleCopy}
            disabled={!address}
            className="flex-1 flex flex-col items-center gap-1 py-2.5 rounded-xl
                       bg-zinc-800/60 hover:bg-zinc-700/60 active:bg-zinc-600/60
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors"
          >
            <Copy className="w-4 h-4 text-[#4ade9a]" />
            <span className="text-[10px] text-zinc-300">コピー</span>
          </button>

          <button
            onClick={() => setQrExpanded((v) => !v)}
            disabled={!address}
            className="flex-1 flex flex-col items-center gap-1 py-2.5 rounded-xl
                       bg-zinc-800/60 hover:bg-zinc-700/60 active:bg-zinc-600/60
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors"
          >
            <QrCode className="w-4 h-4 text-[#4ade9a]" />
            <span className="text-[10px] text-zinc-300">QR コード</span>
          </button>

          <button
            onClick={handleBasescan}
            disabled={!address}
            className="flex-1 flex flex-col items-center gap-1 py-2.5 rounded-xl
                       bg-zinc-800/60 hover:bg-zinc-700/60 active:bg-zinc-600/60
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors"
          >
            <ExternalLink className="w-4 h-4 text-[#4ade9a]" />
            <span className="text-[10px] text-zinc-300">Basescan</span>
          </button>
        </div>
      </div>

      {/* QRコードセクション */}
      {qrExpanded && address && (
        <div className="bg-zinc-900 rounded-2xl p-4 space-y-3 border border-zinc-800">
          <p className="text-zinc-300 text-sm font-medium text-center">受取用 QR コード</p>
          <div className="flex justify-center">
            <canvas ref={canvasRef} className="rounded-xl bg-white p-2" />
          </div>
          <p className="text-zinc-500 text-xs text-center">
            このQRコードをスキャンしてUSDCを受け取れます
          </p>
        </div>
      )}

      {/* セキュリティ注意書き */}
      <div className="flex items-start gap-2 px-1">
        <Shield className="w-4 h-4 text-zinc-500 flex-shrink-0 mt-0.5" />
        <p className="text-zinc-500 text-xs leading-relaxed">
          送金前に先頭4桁・末尾4桁をご確認ください
        </p>
      </div>

      {/* トースト */}
      {toastMsg && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 bg-zinc-800 text-white px-4 py-2 rounded-full text-sm z-[60] shadow-lg">
          {toastMsg}
        </div>
      )}
    </div>
  )
}
