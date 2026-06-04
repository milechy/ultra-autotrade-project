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
#   - assert_not_skip_only_playwright  (Playwright JSON で skip-only を構造的 FAIL に)
#   - assert_not_skip_only_pytest      (pytest summary 行で skip-only を構造的 FAIL に)
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

# ---------------------------------------------------------------------------
# skip-only 構造的判定 helper (G scope, 2026-05-28 追加)
#
# memory [[feedback-skip-only-fail-at-gate-not-spec]] の意図:
#   spec 内に skip-on-skip 多段配線するのではなく、gate script 側で
#   「PASS=0 / FAIL=0 / SKIP>0」を機械的に検出して FAIL に倒す。
#
# 使い方:
#   # Playwright JSON 結果
#   if ! assert_not_skip_only_playwright "${RESULTS_JSON}"; then
#     gate_record FAIL "${LABEL}" "skip-only run (gate 側構造的 FAIL)"
#     exit 1
#   fi
#
#   # pytest log (将来 L6/L7 で pytest 系を追加した場合)
#   pytest ... 2>&1 | tee /tmp/Lx_pytest.log
#   if ! assert_not_skip_only_pytest /tmp/Lx_pytest.log; then
#     gate_record FAIL "${LABEL}" "pytest skip-only (gate 側構造的 FAIL)"
#     exit 1
#   fi
#
# 戻り値:
#   0 — skip-only でない (passed>0 or failed>0)、または判定不能 (ファイル無し)
#   1 — skip-only (passed=0 && failed=0 && skipped>0)
# ---------------------------------------------------------------------------

# Playwright JSON stats フィールド取得 (jq → python3 → grep の 3 段フォールバック)
_parse_playwright_stat() {
  local json="$1" field="$2"
  if [[ ! -f "${json}" ]]; then
    echo 0
    return 0
  fi
  if command -v jq >/dev/null 2>&1; then
    jq -r ".stats.${field} // 0" "${json}" 2>/dev/null || echo 0
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import json,sys
try:
  d=json.load(open('${json}'))
  print(d.get('stats',{}).get('${field}',0))
except Exception:
  print(0)" 2>/dev/null || echo 0
  else
    # 最終フォールバック: grep ベース (脆弱だが skip 判定よりは強い)
    grep -oE "\"${field}\"[[:space:]]*:[[:space:]]*[0-9]+" "${json}" 2>/dev/null \
      | head -1 \
      | grep -oE '[0-9]+$' \
      || echo 0
  fi
}

assert_not_skip_only_playwright() {
  local json="${1:-}"
  if [[ -z "${json}" || ! -f "${json}" ]]; then
    # JSON 無し → 判定不能、別の check で扱う
    return 0
  fi
  local passed failed skipped flaky passed_total
  passed=$(_parse_playwright_stat "${json}" "expected")
  failed=$(_parse_playwright_stat "${json}" "unexpected")
  skipped=$(_parse_playwright_stat "${json}" "skipped")
  flaky=$(_parse_playwright_stat "${json}" "flaky")
  # 数値防御
  passed=${passed:-0}; failed=${failed:-0}; skipped=${skipped:-0}; flaky=${flaky:-0}
  passed_total=$(( passed + flaky ))
  if [[ "${passed_total}" -eq 0 && "${failed}" -eq 0 && "${skipped}" -gt 0 ]]; then
    log_info "assert_not_skip_only_playwright: skip-only detected (passed=0 failed=0 skipped=${skipped})"
    return 1
  fi
  return 0
}

assert_not_skip_only_pytest() {
  local logfile="${1:-}"
  if [[ -z "${logfile}" || ! -f "${logfile}" ]]; then
    return 0
  fi
  # pytest 最終 summary 行を抽出
  # 例: "===== 5 passed, 1 skipped in 1.23s ====="
  #     "===== 3 skipped in 0.5s ====="
  #     "===== 3 failed, 2 passed in 0.5s ====="
  local summary
  summary=$(grep -E '^=+ .*=+$' "${logfile}" 2>/dev/null | grep -E ' in [0-9.]+s ?' | tail -1)
  if [[ -z "${summary}" ]]; then
    # summary 行なし → 判定不能
    return 0
  fi
  local has_pass has_fail has_skip
  has_pass=$(echo "${summary}" | grep -cE '[0-9]+ passed' || true)
  has_fail=$(echo "${summary}" | grep -cE '[0-9]+ (failed|error)' || true)
  has_skip=$(echo "${summary}" | grep -cE '[0-9]+ skipped' || true)
  has_pass=${has_pass:-0}; has_fail=${has_fail:-0}; has_skip=${has_skip:-0}
  if [[ "${has_pass}" -eq 0 && "${has_fail}" -eq 0 && "${has_skip}" -gt 0 ]]; then
    log_info "assert_not_skip_only_pytest: skip-only summary detected ('${summary}')"
    return 1
  fi
  return 0
}
