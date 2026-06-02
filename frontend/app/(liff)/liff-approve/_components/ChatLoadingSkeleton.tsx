// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/ChatLoadingSkeleton.tsx

export function ChatLoadingSkeleton() {
  return (
    <div className="px-3 py-2 space-y-2 animate-pulse">
      {/* history placeholder rows */}
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-12 bg-zinc-900 rounded-lg" />
      ))}

      {/* bubble placeholder */}
      <div className="mt-4 max-w-[88%] bg-zinc-900 rounded-2xl rounded-tl-sm p-3 space-y-2">
        <div className="h-4 w-24 bg-zinc-800 rounded" />
        <div className="h-7 w-32 bg-zinc-800 rounded" />
        <div className="h-2 w-full bg-zinc-800 rounded-full" />
        <div className="h-3 w-full bg-zinc-800 rounded" />
        <div className="h-3 w-3/4 bg-zinc-800 rounded" />
      </div>
    </div>
  );
}
