#!/bin/bash
set -e

echo "🔧 プロジェクトフォルダ構造を作成します..."

# backend
mkdir -p backend/app/{ai,notion,bots,aave,automation,utils}
mkdir -p backend/tests

# frontend
mkdir -p frontend/{pages,components,api}

# docs
mkdir -p docs

# scripts
mkdir -p scripts

# .github (GitHub用)
mkdir -p .github/ISSUE_TEMPLATE

echo "📁 フォルダ作成完了"

# backend 初期ファイル
touch backend/app/main.py
touch backend/requirements.txt

# frontend 初期ファイル
touch frontend/README.md

# docs 初期ファイル（中身はあとでGPTと一緒に埋める前提）
touch docs/00_overview.md
touch docs/01_requirements.md
touch docs/02_phase_plan.md
touch docs/03_directory_structure.md
touch docs/04_api_design.md
touch docs/05_ai_judgement_rules.md
touch docs/06_octobot_signal_flow.md
touch docs/07_aave_operation_logic.md
touch docs/08_automation_rules.md
touch docs/09_notion_schema.md
touch docs/10_next_phase_prompt_generator.md
touch docs/11_prompt_sync_rules.md
touch docs/12_phase_operations.md

# scripts 初期ファイル
touch scripts/backup.sh
touch scripts/monitor.sh
touch scripts/zip_next_phase.sh

# GitHub Issue テンプレ
touch .github/ISSUE_TEMPLATE/feature_request.md
touch .github/ISSUE_TEMPLATE/bug_report.md
touch .github/ISSUE_TEMPLATE/task.md
touch .github/ISSUE_TEMPLATE/requirement_change.md

# GitHub PR テンプレ
touch .github/PULL_REQUEST_TEMPLATE.md

echo "✅ 初期ファイル作成完了"
echo "完了：プロジェクトのフォルダ構成と空ファイルを作成しました。"
