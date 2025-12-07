# 04_api_design.md
# API設計書

## API一覧

### 1. /notion/ingest
NotionからURLを取得し、解析キューへ送る。

### 2. /ai/analyze
ニュースを解析し、判定を返す。

### 3. /octobot/signal
AIの判定をOctoBotに送る。

### 4. /aave/rebalance
BUY/SELL/HOLDに応じて資産操作。

### 5. /report/daily
日次レポート生成。

## データ形式（例）

# 04_api_design.md
# API設計書

## API一覧

### 1. /notion/ingest
NotionからURLを取得し、解析キューへ送る。

### 2. /ai/analyze
ニュースを解析し、判定を返す。

### 3. /octobot/signal
AIの判定をOctoBotに送る。

### 4. /aave/rebalance
BUY/SELL/HOLDに応じて資産操作。

### 5. /report/daily
日次レポート生成。

## データ形式（例）

{
"url": "",
"summary": "",
"sentiment": "",
"action": "BUY",
"confidence": 78
}