# 39_mmt_integration_guide.md
# MMT Market Data API 統合ガイド

## 1. MMT 概要

- **mmt.gg**: 20以上の取引所から統合された暗号通貨マーケットデータ API
- **プロトコル**: REST + WebSocket
- **認証**: `X-API-Key` ヘッダー
- **Base URL**: `https://eu-central-1.mmt.gg/api/v1`
- **シンボル形式**: 統一形式（例: `btc/usd`、`eth/usd`）

---

## 2. Ultra AutoTrade で使用するエンドポイント

### Phase 1 統合（今回実装）

| エンドポイント | 用途                              | デフォルト更新間隔 | コスト |
|--------------|-----------------------------------|-----------------|--------|
| `/stats`     | Funding Rate、bid/ask 板厚       | 30分            | 1x     |
| `/oi`        | Open Interest 推移                | 30分            | 1x     |
| `/candles`   | BTC/ETH OHLCV（1h 足、直近 24h） | 30分            | 1x     |

**取得シンボル**: `btc/usd`、`eth/usd`（デフォルト）
**取得取引所**: `binancef`（デフォルト。無期限先物）

### Phase 2 統合（将来）

| エンドポイント | 用途                              | コスト |
|--------------|-----------------------------------|--------|
| `/vd`        | Volume Delta（大口注文検知）       | 1x     |
| `/heatmap_sd`| Liquidation Heatmap               | 5x     |
| WebSocket    | リアルタイムストリーム（<1秒遅延） | -      |

---

## 3. AI 判定への統合ポイント

### データフロー

```
mmt.gg REST API
    ↓ (30分間隔 background loop)
mmt_feed.py — _cached_mmt: Optional[MMTData]
    ↓ get_cached_mmt_data()
data_feeds/context.py — MarketContext.mmt_data
    ↓ to_prompt_context()
LLM プロンプト（ai/service.py: judge_with_rag）
```

### LLM に渡す情報（to_prompt_section）

```
## MMT Market Data
- btc/usd Funding Rate: 0.000125 (ロング過多)
- eth/usd Funding Rate: -0.000050 (ショート過多)
- btc/usd OI: $12,500,000,000, 変化率: +3.20%
- eth/usd OI: $5,200,000,000, 変化率: -1.50%
```

**Funding Rate の読み方:**
- 正値: ロング過多 → 反転リスク高（過熱シグナル）
- 負値: ショート過多 → 上昇圧力（売られ過ぎシグナル）
- ゼロ付近: 中立

**OI 変化率の読み方:**
- 急増（+5%〜）: レバレッジ拡大 → ボラティリティ上昇リスク
- 急減（-5%〜）: 決済集中 → トレンド転換シグナル

---

## 4. 環境変数設定

| 変数名                | デフォルト値 | 説明                                           |
|--------------------|------------|------------------------------------------------|
| `MMT_API_KEY`      | `""`       | mmt.gg APIキー。空の場合はフィード無効           |
| `MMT_API_ENABLED`  | `false`    | `true` に設定するとフィード有効化                |
| `MMT_UPDATE_INTERVAL` | `1800`  | 更新間隔（秒）。デフォルト 30分                 |

### `.env.staging` への追加例

```bash
MMT_API_KEY=your_api_key_here
MMT_API_ENABLED=true
MMT_UPDATE_INTERVAL=1800
```

---

## 5. フォールバック設計（fail-open）

| 障害シナリオ              | 挙動                                           |
|--------------------------|------------------------------------------------|
| `MMT_API_ENABLED=false`  | ループ未起動、`mmt_data=None`                   |
| `MMT_API_KEY` 未設定     | `fetch_mmt_data()` が `None` を返す             |
| API 一時障害             | 旧キャッシュを保持、次のループで再試行           |
| シンボル個別エラー        | `logger.warning` のみ、他シンボルは継続         |
| `to_prompt_context()` 内 | `mmt_data is None` でセクションをスキップ        |

**既存フィード（ccxt / Perplexity / GDELT）への影響: ゼロ**

---

## 6. コスト見積もり

- Free Tier: mmt.gg/pricing を参照（要確認）
- **1日あたりリクエスト数**:
  - 30分間隔 × 3エンドポイント × 2シンボル = **288 requests/day**
- **Rate Limit**: Weight-based（tier 依存）
- Phase 1 は軽量エンドポイントのみ（weight 1x）

---

## 7. 実装ファイル一覧

| ファイル                                     | 変更種別  | 内容                             |
|--------------------------------------------|---------|----------------------------------|
| `backend/app/data_feeds/mmt_feed.py`       | 新規作成  | フィード実装（キャッシュ + ループ）|
| `backend/app/data_feeds/context.py`        | 追記     | MarketContext に mmt_data 追加   |
| `backend/app/main.py`                      | 追記     | startup_data_feeds にループ追加  |
| `backend/tests/test_mmt_feed.py`           | 新規作成  | 16テストケース                   |
| `docs/39_mmt_integration_guide.md`         | 新規作成  | 本ドキュメント                    |

---

## 8. 有効化手順（APIキー取得後）

```bash
# 1. .env.staging に追記
printf '\nMMT_API_KEY=your_key_here\nMMT_API_ENABLED=true\n' >> /opt/ultra-autotrade/.env.staging

# 2. バックエンドを再起動（フロントエンド再ビルド不要）
cd /opt/ultra-autotrade
./scripts/deploy_staging.sh --backend-only

# 3. 起動確認
docker logs ultra-autotrade-backend 2>&1 | grep -i "mmt"
# → "MMT data feed started (interval: 1800s)"
# → "MMT data updated: 2 stats, 2 OI records, 2 candle sets"
```
