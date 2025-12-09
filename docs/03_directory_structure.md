# 03_directory_structure.md
# ディレクトリ構成

Ultra AutoTrade プロジェクト全体のディレクトリ構成と、  
各ディレクトリ／ファイルの役割をまとめる。

---

project root/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI エントリーポイント（create_app, ルータマウント）
│   │   ├── ai/                     # AI解析ロジック（Phase2 以降）
│   │   │   ├── __init__.py         # AI モジュールパッケージマーカー
│   │   │   ├── schemas.py          # AIAnalysisRequest/Response, AIAnalysisResult, TradeAction など
│   │   │   ├── service.py          # ニュース文から BUY/SELL/HOLD を決定するサービス層
│   │   │   └── router.py           # POST /ai/analyze エンドポイント
│   │   ├── notion/                 # Notion 連携モジュール（Phase1）
│   │   │   ├── __init__.py         # Notion 連携パッケージマーカー
│   │   │   ├── config.py           # Notion API 設定（環境変数読み取り）
│   │   │   ├── client.py           # Notion API クライアント（HTTP 通信）
│   │   │   ├── service.py          # Notion レコード取得・内部モデル変換サービス層
│   │   │   ├── schemas.py          # NotionNewsItem / NotionIngestResponse スキーマ
│   │   │   └── router.py           # POST /notion/ingest エンドポイント定義
│   │   ├── bots/                   # OctoBot 連携モジュール（Phase3）
│   │   │   ├── __init__.py         # パッケージマーカー
│   │   │   ├── config.py           # OctoBot API のエンドポイント/キー/タイムアウト設定
│   │   │   ├── schemas.py          # /octobot/signal 用の Request/Response スキーマ
│   │   │   ├── client.py           # OctoBot 外部シグナル API クライアント
│   │   │   ├── service.py          # AIAnalysisResult → シグナル生成・送信ロジック
│   │   │   └── router.py           # POST /octobot/signal エンドポイント
│   │   ├── aave/                   # Aave 運用ロジック（別フェーズで実装）
│   │   │   ├── __init__.py         # Aave パッケージマーカー
│   │   │   ├── config.py           # Aave 設定（環境変数ラッパー、最大ポジション/クールダウンなど）
│   │   │   ├── client.py           # Aave クライアント（DummyAaveClient など）
│   │   │   ├── service.py          # TradeAction → AaveOperation 変換サービス層
│   │   │   ├── schemas.py          # AaveRebalanceRequest/Response, AaveOperationResult など
│   │   │   ├── router.py           # /aave/rebalance エンドポイント定義
│   │   ├── automation/             # 自動実行・スケジューラ関連（将来拡張）
│   │   └── utils/
│   │       ├── __init__.py         # 共通ユーティリティパッケージマーカー
│   │       └── config.py           # /aave/rebalance エンドポイント定義
│   ├── tests/
│   │   ├── conftest.py             # テスト共通設定（app インポート・環境変数など）
│   │   ├── test_notion_client.py   # Notion API クライアントのユニットテスト
│   │   ├── test_notion_router.py   # /notion/ingest API のテスト
│   │   ├── test_ai_service.py      # AI 判定ロジック（BUY/SELL/HOLD, 信頼度レンジ）のユニットテスト
│   │   ├── test_ai_router.py       # /ai/analyze API のテスト
│   │   ├── test_octobot_client.py  # OctoBotクライアントのユニットテスト
│   │   ├── test_octobot_service.py # OctoBotサービス（安全弁・レート制限）のテスト
│   │   ├── test_octobot_router.py  # /octobot/signal API のテスト
│   │   ├── test_smoke.py           # バックエンド全体のスモークテスト
│   │   ├── test_aave_service.py    # AaveService のユニットテスト（Dummy/Fake クライアント）
│   │   ├── test_aave_router.py     # /aave/rebalance の API テスト
│   │   ├── test_flow_with_aave_stub.py # AI → OctoBot → Aave 統合テストの雛形（現状 skip）
│   │   └── test_ai_service.py      # ...
│   └── requirements.txt            # backend 依存パッケージ一覧
│
├── frontend/
│   ├── pages/                      # 画面ルーティング（Next.js 等を想定）
│   ├── components/                 # UI コンポーネント
│   └── api/                        # フロントエンド側 API 呼び出しラッパ
│
├── docs/
│   ├── 00_overview.md              # プロジェクト全体概要
│   ├── 01_requirements.md          # 要求仕様・非機能要件
│   ├── 02_phase_plan.md            # フェーズ別開発計画
│   ├── 03_directory_structure.md   # 本ファイル（ディレクトリ構成）
│   ├── 04_api_design.md            # Backend API 設計 (/notion/ingest, /ai/analyze, /octobot/signal, /aave/...)
│   ├── 05_ai_judgement_rules.md    # AI 判定ルール（BUY/SELL/HOLD 条件 等）
│   ├── 06_octobot_signal_flow.md   # OctoBot 連携フローとシグナル構造
│   ├── 07_aave_operation_logic.md  # Aave 運用ロジック・リスク管理
│   ├── 08_automation_rules.md      # 自動化・監視・アラートルール
│   ├── 09_notion_schema.md         # Notion DB スキーマと内部モデル対応
│   ├── 10_next_phase_prompt_generator.md # 次フェーズ用プロンプト生成ルール
│   ├── 11_prompt_sync_rules.md     # GPT プロンプト同期ルール
│   ├── 12_phase_operations.md      # フェーズ運用ルール・進め方
│   ├── 13_security_design.md       # セキュリティ設計
│   ├── 14_test_strategy.md         # テスト戦略
│   └── 15_rollback_procedures.md   # ロールバック手順
│
├── scripts/
│   ├── backup.sh                   # バックアップスクリプト
│   ├── monitor.sh                  # 死活監視・メトリクス監視スクリプト
│   ├── zip_phase2_seed.sh          # Phase2 用 seed ファイル ZIP 生成
│   └── zip_phase3_seed.sh          # Phase3 用 seed ファイル ZIP 生成
│
└── README.md                       # プロジェクト概要・セットアップ手順
