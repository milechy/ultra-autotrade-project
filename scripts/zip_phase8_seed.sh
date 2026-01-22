#!/usr/bin/env bash
set -euo pipefail

# Phase8 用 seed ファイルをまとめるスクリプト
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

OUTPUT="phase8_seed_files.zip"

zip -r "${OUTPUT}" \
  backend/app \
  Dockerfile \
  docker-compose.staging.yml \
  infra/systemd/ultra-autotrade-backend.service \
  docs/00_overview.md \
  docs/01_requirements.md \
  docs/02_phase_plan.md \
  docs/03_directory_structure.md \
  docs/04_api_design.md \
  docs/05_ai_judgement_rules.md \
  docs/06_octobot_signal_flow.md \
  docs/07_aave_operation_logic.md \
  docs/08_automation_rules.md \
  docs/09_notion_schema.md \
  docs/10_next_phase_prompt_generator.md \
  docs/11_prompt_sync_rules.md \
  docs/12_phase_operations.md \
  docs/13_security_design.md \
  docs/14_test_strategy.md \
  docs/15_rollback_procedures.md \
  docs/16_infra_deployment_guide.md \
  docs/17_staging_environment_config.md \
  docs/18_scheduler_and_cron.md \
  docs/19_operations_runbook.md \
  docs/20_staging_release_checklist.md

echo "Created ${OUTPUT}"