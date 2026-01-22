#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

OUTPUT="phase10_seed_files.zip"

zip -r "${OUTPUT}" \
  docs/08_automation_rules.md \
  docs/19_operations_runbook.md \
  docs/17_staging_environment_config.md \
  docs/21_production_environment_config.md \
  docs/14_test_strategy.md \
  docs/20_staging_release_checklist.md \
  docs/22_production_release_checklist.md \
  backend/app/automation/schemas.py \
  backend/app/automation/monitoring_service.py \
  backend/app/automation/reporting_service.py \
  backend/tests/test_automation_monitoring.py \
  backend/tests/test_automation_reporting.py

echo "Created ${OUTPUT}"