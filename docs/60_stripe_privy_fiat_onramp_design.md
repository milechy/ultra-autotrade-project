# Stripe x Privy フィアット オンランプ 設計書

**Asana GID:** 1215697731893127
**作成:** 2026-06-15
**ステータス:** Phase A 実装中（設計 + 純粋バリデータ）

---

## 1. 概要

ユーザーがフィアット（法定通貨）を Stripe Crypto Onramp 経由で購入し、
Privy 埋め込みウォレットへ直接着金させるフローを Ultra AutoTrade に統合する設計書。

本書は **Phase A（設計 + 純粋バリデータ、Tier B 自動進行可）** のスコープを扱う。
Stripe API 呼出・webhook signature 検証・着金処理・秘密鍵・API キーの実装は
**フェーズ B（HUMAN-REVIEW-REQUIRED）** 以降で扱う。

---

## 2. 3 段フロー図

```
┌──────────────────────────────────────────────────────────────────┐
│                         フィアット → 暗号資産 オンランプ全体フロー              │
└──────────────────────────────────────────────────────────────────┘

[ユーザー (フィアット)]
      │
      │ 1. オンランプセッション作成リクエスト
      │    (fiat_amount, fiat_currency, target_crypto, destination_wallet_address)
      ▼
[Ultra AutoTrade Backend]
      │
      │ 2. OnrampSessionIntent 検証
      │    (金額・通貨許可リスト・ウォレットアドレス形式)
      │
      │ 3. Stripe Crypto Onramp API でセッション生成  ← [HUMAN-REVIEW フェーズ B]
      │    POST /v1/crypto/onramp_sessions
      │
      ▼
[Stripe Crypto Onramp (ホスト側)]
      │
      │ 4. Privy 埋め込みウォレット UI をユーザーに表示
      │    (フロントエンド埋め込み / SDK)
      │
      │ 5. ユーザーがカード/銀行振込でフィアット決済
      │
      │ 6. Stripe が暗号資産を購入
      │
      ▼
[Privy 埋め込みウォレット]
      │
      │ 7. 暗号資産着金
      │    (OnrampSettlementEvent が発生)
      │
      ▼
[Ultra AutoTrade Backend (webhook 受信)]  ← [HUMAN-REVIEW フェーズ B]
      │
      │ 8. Stripe-Signature HMAC 検証
      │    (X-Webhook-Secret とは別物、詳細は §5 参照)
      │
      │ 9. OnrampSettlementEvent 記録
      │    (status 遷移: pending → settled)
      ▼
[PostgreSQL: onramp_sessions テーブル (フェーズ B で定義)]
```

---

## 3. 既存資産との関係

### 3.1 billing_adapter.py — BillingVendorAdapter / StubBillingAdapter

`backend/app/fees/billing_adapter.py` が定義する `BillingVendorAdapter` プロトコルと
`StubBillingAdapter` は **月次サブスク課金（fee_transactions への記録）** 専用である。

オンランプは「ユーザーが自分のウォレットへフィアットで入金する」フローであり、
**Ultra AutoTrade が課金する月次手数料とは別経路**。両者を混同しないこと。

| 観点 | 月次手数料課金（既存） | フィアット オンランプ（新規） |
|---|---|---|
| 主体 | UATa が Stripe で月次課金 | ユーザーが Stripe Crypto Onramp でフィアット→暗号資産変換 |
| 対象テーブル | `fee_transactions` | `onramp_sessions`（フェーズ B で定義） |
| adapter クラス | `BillingVendorAdapter` / `StubBillingAdapter` | `OnrampProvider`（フェーズ B、別 adapter） |

### 3.2 models.py — vendor_reference_id

`backend/app/fees/models.py:167` の `vendor_reference_id` は `fee_transactions` テーブル向けの
課金ベンダー参照 ID（Stripe charge_id / Paidy payment_id 等）。

`OnrampSettlementEvent.vendor_reference_id` はオンランプセッションの参照 ID として
**同名フィールドを流用するが、テーブルは別**（`onramp_sessions`）。命名の一致は意図的（同一命名規約）。

**【要確認】**: Stripe Crypto Onramp の決済完了 webhook に含まれる参照 ID フィールド名を
Stripe 公式ドキュメントで確認すること（`crypto_onramp_session.id` / `payment_intent.id` 等
複数候補あり）。フェーズ B 実装前に確認が必要。

### 3.3 auth/privy_verifier + auth/schemas — Privy DID / ウォレット紐付け

`backend/app/auth/schemas.py:281` の `WalletConnectRequest` が定義する:

```python
wallet_address: str = Field(..., min_length=42, max_length=42)
```

オンランプの `destination_wallet_address` もこの制約（EVM 0x + 40 hex 文字 = 42 文字）に準拠する。

Privy DID とウォレットの紐付けは `auth/privy_verifier.py` が管理する。
オンランプ着金先ウォレットは当該ユーザーの Privy 埋め込みウォレットアドレスである必要がある。

**【要確認】**: ユーザーが保有する Privy ウォレットアドレスを Backend で取得する API（
`/api/v1/auth/wallet` 等）のエンドポイントパスを実 grep で確認すること。
フェーズ B でのウォレット照合実装前に確認が必要。

### 3.4 webhook/router.py — 既存 X-Webhook-Secret 検証パターン

`backend/app/webhook/router.py:34` の `_verify_webhook_secret` は
**`X-Webhook-Secret` ヘッダー**（固定文字列比較）で内部 webhook を認証している。

Stripe webhook は **`Stripe-Signature` ヘッダーの HMAC-SHA256** で検証する（全く別物）。

```
既存内部 webhook:
  Header: X-Webhook-Secret: <固定文字列>
  検証: timing-safe 文字列比較

Stripe webhook (フェーズ B で実装):
  Header: Stripe-Signature: t=<timestamp>,v1=<HMAC-SHA256署名>
  検証: stripe.WebhookSignature.verify_header() または手動 HMAC-SHA256
```

**[HUMAN-REVIEW-REQUIRED]** Stripe-Signature HMAC 検証の実装は フェーズ B で扱う。
現フェーズでは webhook signature 検証コードを一切含めない。

---

## 4. スキーマ案

### 4.1 OnrampSessionIntent（オンランプ意図）

```
OnrampSessionIntent:
  user_id:                    int         # UATa ユーザー ID
  fiat_amount:                Decimal     # フィアット金額（USD / JPY 等）
  fiat_currency:              str         # ISO 4217 通貨コード（例: "USD", "JPY"）
  target_crypto:              str         # 購入対象暗号資産（例: "ETH", "USDC"）
  destination_wallet_address: str         # 着金先 EVM ウォレットアドレス（0x...42文字）
```

### 4.2 OnrampSettlementEvent（着金イベント）

```
OnrampSettlementEvent:
  intent_id:                  str                 # OnrampSessionIntent の識別子
  status:                     OnrampStatus        # 状態（CREATED/PENDING/SETTLED/FAILED）
  crypto_amount_received:     Optional[Decimal]   # 着金した暗号資産量（SETTLED 時のみ）
  vendor_reference_id:        Optional[str]       # Stripe セッション参照 ID
```

**禁止フィールド**: `stripe_signature`, `webhook_secret`, `api_key` 等の秘密情報は
スキーマに含めない。

---

## 5. 着金イベント 状態遷移図

```
┌─────────┐
│ CREATED │  ─── セッション作成直後の初期状態
└─────────┘
     │
     │ Stripe セッション開始（ユーザーが UI を操作開始）
     ▼
┌─────────┐
│ PENDING │  ─── Stripe 側で処理中（フィアット決済完了待ち / 暗号資産購入中）
└─────────┘
     │
     ├─────────────────────────────┐
     │ 暗号資産着金完了             │ タイムアウト / ユーザーキャンセル / 決済失敗
     ▼                             ▼
┌─────────┐                   ┌────────┐
│ SETTLED │                   │ FAILED │
└─────────┘                   └────────┘
                                    ▲
                                    │
┌─────────┐                         │ 直接失敗（決済試行前エラー等）
│ CREATED │ ────────────────────────┘
└─────────┘
```

### 有効な状態遷移（完全一覧）

| from_status | to_status | 意味 |
|---|---|---|
| CREATED | PENDING | セッション開始 |
| CREATED | FAILED | 即時失敗（検証エラー等） |
| PENDING | SETTLED | 着金完了 |
| PENDING | FAILED | タイムアウト / 失敗 |

### 無効な状態遷移（例）

- `SETTLED → *`（着金完了は終端）
- `FAILED → *`（失敗は終端）
- `PENDING → CREATED`（後退禁止）
- `CREATED → SETTLED`（PENDING をスキップ禁止）

---

## 6. webhook 検証フロー設計

**[HUMAN-REVIEW-REQUIRED]** 以下はフェーズ B の設計概要のみ。現フェーズでは実装しない。

```
Stripe サーバー
  │
  │ POST /api/v1/onramp/webhook
  │ Header: Stripe-Signature: t=<timestamp>,v1=<HMAC-SHA256>
  │ Body: { "type": "crypto_onramp_session.completed", ... }
  ▼
Backend (フェーズ B 実装)
  │
  │ 1. raw body を読み取る（JSON parse 前）
  │ 2. Stripe-Signature ヘッダーをパース (t=..., v1=...)
  │ 3. signed_payload = f"{t}.{raw_body}"
  │ 4. expected = HMAC-SHA256(key=STRIPE_WEBHOOK_SECRET, msg=signed_payload)
  │ 5. timing-safe compare: expected == v1
  │ 6. timestamp replay attack 防止: |now - t| < 300 秒
  │
  │ 7. 検証成功 → OnrampSettlementEvent 構築 → 状態遷移バリデーション
  │ 8. DB 更新 (PENDING → SETTLED / FAILED)
  ▼
PostgreSQL: onramp_sessions (フェーズ B で定義)
```

**注意**: `STRIPE_WEBHOOK_SECRET` は環境変数でのみ管理。コードに直接記載禁止
（Security Rules Rule 1 準拠）。

---

## 7. 決済上限 / KYC ポリシー方針

### 7.1 現時点の方針（暫定値）

| 項目 | 値 | 状態 |
|---|---|---|
| 最小オンランプ額 | USD 10.00 | **暫定値（【要確認】）** |
| 最大オンランプ額 | USD 10,000.00 | **暫定値（【要確認】）** |
| 対応フィアット通貨 | USD, EUR, JPY | **暫定値（【要確認】）** |
| 対応暗号資産 | ETH, USDC | **暫定値（【要確認】）** |
| 上限超過時の扱い | バリデーションエラー返却（onramp セッション作成不可） | 方針確定済 |

### 7.2 KYC ポリシー

Stripe Crypto Onramp は Stripe 側で KYC を処理する。
Ultra AutoTrade Backend 側での KYC 実装は不要（Stripe への委任）。

**【要確認】**: 日本居住者向けの Stripe Crypto Onramp 提供可否（リージョン制限）。
日本向けが不可の場合はオンランプ対象ユーザーの制限が必要。

---

## 8. 【要確認】列挙（実装前に必ず確認する項目）

以下は **推測で確定禁止**。フェーズ B 開始前に Stripe 公式ドキュメント / Stripe ダッシュボードで確認すること。

| 番号 | 確認事項 | 確認ソース |
|---|---|---|
| Q1 | Stripe Crypto Onramp API の提供状況（日本リージョン含む） | Stripe ダッシュボード / docs.stripe.com |
| Q2 | 対応フィアット通貨の確定リスト（USD/EUR/JPY 等） | Stripe Crypto Onramp ドキュメント |
| Q3 | 対応暗号資産の確定リスト（ETH/USDC/その他） | Stripe Crypto Onramp ドキュメント |
| Q4 | 着金経路（Stripe が直接ウォレットへ送金か、中間ブリッジ経由か） | Stripe ドキュメント / Privy 統合ガイド |
| Q5 | webhook イベント名と payload 構造（`crypto_onramp_session.completed` 等） | Stripe webhook ドキュメント |
| Q6 | `Stripe-Signature` HMAC 仕様（`t=` / `v1=` フォーマット確認） | Stripe webhook 署名ドキュメント |
| Q7 | KYC 要件と上限金額の規制（Stripe 利用規約 + 日本法令） | Stripe 利用規約 / 金融庁ガイドライン |
| Q8 | 最小オンランプ額の確定値（Stripe 規定最小値） | Stripe Crypto Onramp ドキュメント |
| Q9 | 最大オンランプ額の確定値（KYC 閾値 / Stripe 上限） | Stripe Crypto Onramp ドキュメント |
| Q10 | Privy ウォレットアドレス取得 API パス（Backend での照合用） | 実コード grep（`/api/v1/auth/wallet` 等） |
| Q11 | vendor_reference_id に相当する Stripe 参照 ID フィールド名 | Stripe webhook payload 確認 |

---

## 9. 段階実装計画

### Phase A: 設計 + 純粋バリデータ（本スライス、Tier B 自動進行可）

**スコープ:**
- `docs/60_stripe_privy_fiat_onramp_design.md`（本書）
- `backend/app/fees/onramp/schemas.py`（OnrampStatus / OnrampSessionIntent / OnrampSettlementEvent）
- `backend/app/fees/onramp/validators.py`（金額 / 通貨 / 状態遷移 / ウォレットアドレス 純粋バリデータ）
- `backend/tests/fees/onramp/`（pytest 単体テスト）

**含まない（フェーズ B 以降）:**
- Stripe SDK import
- Stripe API 呼出
- webhook signature 検証（HMAC）
- APIキー・秘密鍵の参照
- router / main.py への配線
- DB マイグレーション

### Phase B: Stripe SDK + webhook signature 検証 + 着金処理（HUMAN-REVIEW-REQUIRED）

**スコープ:**
- `backend/requirements.txt` への `stripe` 追加
- `backend/app/fees/onramp/stripe_provider.py`（Stripe Crypto Onramp API クライアント）
- `backend/app/fees/onramp/webhook_handler.py`（Stripe-Signature HMAC 検証 + 状態遷移処理）
- DB スキーマ（`onramp_sessions` テーブル）
- Alembic マイグレーション

### Phase C: main.py 配線 + フロント（HUMAN-REVIEW-REQUIRED）

**スコープ:**
- `backend/app/api/routes/onramp.py`（router 定義）
- `backend/app/main.py` への `include_router` 追加
- フロントエンド（オンランプ UI コンポーネント）

---

## 10. セキュリティ考慮事項

- `STRIPE_WEBHOOK_SECRET` は環境変数でのみ管理（Security Rules Rule 1）
- フィアット金額の計算は `Decimal` 型のみ（float 禁止、Security Rules Rule 11）
- API レスポンスの `Decimal` は文字列で返却（JSON シリアライズ）
- webhook endpoint は Stripe-Signature 検証通過後のみ処理（フェーズ B）
- `destination_wallet_address` はユーザーの Privy ウォレットと照合すること（フェーズ B）

---

*Asana GID: 1215697731893127*
