'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import {
  TradeActionBadge,
  WalletAddressMask,
  TxHashLink,
  DateRangeFilter,
} from "@/components/shared";
import type { TxHashLinkProps } from "@/components/shared/TxHashLink";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { saveBlob } from "@/lib/saveBlob";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Download, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import {
  fetchAdminTransactions,
  type AdminTransaction,
} from "@/lib/api/admin-transactions";

// -----------------------------------------------------------------------
// Constants
// -----------------------------------------------------------------------

const PAGE_SIZE = 20;

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}

/** Backend returns lowercase status ("success", "failed", "pending"). */
function statusBadgeClass(status: string): string {
  switch (status.toLowerCase()) {
    case "success":
      return "bg-green-100 text-green-700 border-green-200";
    case "failed":
      return "bg-red-100 text-red-700 border-red-200";
    case "pending":
      return "bg-yellow-100 text-yellow-700 border-yellow-200";
    default:
      return "bg-gray-100 text-gray-700 border-gray-200";
  }
}

function statusLabel(status: string, labels: Record<string, string>): string {
  return labels[status.toLowerCase()] ?? status;
}

function exportCsv(trades: AdminTransaction[], headers: string[]) {
  const rows = trades.map((t) => [
    t.id,
    formatDateTime(t.created_at),
    t.user_id,
    t.wallet_address ?? "",
    t.operation,
    t.asset,
    t.amount,
    t.amount_usd,
    t.status,
    t.tx_hash ?? "",
    t.chain,
    t.is_dry_run ? "Yes" : "No",
  ]);
  const csv = [headers, ...rows].map((r) => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  void saveBlob(blob, `trades-${new Date().toISOString().slice(0, 10)}.csv`);
}

// -----------------------------------------------------------------------
// Page
// -----------------------------------------------------------------------

function TradesContent() {
  const t = useTranslations("AdminTrades");

  const [searchInput, setSearchInput] = useState("");
  const [actionFilter, setActionFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [dateRange, setDateRange] = useState<{ from: Date; to: Date } | "all">("all");
  const [page, setPage] = useState(0);

  const [trades, setTrades] = useState<AdminTransaction[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Debounce search input
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearchChange = (value: string) => {
    setSearchInput(value);
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      setDebouncedSearch(value);
      setPage(0);
    }, 400);
  };

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const filters: Parameters<typeof fetchAdminTransactions>[0] = {
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      };

      // Parse search: if numeric treat as user_id, else as wallet_address substring
      if (debouncedSearch) {
        const numeric = Number(debouncedSearch);
        if (!isNaN(numeric) && debouncedSearch.trim() !== "") {
          filters.user_id = numeric;
        } else {
          filters.wallet_address = debouncedSearch;
        }
      }

      if (actionFilter !== "ALL") filters.operation = actionFilter;

      if (statusFilter !== "ALL") filters.tx_status = statusFilter.toLowerCase();

      if (dateRange !== "all") {
        filters.date_from = dateRange.from.toISOString();
        filters.date_to = dateRange.to.toISOString();
      }

      const res = await fetchAdminTransactions(filters);
      setTrades(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(t("fetchError"));
      setTrades([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, actionFilter, statusFilter, dateRange, page]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  // Reset page when filters change
  const handleActionChange = (v: string) => { setActionFilter(v); setPage(0); };
  const handleStatusChange = (v: string) => { setStatusFilter(v); setPage(0); };
  const handleDateRangeChange = (v: { from: Date; to: Date } | "all") => {
    setDateRange(v);
    setPage(0);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t("pageTitle")}</h1>
          <p className="mt-0.5 text-xs text-gray-400">
            {t("subtitle", { total: total.toLocaleString(), count: trades.length })}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => exportCsv(trades, [
            t("csvHeaderId"), t("csvHeaderDatetime"), t("csvHeaderUserId"),
            t("csvHeaderWallet"), t("csvHeaderOperation"), t("csvHeaderAsset"),
            t("csvHeaderAmount"), t("csvHeaderAmountUsd"), t("csvHeaderStatus"),
            t("csvHeaderTxHash"), t("csvHeaderChain"), t("csvHeaderDryRun"),
          ])}
          disabled={trades.length === 0}
        >
          <Download className="mr-2 h-4 w-4" />
          {t("csvExport")}
        </Button>
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <Input
            placeholder={t("searchPlaceholder")}
            value={searchInput}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="h-8 w-56 text-xs"
          />
          <Select value={actionFilter} onValueChange={handleActionChange}>
            <SelectTrigger className="h-8 w-36 text-xs">
              <SelectValue placeholder={t("actionFilterPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL" className="text-xs">{t("actionAll")}</SelectItem>
              <SelectItem value="BUY" className="text-xs">BUY</SelectItem>
              <SelectItem value="SELL" className="text-xs">SELL</SelectItem>
              <SelectItem value="HOLD" className="text-xs">HOLD</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={handleStatusChange}>
            <SelectTrigger className="h-8 w-36 text-xs">
              <SelectValue placeholder={t("statusFilterPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL" className="text-xs">{t("statusAll")}</SelectItem>
              <SelectItem value="SUCCESS" className="text-xs">{t("statusSuccess")}</SelectItem>
              <SelectItem value="FAILED" className="text-xs">{t("statusFailed")}</SelectItem>
              <SelectItem value="PENDING" className="text-xs">{t("statusPending")}</SelectItem>
            </SelectContent>
          </Select>
          <DateRangeFilter onChange={handleDateRangeChange} presets />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* Desktop Table */}
      <div className="hidden md:block rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">{t("colDatetime")}</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">{t("colUser")}</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">{t("colAction")}</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">{t("colAmount")}</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">{t("colStatus")}</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">{t("colTxHash")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center">
                  <Loader2 className="inline h-5 w-5 animate-spin text-gray-400" />
                </td>
              </tr>
            ) : trades.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-gray-400">
                  {t("noTrades")}
                </td>
              </tr>
            ) : (
              trades.map((trade) => (
                <tr key={trade.id} className="hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDateTime(trade.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    {trade.wallet_address ? (
                      <WalletAddressMask address={trade.wallet_address} />
                    ) : (
                      <span className="text-xs text-gray-500">{t("uidLabel", { uid: trade.user_id })}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <TradeActionBadge action={trade.operation as "BUY" | "SELL" | "HOLD"} />
                      {trade.is_dry_run && (
                        <Badge variant="outline" className="text-xs px-1.5 py-0 text-purple-600 border-purple-200 bg-purple-50">
                          Dry Run
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-800 dark:text-gray-200">
                    {trade.operation === "HOLD" ? "—" : `$${Number(trade.amount_usd).toLocaleString()}`}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className={`text-xs px-2 py-0.5 ${statusBadgeClass(trade.status)}`}>
                      {statusLabel(trade.status, { success: t("statusSuccess"), failed: t("statusFailed"), pending: t("statusPending") })}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    {trade.tx_hash ? (
                      <TxHashLink hash={trade.tx_hash} chain={trade.chain as TxHashLinkProps["chain"]} truncate />
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
        {loading ? (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 text-center">
            <Loader2 className="inline h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : trades.length === 0 ? (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-400">
            {t("noTrades")}
          </div>
        ) : (
          trades.map((trade) => (
            <div key={trade.id} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <TradeActionBadge action={trade.operation as "BUY" | "SELL" | "HOLD"} />
                  {trade.is_dry_run && (
                    <Badge variant="outline" className="text-xs px-1.5 py-0 text-purple-600 border-purple-200 bg-purple-50">
                      Dry Run
                    </Badge>
                  )}
                </div>
                <Badge variant="outline" className={`text-xs px-2 py-0.5 flex-shrink-0 ${statusBadgeClass(trade.status)}`}>
                  {statusLabel(trade.status, { success: t("statusSuccess"), failed: t("statusFailed"), pending: t("statusPending") })}
                </Badge>
              </div>
              <div className="text-xs text-gray-500">{formatDateTime(trade.created_at)}</div>
              <div>
                {trade.wallet_address ? (
                  <WalletAddressMask address={trade.wallet_address} />
                ) : (
                  <span className="text-xs text-gray-500">{t("uidLabel", { uid: trade.user_id })}</span>
                )}
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">{trade.asset}</span>
                <span className="font-mono font-semibold text-gray-800 dark:text-gray-200">
                  {trade.operation === "HOLD" ? "—" : `$${Number(trade.amount_usd).toLocaleString()}`}
                </span>
              </div>
              {trade.tx_hash && (
                <TxHashLink hash={trade.tx_hash} chain={trade.chain as TxHashLinkProps["chain"]} truncate />
              )}
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <span className="text-xs">
            {t("paginationRange", { from: page * PAGE_SIZE + 1, to: Math.min((page + 1) * PAGE_SIZE, total), total: total.toLocaleString() })}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p - 1)}
              disabled={page === 0 || loading}
              className="h-8 px-2"
            >
              <ChevronLeft className="h-4 w-4" />
              {t("prevPage")}
            </Button>
            <span className="text-xs">
              {t("paginationPage", { current: page + 1, totalPages })}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= totalPages - 1 || loading}
              className="h-8 px-2"
            >
              {t("nextPage")}
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function TradesPageInner() {
  const t = useTranslations("AdminTrades");
  return (
    <AuthGuard adminOnly>
      <>
        <title>{t("pageTitleTag")}</title>
        <TradesContent />
      </>
    </AuthGuard>
  );
}

export default function TradesPage() {
  return <TradesPageInner />;
}
