#!/usr/bin/env bash
# yamamoto_24h_observer.sh
# 山本さんテスト 24h 観察 — 自動中間チェック
# Asana: 1214441344571838 / 観察タスク: 1214444133815913
# SQL: Asana サブタスク 1214444691392001 (18:00 JST) + 1214444691441662 (22:00 JST) より verbatim
#
# 環境変数:
#   OBSERVATION_START_UTC  観察開始 UTC (デフォルト: 2026-05-01 02:50:00+00)
#   HETZNER_HOST           Hetzner ホスト (デフォルト: 77.42.46.155)
#   HETZNER_USER           SSH ユーザー   (デフォルト: ultra)
#   HETZNER_SSH_KEY        SSH 鍵パス    (デフォルト: ~/.ssh/hetzner_staging)
#   SLACK_WEBHOOK_URL      Slack Webhook URL (未設定時は通知スキップ)
#
# 実行頻度想定: 4 時間間隔
# cron 例: 0 */4 * * * /opt/ultra-autotrade/scripts/cloud-routine/yamamoto_24h_observer.sh
#
# 使用例:
#   OBSERVATION_START_UTC="2026-05-02 02:50:00+00" ./yamamoto_24h_observer.sh

set -uo pipefail

# -----------------------------------------------------------------------
# 設定
# -----------------------------------------------------------------------
OBS_START="${OBSERVATION_START_UTC:-2026-05-01 02:50:00+00}"
HETZNER_HOST="${HETZNER_HOST:-77.42.46.155}"
HETZNER_USER="${HETZNER_USER:-ultra}"
SSH_KEY="${HETZNER_SSH_KEY:-$HOME/.ssh/hetzner_staging}"
POSTGRES_CTR="ultra-autotrade-postgres-production"
BACKEND_CTR="ultra-autotrade-backend-blue-production"
POSTGRES_USER="ultra"
POSTGRES_DB="ultra_autotrade"
LOG_DIR="$HOME/.cloud-routine"
LOG_FILE="$LOG_DIR/yamamoto_observer.log"

# -----------------------------------------------------------------------
# ログ初期化
# -----------------------------------------------------------------------
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S JST')
echo ""
echo "=================================================================="
echo "yamamoto_24h_observer 開始: $TIMESTAMP"
echo "OBS_START: $OBS_START"
echo "=================================================================="

# -----------------------------------------------------------------------
# 前提チェック
# -----------------------------------------------------------------------
if [[ ! -f "$SSH_KEY" ]]; then
  echo "[ERROR] SSH 鍵が見つかりません: $SSH_KEY"
  echo "  export HETZNER_SSH_KEY=/path/to/key を設定してください"
  exit 1
fi

if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
  ENV_FILE="/opt/ultra-autotrade/.env.production"
  if [[ -f "$ENV_FILE" ]]; then
    SLACK_WEBHOOK_URL=$(grep "^SLACK_WEBHOOK_URL=" "$ENV_FILE" | cut -d= -f2-)
  fi
fi

# -----------------------------------------------------------------------
# ユーティリティ関数
# -----------------------------------------------------------------------
ssh_exec() {
  local cmd="$1"
  local max=3
  local attempt=1
  while [[ $attempt -le $max ]]; do
    if ssh -i "$SSH_KEY" \
           -o ConnectTimeout=15 \
           -o StrictHostKeyChecking=accept-new \
           -o BatchMode=yes \
           "$HETZNER_USER@$HETZNER_HOST" "$cmd" 2>&1; then
      return 0
    fi
    echo "[WARN] SSH 試行 ${attempt}/${max} 失敗 — 10 秒後リトライ" >&2
    sleep 10
    attempt=$((attempt + 1))
  done
  echo "[ERROR] SSH 接続 ${max} 回失敗" >&2
  return 1
}

slack_notify() {
  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "[SKIP] SLACK_WEBHOOK_URL 未設定 — 通知スキップ"
    return 0
  fi
  curl -s -X POST "$SLACK_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$1\"}" > /dev/null
}

extract_section() {
  local output="$1"
  local start_marker="$2"
  local end_marker="$3"
  printf '%s\n' "$output" | awk -v start="$start_marker" -v end="$end_marker" '
    $0 == start { found=1; next }
    $0 == end   { found=0; next }
    found
  '
}

# -----------------------------------------------------------------------
# SSH call 1: psql チェック (A, A-stat, C, D, D-stat, A-recheck)
# SQL は Asana サブタスク 1214444691392001 + 1214444691441662 より verbatim
# -----------------------------------------------------------------------
echo ""
echo ">>> SSH call 1: psql チェック"

SQL_OUTPUT=$(ssh_exec "
echo 'MARKER_A_START' ; \
docker exec $POSTGRES_CTR psql -U $POSTGRES_USER -d $POSTGRES_DB -c \"
SELECT
  to_char(created_at AT TIME ZONE 'Asia/Tokyo', 'MM-DD HH24:MI') AS jst,
  action,
  ROUND(confidence::numeric, 1) AS conf,
  primary_provider,
  primary_action,
  ROUND(primary_confidence::numeric, 1) AS p_conf,
  secondary_action,
  ROUND(secondary_confidence::numeric, 1) AS s_conf
FROM ai_decisions
WHERE created_at >= '$OBS_START'
ORDER BY created_at DESC
LIMIT 10;
\" ; \
echo 'MARKER_A_END' ; \
echo 'MARKER_ASTAT_START' ; \
docker exec $POSTGRES_CTR psql -U $POSTGRES_USER -d $POSTGRES_DB -c \"
SELECT
  COUNT(*) AS n,
  ROUND(AVG(primary_confidence)::numeric, 1) AS avg_p_conf,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY primary_confidence)::numeric, 1) AS median_p_conf,
  COUNT(*) FILTER (WHERE action <> 'HOLD') AS non_hold_count,
  COUNT(*) FILTER (WHERE secondary_confidence = 0) AS sec_zero_count
FROM ai_decisions
WHERE created_at >= '$OBS_START';
\" ; \
echo 'MARKER_ASTAT_END' ; \
echo 'MARKER_C_START' ; \
docker exec $POSTGRES_CTR psql -U $POSTGRES_USER -d $POSTGRES_DB -c \"
SELECT
  id,
  username,
  CASE WHEN wallet_address IS NULL THEN 'NULL'
       ELSE substr(wallet_address, 1, 6) || '...' || substr(wallet_address, -4)
  END AS wallet_short,
  CASE WHEN privy_did IS NULL THEN 'NULL'
       ELSE 'SET (len=' || length(privy_did) || ')'
  END AS privy_did_status,
  execution_policy,
  to_char(updated_at AT TIME ZONE 'Asia/Tokyo', 'MM-DD HH24:MI') AS updated_jst
FROM users WHERE id=11;
\" ; \
echo 'MARKER_C_END' ; \
echo 'MARKER_D_START' ; \
docker exec $POSTGRES_CTR psql -U $POSTGRES_USER -d $POSTGRES_DB -c \"
SELECT
  to_char(created_at AT TIME ZONE 'Asia/Tokyo', 'MM-DD HH24:MI') AS jst,
  user_id,
  operation,
  amount_usd,
  status,
  COALESCE(approved_at::text, '-') AS approved
FROM proposals
WHERE created_at >= '$OBS_START'
ORDER BY created_at DESC
LIMIT 20;
\" ; \
echo 'MARKER_D_END' ; \
echo 'MARKER_DSTAT_START' ; \
docker exec $POSTGRES_CTR psql -U $POSTGRES_USER -d $POSTGRES_DB -c \"
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE user_id = 11) AS yamamoto_count,
  COUNT(*) FILTER (WHERE status = 'pending') AS pending,
  COUNT(*) FILTER (WHERE status = 'approved') AS approved,
  COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
  COUNT(*) FILTER (WHERE status = 'expired') AS expired
FROM proposals
WHERE created_at >= '$OBS_START';
\" ; \
echo 'MARKER_DSTAT_END' ; \
echo 'MARKER_ARECHECK_START' ; \
docker exec $POSTGRES_CTR psql -U $POSTGRES_USER -d $POSTGRES_DB -c \"
SELECT COUNT(*) AS total_decisions,
       MAX(to_char(created_at AT TIME ZONE 'Asia/Tokyo', 'MM-DD HH24:MI')) AS latest_jst
FROM ai_decisions
WHERE created_at >= '$OBS_START';
\" ; \
echo 'MARKER_ARECHECK_END'
") || {
  echo "[ERROR] psql SSH 接続失敗"
  slack_notify "❌ yamamoto_24h_observer: SSH接続失敗 (${TIMESTAMP})\nHetzner ${HETZNER_HOST} への接続が3回失敗しました"
  exit 1
}

# -----------------------------------------------------------------------
# SSH call 2: docker logs + health
# -----------------------------------------------------------------------
echo ""
echo ">>> SSH call 2: docker logs + health"

LOG_OUTPUT=$(ssh_exec "
echo 'MARKER_B_START' ; \
docker logs $BACKEND_CTR --since=24h 2>&1 \
  | grep -E '(aave_chain_registry_miss|aave_reserve_data_fetch_failed|aave_utilization_fetch_failed)' \
  | wc -l ; \
echo 'MARKER_B_END' ; \
echo 'MARKER_BDETAIL_START' ; \
docker logs $BACKEND_CTR --since=24h 2>&1 \
  | grep -E '(aave_chain_registry_miss|aave_reserve_data_fetch_failed|aave_utilization_fetch_failed)' \
  | tail -5 ; \
echo 'MARKER_BDETAIL_END' ; \
echo 'MARKER_HEALTH_START' ; \
docker exec $BACKEND_CTR curl -s http://localhost:8000/health | head -10 ; \
echo 'MARKER_HEALTH_END'
") || {
  echo "[ERROR] docker logs/health SSH 接続失敗"
  slack_notify "❌ yamamoto_24h_observer: SSH接続失敗 (${TIMESTAMP})\nHetzner ${HETZNER_HOST} への接続が3回失敗しました"
  exit 1
}

# -----------------------------------------------------------------------
# セクション抽出
# -----------------------------------------------------------------------
OUT_A=$(extract_section "$SQL_OUTPUT" "MARKER_A_START" "MARKER_A_END")
OUT_ASTAT=$(extract_section "$SQL_OUTPUT" "MARKER_ASTAT_START" "MARKER_ASTAT_END")
OUT_C=$(extract_section "$SQL_OUTPUT" "MARKER_C_START" "MARKER_C_END")
OUT_D=$(extract_section "$SQL_OUTPUT" "MARKER_D_START" "MARKER_D_END")
OUT_DSTAT=$(extract_section "$SQL_OUTPUT" "MARKER_DSTAT_START" "MARKER_DSTAT_END")
OUT_ARECHECK=$(extract_section "$SQL_OUTPUT" "MARKER_ARECHECK_START" "MARKER_ARECHECK_END")
OUT_B=$(extract_section "$LOG_OUTPUT" "MARKER_B_START" "MARKER_B_END")
OUT_BDETAIL=$(extract_section "$LOG_OUTPUT" "MARKER_BDETAIL_START" "MARKER_BDETAIL_END")
OUT_HEALTH=$(extract_section "$LOG_OUTPUT" "MARKER_HEALTH_START" "MARKER_HEALTH_END")

# -----------------------------------------------------------------------
# 出力表示
# -----------------------------------------------------------------------
echo ""
echo "==================================================================="
echo "[A] ai_decisions 推移 (最新10件)"
echo "==================================================================="
echo "$OUT_A"

echo ""
echo "==================================================================="
echo "[A-stat] primary_confidence 統計"
echo "==================================================================="
echo "$OUT_ASTAT"

echo ""
echo "==================================================================="
echo "[B] Aave データ取得エラーカウント (直近24h)"
echo "==================================================================="
echo "エラーカウント: $(echo "$OUT_B" | tr -d ' \t\n')"

echo ""
echo "==================================================================="
echo "[C] 山本さん (id=11) 接続状況"
echo "==================================================================="
echo "$OUT_C"

echo ""
echo "==================================================================="
echo "[D] proposals 出現 (最新20件)"
echo "==================================================================="
echo "$OUT_D"

echo ""
echo "==================================================================="
echo "[D-stat] proposals 統計"
echo "==================================================================="
echo "$OUT_DSTAT"

echo ""
echo "==================================================================="
echo "[A-recheck] ai_decisions 累計"
echo "==================================================================="
echo "$OUT_ARECHECK"

echo ""
echo "==================================================================="
echo "[Health] backend + scheduler"
echo "==================================================================="
echo "$OUT_HEALTH"

# -----------------------------------------------------------------------
# 判定ロジック
# -----------------------------------------------------------------------
FAIL_ITEMS=()
WARN_ITEMS=()

# [A] ai_decisions 推移
A_N=$(printf '%s\n' "$OUT_ASTAT" | grep -E '^ +[0-9]' | head -1 | awk -F'|' '{val=$1; gsub(/[[:space:]]/, "", val); print val}')
A_MEDIAN=$(printf '%s\n' "$OUT_ASTAT" | grep -E '^ +[0-9]' | head -1 | awk -F'|' '{val=$3; gsub(/[[:space:]]/, "", val); print val}')
A_SEC_ZERO=$(printf '%s\n' "$OUT_ASTAT" | grep -E '^ +[0-9]' | head -1 | awk -F'|' '{val=$5; gsub(/[[:space:]]/, "", val); print val}')
A_N="${A_N:-0}"
A_MEDIAN="${A_MEDIAN:-0}"
A_SEC_ZERO="${A_SEC_ZERO:-0}"

echo ""
echo "[A 判定] n=${A_N}, median_p_conf=${A_MEDIAN}, sec_zero_count=${A_SEC_ZERO}"
if [[ "$A_N" -lt 1 ]]; then
  echo "[A] FAIL: ai_decisions 0 件 — scheduler 異常の可能性"
  FAIL_ITEMS+=("[A] ai_decisions 0件 — scheduler 異常の可能性")
elif awk "BEGIN { exit (${A_MEDIAN} > 50) ? 0 : 1 }" 2>/dev/null; then
  echo "[A] PASS: n=${A_N}, median_p_conf=${A_MEDIAN} > 50"
else
  echo "[A] FAIL: median_p_conf=${A_MEDIAN} <= 50 — BUY/SELLゼロ問題の可能性"
  FAIL_ITEMS+=("[A] median_p_conf=${A_MEDIAN} ≤ 50 — BUY/SELLゼロ問題の可能性")
fi
if [[ "$A_SEC_ZERO" -gt 0 ]]; then
  echo "[A] FAIL: sec_zero_count=${A_SEC_ZERO} — PR #142 回帰の可能性"
  FAIL_ITEMS+=("[A] sec_zero_count=${A_SEC_ZERO} — PR #142 回帰の可能性")
fi

# [B] Aave エラー
B_COUNT=$(printf '%s\n' "$OUT_B" | tr -d ' \t\n')
B_COUNT="${B_COUNT:-0}"
echo ""
echo "[B 判定] aave_error_count=${B_COUNT}"
if [[ "$B_COUNT" -eq 0 ]]; then
  echo "[B] PASS: Aave エラー 0 件"
else
  echo "[B] FAIL: Aave エラー ${B_COUNT} 件 — V2→V3移行取りこぼしの可能性"
  FAIL_ITEMS+=("[B] Aave エラー ${B_COUNT}件 — V2→V3移行取りこぼしの可能性")
  if [[ -n "$OUT_BDETAIL" ]]; then
    echo "エラー直近5件:"
    echo "$OUT_BDETAIL"
  fi
fi

# [C] 山本さん接続状況
C_ROW=$(printf '%s\n' "$OUT_C" | grep -E '^ +11 +\|' | head -1)
C_WALLET=$(printf '%s\n' "$C_ROW" | awk -F'|' '{val=$3; gsub(/^ +| +$/, "", val); print val}')
C_PRIVY=$(printf '%s\n' "$C_ROW" | awk -F'|' '{val=$4; gsub(/^ +| +$/, "", val); print val}')
C_WALLET="${C_WALLET:-UNKNOWN}"
C_PRIVY="${C_PRIVY:-UNKNOWN}"

echo ""
echo "[C 判定] wallet=${C_WALLET}, privy_did=${C_PRIVY}"
if [[ "$C_WALLET" == "NULL" && "$C_PRIVY" == "NULL" ]]; then
  echo "[C] WARN: 山本さん未接続 — wallet, privy_did ともに NULL (まだ作業中の可能性)"
  WARN_ITEMS+=("[C] 山本さん未接続 — Slack で進捗確認推奨")
elif [[ "$C_PRIVY" == "NULL" && "$C_WALLET" != "NULL" ]]; then
  echo "[C] FAIL: 不整合 — wallet_address SET だが privy_did NULL"
  FAIL_ITEMS+=("[C] 不整合 — wallet SET/privy_did NULL")
else
  echo "[C] PASS: wallet=${C_WALLET}, privy_did=${C_PRIVY}"
fi

# [D] proposals 出現
D_YAMAMOTO=$(printf '%s\n' "$OUT_DSTAT" | grep -E '^ +[0-9]' | head -1 | awk -F'|' '{val=$2; gsub(/[[:space:]]/, "", val); print val}')
D_YAMAMOTO="${D_YAMAMOTO:-0}"

echo ""
echo "[D 判定] yamamoto_count=${D_YAMAMOTO}"
if [[ "$C_WALLET" == "NULL" ]]; then
  echo "[D] SKIP: 山本さん未接続 — proposals 0 件は正常"
elif [[ "$D_YAMAMOTO" -ge 1 ]]; then
  echo "[D] PASS: yamamoto_count=${D_YAMAMOTO}"
else
  echo "[D] WARN: yamamoto_count=0 — 山本さん deposit 後 4h 経過していれば要確認"
  WARN_ITEMS+=("[D] yamamoto proposals 0件 — deposit 後 4h 経過していれば要確認")
fi

# [Health]
echo ""
echo "[Health 判定]"
if printf '%s\n' "$OUT_HEALTH" | grep -qE '"scheduler_healthy"[[:space:]]*:[[:space:]]*true'; then
  echo "[Health] PASS: scheduler_healthy = true"
else
  echo "[Health] FAIL: scheduler_healthy が true でない"
  FAIL_ITEMS+=("[Health] scheduler_healthy != true")
fi

# -----------------------------------------------------------------------
# 結果サマリ + Slack 通知
# -----------------------------------------------------------------------
echo ""
echo "==================================================================="
echo "判定サマリ"
echo "==================================================================="

if [[ "${#FAIL_ITEMS[@]}" -eq 0 && "${#WARN_ITEMS[@]}" -eq 0 ]]; then
  echo "✅ 全項目 PASS"
  SLACK_MSG="✅ 山本さん観察 中間チェック OK (${TIMESTAMP})\nobs_start: ${OBS_START}\n全 A/B/C/D/Health PASS"

elif [[ "${#FAIL_ITEMS[@]}" -eq 0 ]]; then
  echo "⚠️  警告 ${#WARN_ITEMS[@]} 件 (FAIL なし)"
  if [[ "${#WARN_ITEMS[@]}" -gt 0 ]]; then
    for w in "${WARN_ITEMS[@]}"; do echo "  ⚠️  $w"; done
  fi
  WARN_TEXT=""
  if [[ "${#WARN_ITEMS[@]}" -gt 0 ]]; then
    for w in "${WARN_ITEMS[@]}"; do WARN_TEXT="${WARN_TEXT}⚠️  ${w}\n"; done
  fi
  SLACK_MSG="⚠️  山本さん観察 中間チェック WARN (${TIMESTAMP})\nobs_start: ${OBS_START}\n${WARN_TEXT}"

else
  echo "❌ FAIL ${#FAIL_ITEMS[@]} 件"
  if [[ "${#FAIL_ITEMS[@]}" -gt 0 ]]; then
    for f in "${FAIL_ITEMS[@]}"; do echo "  ❌ $f"; done
  fi
  if [[ "${#WARN_ITEMS[@]}" -gt 0 ]]; then
    for w in "${WARN_ITEMS[@]}"; do echo "  ⚠️  $w"; done
  fi
  FAIL_TEXT=""
  if [[ "${#FAIL_ITEMS[@]}" -gt 0 ]]; then
    for f in "${FAIL_ITEMS[@]}"; do FAIL_TEXT="${FAIL_TEXT}❌ ${f}\n"; done
  fi
  SLACK_MSG="⚠️  山本さん観察 中間チェック NG — STOP (${TIMESTAMP})\nobs_start: ${OBS_START}\n${FAIL_TEXT}→ claude.ai に判断委任"
fi

slack_notify "$SLACK_MSG"

echo ""
echo "=================================================================="
echo "yamamoto_24h_observer 完了: $(date '+%Y-%m-%d %H:%M:%S JST')"
echo "ログ: $LOG_FILE"
echo "=================================================================="

if [[ "${#FAIL_ITEMS[@]}" -gt 0 ]]; then
  exit 1
fi
exit 0
