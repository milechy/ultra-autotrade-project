# P2-A1: Lido Base Mainnet 対応状況調査

調査日: 2026-04-26  
担当: 小林 浩紀  
Asana: 1214121231670782

---

## TL;DR

- wstETH は **2023年9月〜12月** にかけて Base Mainnet に正式展開済み（LidoDAO 承認 + Aave V3 Base 上場完了）
- Base 上の wstETH コントラクトアドレス: `0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452`
- Aave V3 Base に wstETH 担保として上場済み（TVL 約 $40M、供給 13,800 wstETH）
- staking APR は Ethereum 全体として **3〜5%** 程度（2025年時点、利回り圧縮傾向）
- **統合判断: 条件付き推奨** — wstETH は Base で稼働中だが、bridged token の技術的制約（ローカルアンラップ不可、rebase rewards が on-chain 取得不可）に留意が必要

---

## 1. Lido Base Mainnet 対応状況

### 1.1 現在の対応状況

wstETH は Base Mainnet に **完全対応済み**。以下のフェーズで展開された:

| フェーズ | 時期 | 内容 |
|---------|------|------|
| ブリッジ基盤構築 | 2023年9月28日 | wstETH ブリッジコントラクト Base 上にデプロイ |
| LidoDAO 正式承認 | 2023年11月2日 | スナップショット投票完了（圧倒的賛成多数） |
| Aave V3 Base 上場 | 2023年12月9日 | Aave V3 Base で wstETH 担保資産として上場（賛成 566,416 AAVE、100.00%） |

**背景**: Base は OP Stack を採用しているため、Lido は Optimism 向けに開発済みのブリッジソリューションを再利用できた。LayerZero 標準を却下後、Lido は公式(canonical)ブリッジ方式として Base を採択。

### 1.2 コントラクトアドレス（Base Mainnet）

| コントラクト | アドレス |
|------------|---------|
| wstETH Token (Bridged) Proxy | `0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452` |
| wstETH Token Implementation | `0x69ce2505ce515c0203160450157366f927243309` |
| L1 Bridge (Ethereum) Proxy | `0x9de443AdC5A411E83F1878Ef24C3F52C61571e72` |
| L2 Bridge (Base) Proxy | `0xac9D11cD4D7eF6e54F14643a393F68Ca014287AB` |
| Governance Bridge Executor | `0x0E37599436974a25dDeEdF795C848d30Af46eaCF` |
| Chainlink wstETH/stETH 価格フィード | `0xB88BAc61a4Ca37C43a3725912B1f472c9A5bc061` |

参照: [Lido Deployed Contracts — Mainnet](https://docs.lido.fi/deployed-contracts/) / [BaseScan](https://basescan.org/token/0xc1cba3fcea344f92d9239c08c0568f6f2f0ee452)

### 1.3 公式アナウンス・ガバナンス

- **LidoDAO 承認**: ガバナンスフォーラムで Lido DAO recognition proposal for wstETH on Base が審議され、正式承認。実装は Beefy の協力のもとで完成。
- **Aave V3 上場**: [Governance Proposal #394](https://governance-v2.aave.com/governance/proposal/394/) — 2023年12月4日提出、12月9日実行。Aave トークン保有者の 100% 賛成で可決。
- **Superbridge 対応**: OP Mainnet・Base・Unichain・Mode・Lisk・Soneium・Swellchain を含む OP Stack 各チェーンへのブリッジが Superbridge 経由で対応済み。
- **Lido V3 / stVaults (2026年1月30日)**: Lido は 2026年1月30日に stVaults をメインネットで稼働開始。L2 が bridged ETH をステーキングに組み込む仕組みを提供（Linea が先行採用）。wstETH on Base への直接影響は現時点で限定的だが、将来的な L2 ネイティブ統合の基盤となる。

---

## 2. stETH / wstETH インターフェース

### 2.1 stETH の特殊性 (rebase token)

stETH は **毎日リベースするトークン** であり、通常の ERC-20 と挙動が異なる。

**仕組み**: 残高は直接保持せず、プロトコル全体の share で管理される。

```
shares[account] = balanceOf(account) × totalShares / totalPooledEther
```

オラクルが Consensus Layer のバランス更新を報告すると、全保有者の残高が自動的に調整される。

**重要な注意点**:
- rebase 時に `Transfer` イベントを発行しない（ERC-20 非準拠）
- Uniswap・SushiSwap・Maker 等の多くの DeFi プロトコルは rebase トークン非対応
- stETH を対応外プロトコルに直接統合すると、保有者が毎日のステーキング報酬を受け取れない

**セーフガード**:
- 日次 APR 上限: 27%（1日のリベース上限 約 0.074%）
- 総ステーク減少制限: 5%（スラッシングシナリオ対応）
- 5-of-9 オラクルコンセンサスが必要

### 2.2 wstETH wrap/unwrap メカニズム

wstETH は **rebase を行わない DeFi 向け ERC-20 ラッパー**。保有残高は変化せず、代わりに wstETH の stETH 換算レートが日々変化することで報酬を反映する。

**Wrap (stETH → wstETH)**:
1. 指定量の stETH を WstETH コントラクトにロック
2. share bookkeeping 計算式に基づき wstETH をミント
3. ユーザーは固定の wstETH 残高を保持（報酬は価値増加で反映）

**Unwrap (wstETH → stETH)**:
1. wstETH をバーン
2. 対応する stETH をアンロック（ラップ時より多い stETH が戻る）

**レート取得**:
```solidity
// 現在の stETH per wstETH レートを取得
wstETH.stEthPerToken()
wstETH.getStETHByWstETH(10 ** decimals)
```

**技術的注意**: 標準 ERC-20 転送で 1〜2 wei の丸め誤差が発生する場合がある。精度が重要な場合は `transferShares()` を推奨。

### 2.3 Base での deposit/withdraw 経路

**Base は bridged ERC-20 実装のため、重要な制約がある。**

```
Ethereum Mainnet (stETH/wstETH) <──── lock/mint bridge ────> Base (wstETH bridged)
                                                               ↕ NO local unwrap
                                                           Aave V3 Base
                                                           Uniswap/Balancer 等
```

**Base 上でできること**:
- wstETH の保有・転送（通常 ERC-20 として利用可能）
- Aave V3 Base への担保供給・借入
- DEX での売買（Uniswap V3、Aerodrome 等）
- Chainlink オラクル経由でのレート取得

**Base 上でできないこと**:
- wstETH → stETH へのローカルアンラップ（**不可**）
- stETH 残高の on-chain リベース取得（bridged token は share bookkeeping を保持しない）

**ブリッジ経路 (Superbridge 経由)**:

| 方向 | 所要時間 | コスト |
|------|---------|-------|
| Ethereum → Base (deposit) | 数分 | Ethereum ガス代のみ |
| Base → Ethereum (withdraw) | **約 7 日間** | OP Stack セキュリティ要件 |

大口転送（$100,000 超）はスリッページなしのブリッジ経由が DEX より有利。

---

## 3. UATa 統合影響評価

### 3.1 Aave V3 Base Mainnet との統合

wstETH は Aave V3 Base に **2023年12月から上場済み** で、担保利用可能。

**現在のパラメータ (Aave V3 Base, 2023年12月設定)**:

| パラメータ | 値 |
|----------|-----|
| LTV (Loan-to-Value) | **71%** |
| 清算閾値 | **76%** |
| 清算ボーナス | 6% |
| リザーブファクター | 15% |
| 供給キャップ | 4,000 wstETH |
| 借入キャップ | 400 wstETH |
| フラッシュローン | 有効 |
| E-Mode | wrsETH/wstETH E-Mode 対応（後から追加） |

**追加ガバナンス (2025年11月)**: wrsETH/wstETH E-Mode に WETH 借入を追加する提案が審議済み（[Aave Governance](https://governance.aave.com/t/direct-to-aip-add-weth-to-the-wrseth-wsteth-e-mode-on-aave-v3-base-instance/23431)）。

**現在の市場データ (2025年時点)**:
- 総供給量: 約 13,800 wstETH
- 総供給 TVL: 約 $40.02M
- 供給 APY (Aave 側): <0.01%（Aave 単体の利回り — Lido staking 報酬は別途加算）
- 借入量: 約 410 wstETH

**重要**: Aave 上の供給 APY は Lido のステーキング APR を含まない。実質リターンは「Aave 供給 APY + Lido ステーキング APR（3〜5%）」となる。

UATa のヘルスファクター管理（HF < 1.6 で HARD_STOP）において、清算閾値 76% / LTV 71% は既存の Polygon/Arbitrum パラメータと比較して保守的な設定であり、リスク許容範囲内。

### 3.2 APY・流動性

**Lido ステーキング APR**:
- 現在: **3〜5%** （2025年時点、利回り圧縮傾向が継続）
- Ethereum バリデーター増加に伴い低下傾向
- Lido V3 / stVaults (2026年1月〜) により Golden Goose Vault 経由で **〜5% APY** の付加的リターンが可能

**Base の DeFi エコシステム**:
- Base チェーン全体 TVL: 約 $4.3B（2025年時点）
- Aave V3 Base wstETH TVL: 約 $40M（比較的規模は小さい）
- DEX 流動性: Uniswap V3 / Aerodrome (Velodrome の Base フォーク) が主要
- Balancer 流動性プールも利用可能

**流動性リスク**: $40M TVL は Ethereum メインネットの wstETH Aave 市場（数十億ドル規模）と比較して小さい。大口ポジション（供給キャップ 4,000 wstETH）に達した場合、新規供給不可となる点に注意。

### 3.3 セキュリティ・監査状況

**wstETH コントラクト本体**:
- MixBytes wstETH 監査（2021年9月）: **Critical/Major 問題なし**
- ChainSecurity Lido Smart Contract 監査（2022年8月）
- Sigma Prime Security Assessment v2.1（2023年3月）
- その他: Certora, OpenZeppelin, Consensys Diligence, Hexens, Oxorio 等 多数

**OP Stack / Base ブリッジ固有監査**:
- **Ackee Blockchain** stETH on Optimism（2024年6月）: 15 件中 10 件修正、5 件 Acknowledged、Critical/High なし
- **MixBytes** stETH on Optimism（2024年6月）: 20 件中 15 件修正、High 1 件 (修正済み)、Medium 1 件 (修正済み)
- **Cantina** wstETH on Mode 検証（2024年7月）: Base デプロイとの対照検証、Critical 問題なし
- MixBytes による Soneium（2025年1月）・Unichain（2025年2月）・Lisk（2025年4月）検証完了

**追加安全機能**:
- Emergency Multisig: pause/resume 権限保持（緊急時の引き出し停止可能）
- アップグレード可能コントラクト: LidoDAO の Aragon Agent が L1 エンドポイントを管理
- Chainlink 価格フィード: wstETH/stETH レートを提供（`0xB88BAc61a4Ca37C43a3725912B1f472c9A5bc061`）

監査レポートの公開リポジトリ: [https://github.com/lidofinance/audits](https://github.com/lidofinance/audits)

---

## 4. 統合判断 (Pros/Cons)

### Pros

1. **既存稼働の安定性**: wstETH は 2023年末から Base Mainnet + Aave V3 Base で稼働中。新規デプロイではなく実績あり。
2. **OP Stack 互換性**: UATa が既に Aave V3 対応コードを持つため、Polygon/Arbitrum の延長として Base 統合が可能。追加開発コストが低い。
3. **ERC-20 互換**: wstETH（bridged）は rebase なしの通常 ERC-20。`Decimal` 型計算に適した確定的な残高。
4. **Chainlink オラクル提供**: リアルタイムの wstETH/stETH レートが取得可能（オラクル依存の価格計算が安全に実装できる）。
5. **多重監査済み**: OP Stack ブリッジ固有の監査も 2024年に実施済み（Ackee/MixBytes）。
6. **ガバナンス管理**: LidoDAO の Emergency Multisig がブリッジの pause/resume を管理。異常時の対応策あり。
7. **Aave V3 E-Mode 活用**: wrsETH/wstETH E-Mode によりより高い担保効率が期待できる。

### Cons

1. **ローカルアンラップ不可**: Base 上の wstETH は stETH に変換できない。wstETH → ETH 変換はブリッジ経由（7日間）または DEX スワップが必要。
2. **Ethereum → Base 移動の 7 日間遅延**: OP Stack の withdrawal challenge period により、Base から Ethereum へは 7 日間待機が発生。緊急引き出しに対応できない可能性がある。
3. **市場規模の小ささ**: $40M TVL・4,000 wstETH 供給キャップは Ethereum メインネットと比較して小さく、大口ポジションで供給キャップに到達するリスクあり。
4. **低 APY**: staking APR 3〜5% は利回り圧縮傾向にあり、将来的な低下が想定される。
5. **rebase 報酬の on-chain 取得不可**: 自動化ロジックで stETH rebase 報酬をリアルタイム on-chain 取得する実装はできない（Chainlink オフチェーンフィード依存）。
6. **ブリッジリスク**: Lock-and-mint ブリッジは Ethereum 側のロックコントラクトが単一障害点。審査済みだが、ブリッジハック前例（他プロジェクト）として考慮。
7. **stVaults との統合未成熟**: Lido V3 stVaults は 2026年1月に稼働開始したばかりで、Base 側の Native Yield 統合事例はまだ限定的。

### 判断: 条件付き推奨

**推奨するケース**:
- Base エコシステムへのエクスポージャーを持ちながら staking 報酬を獲得したい場合
- Aave V3 Base での担保ポジションを UATa の Polygon/Arbitrum ポジションの分散先として活用する場合
- 既存 Aave V3 統合コードをベースに追加対応コストを抑えたい場合

**注意が必要なケース**:
- 緊急時の即時流動化（7日間ブリッジ遅延が問題になるシナリオ）
- 供給キャップ（4,000 wstETH）に近づいた場合の新規ポジション積み増し
- rebase 報酬の on-chain リアルタイム計算が必要な場合

---

## 5. 次アクション提案

### 短期（Phase 2 — 既存 PoC 評価後）

1. **Aave V3 Base 接続テスト**: 既存の `backend/app/aave/client.py` の `_get_pool_contract()` に Base Mainnet RPC を追加し、wstETH Health Factor 読み取りを確認する（PoC レベル）。
2. **Chainlink オラクル統合確認**: `0xB88BAc61a4Ca37C43a3725912B1f472c9A5bc061` からの wstETH/stETH レート取得を Python で検証。
3. **供給キャップ監視追加**: Aave V3 Base の wstETH 供給キャップ（4,000 wstETH）を monitoring に追加し、80% 到達で Slack アラートを発報。

### 中期（Phase 3 — メインネット統合検討時）

4. **Base Sepolia Testnet での end-to-end テスト**: Aave V3 Base Sepolia への wstETH 供給・借入・返済サイクルを自動化テストで検証（`docs/14_test_strategy.md` §8 参照）。
5. **Risk Engine への Base パラメータ追加**: `backend/app/protocols/` の Risk Engine に Base wstETH LTV 71% / 清算閾値 76% を追記。
6. **引き出しフロー設計**: 緊急引き出しシナリオで 7 日間待機が問題になる場合、Base 上での DEX スワップ（wstETH → WETH → ブリッジ）を代替経路として設計。

### 長期（Phase 4 以降）

7. **Lido stVaults Base 統合監視**: Linea に続く形で Base が Native Yield stVault を採用するか監視。採用された場合、ネイティブブリッジ ETH がそのまま staking に組み込まれる新しい経路が生まれる。

---

## 参照URL

- [Lido Deployed Contracts (Mainnet)](https://docs.lido.fi/deployed-contracts/)
- [wstETH on BaseScan](https://basescan.org/token/0xc1cba3fcea344f92d9239c08c0568f6f2f0ee452)
- [Lido Cross-Chain Tokens Adoption Guide](https://docs.lido.fi/token-guides/cross-chain-tokens-guide/)
- [Lido Tokens Integration Guide](https://docs.lido.fi/guides/lido-tokens-integration-guide/)
- [wstETH Rollup Bridging Guide](https://docs.lido.fi/token-guides/wsteth-bridging-guide/)
- [Aave V3 Base Activation Proposal #299](https://governance-v2.aave.com/governance/proposal/299/)
- [Aave: Onboarding wstETH to Aave V3 on Base Proposal #394](https://governance-v2.aave.com/governance/proposal/394/)
- [Aave V3 Base Market](https://app.aave.com/markets/?marketName=proto_base_v3)
- [Add WETH to wrsETH/wstETH E-Mode on Aave V3 Base](https://governance.aave.com/t/direct-to-aip-add-weth-to-the-wrseth-wsteth-e-mode-on-aave-v3-base-instance/23431)
- [Bridging via Superbridge — Lido Help](https://help.lido.fi/en/articles/11384344-bridging-via-superbridge-op-mainnet-base-unichain-mode-lisk-soneium-and-swellchain)
- [Lido Security Audits](https://docs.lido.fi/security/audits/)
- [lidofinance/audits GitHub](https://github.com/lidofinance/audits)
- [Lido V3 stVaults Is Live](https://blog.lido.fi/lido-v3-is-live-modular-infrastructure-for-a-new-paradigm-of-ethereum-staking/)
- [WstETH Gets on Base After LayerZero Strikeout — Blockworks](https://blockworks.co/news/lido-wsteth-coinbase-base)
- [Lido Protocol Audits Docs](https://docs.lido.fi/security/audits/)
- [DeFiLlama Base Chain](https://defillama.com/chain/base)
- [Lido TVL — DeFiLlama](https://defillama.com/protocol/lido)
