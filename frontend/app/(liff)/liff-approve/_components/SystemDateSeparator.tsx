// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/SystemDateSeparator.tsx

interface SystemDateSeparatorProps {
  date: string; // e.g. "2026/06/01"
}

export function SystemDateSeparator({ date }: SystemDateSeparatorProps) {
  return (
    <div className="flex items-center gap-2 my-3 px-2">
      <div className="flex-1 border-t border-zinc-800" />
      <span className="text-xs text-zinc-600 shrink-0">{date}</span>
      <div className="flex-1 border-t border-zinc-800" />
    </div>
  );
}
