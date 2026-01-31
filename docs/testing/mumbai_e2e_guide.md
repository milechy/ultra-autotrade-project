# Mumbai E2E テストガイド

## 概要

このガイドでは、Polygon Mumbai テストネットを使用した E2E（End-to-End）テストの実行方法を説明します。

E2E テストでは、実際の Aave V3 プロトコルに対してトランザクションを送信し、
`get_health_factor()`, `deposit()`, `withdraw()` の動作を検証します。

---

## 1. 前提条件

### 必須

- [ ] Python 3.10 以上
- [ ] pip パッケージ: `web3`, `eth-account`
- [ ] Mumbai RPC エンドポイント
- [ ] テスト用ウォレット
- [ ] Mumbai MATIC（ガス代）
- [ ] Test USDC（Aave テスト用）

### 推奨

- [ ] Alchemy または Infura の API キー（公開 RPC より安定）
- [ ] PolygonScan API キー（トランザクション確認用）

---

## 2. クイックスタート

### 自動セットアップ

```bash
# セットアップスクリプトを実行
bash scripts/setup_mumbai_test.sh
```

このスクリプトは以下を自動で行います：
1. テストウォレットの生成
2. `.env.test` ファイルの作成
3. Faucet URL の表示
4. PolygonScan リンクの表示

---

## 3. 手動セットアップ

### 3.1 ウォレット生成

```bash
# テストウォレットを生成
python scripts/generate_test_wallet.py

# .env.test に出力
python scripts/generate_test_wallet.py --output backend/.env.test
```

出力例：
```
ウォレットアドレス: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
秘密鍵:             0x1234...abcd
```

### 3.2 Mumbai MATIC を取得

ガス代として Mumbai MATIC が必要です。

1. [Polygon Faucet](https://faucet.polygon.technology/) にアクセス
2. ウォレットアドレスを入力
3. "Mumbai" ネットワークを選択
4. "Submit" をクリック

約 0.2 MATIC が送信されます（E2E テストには十分な量）。

### 3.3 Test USDC を取得

Aave での deposit/withdraw テストには Test USDC が必要です。

1. [Aave Faucet](https://app.aave.com/faucet/) にアクセス
2. ウォレットを接続（Mumbai ネットワーク）
3. "USDC" を選択
4. "Faucet" をクリック

約 10,000 Test USDC が送信されます。

### 3.4 環境変数の設定

```bash
# テンプレートをコピー
cp backend/.env.test.example backend/.env.test

# 秘密鍵を設定（エディタで編集）
# AAVE_WALLET_PRIVATE_KEY=0x...
```

---

## 4. テスト実行

### 基本的な実行方法

```bash
# .env.test を読み込んで実行
source backend/.env.test
pytest backend/tests/ -m e2e -v
```

または：

```bash
# 環境変数で直接指定
RUN_E2E_TESTS=1 pytest backend/tests/ -m e2e -v
```

### 特定のテストのみ実行

```bash
# get_health_factor のテストのみ
RUN_E2E_TESTS=1 pytest backend/tests/test_aave_web3_client.py::test_get_health_factor_live -v

# deposit のテストのみ
RUN_E2E_TESTS=1 pytest backend/tests/test_aave_web3_client.py::test_deposit_live -v
```

### テスト結果の確認

テスト実行後、PolygonScan でトランザクションを確認できます：

```
https://mumbai.polygonscan.com/address/<your-wallet-address>
```

---

## 5. トラブルシューティング

### 5.1 ガス不足エラー

```
Error: insufficient funds for gas
```

**解決方法:**
1. [Polygon Faucet](https://faucet.polygon.technology/) で MATIC を追加取得
2. ウォレット残高を確認（最低 0.1 MATIC 推奨）

### 5.2 RPC エラー

```
Error: Connection refused / Timeout
```

**解決方法:**
1. 別の RPC エンドポイントを試す
2. Alchemy/Infura の API キーを取得して使用

```bash
# .env.test で RPC URL を変更
AAVE_RPC_URL=https://polygon-mumbai.g.alchemy.com/v2/YOUR_API_KEY
```

### 5.3 トランザクション失敗

```
Error: Transaction reverted
```

**考えられる原因:**
- Approval 不足
- 残高不足
- Aave プールの状態変化

**解決方法:**
1. Test USDC 残高を確認
2. Approval トランザクションが成功しているか確認
3. PolygonScan でエラー詳細を確認

### 5.4 Approval エラー

```
Error: ERC20: insufficient allowance
```

**解決方法:**
1. `deposit()` の前に `approve()` が実行されているか確認
2. Approval 金額が deposit 金額以上か確認

### 5.5 Health Factor が None

```
Health factor is None
```

**説明:**
- 借入がない場合、Health Factor は返されません
- これはエラーではなく、正常な動作です

---

## 6. よくある質問（FAQ）

### Q: テストウォレットに本物の MATIC/USDC を送っても大丈夫？

**A:** 絶対にやめてください。テストウォレットの秘密鍵はローカルに保存されており、
セキュリティが十分ではありません。テストネットトークンのみを使用してください。

### Q: E2E テストはどのくらい時間がかかる？

**A:** 各トランザクションに 15-30 秒程度かかります。
全ての E2E テストを実行すると 2-5 分程度です。

### Q: テストが intermittent に失敗する

**A:** RPC のレート制限やネットワーク状態が原因の可能性があります。
Alchemy/Infura の有料プランを使用すると安定します。

### Q: Mumbai テストネットの USDC アドレスは？

**A:** `0x52D800ca262522580CeBAD275395ca6e7598C014`
これは Aave V3 がサポートしている Test USDC です。

### Q: ローカルでテストネットをモックできる？

**A:** ユニットテストでは Web3 をモックしています。
E2E テストは実際のネットワークとの統合を検証するため、
モックは使用しません。

---

## 7. セキュリティベストプラクティス

### 絶対にやってはいけないこと

1. **秘密鍵をコミットしない**
   - `.env.test` は `.gitignore` に含めること
   - 秘密鍵を含むファイルを push しない

2. **本番環境で使用しない**
   - テストウォレットは Mumbai 専用
   - 本番の Polygon/Ethereum では使用しない

3. **実際の資金を送らない**
   - テストウォレットに本物のトークンを送らない
   - Faucet から取得したテストトークンのみ使用

### 推奨事項

1. **定期的にウォレットを更新**
   - 長期間使用するウォレットは避ける
   - 必要に応じて新しいウォレットを生成

2. **RPC キーを保護**
   - Alchemy/Infura の API キーも秘密として扱う
   - キーが漏洩した場合は再生成

3. **テスト後のクリーンアップ**
   - `.env.test` を定期的に削除
   - 不要なウォレットは破棄

---

## 8. 参照リンク

### Mumbai テストネット

- [Polygon Faucet](https://faucet.polygon.technology/)
- [Mumbai PolygonScan](https://mumbai.polygonscan.com/)
- [Mumbai RPC Endpoints](https://wiki.polygon.technology/docs/develop/network-details/network/)

### Aave V3

- [Aave Faucet](https://app.aave.com/faucet/)
- [Aave V3 Docs](https://docs.aave.com/developers/)
- [Aave V3 Mumbai Addresses](https://docs.aave.com/developers/deployed-contracts/v3-testnet-addresses)

### プロジェクト内ドキュメント

- [Aave 運用ロジック](../07_aave_operation_logic.md)
- [セキュリティ設計](../13_security_design.md)
- [テスト戦略](../14_test_strategy.md)

---

## 9. E2E テスト一覧

| テスト名 | 内容 | 前提条件 |
|---------|------|---------|
| `test_web3_client_initialization_live` | RPC 接続確認 | RPC URL |
| `test_get_health_factor_live` | Health Factor 取得 | RPC URL, ウォレット |
| `test_deposit_live` | USDC deposit | RPC URL, ウォレット, Test USDC |
| `test_withdraw_live` | USDC withdraw | RPC URL, ウォレット, 既存 position |

---

## 10. 更新履歴

| 日付 | バージョン | 内容 |
|------|-----------|------|
| 2025-01-25 | 1.0 | 初版作成 |
