'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { executeGridBot, fetchGridStatus } from "@/lib/api/exchange";
import type { GridStatusResponse, GridConfigRequest } from "@/lib/api/exchange";

const SYMBOLS = ["BTC/USDT", "ETH/USDT"] as const;

function GridVisualization({ gridStatus }: { gridStatus: GridStatusResponse }) {
  const upper = parseFloat(gridStatus.upper_price);
  const lower = parseFloat(gridStatus.lower_price);
  const current = gridStatus.current_price ? parseFloat(gridStatus.current_price) : null;
  const range = upper - lower;

  if (range <= 0 || gridStatus.levels.length === 0) {
    return (
      <div style={{ color: "#9ca3af", fontSize: 13, padding: "16px 0" }}>
        グリッドレベルがありません
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
        <span>上限: ${(upper || 0).toLocaleString()}</span>
        <span>下限: ${(lower || 0).toLocaleString()}</span>
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
                <span style={{ fontSize: 11, color: "#374151", fontWeight: 600 }}>✓ 約定</span>
              )}
              {isCurrent && (
                <span style={{ fontSize: 11, color: "#d97706", fontWeight: 700 }}>← 現在値</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Current price overlay label */}
      {current != null && (
        <div style={{ marginTop: 8, fontSize: 13, color: "#d97706", fontWeight: 600 }}>
          現在価格: ${current.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      )}
    </div>
  );
}

function GridContent() {
  const { token } = useAuth();

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
      setError("上限価格・下限価格・各グリッド金額を入力してください");
      return;
    }
    const upper = parseFloat(upperPrice);
    const lower = parseFloat(lowerPrice);
    if (isNaN(upper) || isNaN(lower) || upper <= lower) {
      setError("上限価格は下限価格より大きい値を入力してください");
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
      setError(`Bot起動エラー: ${msg}`);
    } finally {
      setIsExecuting(false);
    }
  }, [token, upperPrice, lowerPrice, gridCount, symbol, amountPerGrid, dryRun]);

  const handleFetchStatus = useCallback(async () => {
    if (!token) return;
    setIsFetchingStatus(true);
    setError(null);
    try {
      const result = await fetchGridStatus(token);
      setGridStatus(result);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`ステータス取得エラー: ${msg}`);
    } finally {
      setIsFetchingStatus(false);
    }
  }, [token]);

  const pnl = gridStatus ? parseFloat(gridStatus.pnl_usd) : null;

  return (
    <>
      {/* ヘッダー */}
      <div style={{ marginBottom: 8 }}>
        <h1 style={{ margin: 0 }}>Grid Trading Bot</h1>
        <p style={{ fontSize: 13, color: "#666", marginTop: 4 }}>
          グリッド間隔で自動売買を行うボット設定
        </p>
      </div>

      {error && (
        <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 16px", borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
          {error}
        </div>
      )}

      {/* 設定フォーム */}
      <section style={{ marginTop: 16 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>グリッド設定</h2>
        <div style={{ ...cardStyle, maxWidth: 520 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

            {/* 上限価格 */}
            <div>
              <label style={labelStyle}>上限価格 (USD)</label>
              <input
                type="number"
                value={upperPrice}
                onChange={(e) => setUpperPrice(e.target.value)}
                placeholder="例: 50000"
                style={inputStyle}
                disabled
              />
            </div>

            {/* 下限価格 */}
            <div>
              <label style={labelStyle}>下限価格 (USD)</label>
              <input
                type="number"
                value={lowerPrice}
                onChange={(e) => setLowerPrice(e.target.value)}
                placeholder="例: 40000"
                style={inputStyle}
                disabled
              />
            </div>

            {/* グリッド数 */}
            <div>
              <label style={labelStyle}>グリッド数（2〜100）</label>
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

            {/* シンボル */}
            <div>
              <label style={labelStyle}>取引ペア</label>
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

            {/* 各グリッド金額 */}
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={labelStyle}>各グリッド金額 (USD)</label>
              <input
                type="number"
                value={amountPerGrid}
                onChange={(e) => setAmountPerGrid(e.target.value)}
                placeholder="例: 100"
                style={inputStyle}
                disabled
              />
            </div>
          </div>

          {/* Dry Run トグル */}
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
              ドライランモード（実際の注文は発行しない）
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
              ドライランモードが有効です。実際の注文は発行されません。
            </div>
          )}
        </div>
      </section>

      {/* アクションボタン */}
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
            {isExecuting ? "起動中..." : "Bot起動"}
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
            {isFetchingStatus ? "取得中..." : "ステータス取得"}
          </button>
        </div>
      </section>

      {/* ステータス表示 */}
      {gridStatus && (
        <>
          <section style={{ marginTop: 32 }}>
            <h2 style={{ fontSize: 16, marginBottom: 12 }}>Bot ステータス</h2>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>

              {/* 稼働状態カード */}
              <div style={cardStyle}>
                <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>稼働状態</div>
                <span style={{
                  display: "inline-block",
                  padding: "4px 14px",
                  borderRadius: 999,
                  fontSize: 16,
                  fontWeight: 700,
                  background: gridStatus.enabled ? "#dcfce7" : "#f3f4f6",
                  color: gridStatus.enabled ? "#16a34a" : "#374151",
                }}>
                  {gridStatus.enabled ? "稼働中" : "停止中"}
                </span>
                <div style={{ marginTop: 8, fontSize: 13, color: "#666" }}>
                  {gridStatus.symbol}
                </div>
              </div>

              {/* 注文統計カード */}
              <div style={cardStyle}>
                <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>注文統計</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: "#111" }}>
                  {gridStatus.filled_orders}
                  <span style={{ fontSize: 16, color: "#666", fontWeight: 400 }}>
                    {" "}/ {gridStatus.total_orders}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>約定済み / 総注文数</div>
              </div>

              {/* PnL カード */}
              <div style={cardStyle}>
                <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>損益 (USD)</div>
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

          {/* グリッドビジュアライゼーション */}
          <section style={{ marginTop: 32 }}>
            <h2 style={{ fontSize: 16, marginBottom: 12 }}>グリッドビジュアライゼーション</h2>
            <GridVisualization gridStatus={gridStatus} />
          </section>
        </>
      )}
    </>
  );
}

export default function GridPage() {
  return (
    <AuthGuard>
      <>
        <title>Grid Trading Bot - Ultra AutoTrade</title>
        {/* Coming Soon overlay */}
        <div className="relative">
          <div className="absolute inset-0 bg-white dark:bg-gray-900/80 backdrop-blur-sm z-10 flex flex-col items-center justify-center rounded-lg">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-700 mb-2">Coming Soon</p>
              <p className="text-gray-500">Phase 2で対応予定</p>
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