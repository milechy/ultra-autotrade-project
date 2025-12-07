# 03_directory_structure.md
# ディレクトリ構成

project root/
├── backend/
│ ├── app/
│ │ ├── main.py                 # FastAPIエントリーポイント
│ │ ├── ai/                     # AI解析ロジック（Phase2以降）
│ │ ├── notion/                 # Notion連携モジュール（Phase1）
│ │ │ ├── __init__.py          # Notion連携パッケージマーカー
│ │ │ ├── config.py            # Notion API設定（環境変数読み取り）
│ │ │ ├── client.py            # Notion APIクライアント（HTTP通信）
│ │ │ ├── service.py           # Notionレコード取得・内部モデル変換サービス層
│ │ │ ├── schemas.py           # NotionNewsItem / NotionIngestResponse スキーマ
│ │ │ └── router.py            # /notion/ingest エンドポイント定義
│ │ ├── bots/                  # OctoBot連携（別フェーズ）
│ │ ├── aave/                  # Aave運用ロジック（別フェーズ）
│ │ ├── automation/            # 自動実行・スケジューラ関連
│ │ └── utils/
│ │     └── config.py          # 共通環境変数ユーティリティ（get_env など）
│ ├── tests/
│ │ ├── test_notion_client.py  # Notion APIクライアントのユニットテスト
│ │ └── test_notion_router.py  # /notion/ingest APIのテスト
│ └── requirements.txt         # backend依存パッケージ一覧
│
├── frontend/
│ ├── pages/
│ ├── components/
│ └── api/
│
├── docs/
│ ├── 00_overview.md
│ ├── 01_requirements.md
│ ├── 02_phase_plan.md
│ ├── 03_directory_structure.md
│ ├── 04_api_design.md
│ ├── 05_ai_judgement_rules.md
│ ├── 06_octobot_signal_flow.md
│ ├── 07_aave_operation_logic.md
│ ├── 08_automation_rules.md
│ └── 09_notion_schema.md
│
├── scripts/
│ ├── backup.sh
│ ├── monitor.sh
│ └── zip_next_phase.sh
│
└── README.md
