#!/usr/bin/env bash
set -euo pipefail

# プロジェクトルート（scripts/ の1つ上）に移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}/backend"

JOB="${1:-daily}"

if [[ "${JOB}" != "daily" && "${JOB}" != "weekly" ]]; then
  echo "Usage: $0 [daily|weekly]" >&2
  exit 1
fi

if command -v poetry >/dev/null 2>&1; then
  poetry run python -m app.automation.jobs "${JOB}"
else
  python -m app.automation.jobs "${JOB}"
fi
