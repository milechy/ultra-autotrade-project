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
  HealthFactorGauge,
  KPICard,
  StatusBadge,
  EmergencyStopButton,
} from "@/components/shared";
import type { AutomationStatus } from "@/lib/types";
import type { ExchangeStatusResponse } from "@/lib/api/exchange";
import type { AaveMonitorStatus } from "@/lib/api/aave";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Users, DollarSign, ArrowLeftRight, Bell } from "lucide-react";

// -----------------------------------------------------------------------
// Mock chart data helpers
// -----------------------------------------------------------------------

type HfTimeRange = "24h" | "7d" | "30d";

function generateHfData(range: HfTimeRange) {
  const now = Date.now();
  let points: number;
  let stepMs: number;
  let labelFmt: (d: Date) => string;

  if (range === "24h") {
    points = 24;
    stepMs = 60 * 60 * 1000;
    labelFmt = (d) => `${d.getHours()}:00`;
  } else if (range === "7d") {
    points = 7;
    stepMs = 24 * 60 * 60 * 1000;
    labelFmt = (d) => `${d.getMonth() + 1}/${d.getDate()}`;
  } else {
    points = 30;
    stepMs = 24 * 60 * 60 * 1000;
    labelFmt = (d) => `${d.getMonth() + 1}/${d.getDate()}`;
  }

  let hf = 2.1;
  return Array.from({ length: points }, (_, i) => {
    const ts = now - (points - 1 - i) * stepMs;
    hf = Math.max(1.4, Math.min(3.5, hf + (Math.random() - 0.5) * 0.12));
    return { label: labelFmt(new Date(ts)), hf: parseFloat(hf.toFixed(2)) };
  });
}

function generateVolumeData() {
  const now = new Date();
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now);
    d.setDate(d.getDate() - (6 - i));
    return {
      label: `${d.getMonth() + 1}/${d.getDate()}`,
      trades: Math.floor(Math.random() * 20) + 1,
    };
  });
}

// -----------------------------------------------------------------------
// Dashboard content
// -----------------------------------------------------------------------

function DashboardContent() {
  const { token } = useAuth();
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null);
  const [exchangeStatus, setExchangeStatus] = useState<ExchangeStatusResponse | null>(null);
  const [aaveStatus, setAaveStatus] = useState<AaveMonitorStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [hfRange, setHfRange] = useState<HfTimeRange>("24h");
  const [hfData] = useState(() => ({
    "24h": generateHfData("24h"),
    "7d": generateHfData("7d"),
    "30d": generateHfData("30d"),
  }));
  const [volumeData] = useState(() => generateVolumeData());

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      const [auto, exchange] = await Promise.all([
        fetchAutomationStatus(token ?? undefined),
        fetchExchangeStatus(token),
      ]);
      setAutomationStatus(auto);
      setExchangeStatus(exchange);
      setLastUpdated(new Date());
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

  // Derive system status
  const systemStatus: "NORMAL" | "SAFE_MODE" | "HARD_STOP" = (() => {
    if (automationStatus?.is_trading_paused) return "HARD_STOP";
    if (hfNum != null && hfNum < 1.8) return "SAFE_MODE";
    return "NORMAL";
  })();

  async function handleEmergencyStop() {
    await apiPost("/api/aave/emergency-stop", {});
    await fetchData();
  }

  // KPI values
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
              最終更新: {lastUpdated.toLocaleTimeString("ja-JP")}（30秒自動更新）
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

      {/* HF Gauge + Chart */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Health Factor Gauge */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-gray-700">Health Factor</h2>
          <div className="flex flex-col items-center gap-4">
            <HealthFactorGauge value={hfNum} size="lg" />
            {aaveStatus == null && (
              <p className="text-xs text-gray-400">取得中...</p>
            )}
            {aaveStatus != null && hfNum == null && (
              <p className="text-sm text-gray-500">借入ポジションなし</p>
            )}
          </div>
        </div>

        {/* HF Line Chart */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">HF 推移</h2>
            <div className="flex gap-1">
              {(["24h", "7d", "30d"] as HfTimeRange[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setHfRange(r)}
                  className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                    hfRange === r
                      ? "bg-blue-600 text-white"
                      : "text-gray-500 hover:bg-gray-100"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={hfData[hfRange]} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis domain={[1.2, 3.5]} tick={{ fontSize: 10 }} />
              <Tooltip formatter={(v: number) => v.toFixed(2)} />
              <Line
                type="monotone"
                dataKey="hf"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Daily Volume Bar Chart */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-sm font-semibold text-gray-700">日別取引量（過去7日）</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={volumeData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            <Bar dataKey="trades" fill="#2563eb" radius={[4, 4, 0, 0]} name="取引数" />
          </BarChart>
        </ResponsiveContainer>
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
