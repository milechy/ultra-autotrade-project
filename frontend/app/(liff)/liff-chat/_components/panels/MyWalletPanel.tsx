// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useState, useCallback, useEffect, useRef } from "react"
import QRCode from "qrcode"
import {
  Copy,
  QrCode,
  ShieldCheck,
  Shield,
  Wallet,
  AlertTriangle,
  RefreshCw,
  Loader2,
} from "lucide-react"
import { useTranslations } from "next-intl"
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
  const t = useTranslations("Liff.panels.myWallet")
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
      showToast(t("toastCopied"))
    } catch {
      showToast(t("toastCopyFailed"))
    }
  }

  // アドレスの先頭4文字・末尾4文字をハイライト表示
  function renderAddress(addr: string) {
    if (addr.length <= 8) return <span className="text-[#1D9E75]">{addr}</span>
    const start = addr.slice(0, 4)
    const mid = addr.slice(4, addr.length - 4)
    const end = addr.slice(-4)
    return (
      <>
        <span className="text-[#1D9E75]">{start}</span>
        <span className="text-[#736f7e]">{mid}</span>
        <span className="text-[#1D9E75]">{end}</span>
      </>
    )
  }

  return (
    <div className="space-y-4">
      {/* ウォレットカード */}
      <div className="bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] rounded-2xl p-4 space-y-3">
        {/* Non-Custodial バッジ + Base Mainnet */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-[#1D9E75]" />
            <span className="text-[#1D9E75] text-xs font-semibold">{t("nonCustodial")}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#1D9E75] inline-block" />
            <span className="text-[#736f7e] text-xs">{t("baseMainnet")}</span>
          </div>
        </div>

        {/* ウォレットアドレス / 各種状態 */}
        {address ? (
          <div className="font-mono text-xs break-all leading-relaxed">
            {renderAddress(address)}
          </div>
        ) : fetchState === "loading" ? (
          <div className="flex items-center gap-2 text-[#736f7e] text-xs">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-[#1D9E75]" />
            <span>{t("addressLoading")}</span>
          </div>
        ) : fetchState === "error" ? (
          // fail-visible: 永久ローディングにせずエラー + リトライ
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <p className="text-red-600 text-xs leading-relaxed">
                {t("addressError")}
              </p>
            </div>
            <button
              onClick={() => linked.refetch()}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl
                         bg-[#1b1a23]/80 hover:bg-[#1b1a23] active:bg-[#1b1a23]
                         transition-colors text-xs text-[#fbf7f0]"
            >
              <RefreshCw className="w-3.5 h-3.5 text-[#1D9E75]" />
              {t("retryBtn")}
            </button>
          </div>
        ) : (
          // empty: 認証済みだがウォレット未接続 → 接続誘導 UI
          <div className="space-y-3 py-1">
            <div className="flex flex-col items-center text-center gap-2">
              <div className="w-11 h-11 rounded-full bg-[#1b1a23]/80 flex items-center justify-center">
                <Wallet className="w-5 h-5 text-[#1D9E75]" />
              </div>
              <p className="text-[#1c1a27] text-sm font-medium">
                {t("walletNotConnected")}
              </p>
              <p className="text-[#736f7e] text-xs leading-relaxed">
                {t("walletNotConnectedDesc")}
              </p>
            </div>
            <button
              onClick={() => void handleConnect()}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl
                         bg-[#1D9E75] hover:bg-[#178a65] active:bg-[#147a5a]
                         transition-colors text-sm font-semibold text-white"
            >
              <Wallet className="w-4 h-4" />
              {t("connectBtn")}
            </button>
            {/* Privy 初期化前など login が使えない場合のフォールバック再試行 */}
            <button
              onClick={() => linked.refetch()}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl
                         bg-[#1b1a23]/70 hover:bg-[#1b1a23] active:bg-[#1b1a23]
                         transition-colors text-xs text-[#fbf7f0]"
            >
              <RefreshCw className="w-3.5 h-3.5 text-[#fbf7f0]" />
              {t("reloadBtn")}
            </button>
          </div>
        )}

        {/* 3つのアクションボタン */}
        <div className="flex gap-2 pt-1">
          <button
            onClick={handleCopy}
            disabled={!address}
            className="flex-1 flex flex-col items-center gap-1 py-2.5 rounded-xl
                       bg-[#1b1a23]/80 hover:bg-[#1b1a23] active:bg-[#1b1a23]
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors"
          >
            <Copy className="w-4 h-4 text-[#1D9E75]" />
            <span className="text-[10px] text-[#fbf7f0]">{t("copyLabel")}</span>
          </button>

          <button
            onClick={() => setQrExpanded((v) => !v)}
            disabled={!address}
            className="flex-1 flex flex-col items-center gap-1 py-2.5 rounded-xl
                       bg-[#1b1a23]/80 hover:bg-[#1b1a23] active:bg-[#1b1a23]
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors"
          >
            <QrCode className="w-4 h-4 text-[#1D9E75]" />
            <span className="text-[10px] text-[#fbf7f0]">{t("qrLabel")}</span>
          </button>

        </div>
      </div>

      {/* QRコードセクション */}
      {qrExpanded && address && (
        <div className="ax-card-warm rounded-2xl p-4 space-y-3 border border-[#1c1a27]/15">
          <p className="text-[#736f7e] text-sm font-medium text-center">{t("qrTitle")}</p>
          <div className="flex justify-center">
            <canvas ref={canvasRef} className="rounded-xl bg-white p-2" />
          </div>
          <p className="text-[#736f7e] text-xs text-center">
            {t("qrNote")}
          </p>
        </div>
      )}

      {/* セキュリティ注意書き */}
      <div className="flex items-start gap-2 px-1">
        <Shield className="w-4 h-4 text-[#736f7e] flex-shrink-0 mt-0.5" />
        <p className="text-[#736f7e] text-xs leading-relaxed">
          {t("securityNote")}
        </p>
      </div>

      {/* トースト */}
      {toastMsg && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 bg-[#1b1a23] text-[#fbf7f0] px-4 py-2 rounded-full text-sm z-[60] shadow-lg">
          {toastMsg}
        </div>
      )}
    </div>
  )
}
