#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ZIP_NAME="phase4_seed_files.zip"

rm -f "$ZIP_NAME"

zip -r "$ZIP_NAME" \
  backend/app/main.py \
  backend/app/ai \
  backend/app/bots \
  backend/app/utils/config.py \
  backend/app/aave \
  backend/tests/test_ai_service.py \
  backend/tests/test_octobot_service.py \
  backend/tests/test_smoke.py \
  docs/00_overview.md \
  docs/01_requirements.md \
  docs/02_phase_plan.md \
  docs/03_directory_structure.md \
  docs/04_api_design.md \
  docs/06_octobot_signal_flow.md \
  docs/07_aave_operation_logic.md \
  docs/08_automation_rules.md \
  docs/13_security_design.md \
  docs/14_test_strategy.md \
  docs/15_rollback_procedures.md
