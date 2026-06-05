// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useState, useEffect } from "react"
import { Copy, QrCode, ExternalLink, ShieldCheck, Shield } from "lucide-react"
import { useWallets } from "@privy-io/react-auth"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

export function MyWalletPanel() {
  const { wallets } = useWallets()
  const [address, setAddress] = useState<string | null>(null)
  const [qrExpanded, setQrExpanded] = useState(false)
  const [toastMsg, setToastMsg] = useState("")

  // Privy embedded wallet アドレスを取得、なければ API から取得
  useEffect(() => {
    const privyWallet = wallets.find((w) => w.walletClientType === "privy")
    if (privyWallet?.address) {
      setAddress(privyWallet.address)
      return
    }

    // Privy ウォレットがない場合は API から取得
    const token =
      typeof window !== "undefined"
        ? (localStorage.getItem("ultra_auth_token") ?? "")
        : ""
    if (!token) return

    fetch(`${API_BASE}/api/user/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.ok ? res.json() : null)
      .then((data: { wallet_address?: string | null } | null) => {
        if (data?.wallet_address) {
          setAddress(data.wallet_address)
        }
      })
      .catch(() => {
        // fail-open: アドレス取得失敗時は null のまま
      })
  }, [wallets])

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

        {/* ウォレットアドレス */}
        {address ? (
          <div className="font-mono text-xs break-all leading-relaxed">
            {renderAddress(address)}
          </div>
        ) : (
          <div className="text-zinc-500 text-xs">ウォレットアドレスを読み込み中...</div>
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
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(address)}`}
              alt="ウォレットアドレス QR コード"
              width={200}
              height={200}
              className="rounded-xl bg-white p-2"
            />
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
