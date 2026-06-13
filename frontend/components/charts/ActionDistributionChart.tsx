'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export type ActionRecord = {
  timestamp: string;
  action: "BUY" | "SELL" | "HOLD";
};

type Period = "7d" | "30d" | "90d";

const COLORS = {
  BUY: "#16a34a",
  SELL: "#dc2626",
  HOLD: "#6b7280",
};

const PERIOD_DAYS: Record<Period, number> = { "7d": 7, "30d": 30, "90d": 90 };

type Props = {
  data: ActionRecord[];
};

export default function ActionDistributionChart({ data }: Props) {
  const t = useTranslations("Charts");
  const [period, setPeriod] = useState<Period>("7d");

  const cutoff = new Date(Date.now() - PERIOD_DAYS[period] * 24 * 60 * 60 * 1000);
  const filtered = data.filter((r) => new Date(r.timestamp) >= cutoff);

  const counts = { BUY: 0, SELL: 0, HOLD: 0 };
  filtered.forEach((r) => {
    counts[r.action]++;
  });
  const total = filtered.length;

  const chartData = (["BUY", "SELL", "HOLD"] as const)
    .filter((a) => counts[a] > 0)
    .map((a) => ({
      name: a,
      value: counts[a],
      pct: total > 0 ? ((counts[a] / total) * 100).toFixed(1) : "0.0",
    }));

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {(["7d", "30d", "90d"] as Period[]).map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            style={{
              padding: "4px 12px",
              borderRadius: 6,
              border: "1px solid #d1d5db",
              fontSize: 12,
              cursor: "pointer",
              background: period === p ? "#1d4ed8" : "#fff",
              color: period === p ? "#fff" : "#374151",
              fontWeight: period === p ? 600 : 400,
            }}
          >
            {p}
          </button>
        ))}
        <span style={{ fontSize: 12, color: "#9ca3af", alignSelf: "center" }}>
          {total}件
        </span>
      </div>

      {chartData.length === 0 ? (
        <div style={{ color: "#9ca3af", fontSize: 13, padding: "24px 0", textAlign: "center" }}>
          {t("noData")}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={90}
              label={({ name, pct }: { name: string; pct: string }) => `${name} ${pct}%`}
              labelLine={false}
            >
              {chartData.map((entry) => (
                <Cell key={entry.name} fill={COLORS[entry.name as keyof typeof COLORS]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number, name: string) => [
                `${value}件 (${chartData.find((d) => d.name === name)?.pct ?? ""}%)`,
                name,
              ]}
              contentStyle={{ fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
