# Web3 Testing Patterns

**Source**: Synthesized from Antigravity Skills + Ultra AutoTrade test strategy

**Purpose**: Comprehensive testing strategies for Web3.py-based Ethereum applications

---

## Testing Pyramid for Web3 Apps

```
        /\
       /  \      E2E (Mumbai Testnet)
      /----\     - Real transactions
     /      \    - Slow, expensive
    /--------\   
   /          \  Integration (Mocked RPC)
  /------------\ - Contract interaction
 /              \- Fast, isolated
/________________\
   Unit Tests     - Pure logic
                  - No Web3 calls
```

---

## 1. Unit Tests (Pure Logic)

### Test Business Logic Without Web3

```python
# backend/tests/test_aave_logic.py

from decimal import Decimal
from app.aave.service import AaveService

def test_health_factor_below_threshold_skips_buy():
    """Test that BUY is skipped when HF < threshold"""
    
    # Mock client that returns low HF
    class FakeClient:
        def get_health_factor(self):
            return Decimal("1.0")  # Below threshold
    
    service = AaveService(client=FakeClient())
    
    result = service.execute_rebalance(
        action="BUY",
        amount=Decimal("10")
    )
    
    # Should be NOOP, not DEPOSIT
    assert result.operation == "NOOP"
    assert result.status == "skipped"
```

### Benefits
- ✅ Fast (no RPC calls)
- ✅ Deterministic (no network variability)
- ✅ Tests business logic in isolation

---

## 2. Integration Tests (Mocked Web3)

### Mock Web3 Provider

```python
# backend/tests/conftest.py

import pytest
from unittest.mock import Mock, MagicMock
from web3 import Web3
from decimal import Decimal

@pytest.fixture
def mock_w3():
    """Mock Web3 instance for integration tests"""
    w3 = Mock(spec=Web3)
    w3.is_connected.return_value = True
    w3.eth.chain_id = 80001  # Mumbai
    w3.eth.gas_price = 30000000000
    
    # Mock account
    mock_account = Mock()
    mock_account.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
    w3.eth.account.from_key.return_value = mock_account
    
    # Mock transaction count
    w3.eth.get_transaction_count.return_value = 42
    
    return w3

@pytest.fixture
def mock_pool_contract(mock_w3):
    """Mock Aave Pool contract"""
    contract = MagicMock()
    
    # Mock getUserAccountData
    contract.functions.getUserAccountData.return_value.call.return_value = (
        100 * 10**18,  # total_collateral
        50 * 10**18,   # total_debt
        50 * 10**18,   # available_borrow
        8000,          # liquidation_threshold
        7500,          # ltv
        2 * 10**18     # health_factor = 2.0
    )
    
    mock_w3.eth.contract.return_value = contract
    return contract
```

### Test Contract Interaction

```python
def test_get_health_factor_calls_contract_correctly(mock_w3, mock_pool_contract):
    """Test that get_health_factor calls contract with correct params"""
    
    from app.aave.web3_client import Web3AaveClient
    
    client = Web3AaveClient(
        w3=mock_w3,
        pool_address="0xPoolAddress",
        private_key="0x" + "1" * 64,
        chain_id=80001
    )
    
    hf = client.get_health_factor()
    
    # Verify contract was called
    mock_pool_contract.functions.getUserAccountData.assert_called_once()
    
    # Verify result
    assert hf == Decimal("2.0")
```

### Test Transaction Construction

```python
def test_deposit_builds_transaction_correctly(mock_w3, mock_pool_contract):
    """Test that deposit builds correct transaction params"""
    
    from app.aave.web3_client import Web3AaveClient
    
    client = Web3AaveClient(
        w3=mock_w3,
        pool_address="0xPoolAddress",
        private_key="0x" + "1" * 64,
        chain_id=80001
    )
    
    # Mock transaction building
    mock_build = mock_pool_contract.functions.supply.return_value.build_transaction
    mock_build.return_value = {
        'from': client.user_address,
        'nonce': 42,
        'gas': 300000
    }
    
    # Mock signing
    mock_signed = Mock()
    mock_signed.rawTransaction = b'0x123'
    mock_w3.eth.account.sign_transaction.return_value = mock_signed
    
    # Mock send and receipt
    mock_w3.eth.send_raw_transaction.return_value = b'0xTxHash'
    mock_w3.eth.wait_for_transaction_receipt.return_value = {'status': 1}
    
    # Execute
    tx_hash = client.deposit(
        asset="0xUSDC",
        amount=Decimal("10")
    )
    
    # Verify supply was called with correct params
    mock_pool_contract.functions.supply.assert_called_once_with(
        Web3.to_checksum_address("0xUSDC"),
        10 * 10**18,  # amount in wei
        client.user_address,
        0  # referralCode
    )
    
    assert tx_hash == "0xTxHash"
```

### Benefits
- ✅ Test Web3 interaction without real blockchain
- ✅ Verify contract calls and parameters
- ✅ Fast and deterministic

---

## 3. End-to-End Tests (Testnet)

### Mumbai Integration Test

```python
# backend/tests/test_aave_mumbai.py

import pytest
import os
from decimal import Decimal
from app.aave.web3_client import Web3AaveClient

@pytest.mark.skipif(
    os.getenv("RUN_E2E_TESTS") != "1",
    reason="E2E tests require testnet and test wallet"
)
class TestAaveMumbai:
    """
    Real transactions on Mumbai testnet
    
    Prerequisites:
    - MUMBAI_RPC_URL in environment
    - TEST_PRIVATE_KEY with Mumbai MATIC for gas
    - Test USDC balance
    """
    
    @pytest.fixture(scope="class")
    def mumbai_client(self):
        return Web3AaveClient(
            rpc_url=os.getenv("MUMBAI_RPC_URL"),
            private_key=os.getenv("TEST_PRIVATE_KEY"),
            pool_address="0x0b913A76beFF3887d35073b8e5530755D60F78C7",
            chain_id=80001
        )
    
    def test_get_health_factor_returns_value(self, mumbai_client):
        """Verify health factor can be read"""
        hf = mumbai_client.get_health_factor()
        
        assert hf is not None
        assert hf > 0
    
    def test_deposit_small_amount(self, mumbai_client):
        """Deposit 0.1 USDC to Aave on Mumbai"""
        
        usdc_mumbai = "0x52D800ca262522580CeBAD275395ca6e7598C014"
        
        # Step 1: Approve
        approval_tx = mumbai_client.approve_token(
            token_address=usdc_mumbai,
            spender=mumbai_client.pool_address,
            amount=Decimal("0.1")
        )
        assert approval_tx.startswith("0x")
        
        # Step 2: Deposit
        deposit_tx = mumbai_client.deposit(
            asset=usdc_mumbai,
            amount=Decimal("0.1")
        )
        assert deposit_tx.startswith("0x")
        
        # Step 3: Verify HF changed
        hf_after = mumbai_client.get_health_factor()
        assert hf_after is not None
```

### Configuration for E2E Tests

```bash
# .env.test (for E2E tests only)
RUN_E2E_TESTS=1
MUMBAI_RPC_URL=https://polygon-mumbai.infura.io/v3/YOUR_PROJECT_ID
TEST_PRIVATE_KEY=0x...  # Test wallet only, never production!
```

### Safety Rules
- ✅ Never use production private keys
- ✅ Use minimal amounts (< 1 USD)
- ✅ Separate test wallet with limited funds
- ✅ Run E2E tests manually, not in CI/CD

---

## 4. Error Handling Tests

### Test RPC Failures

```python
def test_health_factor_returns_none_on_rpc_failure(mock_w3):
    """Fail-closed: Return None when RPC fails"""
    
    # Mock RPC failure
    mock_w3.eth.contract.side_effect = ConnectionError("RPC timeout")
    
    client = Web3AaveClient(w3=mock_w3, ...)
    
    hf = client.get_health_factor()
    
    # Should return None, not raise or return fake value
    assert hf is None
```

### Test Transaction Revert

```python
def test_deposit_raises_on_contract_revert(mock_w3, mock_pool_contract):
    """Test that contract revert raises proper exception"""
    
    from web3.exceptions import ContractLogicError
    
    # Mock contract logic error
    mock_pool_contract.functions.supply.side_effect = ContractLogicError(
        "Insufficient allowance"
    )
    
    client = Web3AaveClient(w3=mock_w3, ...)
    
    with pytest.raises(AaveTransactionError, match="Contract logic error"):
        client.deposit(asset="0xUSDC", amount=Decimal("10"))
```

### Test Timeout

```python
def test_deposit_raises_on_timeout(mock_w3, mock_pool_contract):
    """Test that transaction timeout raises proper exception"""
    
    from web3.exceptions import TimeExhausted
    
    # Mock successful send but timeout on receipt
    mock_w3.eth.send_raw_transaction.return_value = b'0xTxHash'
    mock_w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted()
    
    client = Web3AaveClient(w3=mock_w3, ...)
    
    with pytest.raises(AaveTransactionError, match="timeout"):
        client.deposit(asset="0xUSDC", amount=Decimal("10"))
```

---

## 5. Test Coverage Strategy

### Target Coverage (docs/14_test_strategy.md)

| Component | Unit | Integration | E2E | Target |
|-----------|------|-------------|-----|--------|
| Web3AaveClient | ✅ | ✅ | ✅ | 90%+ |
| AaveService | ✅ | ✅ | ⏸️ | 90%+ |
| Error Handling | ✅ | ✅ | ✅ | 95%+ |

### Coverage Verification

```bash
# Run tests with coverage
pytest backend/tests/ --cov=backend/app/aave --cov-report=term-missing

# Verify coverage meets threshold
pytest backend/tests/ --cov=backend/app/aave --cov-fail-under=90
```

---

## 6. Hardhat / Foundry (Optional)

### For Smart Contract Testing

If you need to test custom contracts (not applicable to Aave integration):

```javascript
// Hardhat example
describe("MyContract", function () {
  it("Should interact with Aave", async function () {
    const [owner] = await ethers.getSigners();
    const contract = await MyContract.deploy();
    
    // Test contract logic
  });
});
```

**Not needed for Ultra AutoTrade**: We're calling existing Aave contracts, not deploying new ones.

---

## 7. Test Naming Convention

```python
# Pattern: test_<action>_<expected_behavior>_when_<condition>

def test_get_health_factor_returns_decimal_when_successful():
    """Happy path"""
    pass

def test_get_health_factor_returns_none_when_rpc_fails():
    """Error path"""
    pass

def test_deposit_raises_error_when_allowance_insufficient():
    """Contract revert"""
    pass
```

---

## 8. Pytest Configuration

```ini
# pytest.ini
[pytest]
testpaths = backend/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Markers
markers =
    unit: Unit tests (fast, no external calls)
    integration: Integration tests (mocked Web3)
    e2e: End-to-end tests (requires testnet)
    
# Run only unit tests by default
addopts = -m "not e2e"
```

### Run Specific Test Types

```bash
# Unit tests only (default)
pytest -m unit

# Integration tests
pytest -m integration

# E2E tests (manual)
RUN_E2E_TESTS=1 pytest -m e2e

# All tests
pytest -m ""
```

---

## Ultra AutoTrade Integration

### Apply to Phase 4 Testing

```python
# backend/tests/test_aave_web3_client.py

import pytest
from decimal import Decimal
from app.aave.web3_client import Web3AaveClient

@pytest.mark.unit
def test_client_initialization():
    """Test that client initializes correctly"""
    # Pure logic test, no Web3 calls
    pass

@pytest.mark.integration
def test_get_health_factor_with_mock(mock_w3, mock_pool_contract):
    """Test health factor with mocked Web3"""
    # Integration test with mocked dependencies
    pass

@pytest.mark.e2e
@pytest.mark.skipif(os.getenv("RUN_E2E_TESTS") != "1")
def test_deposit_on_mumbai(mumbai_client):
    """Real transaction on testnet"""
    # E2E test with real blockchain
    pass
```

---

## References

- pytest: https://docs.pytest.org/
- Web3.py Testing: https://web3py.readthedocs.io/en/stable/examples.html#testing
- Ultra AutoTrade: `docs/14_test_strategy.md`
- FastAPI Testing: `.skills/fastapi-testing-patterns.md`

---

**Next Steps**:
1. Write unit tests for business logic first
2. Add integration tests with mocked Web3
3. Verify 90%+ coverage
4. Add E2E tests on Mumbai (manual)
5. Run regression tests before Phase 5
