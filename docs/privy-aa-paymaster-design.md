# Privy Smart Wallet AA/ERC-4337 + Paymaster 設計 doc

- **Asana GID**: 1215697060370824
- **対象ブランチ**: `chore/aa-paymaster-vendor-spike`
- **作成日**: 2026-06-15
- **ステータス**: 設計フェーズ（スライス1 成果物）

---

## 1. 背景・目的

現在 UATa の Aave tx（deposit / withdraw）はユーザー EOA が直接署名して on-chain に投げる構造である。
ERC-4337 Account Abstraction (AA) + paymaster を導入することで:

1. ユーザーが ETH ガス代を持たなくてよくなる（UATa がスポンサー）
2. Privy の Smart Wallet (ERC-4337 SCW) でシームレスな UX が実現できる
3. 将来的に USDC ガス払いや batch UserOp も可能になる

本 doc は移行の核心リスクを整理し、実装スライス・paymaster ベンダー選定方針・F-9 費目再設計を明文化する。

---

## 1.5 不変条件（ノンカストディアル原則）

AA + Smart Wallet 移行においても以下の不変条件を**絶対に破らない**こと。
session key / SCW owner 設計次第でカストディが silent に移る security-critical なリスクがあるため、明示宣言する。

1. **ユーザー EOA が UserOp の唯一の署名者であり続ける**
   Smart Wallet (SCW) の owner 権限はユーザー EOA が保持する。UATa のサーバー鍵が owner に設定されてはならない。

2. **UATa はガス代スポンサー（paymaster）のみを担う**
   UATa はユーザー秘密鍵・SCW owner 権限を一切保持しない。paymaster policy ポリシーによってガス代を負担するが、tx への署名権限はユーザー EOA のみが持つ。

3. **スライス4 の SmartWalletsProvider 配線でこの不変条件を破らないことを承認ゲートに含める**
   `PrivyRootClient.tsx` への SmartWalletsProvider 配線時に、owner 権限設定・session key 設計が本原則に違反していないことを hkobayashi が確認してから着手すること。

---

## 2. 現状の実装（実コード確認済み）

### 2.1 build-tx エンドポイント（`backend/app/proposals/router.py:716`）

| tx 種別 | `from` | `onBehalfOf` / `to` |
|---|---|---|
| `build_deposit_txs` | `user_wallet`（EOA） | `user_wallet`（EOA） |
| `build_withdraw_tx` | `user_wallet`（EOA） | `user_wallet`（EOA） |

いずれも EOA アドレスをそのまま Aave V3 の calldata に埋め込んでいる。

### 2.2 安全装置（fail-closed / EOA 前提）

| 場所 | 検証内容 | EOA 前提の箇所 |
|---|---|---|
| `aave/client.py:1451` — `verify_supply_onbehalf` | `onBehalfOf == expected_wallet` | `expected_wallet` が EOA アドレス |
| `aave/client.py:1473` — `verify_withdraw_to` | `to == expected_wallet` | `expected_wallet` が EOA アドレス |
| `proposals/router.py:834` — `_verify_on_chain_receipt` | `from == partner_wallet` | EOA が tx を直接 submit する前提。ERC-4337 では `from` = EntryPoint/bundler になる |

### 2.3 Privy フロントエンド現状

- **ライブラリ**: `frontend/lib/wallet/PrivyRootClient.tsx` — `@privy-io/react-auth ^3.29.2`
- **SmartWalletsProvider**: 未配線（通常の EOA embedded wallet のみ）
- **署名経路 3 箇所**:
  - `frontend/app/(partner)/partner/proposals/page.tsx:108`
  - `frontend/app/(liff)/liff-approve/_components/ApproveConfirmSheet.tsx:103`
  - `frontend/app/(user)/withdraw/page.tsx:395`
- **注意**: `frontend/app/arobix/onboarding/page.tsx:47` に "Smart Wallet" テキストが存在するが実装ゼロ

### 2.4 F-9 expense_jpy 現状

- `backend/app/automation/workflow.py:817` および `backend/app/api/v1/fees.py:360` で参照
- `TRADE_FIXED_COST_USD=0.27`（ユーザー EOA ガス代の固定実費として計上）
- paymaster 移行後は費目定義の更新が必要

---

## 3. AA 移行の核心リスク

ERC-4337 では tx の `from` フィールドが **EOA → Smart Wallet コントラクト（EntryPoint 経由）** に変わる。
これにより既存の安全装置が以下のように破綻する:

### リスク1: `verify_supply_onbehalf` の破綻

```python
# aave/client.py:1451 (現状)
assert onBehalfOf == expected_wallet   # expected_wallet = EOA アドレス
```

AA 移行後は `onBehalfOf` に Smart Wallet コントラクトアドレスを渡す必要がある。
`expected_wallet` を EOA → Smart Wallet address に差し替えなければ全 deposit が revert または検証失敗する。

### リスク2: `_verify_on_chain_receipt` の破綻

```python
# proposals/router.py:834 (現状)
assert receipt["from"] == partner_wallet   # EOA が直接送信した前提
```

ERC-4337 UserOperation では `from` が **EntryPoint コントラクト** または **bundler** になるため、
この検証は常に失敗する。代わりに `UserOpHash → getUserOperationReceipt` 経路への書き換えが必要。

### リスク3: submit-tx 経路の変更

現状は `eth_sendRawTransaction` で EOA 署名 tx を投げる構造。
AA 移行後は:

1. `signUserOperation` で UserOp に署名
2. bundler の `eth_sendUserOperation` に投げる
3. `getUserOperationReceipt(userOpHash)` でレシート取得・検証

この 3 ステップへの書き換えが必要であり、**安全装置の配線変更を伴うため HUMAN-REVIEW-REQUIRED**。

---

## 4. Paymaster ベンダー比較

### 4.1 比較表

| 観点 | Pimlico | ZeroDev | Biconomy | Alchemy AA |
|---|---|---|---|---|
| Privy v3 公式統合 | ✅ official | ✅ official | ✅ official | △ 別途設定 |
| Base mainnet サポート | ✅ | ✅ | ✅ | ✅ |
| Base Sepolia サポート | ✅ | ✅ | ✅ | ✅ |
| ETH スポンサー（sponsored）| ✅ | ✅ | ✅ | ✅ |
| USDC ガス払い | ✅ | ✅ | ✅ | ✅ |
| `getUserOperationReceipt` API | ✅ | ✅ | ✅ | ✅ |
| per-UserOp コスト可視化 | ✅ dashboard | ✅ dashboard | ✅ dashboard | ✅ |
| セキュリティ監査実績 | 複数 | 複数 | 複数 | Alchemy 品質 |
| PoC 工数（Privy subpath 親和性）| 最小 | 最小 | 小 | 中 |

### 4.2 推奨とその根拠

**推奨: Pimlico または ZeroDev**

Privy `@privy-io/react-auth/smart-wallets` の subpath import が Pimlico / ZeroDev を
first-class でサポートしているため、PoC の実装コストが最小になる。

確定はしない。PoC で以下を確認してから最終決定すること:

- Base Sepolia で sponsored UserOp を送信し `status=1` が返るか
- `getUserOperationReceipt` が bundler から正常取得できるか
- per-UserOp コストがダッシュボードで可視化されるか

### 4.3 PoC スコープ（スライス7 テストと連動）

```
1. Base Sepolia テストネット上で Privy Smart Wallet を生成
2. paymaster（Pimlico または ZeroDev）経由で sponsored UserOp を送信
3. bundler から UserOpHash を取得
4. getUserOperationReceipt で status=1 と actualGasCost を確認
5. per-UserOp コストをダッシュボードで確認
```

---

## 5. F-9 expense_jpy 再設計方針

### 5.1 現状の問題

`TRADE_FIXED_COST_USD=0.27` はユーザー EOA がガス代を負担する前提の固定実費。
paymaster 移行後はガス代を UATa（UATa 側の paymaster アカウント）が負担するため、
費目の帰属が変わる。

### 5.2 設計案

**案A（推奨）: paymaster 実コスト per-UserOp 記録**

- paymaster API の `getUserOperationReceipt` から `actualGasCost`（wei）を取得
- Decimal 変換して `expense_jpy`（または `expense_usd`）として記録
- `TRADE_FIXED_COST_USD` は廃止（または paymaster 固定ポリシー料金に差し替え）
- メリット: 実費が透明、二重計上なし

**案B: paymaster コストを別費目に分離**

- `PAYMASTER_COST_USD` を新設し、F-9 の `TRADE_FIXED_COST_USD` は据え置き
- デメリット: 「ガス代」費目が二重計上になるリスクがある（F-9 + PAYMASTER_COST）
- 採用しない

### 5.3 移行後の費目方針（スライス6 で確定すること）

paymaster 移行完了後、以下を明文化する:

1. F-9（`expense_jpy`）の「ガス代」費目を廃止
2. `paymaster_actual_gas_cost_usd`（Decimal, 文字列 JSON）を新設
3. `fee_transactions` テーブルに `userOp_hash`（VARCHAR）カラムを追加して per-UserOp 追跡
4. `TRADE_FIXED_COST_USD` 環境変数はコメントアウト + 非推奨化

> **二重計上防止**: 案A を採用した場合でも、旧費目定義が残ると計算ロジックが両方を加算するリスクがある。
> スライス6 では既存の費目参照箇所を全件 grep して削除漏れがないことを確認すること。

---

## 6. 実装スライス一覧

### 6.1 自動進行可（HUMAN-REVIEW 不要）

| スライス | 内容 | ファイル | ステータス |
|---|---|---|---|
| スライス1 | 本設計 doc | `docs/privy-aa-paymaster-design.md` | 完了（本 doc） |
| スライス7 | PoC テスト新規追加（Base Sepolia UserOp 確認） | `backend/tests/` または `frontend/tests/` 新規ファイル | 未着手 |

### 6.2 HUMAN-REVIEW-REQUIRED（人間の承認後に着手）

以下のスライスは安全装置の変更・Tier S ファイルへの変更・金融計算の変更を含むため、
**実装前に人間（hkobayashi）の明示的な承認が必要**。

| スライス | 内容 | 変更対象ファイル | リスク分類 |
|---|---|---|---|
| スライス2 | UserOp receipt 検証 helper 新規 + submit-tx 配線 | `backend/app/proposals/router.py`（L834 `_verify_on_chain_receipt`）、`backend/app/aave/client.py`（L1451/L1473） | 🛑 DeFi 安全装置の変更 |
| スライス3 | `onBehalfOf` → Smart Wallet address 対応 + `users.smart_wallet_address` migration | `backend/app/proposals/router.py`、`backend/migrations/versions/*.py`（新規）、`backend/app/database.py` | 🛑 Tier S（migration） |
| スライス4 | フロント SmartWalletsProvider 配線 + sponsored UserOp 送信 | `frontend/lib/wallet/PrivyRootClient.tsx`、`frontend/app/(partner)/partner/proposals/page.tsx`、`frontend/app/(liff)/liff-approve/_components/ApproveConfirmSheet.tsx`、`frontend/app/(user)/withdraw/page.tsx` | 🛑 Aave tx 経路変更（全署名経路 3 箇所） |
| スライス5 | 依存追加（paymaster SDK） | `frontend/package.json`、`frontend/package-lock.json` | 🛑 Tier S（package.json） |
| スライス6 | F-9 expense_jpy 再設計・二重計上防止 | `backend/app/automation/workflow.py`（L817）、`backend/app/api/v1/fees.py`（L360） | 🛑 金融計算・Decimal 変更 |

---

## 7. 承認ゲート（HUMAN-REVIEW-REQUIRED 全スライス）

各スライスの実装着手前に以下の承認を得ること。

### スライス2 承認ゲート

- [ ] `getUserOperationReceipt` の検証ロジック設計をレビューして承認
- [ ] `_verify_on_chain_receipt` の代替設計（UserOpHash ベース）を承認
- [ ] 安全装置の fail-closed が維持されることを確認

### スライス3 承認ゲート

- [ ] `users.smart_wallet_address` カラム追加 migration の SQL を確認
- [ ] `onBehalfOf` に Smart Wallet アドレスを渡すロジックを承認
- [ ] EOA と Smart Wallet の共存期間の扱い（段階移行）を承認

### スライス4 承認ゲート

- [ ] SmartWalletsProvider 配線箇所（`PrivyRootClient.tsx`）の変更を承認
- [ ] 署名経路 3 箇所（proposals / liff-approve / withdraw）の変更を承認
- [ ] PoC（スライス7）の結果（Base Sepolia status=1 確認）を前提条件とすること
- [ ] **non-custodial 維持の確認**（ユーザー EOA が SCW の唯一の signer / UATa に owner 権限なし）— セクション 1.5 不変条件に違反していないことを確認

### スライス5 承認ゲート

- [ ] paymaster ベンダーの最終選定を承認（Pimlico または ZeroDev）
- [ ] 追加する npm パッケージとバージョンを確認

### スライス6 承認ゲート

- [ ] F-9 費目の廃止・統合方針を承認
- [ ] `fee_transactions` テーブルへの `userOp_hash` カラム追加を承認
- [ ] `TRADE_FIXED_COST_USD` の非推奨化スケジュールを承認

---

## 8. DoD（受入条件）

- [ ] 以下の 3 項目が本 doc に明文化されていること
  - **receipt 検証方式**: `getUserOperationReceipt(userOpHash)` 経路（セクション 3 / スライス2）
  - **onBehalfOf アドレス方針**: Smart Wallet コントラクトアドレスへの差し替え（セクション 3 / スライス3）
  - **F-9 帰属**: 案A（paymaster 実コスト per-UserOp 記録）、`TRADE_FIXED_COST_USD` 廃止（セクション 5 / スライス6）
- [ ] スライス1 / スライス7 の着手前に Planner 通過済み（本 doc がその成果物）
- [ ] HUMAN-REVIEW-REQUIRED 全スライス（2-6）に承認ゲートが明示されていること（セクション 7）

---

## 9. 関連ファイル（参照のみ / 本設計 doc からは変更しない）

| ファイル | 関連箇所 | 備考 |
|---|---|---|
| `backend/app/proposals/router.py` | L716（build-tx）、L834（`_verify_on_chain_receipt`） | スライス2/3 で変更 |
| `backend/app/aave/client.py` | L1451（`verify_supply_onbehalf`）、L1473（`verify_withdraw_to`） | スライス2/3 で変更 |
| `backend/app/automation/workflow.py` | L817（F-9 費目） | スライス6 で変更 |
| `backend/app/api/v1/fees.py` | L360（F-9 参照） | スライス6 で変更 |
| `frontend/lib/wallet/PrivyRootClient.tsx` | SmartWalletsProvider 未配線 | スライス4/5 で変更 |
| `frontend/app/(partner)/partner/proposals/page.tsx` | L108（署名経路） | スライス4 で変更 |
| `frontend/app/(liff)/liff-approve/_components/ApproveConfirmSheet.tsx` | L103（署名経路） | スライス4 で変更 |
| `frontend/app/(user)/withdraw/page.tsx` | L395（署名経路） | スライス4 で変更 |
| `frontend/package.json` | `@privy-io/react-auth ^3.29.2` | スライス5 で変更（Tier S） |

---

## 10. 参考資料

- [Privy Smart Wallets ドキュメント](https://docs.privy.io/wallets/smart-wallets)
- [ERC-4337 仕様（eips.ethereum.org）](https://eips.ethereum.org/EIPS/eip-4337)
- [Pimlico ドキュメント](https://docs.pimlico.io/)
- [ZeroDev ドキュメント](https://docs.zerodev.app/)
- `docs/40_multi_wallet_design.md` — マルチウォレット設計
- `docs/41_kms_vault_design.md` — KMS/Vault 設計
- `docs/13_security_design.md` — セキュリティ設計詳細
