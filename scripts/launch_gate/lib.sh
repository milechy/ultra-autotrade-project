#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/lib.sh
#
# Launch Gate L0-L5 共通ヘルパー。
#
# 提供:
#   - log_pass / log_fail / log_skip   (統一フォーマット出力)
#   - is_dev_vps                       (dev VPS 判定 — prod に SSH 不可な環境かどうか)
#   - gate_record / gate_summary       (結果集約用)
#
# 出力フォーマット (色・CR は使わない):
#   [PASS] L0 schema: <要約>
#   [FAIL] L1 env:    <要約>
#   [SKIP] L2 smoke:  <理由>
# ---------------------------------------------------------------------------

# shellcheck shell=bash

# 二重 source 防止
if [[ "${_LAUNCH_GATE_LIB_SOURCED:-0}" == "1" ]]; then
  return 0 2>/dev/null || true
fi
_LAUNCH_GATE_LIB_SOURCED=1

# ---------------------------------------------------------------------------
# 結果集約用 (parent shell からも見えるように export しない — 同一 shell 前提)
# ---------------------------------------------------------------------------
GATE_RESULTS=()       # 例: "PASS|L0|alembic head 一致"
GATE_FAIL_COUNT=0
GATE_SKIP_COUNT=0
GATE_PASS_COUNT=0

# ---------------------------------------------------------------------------
# 出力ヘルパー (color / CR は使わない、CI で再利用可能なプレーンテキスト)
# ---------------------------------------------------------------------------
log_pass() {
  # $1: ラベル (例 "L0 schema"), $2: 要約
  local label="$1" summary="$2"
  echo "[PASS] ${label}: ${summary}"
}

log_fail() {
  local label="$1" summary="$2"
  echo "[FAIL] ${label}: ${summary}"
}

log_skip() {
  local label="$1" summary="$2"
  echo "[SKIP] ${label}: ${summary}"
}

log_info() {
  local msg="$1"
  echo "[INFO] ${msg}"
}

# ---------------------------------------------------------------------------
# 結果集約
#   gate_record PASS|FAIL|SKIP <label> <summary>
# ---------------------------------------------------------------------------
gate_record() {
  local status="$1" label="$2" summary="$3"
  GATE_RESULTS+=("${status}|${label}|${summary}")
  case "${status}" in
    PASS) GATE_PASS_COUNT=$(( GATE_PASS_COUNT + 1 )); log_pass "${label}" "${summary}" ;;
    FAIL) GATE_FAIL_COUNT=$(( GATE_FAIL_COUNT + 1 )); log_fail "${label}" "${summary}" ;;
    SKIP) GATE_SKIP_COUNT=$(( GATE_SKIP_COUNT + 1 )); log_skip "${label}" "${summary}" ;;
    *)    log_info "unknown status: ${status} ${label} ${summary}" ;;
  esac
}

# ---------------------------------------------------------------------------
# 結果サマリ表示 (最後に呼ぶ)
#   exit code:
#     0 -- FAIL ゼロ
#     1 -- FAIL 1件以上
# ---------------------------------------------------------------------------
gate_summary() {
  echo ""
  echo "=== Launch Gate Summary ==="
  local r status label summary
  for r in "${GATE_RESULTS[@]}"; do
    status="${r%%|*}"
    rest="${r#*|}"
    label="${rest%%|*}"
    summary="${rest#*|}"
    printf "  [%s] %-20s %s\n" "${status}" "${label}" "${summary}"
  done
  echo "---------------------------"
  echo "PASS=${GATE_PASS_COUNT}  FAIL=${GATE_FAIL_COUNT}  SKIP=${GATE_SKIP_COUNT}"

  if [[ "${GATE_FAIL_COUNT}" -gt 0 ]]; then
    echo "Launch Gate: BLOCKED (FAIL=${GATE_FAIL_COUNT})"
    return 1
  fi
  echo "Launch Gate: PASSED (SKIP=${GATE_SKIP_COUNT} は人間貼付け確認が必要)"
  return 0
}

# ---------------------------------------------------------------------------
# dev VPS 判定
#
# memory [[no-prod-vps-commands-from-dev]] に従い、dev VPS から prod に届く
# コマンド (curl http://prod-host, ssh prod, docker exec prod-container 等) を
# 実行しない。dev VPS であれば skip-with-instructions モードに倒す。
#
# 判定:
#   - hostname が "uata-dev*" / "*-dev-*" / "dev-*" を含む
#   - 環境変数 LAUNCH_GATE_FORCE_DEV=1 で強制 dev 扱い
#   - 環境変数 LAUNCH_GATE_FORCE_PROD=1 で強制 prod 扱い (CI / prod VPS から)
# ---------------------------------------------------------------------------
is_dev_vps() {
  if [[ "${LAUNCH_GATE_FORCE_PROD:-0}" == "1" ]]; then
    return 1
  fi
  if [[ "${LAUNCH_GATE_FORCE_DEV:-0}" == "1" ]]; then
    return 0
  fi
  local h
  h="$(hostname 2>/dev/null || uname -n 2>/dev/null || echo "")"
  case "${h}" in
    *uata-dev*|*-dev-*|dev-*|*devbox*) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# PROJECT_ROOT 解決
#   各 L*.sh から source される前提。lib.sh は scripts/launch_gate/lib.sh にある。
# ---------------------------------------------------------------------------
gate_project_root() {
  local lib_dir
  lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # scripts/launch_gate/ から 2 つ上が PROJECT_ROOT
  (cd "${lib_dir}/../.." && pwd)
}
