'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import {
  fetchRebalanceStatus,
  simulateRebalance,
  executeRebalance,
  fetchRebalanceHistory,
} from "@/lib/api/rebalance";
import type {
  RebalanceStatusResponse,
  RebalanceProposal,
  RebalanceHistoryEntry,
} from "@/lib/api/rebalance";

function getHfColor(hf: number): string {
  if (hf >= 1.8) return "#16a34a";
  if (hf >= 1.6) return "#ca8a04";
  return "#dc2626";
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}

function getStatusBadge(status: string): { bg: string; color: string } {
  switch (status) {
    case "executed": return { bg: "#dcfce7", color: "#16a34a" };
    case "pending": return { bg: "#fef9c3", color: "#ca8a04" };
    case "failed": return { bg: "#fee2e2", color: "#dc2626" };
    default: return { bg: "#f3f4f6", color: "#374151" };
  }
}

function RebalanceContent() {
  const t = useTranslations("AdminRebalance");
  const { token } = useAuth();
  const [statusData, setStatusData] = useState<RebalanceStatusResponse | null>(null);
  const [simulationResult, setSimulationResult] = useState<RebalanceProposal | null>(null);
  const [history, setHistory] = useState<RebalanceHistoryEntry[]>([]);
  const [isSimulating, setIsSimulating] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      const [status, hist] = await Promise.all([
        fetchRebalanceStatus(token),
        fetchRebalanceHistory(token),
      ]);
      setStatusData(status);
      setHistory(hist);
      setLastUpdated(new Date());
      setError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(t("errors.fetchError", { message: msg }));
    }
  }, [token, t]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const handleSimulate = async () => {
    if (!token) return;
    setIsSimulating(true);
    setError(null);
    try {
      const res = await simulateRebalance(token);
      setSimulationResult(res.proposal);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(t("errors.simulationError", { message: msg }));
    } finally {
      setIsSimulating(false);
    }
  };

  const handleExecute = async () => {
    if (!token || !simulationResult) return;
    if (!simulationResult.confirmation_token) {
      setError(t("errors.noConfirmationToken"));
      return;
    }
    setIsExecuting(true);
    setError(null);
    try {
      await executeRebalance(token, simulationResult.proposal_id, simulationResult.confirmation_token);
      setShowConfirmDialog(false);
      setSimulationResult(null);
      await fetchData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(t("errors.executeError", { message: msg }));
    } finally {
      setIsExecuting(false);
    }
  };

  const hfRaw = statusData?.health_factor;
  const hfNum = hfRaw != null ? parseFloat(String(hfRaw)) : null;

  const estHfRaw = simulationResult?.estimated_health_factor_after;
  const estHfNum = estHfRaw != null ? parseFloat(String(estHfRaw)) : null;

  const cooldown = statusData?.cooldown_remaining_seconds ?? 0;
  const cooldownMinutes = Math.floor(cooldown / 60);
  const cooldownSeconds = cooldown % 60;

  const hfBadgeLabel = (hf: number) => {
    if (hf >= 1.8) return t("hfBadge.safe");
    if (hf >= 1.6) return t("hfBadge.caution");
    return t("hfBadge.danger");
  };

  const hfBadgeBg = (hf: number) => {
    if (hf >= 1.8) return "#dcfce7";
    if (hf >= 1.6) return "#fef9c3";
    return "#fee2e2";
  };

  const hfBadgeColor = (hf: number) => {
    if (hf >= 1.8) return "#16a34a";
    if (hf >= 1.6) return "#ca8a04";
    return "#dc2626";
  };

  return (
    <>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <h1 style={{ margin: 0 }}>{t("pageTitle")}</h1>
        {lastUpdated && (
          <span style={{ fontSize: 12, color: "#888" }}>
            {t("lastUpdated", { time: lastUpdated.toLocaleTimeString("ja-JP") })}
          </span>
        )}
      </div>

      {error && (
        <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 16px", borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
          {error}
        </div>
      )}

      {/* Status section */}
      <section style={{ marginTop: 16 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("status.heading")}</h2>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>

          {/* HF card */}
          <div style={cardStyle}>
            <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("status.hfCardLabel")}</div>
            {hfNum != null && !isNaN(hfNum) ? (
              <>
                <div style={{ fontSize: 40, fontWeight: 700, color: getHfColor(hfNum), lineHeight: 1.1 }}>
                  {hfNum.toFixed(2)}
                </div>
                <span style={{
                  display: "inline-block",
                  marginTop: 8,
                  padding: "2px 10px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                  background: hfBadgeBg(hfNum),
                  color: hfBadgeColor(hfNum),
                }}>
                  {hfBadgeLabel(hfNum)}
                </span>
              </>
            ) : (
              <div style={{ fontSize: 24, color: "#9ca3af" }}>{t("status.loading")}</div>
            )}
          </div>

          {/* Total assets card */}
          <div style={cardStyle}>
            <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("status.totalAssetsLabel")}</div>
            <div style={{ fontSize: 36, fontWeight: 700, color: "#111" }}>
              {statusData ? `$${parseFloat(statusData.total_value_usd).toFixed(2)}` : <span style={{ color: "#9ca3af", fontSize: 24 }}>{t("status.loading")}</span>}
            </div>
            {statusData && (
              <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <span style={{
                  display: "inline-block",
                  padding: "2px 10px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                  background: statusData.needs_rebalance ? "#fee2e2" : "#dcfce7",
                  color: statusData.needs_rebalance ? "#dc2626" : "#16a34a",
                }}>
                  {statusData.needs_rebalance ? t("status.needsRebalance") : t("status.balanced")}
                </span>
              </div>
            )}
          </div>

          {/* Cooldown card */}
          <div style={cardStyle}>
            <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("status.cooldownLabel")}</div>
            {cooldown > 0 ? (
              <>
                <div style={{ fontSize: 28, fontWeight: 700, color: "#ca8a04" }}>
                  {cooldownMinutes}:{String(cooldownSeconds).padStart(2, "0")}
                </div>
                <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>{t("status.cooldownRemaining")}</div>
              </>
            ) : (
              <div style={{ fontSize: 24, fontWeight: 700, color: "#16a34a" }}>{t("status.cooldownReady")}</div>
            )}
            {statusData?.last_rebalance_at && (
              <div style={{ fontSize: 12, color: "#888", marginTop: 8 }}>
                {t("status.previousRebalance", { time: formatDateTime(statusData.last_rebalance_at) })}
              </div>
            )}
          </div>
        </div>

        {/* Allocation table */}
        {statusData && statusData.current_allocations.length > 0 && (
          <div style={{ marginTop: 20 }}>
            <h3 style={{ fontSize: 14, marginBottom: 8, color: "#374151" }}>{t("status.allocationHeading")}</h3>
            <table style={{ ...tableStyle, maxWidth: 700 }}>
              <thead>
                <tr>
                  <th style={thStyle}>{t("status.colAsset")}</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>{t("status.colCurrentUsd")}</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>{t("status.colCurrentPct")}</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>{t("status.colTargetPct")}</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>{t("status.colDeviation")}</th>
                </tr>
              </thead>
              <tbody>
                {statusData.current_allocations.map((alloc) => {
                  const dev = parseFloat(alloc.deviation_pct);
                  const devColor = Math.abs(dev) >= parseFloat(statusData.deviation_threshold_pct)
                    ? "#dc2626"
                    : "#374151";
                  return (
                    <tr key={alloc.asset_symbol}>
                      <td style={tdStyle}><strong>{alloc.asset_symbol}</strong></td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>${parseFloat(alloc.current_amount_usd).toFixed(2)}</td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>{parseFloat(alloc.current_pct).toFixed(1)}%</td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>{parseFloat(alloc.target_pct).toFixed(1)}%</td>
                      <td style={{ ...tdStyle, textAlign: "right", color: devColor, fontWeight: Math.abs(dev) >= parseFloat(statusData.deviation_threshold_pct) ? 600 : 400 }}>
                        {dev > 0 ? "+" : ""}{dev.toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Actions section */}
      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("actions.heading")}</h2>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <button
            onClick={handleSimulate}
            disabled={isSimulating}
            style={{
              padding: "10px 24px",
              borderRadius: 8,
              border: "none",
              background: isSimulating ? "#9ca3af" : "#2563eb",
              color: "#fff",
              fontWeight: 600,
              fontSize: 14,
              cursor: isSimulating ? "not-allowed" : "pointer",
            }}
          >
            {isSimulating ? t("actions.simulating") : t("actions.simulate")}
          </button>
          <button
            onClick={() => setShowConfirmDialog(true)}
            disabled={!simulationResult || !simulationResult.is_executable || isExecuting}
            style={{
              padding: "10px 24px",
              borderRadius: 8,
              border: "none",
              background: (!simulationResult || !simulationResult.is_executable) ? "#9ca3af" : "#16a34a",
              color: "#fff",
              fontWeight: 600,
              fontSize: 14,
              cursor: (!simulationResult || !simulationResult.is_executable) ? "not-allowed" : "pointer",
            }}
          >
            {t("actions.execute")}
          </button>
        </div>
      </section>

      {/* Simulation result section */}
      {simulationResult && (
        <section style={{ marginTop: 32 }}>
          <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("simulation.heading")}</h2>
          <div style={{ ...cardStyle, maxWidth: 700 }}>

            {/* Executable badge */}
            <div style={{ marginBottom: 12 }}>
              <span style={{
                display: "inline-block",
                padding: "2px 10px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 600,
                background: simulationResult.is_executable ? "#dcfce7" : "#fee2e2",
                color: simulationResult.is_executable ? "#16a34a" : "#dc2626",
              }}>
                {simulationResult.is_executable ? t("simulation.executable") : t("simulation.notExecutable")}
              </span>
            </div>

            {/* Rejection reasons */}
            {simulationResult.rejection_reasons.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#dc2626", marginBottom: 4 }}>{t("simulation.rejectionReasonsHeading")}</div>
                {simulationResult.rejection_reasons.map((reason, i) => (
                  <div key={i} style={{ fontSize: 13, color: "#dc2626", paddingLeft: 12 }}>• {reason}</div>
                ))}
              </div>
            )}

            {/* Estimated HF */}
            {estHfNum != null && !isNaN(estHfNum) && (
              <div style={{ marginBottom: 16, display: "flex", gap: 24, alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 12, color: "#666" }}>{t("simulation.currentHf")}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: hfNum != null ? getHfColor(hfNum) : "#111" }}>
                    {hfNum != null ? hfNum.toFixed(2) : "—"}
                  </div>
                </div>
                <div style={{ fontSize: 20, color: "#9ca3af" }}>→</div>
                <div>
                  <div style={{ fontSize: 12, color: "#666" }}>{t("simulation.estimatedHf")}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: getHfColor(estHfNum) }}>
                    {estHfNum.toFixed(2)}
                  </div>
                </div>
              </div>
            )}

            {/* Proposed operations */}
            {simulationResult.operations.length > 0 && (
              <>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 8 }}>{t("simulation.proposedOpsHeading")}</div>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={thStyle}>{t("simulation.colAsset")}</th>
                      <th style={thStyle}>{t("simulation.colOperation")}</th>
                      <th style={{ ...thStyle, textAlign: "right" }}>{t("simulation.colAmountUsd")}</th>
                      <th style={thStyle}>{t("simulation.colReason")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {simulationResult.operations.map((op, i) => (
                      <tr key={i}>
                        <td style={tdStyle}><strong>{op.asset_symbol}</strong></td>
                        <td style={tdStyle}>
                          <span style={{
                            display: "inline-block",
                            padding: "2px 8px",
                            borderRadius: 999,
                            fontSize: 11,
                            fontWeight: 600,
                            background: op.operation === "deposit" ? "#dcfce7" : "#fee2e2",
                            color: op.operation === "deposit" ? "#16a34a" : "#dc2626",
                          }}>
                            {op.operation}
                          </span>
                        </td>
                        <td style={{ ...tdStyle, textAlign: "right" }}>${parseFloat(op.amount_usd).toFixed(2)}</td>
                        <td style={{ ...tdStyle, fontSize: 12, color: "#666" }}>{op.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </section>
      )}

      {/* Confirm dialog */}
      {showConfirmDialog && simulationResult && (
        <div style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.5)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 1000,
        }}>
          <div style={{
            background: "#fff",
            borderRadius: 12,
            padding: 32,
            maxWidth: 480,
            width: "90%",
            boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
          }}>
            <h3 style={{ margin: "0 0 16px", fontSize: 18 }}>{t("confirmDialog.heading")}</h3>

            <div style={{ marginBottom: 16, fontSize: 14, color: "#374151" }}>
              <div style={{ marginBottom: 8 }}>
                <span style={{ color: "#666" }}>{t("confirmDialog.proposalId")} </span>
                <span style={{ fontFamily: "monospace", fontSize: 12 }}>{simulationResult.proposal_id}</span>
              </div>
              <div style={{ marginBottom: 8 }}>
                <span style={{ color: "#666" }}>{t("confirmDialog.totalAssets")} </span>
                <strong>${parseFloat(simulationResult.total_value_usd).toFixed(2)}</strong>
              </div>
              <div style={{ marginBottom: 8 }}>
                <span style={{ color: "#666" }}>{t("confirmDialog.opCount")} </span>
                <strong>{t("confirmDialog.opCountUnit", { count: simulationResult.operations.length })}</strong>
              </div>
              {estHfNum != null && !isNaN(estHfNum) && (
                <div style={{ marginBottom: 8 }}>
                  <span style={{ color: "#666" }}>{t("confirmDialog.estimatedHf")} </span>
                  <strong style={{ color: getHfColor(estHfNum) }}>{estHfNum.toFixed(2)}</strong>
                </div>
              )}
            </div>

            <div style={{
              background: "#fef9c3",
              border: "1px solid #fde047",
              borderRadius: 8,
              padding: "10px 14px",
              marginBottom: 20,
              fontSize: 13,
              color: "#92400e",
            }}>
              {t("confirmDialog.warning")}
            </div>

            <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
              <button
                onClick={() => setShowConfirmDialog(false)}
                disabled={isExecuting}
                style={{
                  padding: "8px 20px",
                  borderRadius: 8,
                  border: "1px solid #e5e7eb",
                  background: "#fff",
                  color: "#374151",
                  fontWeight: 600,
                  fontSize: 14,
                  cursor: isExecuting ? "not-allowed" : "pointer",
                }}
              >
                {t("confirmDialog.cancel")}
              </button>
              <button
                onClick={handleExecute}
                disabled={isExecuting}
                style={{
                  padding: "8px 20px",
                  borderRadius: 8,
                  border: "none",
                  background: isExecuting ? "#9ca3af" : "#16a34a",
                  color: "#fff",
                  fontWeight: 600,
                  fontSize: 14,
                  cursor: isExecuting ? "not-allowed" : "pointer",
                }}
              >
                {isExecuting ? t("confirmDialog.executing") : t("confirmDialog.execute")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* History section */}
      <section style={{ marginTop: 32, marginBottom: 40 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("history.heading")}</h2>
        {history.length > 0 ? (
          <table style={{ ...tableStyle, maxWidth: 900 }}>
            <thead>
              <tr>
                <th style={thStyle}>{t("history.colProposalId")}</th>
                <th style={thStyle}>{t("history.colCreatedAt")}</th>
                <th style={thStyle}>{t("history.colExecutedAt")}</th>
                <th style={thStyle}>{t("history.colStatus")}</th>
                <th style={{ ...thStyle, textAlign: "right" }}>{t("history.colOpCount")}</th>
                <th style={{ ...thStyle, textAlign: "right" }}>{t("history.colHfBefore")}</th>
                <th style={{ ...thStyle, textAlign: "right" }}>{t("history.colHfAfter")}</th>
              </tr>
            </thead>
            <tbody>
              {history.map((entry) => {
                const badge = getStatusBadge(entry.status);
                const hfBefore = entry.health_factor_before != null ? parseFloat(entry.health_factor_before) : null;
                const hfAfter = entry.health_factor_after != null ? parseFloat(entry.health_factor_after) : null;
                return (
                  <tr key={entry.proposal_id}>
                    <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: 11 }}>
                      {entry.proposal_id.slice(0, 8)}...
                    </td>
                    <td style={{ ...tdStyle, fontSize: 12 }}>{formatDateTime(entry.created_at)}</td>
                    <td style={{ ...tdStyle, fontSize: 12 }}>{formatDateTime(entry.executed_at)}</td>
                    <td style={tdStyle}>
                      <span style={{
                        display: "inline-block",
                        padding: "2px 8px",
                        borderRadius: 999,
                        fontSize: 11,
                        fontWeight: 600,
                        background: badge.bg,
                        color: badge.color,
                      }}>
                        {entry.status}
                      </span>
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right" }}>{entry.operations_count}</td>
                    <td style={{ ...tdStyle, textAlign: "right", color: hfBefore != null ? getHfColor(hfBefore) : "#9ca3af" }}>
                      {hfBefore != null ? hfBefore.toFixed(2) : "—"}
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right", color: hfAfter != null ? getHfColor(hfAfter) : "#9ca3af" }}>
                      {hfAfter != null ? hfAfter.toFixed(2) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div style={{ color: "#9ca3af", fontSize: 14 }}>{t("history.noHistory")}</div>
        )}
      </section>
    </>
  );
}

export default function RebalancePage() {
  return (
    <AuthGuard adminOnly>
      <>
        <title>Aave Rebalance - Ultra AutoTrade</title>
        <RebalanceContent />
      </>
    </AuthGuard>
  );
}

const cardStyle: React.CSSProperties = {
  padding: 20,
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  minWidth: 240,
  background: "#fff",
  boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: 600,
  borderCollapse: "collapse",
  fontSize: 14,
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 12px",
  background: "#f9fafb",
  borderBottom: "1px solid #e5e7eb",
  color: "#374151",
  fontWeight: 600,
};

const tdStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #f3f4f6",
  color: "#374151",
};
