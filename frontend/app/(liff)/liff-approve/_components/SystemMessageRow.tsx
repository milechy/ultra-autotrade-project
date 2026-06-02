// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/SystemMessageRow.tsx

interface SystemMessageRowProps {
  message: string;
}

export function SystemMessageRow({ message }: SystemMessageRowProps) {
  return (
    <div className="flex items-center gap-2 my-2 px-2 animate-in fade-in duration-300">
      <div className="flex-1 border-t border-zinc-800" />
      <span className="text-xs text-zinc-500 shrink-0 text-center">{message}</span>
      <div className="flex-1 border-t border-zinc-800" />
    </div>
  );
}
