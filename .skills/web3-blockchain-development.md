# Web3 Blockchain Development

**Source**: Synthesized from Antigravity Skills (rmyndharis/herdiansah) + Ultra AutoTrade requirements

**Purpose**: Guide Web3.py implementation for Ethereum DApp backends with focus on Aave V3 integration

---

## Core Principles

### 1. **Start Small, Test Often**
```python
# ❌ Bad: Implement everything at once
class Web3AaveClient:
    def __init__(self): ...
    def get_health_factor(self): ...
    def deposit(self): ...
    def withdraw(self): ...
    def borrow(self): ...
    def repay(self): ...

# ✅ Good: Implement incrementally
class Web3AaveClient:
    def __init__(self): ...
    def get_health_factor(self): ...  # Start here, test, then add more
```

### 2. **Explicit Error Handling**
```python
# ❌ Bad: Silent failure
try:
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
except:
    return None  # Error hidden

# ✅ Good: Explicit propagation
try:
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
except Exception as exc:
    logger.error("Transaction failed: %s", exc)
    raise AaveTransactionError(f"Failed to send transaction: {exc}") from exc
```

### 3. **Fail-Closed Design**
```python
# ❌ Bad: Default to risky action
def get_health_factor(self) -> Decimal:
    try:
        return self._fetch_health_factor()
    except:
        return Decimal("999.0")  # Fake safety - allows deposits

# ✅ Good: Fail-closed
def get_health_factor(self) -> Optional[Decimal]:
    try:
        return self._fetch_health_factor()
    except Exception as exc:
        logger.error("Failed to fetch health factor: %s", exc)
        return None  # Caller must handle None = unsafe to proceed
```

---

## Web3.py Setup

### Installation
```bash
pip install web3==6.15.0  # Latest stable as of Jan 2025
```

### Basic Connection
```python
from web3 import Web3
from decimal import Decimal

# RPC endpoint (from environment)
rpc_url = os.getenv("AAVE_RPC_URL")
w3 = Web3(Web3.HTTPProvider(rpc_url))

# Verify connection
if not w3.is_connected():
    raise ConnectionError("Failed to connect to Ethereum RPC")
```

### Network Configuration
```python
# Polygon Mumbai (testnet)
CHAIN_ID = 80001
AAVE_POOL_ADDRESS = "0x0b913A76beFF3887d35073b8e5530755D60F78C7"

# Polygon Mainnet (production)
CHAIN_ID = 137
AAVE_POOL_ADDRESS = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
```

---

## Smart Contract Interaction

### Loading Contract ABI
```python
import json
from pathlib import Path

# Load ABI from file
abi_path = Path(__file__).parent / "abis" / "AavePool.json"
with open(abi_path) as f:
    pool_abi = json.load(f)

# Create contract instance
pool_contract = w3.eth.contract(
    address=Web3.to_checksum_address(AAVE_POOL_ADDRESS),
    abi=pool_abi
)
```

### Reading State (No Transaction)
```python
def get_user_account_data(self, user_address: str) -> dict:
    """Read-only call - no gas cost, no transaction"""
    try:
        result = self.pool_contract.functions.getUserAccountData(
            Web3.to_checksum_address(user_address)
        ).call()
        
        return {
            "total_collateral": result[0],
            "total_debt": result[1],
            "available_borrow": result[2],
            "liquidation_threshold": result[3],
            "ltv": result[4],
            "health_factor": Decimal(result[5]) / Decimal(10**18)
        }
    except Exception as exc:
        logger.error("Failed to fetch user account data: %s", exc)
        raise AaveClientError("Cannot read account data") from exc
```

---

## Transaction Construction

### Pattern: Build → Sign → Send → Wait

```python
def deposit(self, asset: str, amount: Decimal) -> str:
    """
    Deposit asset to Aave pool
    
    Steps:
    1. Build transaction
    2. Sign with private key
    3. Send raw transaction
    4. Wait for receipt
    5. Verify success
    """
    
    # 1. Build transaction
    txn = self.pool_contract.functions.supply(
        Web3.to_checksum_address(asset),
        int(amount * Decimal(10**18)),  # Convert to wei
        Web3.to_checksum_address(self.user_address),
        0  # referralCode
    ).build_transaction({
        'from': self.user_address,
        'nonce': self.w3.eth.get_transaction_count(self.user_address),
        'gas': 300000,  # Estimate first, then use
        'gasPrice': self.w3.eth.gas_price,
        'chainId': self.chain_id
    })
    
    # 2. Sign transaction
    signed_txn = self.w3.eth.account.sign_transaction(
        txn, 
        private_key=self.private_key
    )
    
    # 3. Send raw transaction
    try:
        tx_hash = self.w3.eth.send_raw_transaction(
            signed_txn.rawTransaction
        )
    except Exception as exc:
        logger.error("Failed to send transaction: %s", exc)
        raise AaveTransactionError("Transaction send failed") from exc
    
    # 4. Wait for receipt (with timeout)
    try:
        receipt = self.w3.eth.wait_for_transaction_receipt(
            tx_hash, 
            timeout=120
        )
    except Exception as exc:
        logger.error("Transaction timeout: %s", exc)
        raise AaveTransactionError("Transaction timeout") from exc
    
    # 5. Verify success
    if receipt['status'] != 1:
        raise AaveTransactionError(
            f"Transaction reverted: {tx_hash.hex()}"
        )
    
    return tx_hash.hex()
```

### Gas Estimation
```python
def estimate_gas(self, function_call) -> int:
    """Estimate gas before sending transaction"""
    try:
        estimated = function_call.estimate_gas({'from': self.user_address})
        # Add 20% buffer
        return int(estimated * 1.2)
    except Exception as exc:
        logger.warning("Gas estimation failed: %s", exc)
        # Fallback to safe default
        return 300000
```

---

## ERC20 Token Approval

### Required Before Deposit
```python
def approve_token(self, token_address: str, spender: str, amount: Decimal) -> str:
    """
    Approve spender (Aave Pool) to use tokens
    
    CRITICAL: Must be called before deposit()
    """
    
    # Load ERC20 contract
    erc20_contract = self.w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_ABI  # Standard ERC20 ABI
    )
    
    # Build approval transaction
    txn = erc20_contract.functions.approve(
        Web3.to_checksum_address(spender),
        int(amount * Decimal(10**18))
    ).build_transaction({
        'from': self.user_address,
        'nonce': self.w3.eth.get_transaction_count(self.user_address),
        'gas': 100000,
        'gasPrice': self.w3.eth.gas_price,
        'chainId': self.chain_id
    })
    
    # Sign and send
    signed_txn = self.w3.eth.account.sign_transaction(txn, self.private_key)
    tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    
    if receipt['status'] != 1:
        raise AaveTransactionError("Approval failed")
    
    return tx_hash.hex()
```

---

## Error Handling Patterns

### RPC Errors
```python
from web3.exceptions import (
    ContractLogicError,
    TransactionNotFound,
    TimeExhausted
)

def safe_call_with_retry(self, func, max_retries=3):
    """Retry pattern for transient RPC failures"""
    for attempt in range(max_retries):
        try:
            return func()
        except (ConnectionError, TimeExhausted) as exc:
            if attempt == max_retries - 1:
                raise AaveClientError("RPC connection failed") from exc
            logger.warning(f"RPC error (attempt {attempt+1}/{max_retries}): {exc}")
            time.sleep(2 ** attempt)  # Exponential backoff
```

### Contract Reverts
```python
try:
    tx_hash = self.deposit(asset, amount)
except ContractLogicError as exc:
    # Contract rejected transaction (e.g., insufficient allowance)
    logger.error("Contract logic error: %s", exc)
    raise AaveOperationError("Deposit rejected by contract") from exc
```

---

## Testing Strategies

### Mock Web3 Provider
```python
from unittest.mock import Mock, patch

@pytest.fixture
def mock_w3():
    w3 = Mock(spec=Web3)
    w3.is_connected.return_value = True
    w3.eth.chain_id = 80001
    w3.eth.gas_price = 30000000000
    return w3

def test_get_health_factor(mock_w3):
    client = Web3AaveClient(w3=mock_w3)
    
    # Mock contract call
    mock_w3.eth.contract.return_value.functions.getUserAccountData.return_value.call.return_value = (
        100000000000000000000,  # total_collateral
        50000000000000000000,   # total_debt
        50000000000000000000,   # available_borrow
        8000,                    # liquidation_threshold
        7500,                    # ltv
        2000000000000000000      # health_factor = 2.0
    )
    
    hf = client.get_health_factor()
    assert hf == Decimal("2.0")
```

### Integration Test (Mumbai)
```python
@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="Integration tests require testnet connection"
)
def test_deposit_mumbai():
    """Real transaction on Mumbai testnet"""
    client = Web3AaveClient(
        rpc_url=os.getenv("MUMBAI_RPC_URL"),
        private_key=os.getenv("TEST_PRIVATE_KEY")  # Test wallet only!
    )
    
    # Use test USDC on Mumbai
    tx_hash = client.deposit(
        asset="0x52D800ca262522580CeBAD275395ca6e7598C014",  # USDC Mumbai
        amount=Decimal("0.1")
    )
    
    assert tx_hash.startswith("0x")
```

---

## Security Best Practices

### 1. **Never Log Private Keys**
```python
# ❌ Bad
logger.info(f"Using private key: {private_key}")

# ✅ Good
logger.info("Initialized Web3 client with configured wallet")
```

### 2. **Validate Addresses**
```python
def _validate_address(self, address: str) -> str:
    """Ensure address is checksummed"""
    if not Web3.is_address(address):
        raise ValueError(f"Invalid Ethereum address: {address}")
    return Web3.to_checksum_address(address)
```

### 3. **Separate Test and Production Wallets**
```python
# ❌ Bad: Same wallet for test and prod
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# ✅ Good: Environment-specific
if os.getenv("ENV") == "production":
    PRIVATE_KEY = os.getenv("PROD_PRIVATE_KEY")
else:
    PRIVATE_KEY = os.getenv("TEST_PRIVATE_KEY")
```

---

## Ultra AutoTrade Integration

### Apply to Web3AaveClient

```python
# backend/app/aave/web3_client.py

from web3 import Web3
from decimal import Decimal
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class Web3AaveClient:
    """
    Web3.py-based Aave V3 client
    
    Implements:
    - get_health_factor() - Read user account data
    - deposit() - Supply assets to Aave pool
    - withdraw() - Withdraw assets from Aave pool
    
    Security:
    - Fail-closed on errors
    - Explicit error propagation
    - No silent failures
    """
    
    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        pool_address: str,
        chain_id: int
    ):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Ethereum RPC")
        
        self.private_key = private_key
        self.user_address = self.w3.eth.account.from_key(private_key).address
        self.pool_address = Web3.to_checksum_address(pool_address)
        self.chain_id = chain_id
        
        # Load contract (ABI from file or hardcoded)
        self.pool_contract = self._load_pool_contract()
    
    def get_health_factor(self) -> Optional[Decimal]:
        """
        Fetch current health factor
        
        Returns:
            Decimal if successful, None if error (fail-closed)
        """
        try:
            result = self.pool_contract.functions.getUserAccountData(
                self.user_address
            ).call()
            
            # result[5] is health factor in wei (18 decimals)
            return Decimal(result[5]) / Decimal(10**18)
        except Exception as exc:
            logger.error("Failed to fetch health factor: %s", exc)
            return None  # Fail-closed: None = unsafe to proceed
    
    def deposit(self, asset: str, amount: Decimal) -> str:
        """
        Deposit asset to Aave pool
        
        Prerequisites:
        - Token approval must be done first (approve_token)
        
        Returns:
            Transaction hash
        
        Raises:
            AaveTransactionError on failure
        """
        # Implementation follows pattern above
        pass
    
    # ... (withdraw, approve_token, etc.)
```

---

## References

- Aave V3 Docs: https://docs.aave.com/developers/
- Web3.py Docs: https://web3py.readthedocs.io/
- Polygon Mumbai: https://mumbai.polygonscan.com/
- Ultra AutoTrade: `docs/07_aave_operation_logic.md`

---

**Next Steps**:
1. Implement `get_health_factor()` first (read-only, no gas)
2. Add unit tests with mocked Web3
3. Test on Mumbai testnet
4. Implement `deposit()` with approval flow
5. Add integration tests
