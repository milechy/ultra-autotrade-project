#!/usr/bin/env bash
set -euo pipefail

OUTPUT_ZIP="phase5_seed_files.zip"

zip -r "${OUTPUT_ZIP}" \
  backend/app/main.py \
  backend/app/ai \
  backend/app/bots \
  backend/app/aave \
  backend/app/utils \
  backend/tests/test_ai_service.py \
  backend/tests/test_octobot_service.py \
  backend/tests/test_aave_service.py \
  backend/tests/test_aave_router.py \
  docs/00_overview.md \
  docs/01_requirements.md \
  docs/02_phase_plan.md \
  docs/08_automation_rules.md \
  docs/13_security_design.md \
  docs/14_test_strategy.md \
  docs/15_rollback_procedures.md
