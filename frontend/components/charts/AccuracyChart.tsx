'use client'

import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export type AccuracyPoint = {
  timestamp: string;
  phase_a: "BUY" | "SELL" | "HOLD";
  phase_b: "BUY" | "SELL" | "HOLD" | null;
  agreed: boolean;
};

type Props = {
  data: AccuracyPoint[];
};

function formatLabel(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("ja-JP", {
      month: "2-digit",
      day: "2-digit",
      timeZone: "Asia/Tokyo",
    });
  } catch {
    return iso;
  }
}

export default function AccuracyChart({ data }: Props) {
  const byDay: Record<string, { total: number; agreed: number }> = {};
  for (const p of data) {
    if (!p.phase_b) continue;
    const key = formatLabel(p.timestamp);
    if (!byDay[key]) byDay[key] = { total: 0, agreed: 0 };
    byDay[key].total++;
    if (p.agreed) byDay[key].agreed++;
  }

  const chartData = Object.entries(byDay).map(([label, { total, agreed }]) => ({
    label,
    agreementRate: total > 0 ? Math.round((agreed / total) * 100) : 0,
  }));

  if (chartData.length === 0) {
    return (
      <div style={{ color: "#9ca3af", fontSize: 13, padding: "24px 0", textAlign: "center" }}>
        Two-Phase判定データがありません
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: "#6b7280" }}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 11, fill: "#6b7280" }}
          tickFormatter={(v: number) => `${v}%`}
        />
        <ReferenceLine
          y={80}
          stroke="#f59e0b"
          strokeDasharray="4 4"
          label={{ value: "目標80%", fontSize: 10, fill: "#f59e0b" }}
        />
        <Tooltip
          formatter={(v: number) => [`${v}%`, "Two-Phase一致率"]}
          labelStyle={{ fontSize: 12 }}
          contentStyle={{ fontSize: 12 }}
        />
        <Line
          type="monotone"
          dataKey="agreementRate"
          stroke="#2563eb"
          strokeWidth={2}
          dot={{ r: 4 }}
          name="Two-Phase一致率"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
