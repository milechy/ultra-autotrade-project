# P2-B1: Pendle Finance Base Mainnet 対応状況調査

調査日: 2026-04-26
担当: 小林 浩紀
Asana: 1214121321788692

---

## TL;DR

Pendle Finance は Base Mainnet (Chain ID 8453) に正式デプロイ済み。Router V4・Market Factory V5/V6 を含むコアコントラクト一式が稼働しており、PT-cbETH など Base ネイティブ資産のマーケットが存在する。PT トークンは Aave V3 への担保化が **Ethereum Mainnet では** 2025年4月に承認・実施済みだが、**Base の Aave V3 への PT 担保化は未実施**。Pendle 全体の TVL は 2025年9月に $13B でピークアウトし、2025年末以降は下落傾向。UATa への統合は技術的には可能だが、満期管理コスト・Base TVL の薄さ・Aave V3 Base 未対応の3点が課題。

---

## 1. Pendle Finance Base Mainnet 対応状況

### 1.1 デプロイ確認

Pendle V2 は Base Mainnet (Chain ID: 8453) に正式デプロイ済み。対応チェーン: Ethereum, Arbitrum, BNB Chain, Optimism, Mantle, Base, Sonic, HyperEVM, Berachain。

### 1.2 Base コントラクトアドレス (8453-core.json より)

| コントラクト | アドレス |
|---|---|
| Router V4 | `0x888888888889758F76e7103c6CbF23ABbF58F946` |
| Router Static | `0xB4205a645c7e920BD8504181B1D7f2c5C955C3e7` |
| Proxy Admin | `0xA28c08f165116587D4F3E708743B4dEe155c5E64` |
| Yield Contract Factory V5 | `0x963ddBB35c1AE44e2a159E3b5fb5177E0B32660d` |
| Market Factory V5 | `0x59968008a703dC13E6beaECed644bdCe4ee45d13` |
| Yield Contract Factory V6 | `0xdDBfA21ecf024971486684E4E1600998ADeabc88` |
| Market Factory V6 | `0x81E80A50E56d10C501fF17B5Fe2F662bd9EA4590` |
| SY Factory | `0x466CeD3b33045Ea986B2f306C8D0aA8067961CF8` |
| PT/YT/LP Oracle | `0x5542be50420E88dd7D5B4a3D488FA6ED82F6DAc2` |
| Chainlink Oracle Factory | `0x6502cda86f9110f3655512237C9FF2B9CE247c69` |
| Pendle Swap | `0xd4F480965D2347d421F1bEC7F545682E5Ec2151D` |
| Gauge Controller | `0x17F100fB4bE2707675c6439468d38249DD993d58` |

ソース: [pendle-core-v2-public/deployments/8453-core.json](https://github.com/pendle-finance/pendle-core-v2-public/blob/main/deployments/8453-core.json)

### 1.3 確認済みマーケット (Base)

| マーケット | 満期 | マーケットアドレス |
|---|---|---|
| PT-cbETH | 2025-12-24 | `0x483f2e223c58a5ef19c4b32fbc6de57709749cb3` |
| PT-sUSDz | 調査中 | - |

- cbETH (Coinbase Wrapped Staked ETH) が Base のメイン LSD として活用されている
- sUSDz (RWA-backed stablecoin) もリスト済み
- 他マーケット（weETH, cbBTC等）は公式アプリで確認要（JS アプリのためクロール不可）

---

## 2. PT / YT トークン設計

### 2.1 基本メカニズム

Pendle は利回り付き資産 (Yield-Bearing Token) を3層に分解する:

```
Yield-Bearing Token (例: cbETH)
    ↓ wrap
SY Token (Standardized Yield) — 利回りロジックの標準化レイヤー
    ↓ split
PT (Principal Token)  +  YT (Yield Token)
```

| トークン | 性質 | 利益源泉 |
|---|---|---|
| PT | 元本トークン。満期に1:1で元資産に交換可能 | 購入時のディスカウント → 固定利回り |
| YT | 利回りトークン。満期まで元資産の利回りを全額受け取る | 変動利回りの最大化 |

### 2.2 満期管理

- PT は満期日に元資産 1:1 で償還される（redeem）
- 満期後も未 redeem の PT は価値を失わないが、利回り生成は停止
- 満期毎に新マーケットを作成する必要がある（例: PT-cbETH Dec 2025 → 新たに Mar 2026 を作成）
- **UATa 視点**: ポジション管理ロジックに「満期 N日前アラート」「自動 redeem or rollover」が必要

### 2.3 プレミアム/ディスカウント形成

PT の価格 = 元資産価格 × (1 - implied yield × 残存日数/365)

- implied yield が高い（市場が将来利回り上昇を予想）→ PT は割安
- implied yield が低い → PT は割高（固定利回りの魅力が薄れる）
- AMM は Pendle 独自の式で PT/SY の交換レートを決定（通常の Uniswap とは異なる）

### 2.4 Aave V3 担保化 (Ethereum Mainnet のみ)

2025年4月11日、Aave DAO ARFC スナップショット可決（446.5K 票、賛成多数）。

| パラメータ | 内容 |
|---|---|
| 対象 | PT-sUSDe (Jul 2025), その後複数満期に拡張 |
| LTV/LT | 元資産（sUSDe）のパラメータに準拠 |
| オラクル | 動的線形割引率モデル (linearly increasing lower bound) |
| 借入 | 禁止（レバレッジループ防止） |
| ガバナンス調整 | 2日ごとに最大 50bps の LTV 変更を steward が実行可能 |

**重要**: 上記は **Ethereum Mainnet の Aave V3 Core Instance** のみ。  
Base の Aave V3 への PT 担保化提案は 2026-04-26 時点で未確認。

---

## 3. UATa 統合影響評価

### 3.1 想定 APY (PT 固定利回り)

Pendle の PT 固定利回り実績:
- PT-sUSDe: 平均 8.8% (stablecoin 系)
- PT-USDe: 同等水準
- PT-cbETH: cbETH の staking APY (~3-4%) × 時価・期間依存のディスカウント → **実質 3-6% 程度の固定 ETH 建て利回り**

stablecoin 系 PT の方が APY が高い傾向（Ethena 等の高利回り資産が基盤）。LST 系（cbETH）は比較的低め。

### 3.2 流動性 (TVL)

| 指標 | 値 | 時期 |
|---|---|---|
| Pendle 全体 TVL ピーク | ~$13B | 2025年9月 |
| Pendle 全体 TVL (2025年末〜) | $3.7B〜 (下落傾向) | 2025年末〜2026年初 |
| Base チェーン TVL | 詳細不明 (全体の数%と推定) | 2026年4月時点 |
| Pendle 総プール数 | 240+ | 2026年初 |
| 平均プール APY | 6.31% | 2026年初 |

Base チェーンは Ethereum・Arbitrum に比べて TVL が薄い点に注意。

### 3.3 リスク評価

| リスク | 内容 | 評価 |
|---|---|---|
| 満期管理 | 各満期毎にポジション管理が必要。自動 rollover ロジック必須 | 高 |
| 流動性 | Base の Pendle 流動性はメインチェーンより薄い。大口エントリーでスリッページ増 | 中〜高 |
| PT 価格変動 | 金利環境変化で implied yield が変動 → PT 時価評価の変動 | 中 |
| Aave V3 未対応 | Base の Aave V3 で PT を担保利用不可（Ethereum のみ対応） | 中（戦略制約） |
| スマートコントラクト | SY → PT/YT の分解ロジック + Pendle AMM の複合リスク | 中 |
| TVL 下落トレンド | 2025年末以降 TVL 減少傾向。流動性の持続性に懸念 | 中 |
| プロトコル持続性 | 2026年のフォーカスは Boros (perpetual yield) + Citadel (機関投資家) 向け | 低〜中 |

---

## 4. 統合判断 (Pros/Cons)

### Pros

1. **固定利回りの確保**: PT は購入時に利回りが確定。AI 判断でのリスク管理がシンプルになる
2. **Base 対応済み**: Router・Factory は Base に完全デプロイ。即時インテグレーション可能
3. **コンポーザビリティ**: SY ラッパーにより cbETH など Base ネイティブ LST を統一インターフェースで扱える
4. **Aave との相性（Ethereum）**: Ethereum では PT が Aave V3 担保として承認済み。将来的な Base 対応の可能性あり
5. **多様な満期**: 3ヶ月〜1年の固定利回りポジションが選択可能

### Cons

1. **満期管理の複雑性**: 各満期のロールオーバーに実装コストが高い（rollover scheduler 必須）
2. **Base TVL が薄い**: 大口ポジションでスリッページリスク。流動性に上限あり
3. **Aave V3 Base 未連携**: UATa の戦略（Aave 担保 → Pendle PT で固定利回り）が Base では不可
4. **TVL 下落トレンド**: 2025年末〜2026年のプロトコル利用率低下リスク
5. **開発優先度**: Pendle チームのフォーカスは Boros・Citadel (Solana/Hyperliquid) にシフト。Base は二次的

### 総合判断

**Phase 2 での優先度: 中（後回し可）**

- Lido/Aave V3 Base の組み合わせの方がシンプルで流動性が高く、優先すべき
- Pendle 統合は「固定利回りオプションの追加」として Phase 3 以降で検討
- Ethereum Mainnet での Pendle + Aave V3 統合の方が成熟しており、Base より先行実装を推奨

---

## 5. 次アクション提案

| 優先度 | アクション | 担当 | 期限目安 |
|---|---|---|---|
| P1 | Aave V3 Base に PT 担保化提案が出るかモニタリング (governance.aave.com) | 調査担当 | 継続 |
| P2 | Base 上の Pendle 現行マーケット一覧を API で取得してスプレッドシート化 | エンジニア | Phase 3 開始時 |
| P2 | Pendle SDK (pendle-sdk-core) を用いた PT 価格取得の PoC | エンジニア | Phase 3 |
| P3 | 満期自動ロールオーバーロジックの設計 (Pendle AMM Swap 統合) | エンジニア | Phase 3 以降 |
| P3 | Pendle Boros (perpetual yield) の UATa 統合可能性調査 | 調査担当 | Phase 4 |

---

## 参照URL

- [Pendle Finance 公式](https://www.pendle.finance)
- [Pendle ドキュメント](https://docs.pendle.finance)
- [pendle-core-v2-public GitHub (Base deployment 8453-core.json)](https://github.com/pendle-finance/pendle-core-v2-public/blob/main/deployments/8453-core.json)
- [DefiLlama: Pendle TVL](https://defillama.com/protocol/pendle)
- [Aave Governance: ARFC Onboard Pendle PT tokens to Aave V3](https://governance.aave.com/t/arfc-onboard-pendle-pt-tokens-to-aave-v3-core-instance/20541)
- [Aave Governance: PT-USDG-28MAY2026 onboarding](https://governance.aave.com/t/arfc-onboard-pt-usdg-28may2026-to-aave-v3-core-instance/24345)
- [PT cbETH Base マーケット](https://app.pendle.finance/trade/markets/0x483f2e223c58a5ef19c4b32fbc6de57709749cb3?view=pt&chain=base)
- [Pendle 2025 展望 (Greythorn)](https://0xgreythorn.medium.com/pendle-2025-building-defis-fixed-income-layer-175a5eeb10fd)
- [TokenInsight Pendle Deep Dive (Feb 2026)](https://tokeninsight.medium.com/deep-dive-of-pendle-ebcf8b5b9131)
