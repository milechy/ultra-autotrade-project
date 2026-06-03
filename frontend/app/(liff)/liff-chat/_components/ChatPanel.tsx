// Copyright (c) Ultra AutoTrade. All rights reserved.
// _components/ChatPanel.tsx — スタブ（別エージェントが Phase 4 L2 で実装予定）
export function ChatPanel({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />
      <div
        className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-900 rounded-t-2xl
                   h-[85vh] animate-in slide-in-from-bottom duration-300"
      >
        <div className="flex items-center bg-[#1a3d2e] px-4 py-3 rounded-t-2xl">
          <button onClick={onClose} className="text-white mr-3 text-xl leading-none">
            ✕
          </button>
          <span className="text-white font-semibold">UATa AI</span>
        </div>
        <div className="flex items-center justify-center h-[calc(100%-56px)] text-zinc-600 text-sm">
          チャット機能を読み込み中...
        </div>
      </div>
    </>
  )
}
