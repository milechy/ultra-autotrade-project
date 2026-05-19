#!/usr/bin/env bash
# =============================================================================
# cloudflare_audit_log_polling.sh — Cloudflare Dashboard 変更検知 → Slack 通知
#
# 背景:
#   2026-05-09 cloudflared ingress port mismatch が 12 日間未検知だった。
#   Cloudflare Logpush は Enterprise plan 必須のため、API polling で代替。
#   Cloudflare Audit Logs API を 10 分間隔で polling し、Tunnel/DNS 変更を
#   Slack #ultra-auto-project に通知する。
#
# 使用方法:
#   # cron (10分間隔): */10 * * * * /opt/ultra-autotrade/main/scripts/cloudflare_audit_log_polling.sh
#   bash scripts/cloudflare_audit_log_polling.sh
#   bash scripts/cloudflare_audit_log_polling.sh --dry-run  # 通知なし確認モード
#
# 必要な環境変数 (.env.production または cron 環境):
#   CF_API_TOKEN     — Cloudflare API Token (Audit Logs: Read 権限)
#   CF_ACCOUNT_ID    — Cloudflare Account ID
#   SLACK_WEBHOOK_URL — Slack Incoming Webhook URL
#
# 取得する API Token の権限:
#   Account > Account Settings > Read
#   (Audit Logs を読むには Account Settings 権限が必要)
#
# 参照:
#   https://developers.cloudflare.com/api/resources/audit-logs/methods/list/
#   docs/postmortems/2026-05-09_staging_api_502.md
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ─── 設定 ────────────────────────────────────────────────────────────
STATE_FILE="${STATE_FILE:-/tmp/cloudflare_audit_last_seen.txt}"
DRY_RUN=false
for arg in "$@"; do
  [[ "${arg}" == "--dry-run" ]] && DRY_RUN=true
done

# ─── 環境変数チェック ─────────────────────────────────────────────────
CF_API_TOKEN="${CF_API_TOKEN:-}"
CF_ACCOUNT_ID="${CF_ACCOUNT_ID:-}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"

# .env.production から読み込む（cron 実行時用）
if [[ -z "${CF_API_TOKEN}" ]] && [[ -f "${PROJECT_ROOT}/.env.production" ]]; then
  CF_API_TOKEN="$(grep '^CF_API_TOKEN=' "${PROJECT_ROOT}/.env.production" | cut -d= -f2-)"
  CF_ACCOUNT_ID="$(grep '^CF_ACCOUNT_ID=' "${PROJECT_ROOT}/.env.production" | cut -d= -f2-)"
  SLACK_WEBHOOK_URL="$(grep '^SLACK_WEBHOOK_URL=' "${PROJECT_ROOT}/.env.production" | cut -d= -f2-)"
fi

if [[ -z "${CF_API_TOKEN}" ]]; then
  echo "[cf-audit] ERROR: CF_API_TOKEN が未設定。.env.production に CF_API_TOKEN=<token> を追加してください。" >&2
  echo "[cf-audit] API Token 作成手順: Cloudflare Dashboard → My Profile → API Tokens → Create Token" >&2
  echo "[cf-audit]   Template: 'Read All Resources' または カスタム: Account Settings:Read" >&2
  exit 1
fi

if [[ -z "${CF_ACCOUNT_ID}" ]]; then
  echo "[cf-audit] ERROR: CF_ACCOUNT_ID が未設定。Cloudflare Dashboard → ホーム → Account ID を確認してください。" >&2
  exit 1
fi

# ─── 最終確認タイムスタンプ取得 ───────────────────────────────────────
if [[ -f "${STATE_FILE}" ]]; then
  LAST_SEEN="$(cat "${STATE_FILE}")"
else
  # 初回実行: 10 分前から取得
  LAST_SEEN="$(date -u -d '10 minutes ago' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
    || date -u -v-10M '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
    || python3 -c "from datetime import datetime, timedelta; print((datetime.utcnow()-timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
fi

NOW="$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
  || python3 -c "from datetime import datetime; print(datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))")"

echo "[cf-audit] polling: ${LAST_SEEN} → ${NOW}"

# ─── Cloudflare Audit Logs API 呼び出し ───────────────────────────────
CF_API_BASE="https://api.cloudflare.com/client/v4"
AUDIT_URL="${CF_API_BASE}/accounts/${CF_ACCOUNT_ID}/audit_logs"

PARAMS="per_page=100&direction=desc&since=${LAST_SEEN}&before=${NOW}"

RESPONSE=$(curl -sf \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${AUDIT_URL}?${PARAMS}" 2>&1) || {
  echo "[cf-audit] ERROR: Cloudflare API 呼び出し失敗: ${RESPONSE}" >&2
  exit 1
}

# success フィールド確認
SUCCESS=$(echo "${RESPONSE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('success','false'))" 2>/dev/null || echo "false")
if [[ "${SUCCESS}" != "True" ]] && [[ "${SUCCESS}" != "true" ]]; then
  ERRORS=$(echo "${RESPONSE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('errors','unknown'))" 2>/dev/null || echo "${RESPONSE}")
  echo "[cf-audit] ERROR: API エラー: ${ERRORS}" >&2
  exit 1
fi

# ─── 監視対象アクション判定 ───────────────────────────────────────────
# Tunnel 関連 / DNS 関連 / Firewall ルール変更のみフィルタ
INTERESTING_ENTRIES=$(echo "${RESPONSE}" | python3 - <<'PYEOF'
import sys, json

data = json.load(sys.stdin)
result = data.get("result", [])

WATCH_RESOURCE_TYPES = {
    "cloudflare_tunnel",
    "tunnel",
    "tunnel_route",
    "tunnel_virtual_network",
    "dns_record",
    "zone_setting",
    "firewall_rule",
    "access_application",
    "access_policy",
}

WATCH_ACTION_TYPES = {
    "create",
    "update",
    "delete",
    "rotate",
    "revoke",
}

interesting = []
for entry in result:
    resource = entry.get("resource", {})
    resource_type = resource.get("type", "").lower()
    action = entry.get("action", {}).get("type", "").lower()

    if resource_type in WATCH_RESOURCE_TYPES and action in WATCH_ACTION_TYPES:
        interesting.append({
            "id": entry.get("id", ""),
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource.get("id", ""),
            "actor": entry.get("actor", {}).get("email", entry.get("actor", {}).get("type", "unknown")),
            "when": entry.get("when", ""),
            "metadata": entry.get("metadata", {}),
        })

print(json.dumps(interesting, ensure_ascii=False))
PYEOF
)

ENTRY_COUNT=$(echo "${INTERESTING_ENTRIES}" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

echo "[cf-audit] 監視対象エントリ: ${ENTRY_COUNT} 件"

# ─── 検知なし → state 更新して終了 ───────────────────────────────────
if [[ "${ENTRY_COUNT}" -eq 0 ]]; then
  echo "[cf-audit] 変更なし"
  echo "${NOW}" > "${STATE_FILE}"
  exit 0
fi

# ─── 変更検知 → Slack 通知 ────────────────────────────────────────────
SLACK_TEXT="*[cloudflare-audit] Dashboard 変更を検知 (${ENTRY_COUNT} 件)*\n\n"

ENTRIES_SUMMARY=$(echo "${INTERESTING_ENTRIES}" | python3 - <<'PYEOF'
import sys, json

entries = json.load(sys.stdin)
lines = []
for e in entries[:10]:  # 最大 10 件表示
    when = e.get("when", "")[:16]  # YYYY-MM-DDTHH:MM
    lines.append(f"  [{when}] {e['action'].upper()} {e['resource_type']} ({e['actor']})")
    meta = e.get("metadata", {})
    if meta:
        # 重要なメタデータを表示
        for k in ["hostname", "service", "name", "description"]:
            if k in meta:
                lines.append(f"    {k}: {meta[k]}")

if len(entries) > 10:
    lines.append(f"  ... 他 {len(entries)-10} 件")

print("\n".join(lines))
PYEOF
)

SLACK_TEXT+="```${ENTRIES_SUMMARY}```\n\n"
SLACK_TEXT+="⚠️ Tunnel/DNS 変更が含まれる場合は drift check を実行してください:\n"
SLACK_TEXT+="\`\`\`bash scripts/env_drift_check.sh\`\`\`\n"
SLACK_TEXT+="参照: docs/51_horizontal_propagation_checklist.md"

echo "[cf-audit] 変更検知:"
echo "${ENTRIES_SUMMARY}"

if "${DRY_RUN}"; then
  echo "[cf-audit] DRY-RUN: Slack 通知をスキップ"
  echo "${NOW}" > "${STATE_FILE}"
  exit 0
fi

if [[ -z "${SLACK_WEBHOOK_URL}" ]]; then
  echo "[cf-audit] WARN: SLACK_WEBHOOK_URL が未設定のため通知をスキップ" >&2
  echo "${NOW}" > "${STATE_FILE}"
  exit 0
fi

curl -s -X POST "${SLACK_WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json,sys; print(json.dumps({'text': sys.argv[1]}))" "${SLACK_TEXT}")" > /dev/null 2>&1 \
  && echo "[cf-audit] Slack 通知送信完了" \
  || echo "[cf-audit] WARN: Slack 通知の送信に失敗" >&2

echo "${NOW}" > "${STATE_FILE}"
exit 0
