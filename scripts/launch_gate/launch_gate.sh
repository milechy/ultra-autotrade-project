#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/launch_gate.sh
#
# Launch Gate L0-L5 集約エントリポイント。
# launch_gate/ ディレクトリ内から直接実行可能。
#
# Usage:
#   bash scripts/launch_gate/launch_gate.sh
#   bash scripts/launch_gate/launch_gate.sh --env=staging
#   bash scripts/launch_gate/launch_gate.sh --env=production
#   bash scripts/launch_gate/launch_gate.sh --only=L1,L2
#   bash scripts/launch_gate/launch_gate.sh --skip=L0,L3
#   bash scripts/launch_gate/launch_gate.sh --help
#
# Lanes:
#   L0 schema    -- alembic / SQLAlchemy gap (staging == production)
#   L1 env       -- .env.staging / .env.production の意味的分離
#   L2 smoke     -- /health + 主要 5 endpoint が 2xx (LAUNCH_GATE_SMOKE_TOKEN 対応)
#   L3 e2e       -- yamamoto-partner-flow.spec.ts 完走
#   L4 kill      -- POST /api/automation/emergency-stop が動く
#   L5 wiring    -- 孤立 router (main.py 未 register) 検出
#
# Exit codes:
#   0 -- FAIL ゼロ (SKIP は許容、人間貼付け確認が必要)
#   1 -- 1 件以上 FAIL もしくは不正引数
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

# ---------------------------------------------------------------------------
# 引数 parse
# ---------------------------------------------------------------------------
ENV_TARGET="staging"
ONLY=""
SKIP=""

show_help() {
  awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
}

for arg in "$@"; do
  case "${arg}" in
    --env=*)   ENV_TARGET="${arg#--env=}" ;;
    --only=*)  ONLY="${arg#--only=}" ;;
    --skip=*)  SKIP="${arg#--skip=}" ;;
    --help|-h) show_help; exit 0 ;;
    *)
      echo "[launch_gate] unknown arg: ${arg}" >&2
      show_help
      exit 1
      ;;
  esac
done

case "${ENV_TARGET}" in
  staging|production) ;;
  *)
    echo "[launch_gate] --env must be 'staging' or 'production' (got: ${ENV_TARGET})" >&2
    exit 1
    ;;
esac

# ---------------------------------------------------------------------------
# 実行する Lane の決定
# ---------------------------------------------------------------------------
ALL_LANES=(L0 L1 L2 L3 L4 L5)
declare -A LANE_SCRIPT=(
  [L0]="${SCRIPT_DIR}/L0_schema.sh"
  [L1]="${SCRIPT_DIR}/L1_env.sh"
  [L2]="${SCRIPT_DIR}/L2_smoke.sh"
  [L3]="${SCRIPT_DIR}/L3_e2e.sh"
  [L4]="${SCRIPT_DIR}/L4_killswitch.sh"
  [L5]="${SCRIPT_DIR}/L5_wiring_lint.sh"
)

_csv_to_set() {
  local csv="$1"
  echo "${csv}" | tr ',' '\n' | sed '/^$/d'
}

selected=()
if [[ -n "${ONLY}" ]]; then
  while IFS= read -r ln; do
    if [[ -n "${LANE_SCRIPT[${ln}]:-}" ]]; then
      selected+=("${ln}")
    else
      echo "[launch_gate] --only に未知の lane: ${ln}" >&2
      exit 1
    fi
  done < <(_csv_to_set "${ONLY}")
else
  selected=("${ALL_LANES[@]}")
fi

if [[ -n "${SKIP}" ]]; then
  skipset="$(_csv_to_set "${SKIP}")"
  remaining=()
  for ln in "${selected[@]}"; do
    if echo "${skipset}" | grep -qE "^${ln}$"; then
      log_info "skipping ${ln} (per --skip)"
    else
      remaining+=("${ln}")
    fi
  done
  selected=("${remaining[@]}")
fi

# ---------------------------------------------------------------------------
# 実行ヘッダ
# ---------------------------------------------------------------------------
echo "=========================================="
echo " Ultra AutoTrade Launch Gate"
echo "   env:    ${ENV_TARGET}"
echo "   lanes:  ${selected[*]:-(none)}"
echo "   host:   $(hostname 2>/dev/null || uname -n)"
echo "   time:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
[[ -n "${LAUNCH_GATE_SMOKE_TOKEN:-}" ]] && echo "   token:  LAUNCH_GATE_SMOKE_TOKEN set"
echo "=========================================="

if [[ "${#selected[@]}" -eq 0 ]]; then
  echo "[launch_gate] no lanes selected after --only/--skip; nothing to do."
  exit 1
fi

# ---------------------------------------------------------------------------
# Lane を順次実行。
# 各 L*.sh は独立 bash subshell で起動し、exit code で PASS/FAIL を判定。
# PASS と SKIP の区別は標準出力の [PASS]/[SKIP] 行で判定する。
# ---------------------------------------------------------------------------
fail_lanes=()
pass_lanes=()
skip_lanes=()

for ln in "${selected[@]}"; do
  script="${LANE_SCRIPT[${ln}]}"
  echo ""
  echo "==> ${ln} (${script##*/})"
  if [[ ! -f "${script}" ]]; then
    echo "[FAIL] ${ln}: lane script 不在: ${script}"
    fail_lanes+=("${ln}")
    continue
  fi

  output_file="$(mktemp -t "launch_gate_${ln}_XXXXXX")"
  ENV_TARGET="${ENV_TARGET}" bash "${script}" 2>&1 | tee "${output_file}"
  rc=${PIPESTATUS[0]}

  if [[ "${rc}" -ne 0 ]]; then
    fail_lanes+=("${ln}")
  elif grep -q "^\[SKIP\] ${ln} " "${output_file}"; then
    skip_lanes+=("${ln}")
  else
    pass_lanes+=("${ln}")
  fi
  rm -f "${output_file}"
done

# ---------------------------------------------------------------------------
# 最終サマリ
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo " Launch Gate Summary (env=${ENV_TARGET})"
echo "=========================================="
echo "  PASS (${#pass_lanes[@]}): ${pass_lanes[*]:-}"
echo "  SKIP (${#skip_lanes[@]}): ${skip_lanes[*]:-}"
echo "  FAIL (${#fail_lanes[@]}): ${fail_lanes[*]:-}"
echo "------------------------------------------"

if [[ "${#fail_lanes[@]}" -gt 0 ]]; then
  echo "Launch Gate: BLOCKED — launch 不可。上記 FAIL lane を修正してください。"
  exit 1
fi

if [[ "${#skip_lanes[@]}" -gt 0 ]]; then
  echo "Launch Gate: CONDITIONAL PASS — SKIP lane は人間が prod VPS で実行し"
  echo "             結果を貼り付けて確認するまで実質完了ではありません。"
else
  echo "Launch Gate: PASSED — launch 可。"
fi
exit 0
