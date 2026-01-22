#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

OUTPUT="phase11_seed_files.zip"

zip -r "${OUTPUT}" \
  backend/app/automation/schemas.py \
  backend/app/automation/monitoring_service.py \
  backend/app/automation/reporting_service.py \
  backend/tests/test_automation_dashboard_view.py \
  backend/tests/test_automation_reporting.py \
  docs/08_automation_rules.md \
  docs/19_operations_runbook.md \
  docs/14_test_strategy.md

echo "Created ${OUTPUT}"