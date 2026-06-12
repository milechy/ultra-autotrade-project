'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { executeGridBot, fetchGridStatus } from "@/lib/api/exchange";
import type { GridStatusResponse, GridConfigRequest } from "@/lib/api/exchange";

const SYMBOLS = ["BTC/USDT", "ETH/USDT"] as const;

function GridVisualization({ gridStatus }: { gridStatus: GridStatusResponse }) {
  const t = useTranslations("Grid");
  const upper = parseFloat(gridStatus.upper_price);
  const lower = parseFloat(gridStatus.lower_price);
  const current = gridStatus.current_price ? parseFloat(gridStatus.current_price) : null;
  const range = upper - lower;

  if (range <= 0 || gridStatus.levels.length === 0) {
    return (
      <div style={{ color: "#9ca3af", fontSize: 13, padding: "16px 0" }}>
        {t("noGridLevels")}
      </div>
    );
  }

  // Show levels sorted from highest price to lowest
  const sortedLevels = [...gridStatus.levels].sort(
    (a, b) => parseFloat(b.price) - parseFloat(a.price)
  );

  return (
    <div style={{ position: "relative", width: "100%", maxWidth: 480 }}>
      {/* Price axis labels */}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 11, color: "#666" }}>
        <span>{t("upperLabel")}: ${(upper || 0).toLocaleString()}</span>
        <span>{t("lowerLabel")}: ${(lower || 0).toLocaleString()}</span>
      </div>

      {/* Grid levels container */}
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden", background: "#f9fafb" }}>
        {sortedLevels.map((level, i) => {
          const price = parseFloat(level.price);
          const isBuy = level.side === "buy";
          const isCurrent =
            current != null &&
            i < sortedLevels.length - 1 &&
            price >= current &&
            parseFloat(sortedLevels[i + 1]?.price ?? "0") <= current;

          return (
            <div
              key={level.order_id ?? `${level.price}-${i}`}
              style={{
                display: "flex",
                alignItems: "center",
                padding: "4px 10px",
                background: isBuy
                  ? level.filled ? "#bbf7d0" : "#dcfce7"
                  : level.filled ? "#fecaca" : "#fee2e2",
                borderBottom: i < sortedLevels.length - 1 ? "1px solid rgba(0,0,0,0.06)" : "none",
                fontSize: 12,
                gap: 8,
              }}
            >
              {/* Current price indicator */}
              <span style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: isCurrent ? "#f59e0b" : "transparent",
                border: isCurrent ? "2px solid #d97706" : "none",
                flexShrink: 0,
              }} />
              <span style={{ fontFamily: "monospace", fontWeight: isCurrent ? 700 : 400, color: "#374151", flex: 1 }}>
                ${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span style={{
                padding: "1px 8px",
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 600,
                background: isBuy ? "#16a34a" : "#dc2626",
                color: "#fff",
              }}>
                {isBuy ? "BUY" : "SELL"}
              </span>
              {level.filled && (
                <span style={{ fontSize: 11, color: "#374151", fontWeight: 600 }}>✓ {t("filled")}</span>
              )}
              {isCurrent && (
                <span style={{ fontSize: 11, color: "#d97706", fontWeight: 700 }}>{t("currentPriceIndicator")}</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Current price overlay label */}
      {current != null && (
        <div style={{ marginTop: 8, fontSize: 13, color: "#d97706", fontWeight: 600 }}>
          {t("currentPriceLabel")}: ${current.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      )}
    </div>
  );
}

function GridContent() {
  const { token } = useAuth();
  const t = useTranslations("Grid");

  const [upperPrice, setUpperPrice] = useState("");
  const [lowerPrice, setLowerPrice] = useState("");
  const [gridCount, setGridCount] = useState(10);
  const [symbol, setSymbol] = useState<string>(SYMBOLS[0]);
  const [amountPerGrid, setAmountPerGrid] = useState("");
  const [dryRun, setDryRun] = useState(true);

  const [gridStatus, setGridStatus] = useState<GridStatusResponse | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isFetchingStatus, setIsFetchingStatus] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExecute = useCallback(async () => {
    if (!token) return;
    if (!upperPrice || !lowerPrice || !amountPerGrid) {
      setError(t("errInputRequired"));
      return;
    }
    const upper = parseFloat(upperPrice);
    const lower = parseFloat(lowerPrice);
    if (isNaN(upper) || isNaN(lower) || upper <= lower) {
      setError(t("errUpperLower"));
      return;
    }
    setIsExecuting(true);
    setError(null);
    try {
      const config: GridConfigRequest = {
        upper_price: upperPrice,
        lower_price: lowerPrice,
        grid_count: gridCount,
        symbol,
        amount_per_grid_usd: amountPerGrid,
        enabled: true,
        dry_run: dryRun,
      };
      const result = await executeGridBot(token, config);
      setGridStatus(result);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(t("botStartError", { msg }));
    } finally {
      setIsExecuting(false);
    }
  }, [token, upperPrice, lowerPrice, gridCount, symbol, amountPerGrid, dryRun, t]);

  const handleFetchStatus = useCallback(async () => {
    if (!token) return;
    setIsFetchingStatus(true);
    setError(null);
    try {
      const result = await fetchGridStatus(token);
      setGridStatus(result);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(t("statusFetchError", { msg }));
    } finally {
      setIsFetchingStatus(false);
    }
  }, [token, t]);

  const pnl = gridStatus ? parseFloat(gridStatus.pnl_usd) : null;

  return (
    <>
      {/* header */}
      <div style={{ marginBottom: 8 }}>
        <h1 style={{ margin: 0 }}>Grid Trading Bot</h1>
        <p style={{ fontSize: 13, color: "#666", marginTop: 4 }}>
          {t("subtitle")}
        </p>
      </div>

      {error && (
        <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 16px", borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
          {error}
        </div>
      )}

      {/* settings form */}
      <section style={{ marginTop: 16 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("gridSettings")}</h2>
        <div style={{ ...cardStyle, maxWidth: 520 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

            {/* upper price */}
            <div>
              <label style={labelStyle}>{t("upperPriceLabel")}</label>
              <input
                type="number"
                value={upperPrice}
                onChange={(e) => setUpperPrice(e.target.value)}
                placeholder={t("upperPricePlaceholder")}
                style={inputStyle}
                disabled
              />
            </div>

            {/* lower price */}
            <div>
              <label style={labelStyle}>{t("lowerPriceLabel")}</label>
              <input
                type="number"
                value={lowerPrice}
                onChange={(e) => setLowerPrice(e.target.value)}
                placeholder={t("lowerPricePlaceholder")}
                style={inputStyle}
                disabled
              />
            </div>

            {/* grid count */}
            <div>
              <label style={labelStyle}>{t("gridCountLabel")}</label>
              <input
                type="number"
                value={gridCount}
                min={2}
                max={100}
                onChange={(e) => setGridCount(Math.min(100, Math.max(2, parseInt(e.target.value) || 10)))}
                style={inputStyle}
                disabled
              />
            </div>

            {/* symbol */}
            <div>
              <label style={labelStyle}>{t("symbolLabel")}</label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
                disabled
              >
                {SYMBOLS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>

            {/* amount per grid */}
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={labelStyle}>{t("amountPerGridLabel")}</label>
              <input
                type="number"
                value={amountPerGrid}
                onChange={(e) => setAmountPerGrid(e.target.value)}
                placeholder={t("amountPerGridPlaceholder")}
                style={inputStyle}
                disabled
              />
            </div>
          </div>

          {/* dry run toggle */}
          <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 10 }}>
            <input
              id="dry-run-toggle"
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              style={{ width: 16, height: 16, cursor: "pointer" }}
              disabled
            />
            <label htmlFor="dry-run-toggle" style={{ fontSize: 14, color: "#374151", cursor: "pointer" }}>
              {t("dryRunLabel")}
            </label>
          </div>

          {dryRun && (
            <div style={{
              marginTop: 10,
              background: "#fef9c3",
              border: "1px solid #fde047",
              borderRadius: 8,
              padding: "8px 12px",
              fontSize: 13,
              color: "#92400e",
            }}>
              {t("dryRunActive")}
            </div>
          )}
        </div>
      </section>

      {/* action buttons */}
      <section style={{ marginTop: 24 }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <button
            onClick={handleExecute}
            disabled={true}
            style={{
              padding: "10px 24px",
              borderRadius: 8,
              border: "none",
              background: "#9ca3af",
              color: "#fff",
              fontWeight: 600,
              fontSize: 14,
              cursor: "not-allowed",
            }}
          >
            {isExecuting ? t("starting") : t("startBot")}
          </button>
          <button
            onClick={handleFetchStatus}
            disabled={true}
            style={{
              padding: "10px 24px",
              borderRadius: 8,
              border: "none",
              background: "#9ca3af",
              color: "#fff",
              fontWeight: 600,
              fontSize: 14,
              cursor: "not-allowed",
            }}
          >
            {isFetchingStatus ? t("fetching") : t("fetchStatus")}
          </button>
        </div>
      </section>

      {/* status display */}
      {gridStatus && (
        <>
          <section style={{ marginTop: 32 }}>
            <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("botStatus")}</h2>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>

              {/* operation status card */}
              <div style={cardStyle}>
                <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("operationStatus")}</div>
                <span style={{
                  display: "inline-block",
                  padding: "4px 14px",
                  borderRadius: 999,
                  fontSize: 16,
                  fontWeight: 700,
                  background: gridStatus.enabled ? "#dcfce7" : "#f3f4f6",
                  color: gridStatus.enabled ? "#16a34a" : "#374151",
                }}>
                  {gridStatus.enabled ? t("running") : t("stopped")}
                </span>
                <div style={{ marginTop: 8, fontSize: 13, color: "#666" }}>
                  {gridStatus.symbol}
                </div>
              </div>

              {/* order stats card */}
              <div style={cardStyle}>
                <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("orderStats")}</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: "#111" }}>
                  {gridStatus.filled_orders}
                  <span style={{ fontSize: 16, color: "#666", fontWeight: 400 }}>
                    {" "}/ {gridStatus.total_orders}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>{t("filledOrders")}</div>
              </div>

              {/* PnL card */}
              <div style={cardStyle}>
                <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("pnl")}</div>
                <div style={{
                  fontSize: 32,
                  fontWeight: 700,
                  color: pnl != null ? (pnl >= 0 ? "#16a34a" : "#dc2626") : "#111",
                }}>
                  {pnl != null ? `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}` : "—"}
                </div>
              </div>
            </div>
          </section>

          {/* grid visualization */}
          <section style={{ marginTop: 32 }}>
            <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("gridVisualization")}</h2>
            <GridVisualization gridStatus={gridStatus} />
          </section>
        </>
      )}
    </>
  );
}

export default function GridPage() {
  const t = useTranslations("Grid");
  return (
    <AuthGuard>
      <>
        <title>Grid Trading Bot - Ultra AutoTrade</title>
        {/* Coming Soon overlay */}
        <div className="relative">
          <div className="absolute inset-0 bg-white dark:bg-gray-900/80 backdrop-blur-sm z-10 flex flex-col items-center justify-center rounded-lg">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-700 mb-2">Coming Soon</p>
              <p className="text-gray-500">{t("comingSoon")}</p>
            </div>
          </div>
          <div className="pointer-events-none select-none">
            <GridContent />
          </div>
        </div>
      </>
    </AuthGuard>
  );
}

const cardStyle: React.CSSProperties = {
  padding: 20,
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  minWidth: 200,
  background: "#fff",
  boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 13,
  color: "#374151",
  fontWeight: 600,
  marginBottom: 4,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid #e5e7eb",
  fontSize: 14,
  color: "#111",
  background: "#fff",
  boxSizing: "border-box",
};
