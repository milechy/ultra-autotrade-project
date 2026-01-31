# Aave 開発ガイド

## 開発原則（Best Practices準拠）

### 1. Start Small, Iterate
- 最初はget_health_factor()のみ実装
- 次にdeposit()のテスト
- 最後にwithdraw()の実装

### 2. Explicit is Better
```python
# Bad: 暗黙の動作
def deposit(amount):
    _approve_and_supply(amount)

# Good: 明示的な手順
def deposit(self, asset_symbol: str, amount: Decimal) -> str:
    """
    指定したトークンを Aave に deposit する。

    手順:
    1. ERC20.approve(Pool, amount)
    2. Pool.supply(amount)

    Returns:
        str: トランザクションハッシュ
    """
    approve_tx = self._approve_token(asset_symbol, amount)
    logger.info("Approve tx: %s", approve_tx)

    supply_tx = self._supply_to_pool(asset_symbol, amount)
    logger.info("Supply tx: %s", supply_tx)

    return supply_tx
```

### 3. Trust but Verify
- テストネットで deposit/withdraw を3回ずつテスト
- Mumbai Explorer でトランザクション確認
- ガス代・実行時間を記録

## Aave V3 の仕様
- **supply()**: Aave V2のdeposit()に相当
- **healthFactor**: 1e18スケール（1.0 = 1000000000000000000）
- **Mumbai Pool**: `0x6C9fB0D5bD9429eb9Cd96B85B81d872281771E6B`

## トランザクションパターン
```python
# 1. Approve (ERC20 -> Pool)
approve_tx = token.functions.approve(pool.address, amount_wei).build_transaction({
    'from': wallet.address,
    'nonce': w3.eth.get_transaction_count(wallet.address),
    'gas': 100000,
    'gasPrice': w3.eth.gas_price
})

# 2. Supply (Pool)
supply_tx = pool.functions.supply(
    token.address,
    amount_wei,
    wallet.address,
    0
).build_transaction({...})

# 3. Wait for receipt
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

# 4. Check status
if receipt.status != 1:
    raise AaveTransactionError("Transaction failed")
```

## エラーハンドリング（Best Practice準拠）

### Bad: Silent failure
```python
try:
    client.deposit(amount)
except Exception:
    return None  # エラーを隠蔽
```

### Good: Explicit error propagation
```python
try:
    tx_hash = client.deposit(amount)
    logger.info("Deposit successful: %s", tx_hash)
    return tx_hash
except Web3Exception as exc:
    logger.error("Web3 error during deposit: %s", exc)
    raise AaveTransactionError(f"Deposit failed: {exc}") from exc
```

## テスト戦略
```python
# Unit test: Web3をモック
@patch('app.aave.client.Web3')
def test_deposit_builds_correct_transaction(mock_web3):
    ...

# Integration test: テストネット使用
@pytest.mark.integration
def test_deposit_on_mumbai():
    ...

# E2E test: staging環境
@pytest.mark.e2e
def test_full_flow_notion_to_aave():
    ...
```

## 禁止事項
- 本番ウォレットの秘密鍵をコードに埋め込む
- エラーをtry-exceptで握りつぶす
- ガス代見積もりなしでトランザクション送信
- テストなしでmainブランチにマージ
