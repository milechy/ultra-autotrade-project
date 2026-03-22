'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { fetchAutomationStatus } from "@/lib/api/automation";
import { fetchExchangeStatus } from "@/lib/api/exchange";
import { fetchAaveStatus } from "@/lib/api/aave";
import { apiPost } from "@/lib/api/client";
import {
  KPICard,
  StatusBadge,
  EmergencyStopButton,
} from "@/components/shared";
import type { AutomationStatus } from "@/lib/types";
import type { ExchangeStatusResponse } from "@/lib/api/exchange";
import type { AaveMonitorStatus } from "@/lib/api/aave";
import { Users, DollarSign, ArrowLeftRight, Bell } from "lucide-react";

// 静的モックデータ（Math.random() を避けて hydration mismatch を防ぐ）
const STATIC_VOLUME_DATA = [
  { label: "3/16", trades: 8 },
  { label: "3/17", trades: 12 },
  { label: "3/18", trades: 5 },
  { label: "3/19", trades: 17 },
  { label: "3/20", trades: 9 },
  { label: "3/21", trades: 14 },
  { label: "3/22", trades: 6 },
];

// シンプルなバーグラフ（CSS のみ、recharts 不使用）
function SimpleBarChart({ data }: { data: { label: string; trades: number }[] }) {
  const maxVal = Math.max(...data.map((d) => d.trades), 1);
  return (
    <div className="flex h-[160px] items-end gap-2">
      {data.map((d) => (
        <div key={d.label} className="flex flex-1 flex-col items-center gap-1">
          <div
            className="w-full rounded-t bg-blue-500"
            style={{ height: `${(d.trades / maxVal) * 120}px` }}
          />
          <span className="text-[10px] text-gray-500">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

// Health Factor 数値表示（HealthFactorGauge の代替）
function HfDisplay({ value }: { value: number | null }) {
  if (value === null) {
    return <p className="text-4xl font-bold text-gray-300">—</p>;
  }
  const color = value >= 2.0 ? "text-green-600" : value >= 1.6 ? "text-yellow-500" : "text-red-600";
  return (
    <div className="flex flex-col items-center gap-1">
      <p className={`text-5xl font-bold ${color}`}>{value.toFixed(2)}</p>
      <p className="text-xs text-gray-400">Health Factor</p>
    </div>
  );
}

function DashboardContent() {
  const { token } = useAuth();
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null);
  const [exchangeStatus, setExchangeStatus] = useState<ExchangeStatusResponse | null>(null);
  const [aaveStatus, setAaveStatus] = useState<AaveMonitorStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      const [auto, exchange] = await Promise.all([
        fetchAutomationStatus(token ?? undefined),
        fetchExchangeStatus(token),
      ]);
      setAutomationStatus(auto);
      setExchangeStatus(exchange);
      setLastUpdated(new Date().toLocaleTimeString("ja-JP"));
      setError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`データ取得エラー: ${msg}`);
    }
    try {
      const aave = await fetchAaveStatus(token);
      setAaveStatus(aave);
    } catch {
      // ベストエフォート
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const hfNum =
    aaveStatus?.health_factor != null ? parseFloat(aaveStatus.health_factor) : null;

  const systemStatus: "NORMAL" | "SAFE_MODE" | "HARD_STOP" = (() => {
    if (automationStatus?.is_trading_paused) return "HARD_STOP";
    if (hfNum != null && hfNum < 1.8) return "SAFE_MODE";
    return "NORMAL";
  })();

  async function handleEmergencyStop() {
    await apiPost("/api/aave/emergency-stop", {});
    await fetchData();
  }

  const totalTrades = exchangeStatus?.daily_trades_used ?? "—";
  const aaveUsdcRaw = aaveStatus?.balance?.usdc_balance;
  const aaveAUsdcRaw = aaveStatus?.balance?.a_usdc_balance;
  const aaveTotal =
    aaveUsdcRaw != null && aaveAUsdcRaw != null
      ? `$${(parseFloat(aaveUsdcRaw) + parseFloat(aaveAUsdcRaw)).toFixed(0)}`
      : "$—";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">運用ダッシュボード</h1>
          {lastUpdated && (
            <p className="mt-0.5 text-xs text-gray-400">
              最終更新: {lastUpdated}（30秒自動更新）
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={systemStatus} />
          <EmergencyStopButton onStop={handleEmergencyStop} variant="inline" />
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KPICard
          label="総ユーザー数"
          value={42}
          suffix="人"
          icon={Users}
          trend="up"
          trendValue="+3"
        />
        <KPICard
          label="総AUM"
          value={aaveTotal}
          icon={DollarSign}
        />
        <KPICard
          label="本日の取引件数"
          value={totalTrades}
          suffix="件"
          icon={ArrowLeftRight}
        />
        <KPICard
          label="直近24hイベント数"
          value={7}
          suffix="件"
          icon={Bell}
          trend="flat"
        />
      </div>

      {/* HF Display + Volume Chart */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Health Factor */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-gray-700">Health Factor</h2>
          <div className="flex flex-col items-center gap-4 py-4">
            <HfDisplay value={hfNum} />
            {aaveStatus == null && (
              <p className="text-xs text-gray-400">取得中...</p>
            )}
            {aaveStatus != null && hfNum == null && (
              <p className="text-sm text-gray-500">借入ポジションなし</p>
            )}
          </div>
        </div>

        {/* Daily Volume */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-gray-700">日別取引量（過去7日）</h2>
          <SimpleBarChart data={STATIC_VOLUME_DATA} />
        </div>
      </div>

      {/* System Status Detail */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-sm font-semibold text-gray-700">システム状態</h2>
        <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-3">
          <div>
            <p className="text-xs text-gray-400">自動売買</p>
            <p className={`font-medium ${automationStatus?.is_trading_paused ? "text-red-600" : "text-green-600"}`}>
              {automationStatus == null ? "取得中..." : automationStatus.is_trading_paused ? "停止中" : "稼働中"}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400">取引所接続</p>
            <p className={`font-medium ${exchangeStatus?.connected ? "text-green-600" : "text-gray-400"}`}>
              {exchangeStatus == null ? "取得中..." : exchangeStatus.connected ? "接続済" : "未接続"}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400">日次残取引枠</p>
            <p className="font-medium text-gray-700">
              {exchangeStatus == null ? "取得中..." : `${exchangeStatus.daily_trades_used ?? "—"} 件使用`}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DashboardIndex() {
  return (
    <AuthGuard>
      <>
        <title>運用ダッシュボード - Ultra AutoTrade</title>
        <DashboardContent />
      </>
    </AuthGuard>
  );
}
