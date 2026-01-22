#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

zip -r phase2_seed_files.zip \
  backend/app/main.py \
  backend/app/notion \
  backend/app/utils/config.py \
  backend/requirements.txt \
  backend/tests/test_notion_client.py \
  backend/tests/test_notion_router.py \
  docs/00_overview.md \
  docs/01_requirements.md \
  docs/02_phase_plan.md \
  docs/03_directory_structure.md \
  docs/04_api_design.md \
  docs/05_ai_judgement_rules.md \
  docs/09_notion_schema.md \
  docs/10_next_phase_prompt_generator.md \
  docs/11_prompt_sync_rules.md \
  docs/12_phase_operations.md \
  docs/14_test_strategy.md \
  docs/15_rollback_procedures.md \
  -x "*/__pycache__/*" "*.pyc"

