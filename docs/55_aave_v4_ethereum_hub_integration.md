# 55_aave_v4_ethereum_hub_integration.md
# Aave V4 Ethereum Hub 統合レイヤー選定書 (EPIC-7 7-1b)

作成日: 2026-06-15
ブランチ: feat/aave-v4-ethereum-hub-scaffold
親設計書: docs/54_aave_v4_migration_design.md (EPIC-7 7-1) — 本書は同書の差分のみを記述する

> **親設計書との関係 (必読)**: docs/54 は全体移行設計 (env フラグ / chains.py 拡張 / ABI 差分 /
> リスク一覧 / rollback) を定義する正本。本書 (docs/55) は **統合レイヤー選定 (A/B/C 三択) と
> `backend/app/aave_v4/` scaffold の実装詳細** のみを扱う。docs/54 の記述と重複する場合は
> 本書での再記述を避け、docs/54 を参照すること。

> **Status: Phase 0 scaffold 実装済み / 統合レイヤー未確定 (HUMAN-REVIEW 待ち)**
> `backend/app/aave_v4/` は新規モジュール（既存 `backend/app/aave/` V3 は無改変）。
> 依存追加・tx 送信・main.py 配線は HUMAN-REVIEW 要承認 (§4, §5)。

---

## 0. Summary (本書スコープ)

| 項目 | 内容 |
|---|---|
| 本書スコープ | `@aave/client` 等の統合レイヤー採用可否 + Ethereum Hub 統合層選定 |
| 実装状態 | Phase 0 scaffold: read-only スタブのみ (`aave_v4/client.py` / `aave_v4/schemas.py`) |
| 決定事項 | モジュール配置 = `backend/app/aave_v4/`、V3 との共存方針 (§6 参照) |
| 未決定事項 | 統合レイヤー三択 (§3)、SDK 依存追加 (§4)、Hub アドレス確定後の実装 (§5 Phase 2-4) |
| 親設計書 | docs/54 §3.1 (AAVE_PROTOCOL_VERSION フラグ) / §3.2 (chains.py V4 アドレス登録) / §4 (ABI 差分吸収) |

docs/54 と本書の分担:

```
docs/54: 全体移行設計 (env フラグ / chains.py 拡張 / ABI 吸収 / rollback)
  └─ docs/55 (本書): 統合レイヤー選定 + aave_v4/ scaffold 実装詳細
```

---

## 1. 統合層の言語判定

### 1.1 現状の backend 実装

Ultra AutoTrade の backend は **Python 3.11 / FastAPI / web3.py** ベースで実装されている。
既存 V3 クライアントの実パス: `backend/app/aave/client.py`

重要な実装事実 (grep 済み実値):

- `AaveClientBase(ABC)` — L244: `get_health_factor(wallet_address: str) -> Decimal`
- `AaveClientBase(ABC)` — L303: `get_account_data(wallet_address: str) -> AccountData`
- `AaveClientBase(ABC)` — L305: `get_pool_utilization(asset_symbol: str) -> Optional[Decimal]`
- `AccountData` — L235: dataclass、全フィールド Decimal 型
- `make_aave_client()` — L1274: factory 関数 (V4 版フラグ分岐の主入口、docs/54 §3.1)
- web3.py の `encode_abi()` — L1130-1131: web3.py v7 API (v6 との API drift に注意、CLAUDE.md ドリフトカタログ)

### 1.2 `@aave/client` の言語・対応状況

【要確認】以下は 2026-06 時点の調査記録であり、実装前に再確認すること:

| 確認項目 | 状況 | 確認方法 |
|---|---|---|
| 正式パッケージ名 | 【要確認】`@aave/protocol-js` か `@aave/client` か不明 | `npm info @aave/client` / Aave GitHub 検索 |
| 言語 | 【要確認】JS/TS の可能性大 (Aave 公式 SDK は JS/TS が主流) | npm / GitHub 確認 |
| Python バインディング | 【要確認】公式 Python SDK は確認できず | PyPI `aave` パッケージ調査 |
| 対応チェーン | 【要確認】Ethereum mainnet のみか Base も対象か | SDK ドキュメント確認 |
| Hub read API 範囲 | 【要確認】`getUserAccountData` 相当の提供可否 | SDK ドキュメント確認 |
| V4 対応状況 | 【要確認】V4 Hub/Spoke のメソッドを提供するか | SDK ドキュメント / Changelog 確認 |

> 上記確認を行わずに「`@aave/client` を採用する」と結論を出してはならない。
> 確認は docs/54 §2.4 の UNVERIFIED 解消と並行して行うこと。

---

## 2. モジュール配置案

### 2.1 採用案: `backend/app/aave_v4/` 新規モジュール (現行)

```
backend/app/
├── aave/              ← V3 クライアント (無改変)
│   ├── client.py      ← AaveClientBase / Web3AaveClient / DummyAaveClient
│   ├── chains.py      ← CHAIN_REGISTRY (V4 アドレス追加は docs/54 §3.2 参照)
│   └── ...
└── aave_v4/           ← V4 統合レイヤー (本 scaffold で新規作成)
    ├── __init__.py    ← パッケージ exports
    ├── schemas.py     ← AaveV4HubConfig / V4AccountData (Decimal 型)
    └── client.py      ← AaveV4ClientBase / AaveV4EthereumHubClient / DummyAaveV4Client
```

**利点**:
- 既存 V3 (`aave/`) を一切改変しない → 回帰リスクゼロ
- `AaveClientBase` 継承で service 層の型注釈を変更不要
- `AAVE_PROTOCOL_VERSION` フラグで即時 V3 復帰可能 (docs/54 §3.1)
- テスト (`tests/aave/test_aave_v4_client_stub.py`) が V3 との独立性を検証

**制約**:
- `make_aave_client()` への V4 分岐追加は Phase 4 (HUMAN-REVIEW 必須)
- 独自 `aave_v4/` パッケージが将来 `aave/` と乖離するリスク (§6 共存戦略で管理)

### 2.2 代替案

| 案 | 概要 | pros | cons |
|---|---|---|---|
| A. V3 `client.py` に直接追加 | `Web3AaveClient` に V4 分岐を追加 | ファイル数増加なし | 既存テスト全件がリグレッション対象。Tier S ファイル改変 (HUMAN-REVIEW) |
| B. `protocols/aave_v4.py` として追加 | Phase 2 PoC (`protocols/lido.py` に倣う) | protocols 層の一貫性 | Aave は BaseProtocolClient 系列と別系統 (docs/54 §1.5)。二重継承の複雑化 |

---

## 3. 統合層三択比較表

> **本節は選択肢の整理のみ。確定は人間承認 (HUMAN-REVIEW) による。**
> docs/54 §2.4 の UNVERIFIED 項目が解消するまで選択肢は絞り込まない。

### (A) backend web3.py 直叩き (docs/54 §3-§4 路線)

| 項目 | 内容 |
|---|---|
| 概要 | 既存 V3 と同様に web3.py + ABI で V4 Hub/Spoke を直叩き |
| 追加依存 | なし (web3.py は既存) |
| 既存安全装置整合 | HF < 1.6 HARD_STOP / cooldown / Decimal: **全て既存実装をそのまま利用可能** |
| 実装コスト | V4 ABI 定義 + Hub/Spoke アドレス + encode_abi 書き換え |
| リスク | ABI UNVERIFIED (docs/54 §2.4) / web3.py v7 API drift (CLAUDE.md ドリフトカタログ) |
| 採用条件 | V4 Spoke ABI が公開後、web3.py で動作検証済みのこと |

### (B) `@aave/client` (JS/TS) を frontend 統合層として使用

| 項目 | 内容 |
|---|---|
| 概要 | Next.js frontend で `@aave/client` を呼び出し、backend は read API を呼ぶ |
| 追加依存 | **frontend に npm パッケージ追加 (Tier S: package.json / HUMAN-REVIEW 必須)** |
| 既存安全装置整合 | HF < 1.6 HARD_STOP は backend 側にある → frontend 経由 tx は安全装置をバイパスするリスク |
| 実装コスト | JS SDK 学習 + frontend/backend 間のデータ変換レイヤー |
| リスク | 安全装置の backend 側配置が保てるか要設計 / SDK 言語が UNVERIFIED (§1.2) |
| 採用条件 | SDK 言語・V4 対応の公式確認 + 安全装置配置の設計承認 |

### (C) Node.js サイドカー

| 項目 | 内容 |
|---|---|
| 概要 | Node.js プロセスで `@aave/client` を動かし、backend (Python) から gRPC/REST で呼ぶ |
| 追加依存 | Node.js コンテナ追加 (docker-compose.* 変更 / Tier S / HUMAN-REVIEW) + npm パッケージ |
| 既存安全装置整合 | サイドカー呼び出しは RPC 増加 → latency / SLA リスク |
| 実装コスト | 最大 (コンテナ + インターフェース + 運用) |
| リスク | インフラ複雑度増加 / docker-compose Tier S 変更 |
| 採用条件 | (A) / (B) が技術的に不可な場合の最終手段 |

**現時点の暫定方針**: docs/54 §2.4 の UNVERIFIED が解消し V4 Spoke ABI が取得できれば **(A) が最小変更**。
選定確定は HUMAN-REVIEW 後。

---

## 4. 依存追加リスト案 (Phase 1 以降 / HUMAN-REVIEW 必須)

> **本 Phase 0 scaffold では依存を一切追加しない。**
> `backend/requirements.txt` および `frontend/package.json` は Tier S ファイルであり、
> HUMAN-REVIEW 承認なく変更してはならない (CLAUDE.md Tier 分類)。

| 案 | パッケージ | 追加先 | Tier | HUMAN-REVIEW |
|---|---|---|---|---|
| (A) web3.py 直叩き | 不要 (web3 は既存) | — | — | 不要 |
| (B) @aave/client (JS) | 【要確認】`@aave/client` or `@aave/protocol-js` | `frontend/package.json` | **S** | **必須** |
| (C) Node サイドカー | 【要確認】SDK 名 | Node.js Dockerfile / compose | **S** | **必須** |

---

## 5. 段階実装計画

| フェーズ | 作業 | 承認要否 | 状態 |
|---|---|---|---|
| **Phase 0** (本スライス) | `backend/app/aave_v4/` scaffold、read-only スタブ、pytest | 不要 | **完了** |
| **Phase 1** | 統合レイヤー三択 確定 + 依存追加 (Tier S) | **HUMAN-REVIEW 必須** | 未着手 |
| **Phase 2** | read API 実装 (HF / account data / pool utilization) | HUMAN-REVIEW 推奨 | 未着手 |
| **Phase 3** | write/tx 実装 (supply / withdraw / approve) | **HUMAN-REVIEW 必須** | 未着手 |
| **Phase 4** | `main.py` 配線 + `make_aave_client()` V4 分岐 | **HUMAN-REVIEW 必須** | 未着手 |

Phase 1 着手前提条件:
- docs/54 §2.4 の UNVERIFIED (V4 Hub/Spoke ABI) が解消していること
- Base 上 V4 デプロイアドレスが Aave 公式アドレス帳に掲載されていること (`@aave/client` §1.2 確認含む)

Phase 3 着手前提条件:
- Phase 2 staging soak (Shadow Mode) で HF 取得が安定していること
- docs/54 §5 リスク一覧の HF 互換性検証 (Phase 2 での実測) が完了していること

---

## 6. 既存 V3 との共存戦略

### 6.1 原則

- `backend/app/aave/` (V3) は **本 Phase 0 で一切改変しない**
- `backend/app/aave_v4/` は新規パッケージとして独立
- V4 への切替は `AAVE_PROTOCOL_VERSION=v4` env フラグのみで制御 (docs/54 §3.1)
- rollback は `.env.production` / `.env.staging` で `v3` に戻してコンテナ再起動 (数分以内)

### 6.2 分岐方針 (Phase 4 以降)

```
make_aave_client()               ← backend/app/aave/client.py L1274 (Tier S / HUMAN-REVIEW)
  └─ AAVE_PROTOCOL_VERSION
       ├─ "v3" → Web3AaveClient  (現行 / 無改変)
       └─ "v4" → AaveV4EthereumHubClient  (Phase 2 実装後)
```

呼出側 (`service.py` / `rebalance_service.py`) は `AaveClientBase` を型注釈とするため、
V4 実装クラスに差し替えても **service 層の変更は不要** (OCP 準拠)。

### 6.3 本スライスで触ったファイル / 触らなかったファイル

| ファイル | 状態 | 理由 |
|---|---|---|
| `backend/app/aave_v4/__init__.py` | **新規作成** | 本スライスの対象 |
| `backend/app/aave_v4/schemas.py` | **新規作成** | 本スライスの対象 |
| `backend/app/aave_v4/client.py` | **新規作成** | 本スライスの対象 |
| `backend/tests/aave/test_aave_v4_client_stub.py` | **新規作成** | 本スライスの対象 |
| `backend/app/aave/client.py` | **無改変** | HUMAN-REVIEW スライス外 |
| `backend/app/main.py` | **無改変** | HUMAN-REVIEW スライス / Phase 4 |
| `backend/requirements.txt` | **無改変** | Tier S / Phase 1 承認後 |
| `frontend/package.json` | **無改変** | Tier S / Phase 1 承認後 |
| `docs/54_aave_v4_migration_design.md` | **無改変** | 親設計書 / 本書が差分参照 |
