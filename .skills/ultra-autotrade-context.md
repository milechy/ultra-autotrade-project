# Ultra AutoTrade プロジェクトコンテキスト

## プロジェクト概要
- **目的**: OctoBot x AI x Aave の暗号資産自動運用システム
- **入力**: Notion にニュースURLを貼る
- **処理**: AI判定（BUY/SELL/HOLD） → OctoBot取引シグナル → Aave資産運用
- **出力**: 自動取引 + レポート + ダッシュボード

## Tech Stack
- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: Next.js + Mantine UI（日本語化済み）
- **Database**: Notion (structured data), SQLite (auth)
- **Infrastructure**: Docker Compose, Hetzner Cloud
- **Network**: Polygon Mumbai (staging), Polygon (production予定)

## 環境
- **Development**: Codespaces
- **Staging**: 77.42.46.155 (Hetzner, testnet only)
  - Frontend: http://77.42.46.155:3000
  - Backend: http://77.42.46.155:8000
- **Production**: 未デプロイ

## コアな設計原則
1. **Security First**: docs/13_security_design.md 参照
   - `.env.staging` と `.env.production` を絶対に混同しない
   - API keys は環境変数のみ
   - Aave operations は testnet のみ（本番まで）

2. **Documentation is Truth**: すべての仕様は docs/*.md にある
   - 25+ markdown files
   - コーディング前に必ず関連 docs を読む

3. **Test Coverage**: 193+ passing tests
   - `pytest backend/tests/` でフルテスト実行
   - Phase ごとに comprehensive testing

4. **Phase-Based Development**: 現在 Phase 12
   - Clear scope per phase
   - See docs/02_phase_plan.md

5. **Fail-Closed**: エラー時は安全側（停止）に倒す
   - emergency_stop (monitoring_service)
   - Health Factor < 1.6 で自動停止

## ディレクトリ構造
```
project-root/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI entry point
│   │   ├── aave/                       # Aave V3 integration
│   │   ├── automation/                 # Monitoring, emergency stop, reporting
│   │   │   ├── workflow.py             # Notion → AI → OctoBot orchestration
│   │   │   ├── monitoring_service.py   # Health checks, HF monitoring
│   │   │   └── reporting_service.py    # Daily/weekly reports
│   │   ├── bots/                       # OctoBot integration
│   │   ├── ai/                         # AI judgment logic
│   │   ├── notion/                     # Notion API client
│   │   └── auth/                       # Authentication (SQLite)
│   ├── tests/                          # pytest tests (193+)
│   └── requirements.txt
├── frontend/
│   ├── pages/                          # Next.js pages (Japanese)
│   ├── components/                     # Mantine UI components
│   └── package.json
├── docs/                               # Design docs (source of truth)
│   ├── 00_overview.md
│   ├── 04_api_design.md
│   ├── 07_aave_operation_logic.md
│   ├── 08_automation_rules.md
│   ├── 13_security_design.md
│   ├── 14_test_strategy.md
│   ├── 19_operations_runbook.md
│   ├── 23_ui_localization_guide.md     # UI Japanese localization
│   ├── 24_partner_test_guide.md        # Partner testing guide
│   └── 25_workflow_architecture.md     # Automation workflow
└── scripts/
    └── deploy_staging_backend.sh
```

## Phase 進捗
- ✅ Phase 1: Notion API連携
- ✅ Phase 2: AI判定ロジック
- ✅ Phase 3: OctoBot連携
- ✅ Phase 4: Aave統合（Web3AaveClient実装）
- ✅ Phase 5: 監視・自動化
- ✅ Phase 6: レポート生成
- ✅ Phase 7: Staging デプロイ
- ✅ Phase 8-11: API/Dashboard 実装
- ✅ **Phase 12: UI日本語化 + パートナーテスト準備** ← 現在
- 🔄 Phase 13: Aave 本格統合（予定）
- 🔄 Phase 14: Production デプロイ（予定）

## 重要なコマンド

### Testing
```bash
# Full test suite
cd backend && pytest

# Specific module
pytest backend/tests/test_workflow_service.py

# With coverage
pytest --cov=app backend/tests/
```

### Staging Deployment
```bash
# SSH to staging
ssh root@77.42.46.155

# Update and restart
cd /opt/ultra-autotrade
git pull origin main
docker compose -f docker-compose.staging.yml restart backend frontend
```

### Log Monitoring
```bash
# Backend logs
docker logs ultra-autotrade-backend-staging --tail 100 -f

# Automation workflow logs
tail -f /var/log/ultra/automation.log

# Health check
curl http://localhost:8000/health
```

## 重要なドキュメント

### Must Read Before Coding
- `docs/13_security_design.md`: **Security policies (CRITICAL)**
- `docs/04_api_design.md`: API specifications
- `docs/14_test_strategy.md`: Testing patterns

### Architecture & Design
- `docs/00_overview.md`: Project overview
- `docs/03_directory_structure.md`: File organization
- `docs/25_workflow_architecture.md`: Automation workflow

### Aave & Risk Management
- `docs/07_aave_operation_logic.md`: Aave operation rules (HF thresholds)
- `docs/08_automation_rules.md`: Monitoring, alerts, retry logic

### Operations & Deployment
- `docs/16_infra_deployment_guide.md`: Deployment procedures
- `docs/19_operations_runbook.md`: Daily operations, troubleshooting

### Testing & QA
- `docs/14_test_strategy.md`: Unit/Integration/E2E testing
- `docs/24_partner_test_guide.md`: Partner testing procedures

### Localization
- `docs/23_ui_localization_guide.md`: UI Japanese localization

## Critical Warnings

### Environment Variables
**NEVER:**
- Commit `.env.*` files to Git
- Mix staging/production values
- Hard-code API keys
- Use production keys in staging

**ALWAYS:**
- Use `.env.staging` on staging
- Use `.env.production` on production (when ready)
- Verify env vars before deploy

### Aave Safety
**Current Status**: Testnet only (Polygon Mumbai)

**Rules:**
- Use testnet ONLY until production approval
- Health Factor minimum: 1.6
- Cooldown: 10 minutes between trades
- NEVER increase position when HF < threshold

### OctoBot Integration
**Status**: Operational on staging

**Key Points:**
- Rate limiting: 3 signals per hour per action type
- Confidence threshold: 70+
- HOLD actions NOT sent to OctoBot

## Troubleshooting

### Common Issues

**Login Error:**
- Symptom: "Invalid email or password"
- Cause: User not created, or using `username` instead of `email`
- Solution: docs/19_operations_runbook.md § 11.1

**UI Shows English:**
- Symptom: Pages in English instead of Japanese
- Cause: Browser cache or container not restarted
- Solution: Ctrl+Shift+R, then restart frontend container

**Notion Not Processing:**
- Symptom: Status stays "未処理" for 10+ minutes
- Cause: cron not running, invalid URL, or backend error
- Solution: Check cron (`crontab -l`), check logs

**Tests Failing:**
- Solution: Check env vars, read error message, see docs/14_test_strategy.md

## Project Status (Phase 12 Complete)

**Completed:**
- ✅ Notion → AI → OctoBot → Notion workflow (automated, 5-min cron)
- ✅ Frontend dashboard (fully localized to Japanese)
- ✅ Partner testing environment (staging)
- ✅ Authentication system (SQLite-based)
- ✅ 193+ passing tests
- ✅ Comprehensive documentation (25+ docs)

**In Progress:**
- 🔄 Partner feedback collection
- 🔄 UI/UX improvements based on feedback

**Next Phases:**
- Phase 13: Aave full integration (0% → 100%)
- Phase 14: Production deployment
- Phase 15: Enhanced monitoring & alerting

## Best Practices

1. **Incremental Development**: Phase-based, clear scope
2. **Explicit Over Implicit**: All behaviors explicitly defined
3. **Trust But Verify**: Test after every phase
4. **Security by Default**: Never compromise on security
5. **Documentation First**: Update docs before/during implementation

## Notes

- All project files in `/mnt/project/`
- Current session in Codespaces
- For detailed workflows, see docs/25_workflow_architecture.md
- For partner testing, see docs/24_partner_test_guide.md