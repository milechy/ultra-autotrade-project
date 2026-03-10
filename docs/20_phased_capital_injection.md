# 段階的資金投入計画

## 概要

Ultra AutoTradeの本番運用開始にあたり、リスク管理を最優先として段階的に資金を投入する。
各フェーズにはGo/No-Go基準を設け、前フェーズの目標達成後にのみ次フェーズへ移行する。

## フェーズ定義

### Phase 1: マイクロテスト（$50〜$100）
**目的:** 本番APIとの疎通確認・Shadow Modeから実トレードへの移行テスト

| 項目 | 設定値 |
|------|--------|
| 最大1注文 | $50 |
| 1日最大取引額 | $100 |
| 最大取引回数/日 | 5回 |
| 運用期間 | 1〜2週間 |
| EXCHANGE_PHASE | 1 |

**Go/No-Go基準（Phase 1 → Phase 2）:**
- [ ] 連続5日間、システムエラーなし
- [ ] Shadow Mode記録との判定一致率 > 90%
- [ ] 未実現損失が投入資金の20%以内
- [ ] Health Factor（Aave使用時）常時 > 1.8
- [ ] 緊急停止機能の動作確認済み

### Phase 2: 小規模本番運用（$500）
**目的:** 実際の市場での収益性・安定性を確認

| 項目 | 設定値 |
|------|--------|
| 最大1注文 | $100 |
| 1日最大取引額 | $500 |
| 最大取引回数/日 | 10回 |
| 運用期間 | 2〜4週間 |
| EXCHANGE_PHASE | 2 |

**Go/No-Go基準（Phase 2 → Phase 3）:**
- [ ] 2週間以上の安定運用
- [ ] シャープレシオ > 1.0（週次）
- [ ] 最大ドローダウン < 15%
- [ ] AI判定精度（事後評価） > 60%
- [ ] システム稼働率 > 99%（計画外ダウンタイムなし）
- [ ] セキュリティ監査完了

### Phase 3: 本格運用（$1,000〜）
**目的:** スケールアップと利益最大化

| 項目 | 設定値 |
|------|--------|
| 最大1注文 | 総資産の10% |
| 1日最大取引額 | 総資産の30% |
| 最大取引回数/日 | 30回（CLAUDE.md準拠） |
| 運用期間 | 継続 |
| EXCHANGE_PHASE | 3 |

**継続条件:**
- 週次レビューで上記Phase 2基準を継続維持
- 月次セキュリティレビュー実施
- 四半期ごとにAI判定ロジック見直し

## 緊急停止条件（全フェーズ共通）

以下いずれかの場合、即座にトレードを停止する:
- 1日の損失が投入資金の10%超
- Health Factor < 1.6（Aave使用時）
- システムエラー連続3回
- 手動による緊急停止フラグ（上書き不可）

## 設定方法

環境変数 `EXCHANGE_PHASE` でフェーズを指定する:

```bash
# Phase 1
EXCHANGE_PHASE=1
EXCHANGE_MAX_ORDER_USD=50
EXCHANGE_DAILY_TRADE_LIMIT=5

# Phase 2
EXCHANGE_PHASE=2
EXCHANGE_MAX_ORDER_USD=100
EXCHANGE_DAILY_TRADE_LIMIT=10

# Phase 3
EXCHANGE_PHASE=3
# EXCHANGE_MAX_ORDER_USD は総資産の10%として動的計算
EXCHANGE_DAILY_TRADE_LIMIT=30
```

## 参照
- docs/13_security_design.md — セキュリティルール
- docs/17_staging_environment_config.md — 環境別設定
- backend/app/exchange/config.py — 設定値実装
