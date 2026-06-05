// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { ChevronLeft } from "lucide-react"

interface SlideUpPanelProps {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  maxHeight?: string
}

export function SlideUpPanel({
  open,
  onClose,
  title,
  children,
  maxHeight = "90vh",
}: SlideUpPanelProps) {
  if (!open) return null
  return (
    <>
      {/* バックドロップ */}
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />
      {/* パネル本体 */}
      <div
        style={{ maxHeight }}
        className="fixed bottom-0 left-0 right-0 z-50
                   bg-zinc-900 rounded-t-2xl border-t border-zinc-800
                   overflow-y-auto
                   animate-in slide-in-from-bottom duration-300"
      >
        {/* ドラッグハンドル + ヘッダー */}
        <div className="sticky top-0 bg-zinc-900 pt-3 pb-0 px-4">
          <div className="mx-auto mb-3 h-1 w-8 rounded-full bg-zinc-700" />
          {/* パネルヘッダー */}
          <div className="flex items-center bg-[#1a3d2e] -mx-4 px-4 py-3 mb-4">
            <button onClick={onClose} className="text-white mr-2">
              <ChevronLeft className="w-5 h-5" />
            </button>
            <h2 className="text-white font-semibold text-base">{title}</h2>
          </div>
        </div>
        <div className="px-4 pb-8">{children}</div>
      </div>
    </>
  )
}
