#!/usr/bin/env bash
set -euo pipefail

# プロジェクトルート（scripts/ の1つ上）に移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}/backend"

# Python 仮想環境の管理方法は環境によって異なるため、
# ここでは poetry があればそれを使い、なければ素の python を使う。
if command -v poetry >/dev/null 2>&1; then
  poetry run python -m app.automation.jobs backup-only
else
  python -m app.automation.jobs backup-only
fi
