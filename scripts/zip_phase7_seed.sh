#!/usr/bin/env bash
set -euo pipefail

OUTPUT="phase7_seed_files.zip"

zip -r "${OUTPUT}" \
  docs/*.md \
  backend/app/main.py \
  backend/app/ai \
  backend/app/notion \
  backend/app/bots \
  backend/app/aave \
  backend/app/automation \
  backend/app/notifications \
  backend/tests \
  scripts/backup.sh \
  scripts/monitor.sh
