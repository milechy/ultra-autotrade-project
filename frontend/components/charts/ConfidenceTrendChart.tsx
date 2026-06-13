'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React from "react";
import { useTranslations } from "next-intl";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export type ConfidencePoint = {
  timestamp: string;
  action: "BUY" | "SELL" | "HOLD";
  confidence: number;
  prompt_version: string;
};

type Props = {
  data: ConfidencePoint[];
};

const ACTION_COLORS: Record<string, string> = {
  BUY: "#16a34a",
  SELL: "#dc2626",
  HOLD: "#6b7280",
};

function formatLabel(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Tokyo",
    });
  } catch {
    return iso;
  }
}

export default function ConfidenceTrendChart({ data }: Props) {
  const t = useTranslations("Charts");

  if (data.length === 0) {
    return (
      <div style={{ color: "#9ca3af", fontSize: 13, padding: "24px 0", textAlign: "center" }}>
        {t("noData")}
      </div>
    );
  }

  const chartData = data.map((p) => ({
    label: formatLabel(p.timestamp),
    BUY: p.action === "BUY" ? p.confidence : null,
    SELL: p.action === "SELL" ? p.confidence : null,
    HOLD: p.action === "HOLD" ? p.confidence : null,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
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
        <Tooltip
          formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name]}
          labelStyle={{ fontSize: 12 }}
          contentStyle={{ fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="BUY"
          stroke={ACTION_COLORS.BUY}
          strokeWidth={2}
          dot={false}
          connectNulls
          name="BUY"
        />
        <Line
          type="monotone"
          dataKey="SELL"
          stroke={ACTION_COLORS.SELL}
          strokeWidth={2}
          dot={false}
          connectNulls
          name="SELL"
        />
        <Line
          type="monotone"
          dataKey="HOLD"
          stroke={ACTION_COLORS.HOLD}
          strokeWidth={2}
          dot={false}
          connectNulls
          name="HOLD"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
