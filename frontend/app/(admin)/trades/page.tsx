'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useMemo } from "react";
import AuthGuard from "@/components/AuthGuard";
import {
  TradeActionBadge,
  WalletAddressMask,
  TxHashLink,
  DateRangeFilter,
} from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Download } from "lucide-react";

// -----------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------

type TradeAction = "BUY" | "SELL" | "HOLD";
type TradeStatus = "SUCCESS" | "FAILED" | "PENDING";

interface Trade {
  id: string;
  timestamp: string;
  userId: string;
  walletAddress: string;
  action: TradeAction;
  asset: string;
  amount: number;
  amountUSD: number;
  status: TradeStatus;
  txHash: string | null;
  chain: "arbitrum" | "base" | "ethereum";
  isDryRun: boolean;
}

// -----------------------------------------------------------------------
// TODO: GET /api/admin/trades - Replace mock data with real API
// -----------------------------------------------------------------------

const MOCK_TRADES: Trade[] = [
  {
    id: "trade-001",
    timestamp: "2026-03-22T10:30:00Z",
    userId: "user-1",
    walletAddress: "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12",
    action: "BUY",
    asset: "USDC",
    amount: 500,
    amountUSD: 500,
    status: "SUCCESS",
    txHash: "0xabc123def456abc123def456abc123def456abc123def456abc123def456abc1",
    chain: "arbitrum",
    isDryRun: false,
  },
  {
    id: "trade-002",
    timestamp: "2026-03-22T09:15:00Z",
    userId: "user-2",
    walletAddress: "0x1234567890AbCdEf1234567890AbCdEf12345678",
    action: "SELL",
    asset: "USDC",
    amount: 200,
    amountUSD: 200,
    status: "SUCCESS",
    txHash: "0xdef456abc789def456abc789def456abc789def456abc789def456abc789def4",
    chain: "base",
    isDryRun: false,
  },
  {
    id: "trade-003",
    timestamp: "2026-03-22T08:00:00Z",
    userId: "user-1",
    walletAddress: "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12",
    action: "HOLD",
    asset: "USDC",
    amount: 0,
    amountUSD: 0,
    status: "SUCCESS",
    txHash: null,
    chain: "arbitrum",
    isDryRun: true,
  },
  {
    id: "trade-004",
    timestamp: "2026-03-21T22:45:00Z",
    userId: "user-3",
    walletAddress: "0x9876543210FeDcBa9876543210FeDcBa98765432",
    action: "BUY",
    asset: "ETH",
    amount: 0.15,
    amountUSD: 412,
    status: "FAILED",
    txHash: null,
    chain: "ethereum",
    isDryRun: false,
  },
  {
    id: "trade-005",
    timestamp: "2026-03-21T18:30:00Z",
    userId: "user-2",
    walletAddress: "0x1234567890AbCdEf1234567890AbCdEf12345678",
    action: "BUY",
    asset: "USDC",
    amount: 1000,
    amountUSD: 1000,
    status: "SUCCESS",
    txHash: "0xfed123abc456fed123abc456fed123abc456fed123abc456fed123abc456fed1",
    chain: "arbitrum",
    isDryRun: true,
  },
  {
    id: "trade-006",
    timestamp: "2026-03-21T14:00:00Z",
    userId: "user-4",
    walletAddress: "0xFeDcBa9876543210FeDcBa9876543210FeDcBa98",
    action: "SELL",
    asset: "USDC",
    amount: 750,
    amountUSD: 750,
    status: "PENDING",
    txHash: null,
    chain: "arbitrum",
    isDryRun: false,
  },
  {
    id: "trade-007",
    timestamp: "2026-03-21T10:15:00Z",
    userId: "user-1",
    walletAddress: "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12",
    action: "BUY",
    asset: "WBTC",
    amount: 0.005,
    amountUSD: 325,
    status: "SUCCESS",
    txHash: "0x111aaa222bbb333ccc444ddd555eee666fff777aaa888bbb999ccc000ddd111e",
    chain: "base",
    isDryRun: false,
  },
  {
    id: "trade-008",
    timestamp: "2026-03-20T20:00:00Z",
    userId: "user-5",
    walletAddress: "0xCaFeBaBe1234567890CaFeBaBe1234567890CaFe",
    action: "SELL",
    asset: "ETH",
    amount: 0.3,
    amountUSD: 823,
    status: "SUCCESS",
    txHash: "0x222bbb333ccc444ddd555eee666fff777aaa888bbb999ccc000ddd111eee222f",
    chain: "ethereum",
    isDryRun: false,
  },
  {
    id: "trade-009",
    timestamp: "2026-03-20T16:30:00Z",
    userId: "user-3",
    walletAddress: "0x9876543210FeDcBa9876543210FeDcBa98765432",
    action: "HOLD",
    asset: "USDC",
    amount: 0,
    amountUSD: 0,
    status: "SUCCESS",
    txHash: null,
    chain: "arbitrum",
    isDryRun: false,
  },
  {
    id: "trade-010",
    timestamp: "2026-03-20T09:00:00Z",
    userId: "user-2",
    walletAddress: "0x1234567890AbCdEf1234567890AbCdEf12345678",
    action: "BUY",
    asset: "USDC",
    amount: 300,
    amountUSD: 300,
    status: "FAILED",
    txHash: null,
    chain: "base",
    isDryRun: true,
  },
];

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}

function statusBadgeClass(status: TradeStatus): string {
  switch (status) {
    case "SUCCESS":
      return "bg-green-100 text-green-700 border-green-200";
    case "FAILED":
      return "bg-red-100 text-red-700 border-red-200";
    case "PENDING":
      return "bg-yellow-100 text-yellow-700 border-yellow-200";
  }
}

function statusLabel(status: TradeStatus): string {
  switch (status) {
    case "SUCCESS": return "成功";
    case "FAILED": return "失敗";
    case "PENDING": return "処理中";
  }
}

function exportCsv(trades: Trade[]) {
  const headers = [
    "ID", "日時", "ユーザーID", "ウォレット", "操作", "アセット",
    "数量", "USD相当", "ステータス", "Tx Hash", "チェーン", "Dry Run",
  ];
  const rows = trades.map((t) => [
    t.id,
    formatDateTime(t.timestamp),
    t.userId,
    t.walletAddress,
    t.action,
    t.asset,
    t.amount,
    t.amountUSD,
    t.status,
    t.txHash ?? "",
    t.chain,
    t.isDryRun ? "Yes" : "No",
  ]);
  const csv = [headers, ...rows].map((r) => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `trades-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// -----------------------------------------------------------------------
// Page
// -----------------------------------------------------------------------

function TradesContent() {
  const [userFilter, setUserFilter] = useState("");
  const [actionFilter, setActionFilter] = useState<"ALL" | TradeAction>("ALL");
  const [statusFilter, setStatusFilter] = useState<"ALL" | TradeStatus>("ALL");
  const [dateRange, setDateRange] = useState<{ from: Date; to: Date } | "all">("all");

  const filtered = useMemo(() => {
    return MOCK_TRADES.filter((t) => {
      if (userFilter && !t.walletAddress.toLowerCase().includes(userFilter.toLowerCase()) &&
          !t.userId.toLowerCase().includes(userFilter.toLowerCase())) return false;
      if (actionFilter !== "ALL" && t.action !== actionFilter) return false;
      if (statusFilter !== "ALL" && t.status !== statusFilter) return false;
      if (dateRange !== "all") {
        const ts = new Date(t.timestamp);
        if (ts < dateRange.from || ts > dateRange.to) return false;
      }
      return true;
    });
  }, [userFilter, actionFilter, statusFilter, dateRange]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">取引履歴</h1>
          <p className="mt-0.5 text-xs text-gray-400">
            全ユーザーの取引一覧 — {filtered.length} 件表示
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => exportCsv(filtered)}>
          <Download className="mr-2 h-4 w-4" />
          CSV エクスポート
        </Button>
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <Input
            placeholder="ユーザー / ウォレットで検索..."
            value={userFilter}
            onChange={(e) => setUserFilter(e.target.value)}
            className="h-8 w-56 text-xs"
          />
          <Select value={actionFilter} onValueChange={(v) => setActionFilter(v as typeof actionFilter)}>
            <SelectTrigger className="h-8 w-36 text-xs">
              <SelectValue placeholder="操作種別" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL" className="text-xs">すべての操作</SelectItem>
              <SelectItem value="BUY" className="text-xs">BUY</SelectItem>
              <SelectItem value="SELL" className="text-xs">SELL</SelectItem>
              <SelectItem value="HOLD" className="text-xs">HOLD</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}>
            <SelectTrigger className="h-8 w-36 text-xs">
              <SelectValue placeholder="ステータス" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL" className="text-xs">すべて</SelectItem>
              <SelectItem value="SUCCESS" className="text-xs">成功</SelectItem>
              <SelectItem value="FAILED" className="text-xs">失敗</SelectItem>
              <SelectItem value="PENDING" className="text-xs">処理中</SelectItem>
            </SelectContent>
          </Select>
          <DateRangeFilter onChange={setDateRange} presets />
        </div>
      </div>

      {/* Desktop Table */}
      <div className="hidden md:block rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">日時</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">ユーザー</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">操作</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">金額</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">ステータス</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">TxHash</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-gray-400">
                  条件に一致する取引がありません
                </td>
              </tr>
            ) : (
              filtered.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50 dark:bg-gray-900 transition-colors">
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDateTime(t.timestamp)}
                  </td>
                  <td className="px-4 py-3">
                    <WalletAddressMask address={t.walletAddress} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <TradeActionBadge action={t.action} />
                      {t.isDryRun && (
                        <Badge variant="outline" className="text-xs px-1.5 py-0 text-purple-600 border-purple-200 bg-purple-50">
                          Dry Run
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-800 dark:text-gray-200">
                    {t.action === "HOLD" ? "—" : `$${t.amountUSD.toLocaleString()}`}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className={`text-xs px-2 py-0.5 ${statusBadgeClass(t.status)}`}>
                      {statusLabel(t.status)}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    {t.txHash ? (
                      <TxHashLink hash={t.txHash} chain={t.chain} truncate />
                    ) : (
                      <span className="text-xs text-gray-400">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile Cards */}
      <div className="md:hidden space-y-3">
        {filtered.length === 0 ? (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-400">
            条件に一致する取引がありません
          </div>
        ) : (
          filtered.map((t) => (
            <div key={t.id} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <TradeActionBadge action={t.action} />
                  {t.isDryRun && (
                    <Badge variant="outline" className="text-xs px-1.5 py-0 text-purple-600 border-purple-200 bg-purple-50">
                      Dry Run
                    </Badge>
                  )}
                </div>
                <Badge variant="outline" className={`text-xs px-2 py-0.5 flex-shrink-0 ${statusBadgeClass(t.status)}`}>
                  {statusLabel(t.status)}
                </Badge>
              </div>
              <div className="text-xs text-gray-500">{formatDateTime(t.timestamp)}</div>
              <div>
                <WalletAddressMask address={t.walletAddress} />
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">{t.asset}</span>
                <span className="font-mono font-semibold text-gray-800 dark:text-gray-200">
                  {t.action === "HOLD" ? "—" : `$${t.amountUSD.toLocaleString()}`}
                </span>
              </div>
              {t.txHash && (
                <TxHashLink hash={t.txHash} chain={t.chain} truncate />
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default function TradesPage() {
  return (
    <AuthGuard>
      <>
        <title>取引履歴 - Ultra AutoTrade</title>
        <TradesContent />
      </>
    </AuthGuard>
  );
}
