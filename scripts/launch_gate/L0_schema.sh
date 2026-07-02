#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/L0_schema.sh
#
# Launch Gate L0: schema / migration ギャップ検査。
#
# 目的:
#   staging と production の DB schema (= alembic head / model 定義) が
#   一致しているかを確認する。launch 直前に不足 migration があると
#   "実装完了→ローンチ不能" の典型パターンになる。
#
# 実装:
#   既存 scripts/check_db_migration_gap.sh を staging / production それぞれで呼ぶ。
#   両方 exit 0 (= ギャップ無し) なら PASS。
#
# Usage (launch_gate.sh から source して呼ばれる):
#   ENV_TARGET=staging  bash scripts/launch_gate/L0_schema.sh
#   ENV_TARGET=production bash scripts/launch_gate/L0_schema.sh
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

PROJECT_ROOT="$(gate_project_root)"
GAP_SCRIPT="${PROJECT_ROOT}/scripts/check_db_migration_gap.sh"
LABEL="L0 schema"

# ENV_TARGET が明示設定された場合はその1環境のみ、未指定時は staging / production 両方
if [[ -n "${ENV_TARGET:-}" ]]; then
  run_envs=("${ENV_TARGET}")
else
  run_envs=(staging production)
fi
ENV_TARGET="${ENV_TARGET:-staging}"

if [[ ! -x "${GAP_SCRIPT}" && ! -f "${GAP_SCRIPT}" ]]; then
  gate_record FAIL "${LABEL}" "check_db_migration_gap.sh が見つかりません: ${GAP_SCRIPT}"
  exit 1
fi

# dev VPS からは prod DB に届かないので skip-with-instructions
if is_dev_vps; then
  echo "[INFO] L0 schema: dev VPS のため DB に直接アクセスできません。"
  echo "       2026-07-02移行後、staging と production は別 VPS です。以下を実行し、exit 0 を確認してください:"
  echo ""
  for env in "${run_envs[@]}"; do
    case "${env}" in
      production) echo "         ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14 'cd /opt/ultra-autotrade && bash ${GAP_SCRIPT} --env=${env}'" ;;
      staging)    echo "         ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142 'cd /opt/ultra-autotrade && bash ${GAP_SCRIPT} --env=${env}'" ;;
      *)          echo "         bash ${GAP_SCRIPT} --env=${env}" ;;
    esac
  done
  echo ""
  echo "       0 でない場合は alembic head に gap あり → launch 不可。"
  gate_record SKIP "${LABEL}" "dev VPS のため手動実行 (production=5.223.88.14 / staging=188.34.167.142 で check_db_migration_gap.sh --env={${run_envs[*]}})"
  exit 0
fi

# prod / staging 側 (本物の VPS) で実行された場合
fail_envs=()
for env in "${run_envs[@]}"; do
  echo "--- L0 schema: ${env} ---"
  if bash "${GAP_SCRIPT}" --env="${env}"; then
    echo "  [ok] ${env}"
  else
    rc=$?
    fail_envs+=("${env}(rc=${rc})")
  fi
done

if [[ "${#fail_envs[@]}" -eq 0 ]]; then
  gate_record PASS "${LABEL}" "${run_envs[*]} alembic gap なし"
  exit 0
fi

gate_record FAIL "${LABEL}" "schema gap あり: ${fail_envs[*]}"
exit 1
