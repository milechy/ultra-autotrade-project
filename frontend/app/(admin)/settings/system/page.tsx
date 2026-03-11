'use client'

// frontend/app/(admin)/settings/system/page.tsx
import React, { useState, useEffect, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { fetchAutomationStatus } from "@/lib/api/automation";
import { fetchExchangeStatus } from "@/lib/api/exchange";
import type { AutomationStatus } from "@/lib/types";
import type { ExchangeStatusResponse } from "@/lib/api/exchange";

export default function SystemSettingsPage() {
  return (
    <AuthGuard adminOnly>
      <SystemSettingsContent />
    </AuthGuard>
  );
}

type ConfirmTarget =
  | "hf_threshold"
  | "cooldown"
  | "operation_mode"
  | "slack_notify"
  | "line_notify"
  | null;

function SystemSettingsContent() {
  const { token } = useAuth();

  // Remote data
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null);
  const [exchangeStatus, setExchangeStatus] = useState<ExchangeStatusResponse | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Editable field states
  const [hfThreshold, setHfThreshold] = useState<number>(1.6);
  const [cooldownMinutes, setCooldownMinutes] = useState<number>(10);
  const [operationMode, setOperationMode] = useState<"normal" | "shadow" | "emergency">("normal");
  const [slackEnabled, setSlackEnabled] = useState<boolean>(true);
  const [lineEnabled, setLineEnabled] = useState<boolean>(false);

  // Inline edit pending values (before confirm)
  const [pendingHf, setPendingHf] = useState<number>(1.6);
  const [pendingCooldown, setPendingCooldown] = useState<number>(10);
  const [pendingOpMode, setPendingOpMode] = useState<"normal" | "shadow" | "emergency">("normal");
  const [pendingSlack, setPendingSlack] = useState<boolean>(true);
  const [pendingLine, setPendingLine] = useState<boolean>(false);

  // Which field is in "confirm" mode
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget>(null);

  // Per-field success/error messages
  const [fieldSuccess, setFieldSuccess] = useState<Partial<Record<NonNullable<ConfirmTarget>, string>>>({});
  const [fieldError, setFieldError] = useState<Partial<Record<NonNullable<ConfirmTarget>, string>>>({});
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    if (!token) return;
    setLoadingData(true);
    setFetchError(null);
    try {
      const [auto, exch] = await Promise.all([
        fetchAutomationStatus(),
        fetchExchangeStatus(token),
      ]);
      setAutomationStatus(auto);
      setExchangeStatus(exch);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "データの取得に失敗しました";
      setFetchError(message);
    } finally {
      setLoadingData(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Open inline confirm for a field
  const openConfirm = (target: NonNullable<ConfirmTarget>) => {
    // Copy current values to pending
    if (target === "hf_threshold") setPendingHf(hfThreshold);
    if (target === "cooldown") setPendingCooldown(cooldownMinutes);
    if (target === "operation_mode") setPendingOpMode(operationMode);
    if (target === "slack_notify") setPendingSlack(slackEnabled);
    if (target === "line_notify") setPendingLine(lineEnabled);
    setConfirmTarget(target);
    setFieldSuccess({});
    setFieldError({});
  };

  const cancelConfirm = () => {
    setConfirmTarget(null);
  };

  const handleConfirm = async (target: NonNullable<ConfirmTarget>) => {
    setSaving(true);
    setFieldError({});
    setFieldSuccess({});
    try {
      // Mock POST — replace with real endpoints when available
      await new Promise<void>((resolve) => setTimeout(resolve, 600));

      // Apply pending value to committed state
      if (target === "hf_threshold") setHfThreshold(pendingHf);
      if (target === "cooldown") setCooldownMinutes(pendingCooldown);
      if (target === "operation_mode") setOperationMode(pendingOpMode);
      if (target === "slack_notify") setSlackEnabled(pendingSlack);
      if (target === "line_notify") setLineEnabled(pendingLine);

      setFieldSuccess((prev) => ({ ...prev, [target]: "設定を保存しました" }));
      setConfirmTarget(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "保存に失敗しました";
      setFieldError((prev) => ({ ...prev, [target]: message }));
    } finally {
      setSaving(false);
    }
  };

  if (loadingData) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "#888" }}>
        読み込み中...
      </div>
    );
  }

  const shadowModeActive = automationStatus?.is_trading_paused ?? false;

  return (
    <>
      <title>システム設定 - Ultra AutoTrade</title>

      <h1 style={{ marginBottom: 6 }}>システム設定</h1>
      <p style={{ marginTop: 0, color: "#555" }}>
        AI・取引所・Aave・通知の設定を確認・変更できます。
      </p>

      {fetchError && (
        <div style={errorBannerStyle}>
          データ取得エラー: {fetchError}
          <button onClick={loadData} style={retryBtnStyle}>再試行</button>
        </div>
      )}

      {/* ── Section 1: AI設定 ── */}
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>AI設定</h2>

        <div style={fieldRowStyle}>
          <span style={labelStyle}>Shadow Mode</span>
          <span style={valueStyle}>
            <span style={shadowModeActive ? badgeActiveStyle : badgeInactiveStyle}>
              {shadowModeActive ? "ON" : "OFF"}
            </span>
            {automationStatus?.emergency_reason && (
              <span style={{ marginLeft: 8, fontSize: 12, color: "#c62828" }}>
                ({automationStatus.emergency_reason})
              </span>
            )}
          </span>
          <span style={readOnlyHintStyle}>読み取り専用</span>
        </div>

        <div style={fieldRowStyle}>
          <span style={labelStyle}>プロンプトバージョン</span>
          <span style={valueStyle}>v2.0</span>
          <span style={readOnlyHintStyle}>読み取り専用</span>
        </div>

        <div style={{ ...fieldRowStyle, borderBottom: "none" }}>
          <span style={labelStyle}>フォールバックモデル</span>
          <span style={valueStyle}>gpt-4o</span>
          <span style={readOnlyHintStyle}>読み取り専用</span>
        </div>
      </section>

      {/* ── Section 2: Exchange設定 ── */}
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Exchange設定</h2>

        <div style={fieldRowStyle}>
          <span style={labelStyle}>Phase</span>
          <span style={valueStyle}>Phase A</span>
          <span style={readOnlyHintStyle}>読み取り専用</span>
        </div>

        <div style={fieldRowStyle}>
          <span style={labelStyle}>Sandbox</span>
          <span style={valueStyle}>
            {exchangeStatus == null ? (
              <span style={{ color: "#888" }}>—</span>
            ) : (
              <span style={exchangeStatus.sandbox_mode ? badgeWarningStyle : badgeActiveStyle}>
                {exchangeStatus.sandbox_mode ? "ON (Sandbox)" : "OFF (本番)"}
              </span>
            )}
          </span>
          <span style={readOnlyHintStyle}>読み取り専用</span>
        </div>

        <div style={{ ...fieldRowStyle, borderBottom: "none" }}>
          <span style={labelStyle}>取引上限 / 日</span>
          <span style={valueStyle}>
            {exchangeStatus == null ? (
              <span style={{ color: "#888" }}>—</span>
            ) : (
              <span>{exchangeStatus.daily_trade_limit} 回</span>
            )}
          </span>
          <span style={readOnlyHintStyle}>読み取り専用</span>
        </div>
      </section>

      {/* ── Section 3: Aave設定 ── */}
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Aave設定</h2>

        {/* HF閾値 */}
        <div style={fieldRowStyle}>
          <span style={labelStyle}>HF閾値</span>
          <span style={valueStyle}>{hfThreshold}</span>
          {confirmTarget !== "hf_threshold" && (
            <button style={editBtnStyle} onClick={() => openConfirm("hf_threshold")}>
              変更
            </button>
          )}
        </div>
        {fieldSuccess.hf_threshold && (
          <div style={inlineSuccessStyle}>{fieldSuccess.hf_threshold}</div>
        )}
        {fieldError.hf_threshold && (
          <div style={inlineErrorStyle}>{fieldError.hf_threshold}</div>
        )}
        {confirmTarget === "hf_threshold" && (
          <div style={confirmBoxStyle}>
            <label style={inputLabelStyle}>新しいHF閾値</label>
            <input
              type="number"
              step="0.1"
              min="1.0"
              max="3.0"
              value={pendingHf}
              onChange={(e) => setPendingHf(parseFloat(e.target.value))}
              style={inputStyle}
            />
            <p style={confirmTextStyle}>この設定を変更しますか？</p>
            <div style={confirmButtonRowStyle}>
              <button
                style={confirmBtnStyle}
                onClick={() => handleConfirm("hf_threshold")}
                disabled={saving}
              >
                {saving ? "保存中..." : "確認"}
              </button>
              <button style={cancelBtnStyle} onClick={cancelConfirm} disabled={saving}>
                キャンセル
              </button>
            </div>
          </div>
        )}

        {/* クールダウン */}
        <div style={fieldRowStyle}>
          <span style={labelStyle}>クールダウン</span>
          <span style={valueStyle}>{cooldownMinutes} 分</span>
          {confirmTarget !== "cooldown" && (
            <button style={editBtnStyle} onClick={() => openConfirm("cooldown")}>
              変更
            </button>
          )}
        </div>
        {fieldSuccess.cooldown && (
          <div style={inlineSuccessStyle}>{fieldSuccess.cooldown}</div>
        )}
        {fieldError.cooldown && (
          <div style={inlineErrorStyle}>{fieldError.cooldown}</div>
        )}
        {confirmTarget === "cooldown" && (
          <div style={confirmBoxStyle}>
            <label style={inputLabelStyle}>新しいクールダウン（分）</label>
            <input
              type="number"
              step="1"
              min="1"
              max="120"
              value={pendingCooldown}
              onChange={(e) => setPendingCooldown(parseInt(e.target.value, 10))}
              style={inputStyle}
            />
            <p style={confirmTextStyle}>この設定を変更しますか？</p>
            <div style={confirmButtonRowStyle}>
              <button
                style={confirmBtnStyle}
                onClick={() => handleConfirm("cooldown")}
                disabled={saving}
              >
                {saving ? "保存中..." : "確認"}
              </button>
              <button style={cancelBtnStyle} onClick={cancelConfirm} disabled={saving}>
                キャンセル
              </button>
            </div>
          </div>
        )}

        {/* Operation Mode */}
        <div style={{ ...fieldRowStyle, borderBottom: "none" }}>
          <span style={labelStyle}>Operation Mode</span>
          <span style={valueStyle}>
            <span style={opModeBadgeStyle(operationMode)}>{operationMode}</span>
          </span>
          {confirmTarget !== "operation_mode" && (
            <button style={editBtnStyle} onClick={() => openConfirm("operation_mode")}>
              変更
            </button>
          )}
        </div>
        {fieldSuccess.operation_mode && (
          <div style={inlineSuccessStyle}>{fieldSuccess.operation_mode}</div>
        )}
        {fieldError.operation_mode && (
          <div style={inlineErrorStyle}>{fieldError.operation_mode}</div>
        )}
        {confirmTarget === "operation_mode" && (
          <div style={confirmBoxStyle}>
            <label style={inputLabelStyle}>Operation Mode を選択</label>
            <select
              value={pendingOpMode}
              onChange={(e) =>
                setPendingOpMode(e.target.value as "normal" | "shadow" | "emergency")
              }
              style={selectStyle}
            >
              <option value="normal">normal</option>
              <option value="shadow">shadow</option>
              <option value="emergency">emergency</option>
            </select>
            <p style={confirmTextStyle}>この設定を変更しますか？</p>
            <div style={confirmButtonRowStyle}>
              <button
                style={confirmBtnStyle}
                onClick={() => handleConfirm("operation_mode")}
                disabled={saving}
              >
                {saving ? "保存中..." : "確認"}
              </button>
              <button style={cancelBtnStyle} onClick={cancelConfirm} disabled={saving}>
                キャンセル
              </button>
            </div>
          </div>
        )}
      </section>

      {/* ── Section 4: 通知設定 ── */}
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>通知設定</h2>

        {/* Slack通知 */}
        <div style={fieldRowStyle}>
          <span style={labelStyle}>Slack通知</span>
          <span style={valueStyle}>
            <span style={slackEnabled ? badgeActiveStyle : badgeInactiveStyle}>
              {slackEnabled ? "ON" : "OFF"}
            </span>
          </span>
          {confirmTarget !== "slack_notify" && (
            <button style={editBtnStyle} onClick={() => openConfirm("slack_notify")}>
              変更
            </button>
          )}
        </div>
        {fieldSuccess.slack_notify && (
          <div style={inlineSuccessStyle}>{fieldSuccess.slack_notify}</div>
        )}
        {fieldError.slack_notify && (
          <div style={inlineErrorStyle}>{fieldError.slack_notify}</div>
        )}
        {confirmTarget === "slack_notify" && (
          <div style={confirmBoxStyle}>
            <label style={toggleRowStyle}>
              <span style={inputLabelStyle}>Slack通知</span>
              <input
                type="checkbox"
                checked={pendingSlack}
                onChange={(e) => setPendingSlack(e.target.checked)}
                style={{ width: 18, height: 18, cursor: "pointer" }}
              />
              <span style={{ fontSize: 14, color: "#333", marginLeft: 4 }}>
                {pendingSlack ? "ON" : "OFF"}
              </span>
            </label>
            <p style={confirmTextStyle}>この設定を変更しますか？</p>
            <div style={confirmButtonRowStyle}>
              <button
                style={confirmBtnStyle}
                onClick={() => handleConfirm("slack_notify")}
                disabled={saving}
              >
                {saving ? "保存中..." : "確認"}
              </button>
              <button style={cancelBtnStyle} onClick={cancelConfirm} disabled={saving}>
                キャンセル
              </button>
            </div>
          </div>
        )}

        {/* LINE通知 */}
        <div style={{ ...fieldRowStyle, borderBottom: "none" }}>
          <span style={labelStyle}>LINE通知</span>
          <span style={valueStyle}>
            <span style={lineEnabled ? badgeActiveStyle : badgeInactiveStyle}>
              {lineEnabled ? "ON" : "OFF"}
            </span>
          </span>
          {confirmTarget !== "line_notify" && (
            <button style={editBtnStyle} onClick={() => openConfirm("line_notify")}>
              変更
            </button>
          )}
        </div>
        {fieldSuccess.line_notify && (
          <div style={inlineSuccessStyle}>{fieldSuccess.line_notify}</div>
        )}
        {fieldError.line_notify && (
          <div style={inlineErrorStyle}>{fieldError.line_notify}</div>
        )}
        {confirmTarget === "line_notify" && (
          <div style={confirmBoxStyle}>
            <label style={toggleRowStyle}>
              <span style={inputLabelStyle}>LINE通知</span>
              <input
                type="checkbox"
                checked={pendingLine}
                onChange={(e) => setPendingLine(e.target.checked)}
                style={{ width: 18, height: 18, cursor: "pointer" }}
              />
              <span style={{ fontSize: 14, color: "#333", marginLeft: 4 }}>
                {pendingLine ? "ON" : "OFF"}
              </span>
            </label>
            <p style={confirmTextStyle}>この設定を変更しますか？</p>
            <div style={confirmButtonRowStyle}>
              <button
                style={confirmBtnStyle}
                onClick={() => handleConfirm("line_notify")}
                disabled={saving}
              >
                {saving ? "保存中..." : "確認"}
              </button>
              <button style={cancelBtnStyle} onClick={cancelConfirm} disabled={saving}>
                キャンセル
              </button>
            </div>
          </div>
        )}
      </section>
    </>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const sectionStyle: React.CSSProperties = {
  marginTop: 24,
  padding: 20,
  border: "1px solid #eee",
  borderRadius: 12,
  background: "#fff",
};

const sectionTitleStyle: React.CSSProperties = {
  margin: 0,
  marginBottom: 12,
  fontSize: 16,
  fontWeight: 600,
  color: "#1a1a1a",
};

const fieldRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  padding: "10px 0",
  borderBottom: "1px solid #f5f5f5",
  gap: 8,
};

const labelStyle: React.CSSProperties = {
  width: 160,
  color: "#666",
  fontSize: 14,
  flexShrink: 0,
};

const valueStyle: React.CSSProperties = {
  flex: 1,
  fontSize: 14,
  color: "#1a1a1a",
};

const readOnlyHintStyle: React.CSSProperties = {
  fontSize: 11,
  color: "#aaa",
  flexShrink: 0,
};

const badgeActiveStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 10px",
  borderRadius: 4,
  fontSize: 12,
  background: "#e8f5e9",
  color: "#2e7d32",
  fontWeight: 600,
};

const badgeInactiveStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 10px",
  borderRadius: 4,
  fontSize: 12,
  background: "#f5f5f5",
  color: "#757575",
  fontWeight: 600,
};

const badgeWarningStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 10px",
  borderRadius: 4,
  fontSize: 12,
  background: "#fff8e1",
  color: "#e65100",
  fontWeight: 600,
};

const opModeBadgeStyle = (mode: "normal" | "shadow" | "emergency"): React.CSSProperties => {
  const map: Record<string, React.CSSProperties> = {
    normal: { background: "#e8f5e9", color: "#2e7d32" },
    shadow: { background: "#e3f2fd", color: "#1565c0" },
    emergency: { background: "#ffebee", color: "#c62828" },
  };
  return {
    display: "inline-block",
    padding: "2px 10px",
    borderRadius: 4,
    fontSize: 12,
    fontWeight: 600,
    ...map[mode],
  };
};

const editBtnStyle: React.CSSProperties = {
  padding: "4px 14px",
  background: "#1976d2",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  fontSize: 13,
  cursor: "pointer",
  flexShrink: 0,
};

const confirmBoxStyle: React.CSSProperties = {
  margin: "4px 0 12px 0",
  padding: "14px 16px",
  background: "#fafafa",
  border: "1px solid #e0e0e0",
  borderRadius: 8,
};

const confirmTextStyle: React.CSSProperties = {
  margin: "10px 0 8px 0",
  fontSize: 13,
  color: "#444",
};

const confirmButtonRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
};

const confirmBtnStyle: React.CSSProperties = {
  padding: "6px 18px",
  background: "#1976d2",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  fontSize: 13,
  cursor: "pointer",
};

const cancelBtnStyle: React.CSSProperties = {
  padding: "6px 18px",
  background: "#fff",
  color: "#555",
  border: "1px solid #ccc",
  borderRadius: 6,
  fontSize: 13,
  cursor: "pointer",
};

const inputLabelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: 4,
  fontSize: 13,
  color: "#555",
};

const inputStyle: React.CSSProperties = {
  width: 120,
  padding: "6px 10px",
  border: "1px solid #ddd",
  borderRadius: 6,
  fontSize: 14,
};

const selectStyle: React.CSSProperties = {
  padding: "6px 10px",
  border: "1px solid #ddd",
  borderRadius: 6,
  fontSize: 14,
  background: "#fff",
  cursor: "pointer",
};

const toggleRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  cursor: "pointer",
};

const inlineSuccessStyle: React.CSSProperties = {
  margin: "2px 0 8px 0",
  padding: "6px 12px",
  background: "#e8f5e9",
  border: "1px solid #c8e6c9",
  borderRadius: 6,
  fontSize: 13,
  color: "#2e7d32",
};

const inlineErrorStyle: React.CSSProperties = {
  margin: "2px 0 8px 0",
  padding: "6px 12px",
  background: "#fff5f5",
  border: "1px solid #f1c0c0",
  borderRadius: 6,
  fontSize: 13,
  color: "#c62828",
};

const errorBannerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "10px 16px",
  background: "#fff5f5",
  border: "1px solid #f1c0c0",
  borderRadius: 8,
  fontSize: 14,
  color: "#c62828",
  marginBottom: 16,
};

const retryBtnStyle: React.CSSProperties = {
  padding: "4px 12px",
  background: "#c62828",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  fontSize: 13,
  cursor: "pointer",
};
