#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

ZIP_NAME="phase6_seed_files.zip"

cd "${ROOT_DIR}"

zip -r "${ZIP_NAME}" \
  backend/app/automation/*.py \
  backend/app/notifications/*.py \
  backend/app/aave/service.py \
  backend/app/bots/service.py \
  backend/tests/test_automation_*.py \
  backend/tests/test_notifications_service.py \
  docs/02_phase_plan.md \
  docs/03_directory_structure.md \
  docs/08_automation_rules.md \
  docs/13_security_design.md \
  docs/14_test_strategy.md \
  docs/15_rollback_procedures.md \
  scripts/backup.sh \
  scripts/monitor.sh
