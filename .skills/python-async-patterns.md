# Python Async Patterns

**Source**: Synthesized from Antigravity Skills + Ultra AutoTrade Phase 5-6 requirements

**Purpose**: Master asyncio, concurrent programming, and async/await for high-performance backend operations

---

## When to Use Async

### ✅ Good Use Cases
1. **Parallel RPC calls** - Check multiple wallets simultaneously
2. **Background tasks** - Monitoring, reporting without blocking API
3. **I/O-bound operations** - API calls, database queries
4. **Concurrent monitoring** - Health factor checks across multiple positions

### ❌ Bad Use Cases
1. CPU-bound operations (use multiprocessing instead)
2. Simple sequential logic (adds complexity without benefit)
3. Synchronous libraries (web3.py is mostly sync)

---

## Basic Async/Await

### Simple Async Function

```python
import asyncio
from typing import List

async def fetch_health_factor(wallet: str) -> float:
    """Async wrapper around sync Web3 call"""
    # Simulate I/O operation
    await asyncio.sleep(0.1)
    
    # In reality, call sync Web3 in executor
    hf = await asyncio.to_thread(
        sync_get_health_factor, wallet
    )
    return hf

async def main():
    wallets = ["0xWallet1", "0xWallet2", "0xWallet3"]
    
    # Run concurrently
    tasks = [fetch_health_factor(w) for w in wallets]
    results = await asyncio.gather(*tasks)
    
    print(f"Health factors: {results}")

# Run
asyncio.run(main())
```

---

## Pattern 1: Parallel RPC Calls

### Problem: Sequential calls are slow

```python
# ❌ Bad: Sequential (3 seconds total)
def check_all_wallets(wallets: List[str]) -> List[float]:
    results = []
    for wallet in wallets:
        hf = get_health_factor(wallet)  # 1 second each
        results.append(hf)
    return results  # Takes 3 seconds for 3 wallets
```

### Solution: Concurrent execution

```python
# ✅ Good: Concurrent (1 second total)
import asyncio

async def check_all_wallets(wallets: List[str]) -> List[float]:
    """Check multiple wallets in parallel"""
    
    async def check_wallet(wallet: str) -> float:
        # Run sync function in thread pool
        return await asyncio.to_thread(get_health_factor, wallet)
    
    tasks = [check_wallet(w) for w in wallets]
    return await asyncio.gather(*tasks)  # All execute concurrently

# Usage
wallets = ["0xA", "0xB", "0xC"]
results = asyncio.run(check_all_wallets(wallets))
```

### With Error Handling

```python
async def check_all_wallets_safe(wallets: List[str]) -> List[Optional[float]]:
    """Check wallets with individual error handling"""
    
    async def check_wallet_safe(wallet: str) -> Optional[float]:
        try:
            return await asyncio.to_thread(get_health_factor, wallet)
        except Exception as exc:
            logger.error(f"Failed to check {wallet}: {exc}")
            return None  # Fail-closed
    
    tasks = [check_wallet_safe(w) for w in wallets]
    return await asyncio.gather(*tasks)
```

---

## Pattern 2: Background Tasks

### Problem: Blocking the API response

```python
# ❌ Bad: User waits for monitoring to finish
@router.post("/aave/rebalance")
def rebalance(request: Request):
    result = execute_rebalance(...)
    
    # This blocks the response
    run_monitoring_check()  # 5 seconds
    generate_report()       # 10 seconds
    
    return result  # User waits 15 seconds
```

### Solution: Background tasks

```python
# ✅ Good: Fire and forget
from fastapi import BackgroundTasks

@router.post("/aave/rebalance")
async def rebalance(
    request: Request,
    background_tasks: BackgroundTasks
):
    result = execute_rebalance(...)
    
    # Run in background
    background_tasks.add_task(run_monitoring_check)
    background_tasks.add_task(generate_report)
    
    return result  # User gets immediate response
```

### Long-Running Background Task

```python
import asyncio

async def continuous_monitoring():
    """Run forever in background"""
    while True:
        try:
            # Check health factors
            await check_all_positions()
            
            # Check for emergency conditions
            await check_emergency_stop()
            
            # Wait 1 minute
            await asyncio.sleep(60)
        except Exception as exc:
            logger.error(f"Monitoring error: {exc}")
            await asyncio.sleep(10)  # Brief pause on error

# Start on app startup
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(continuous_monitoring())
```

---

## Pattern 3: Mixing Sync and Async

### Web3.py is Synchronous

```python
from web3 import Web3

# This is sync
def get_health_factor_sync(wallet: str) -> float:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    # ... sync calls
    return hf
```

### Wrap in Executor

```python
import asyncio

async def get_health_factor_async(wallet: str) -> float:
    """Async wrapper for sync Web3 call"""
    
    # Run sync function in thread pool
    return await asyncio.to_thread(
        get_health_factor_sync, wallet
    )

# Or use executor explicitly
async def get_health_factor_async(wallet: str) -> float:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,  # Default executor
        get_health_factor_sync,
        wallet
    )
```

---

## Pattern 4: Timeout and Cancellation

### Timeout for RPC Calls

```python
async def get_health_factor_with_timeout(
    wallet: str,
    timeout: float = 5.0
) -> Optional[float]:
    """Get health factor with timeout"""
    
    try:
        return await asyncio.wait_for(
            get_health_factor_async(wallet),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"Timeout checking {wallet}")
        return None  # Fail-closed
```

### Cancel Tasks on Shutdown

```python
class MonitoringService:
    def __init__(self):
        self._task = None
    
    async def start(self):
        """Start background monitoring"""
        self._task = asyncio.create_task(continuous_monitoring())
    
    async def stop(self):
        """Gracefully stop monitoring"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.info("Monitoring stopped")

# App shutdown
@app.on_event("shutdown")
async def shutdown_event():
    await monitoring_service.stop()
```

---

## Pattern 5: Rate Limiting

### Problem: Too many concurrent RPC calls

```python
# ❌ Bad: 1000 concurrent calls overwhelm RPC
async def check_1000_wallets(wallets: List[str]):
    tasks = [check_wallet(w) for w in wallets]  # 1000 tasks
    return await asyncio.gather(*tasks)  # RPC crashes
```

### Solution: Semaphore for concurrency limit

```python
# ✅ Good: Limit to 10 concurrent calls
import asyncio

async def check_wallets_limited(
    wallets: List[str],
    max_concurrent: int = 10
) -> List[Optional[float]]:
    """Check wallets with concurrency limit"""
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def check_wallet_limited(wallet: str) -> Optional[float]:
        async with semaphore:  # Only 10 can run at once
            return await check_wallet(wallet)
    
    tasks = [check_wallet_limited(w) for w in wallets]
    return await asyncio.gather(*tasks)
```

---

## Pattern 6: Error Handling

### Fail-Closed on Any Error

```python
async def parallel_operation_fail_closed(items: List[str]) -> bool:
    """
    Return False if ANY operation fails
    
    Use for critical operations (e.g., emergency checks)
    """
    
    async def process_item(item: str) -> bool:
        try:
            result = await do_something(item)
            return result is not None
        except Exception as exc:
            logger.error(f"Failed to process {item}: {exc}")
            return False
    
    tasks = [process_item(item) for item in items]
    results = await asyncio.gather(*tasks)
    
    # Fail-closed: Return False if any failed
    return all(results)
```

### Partial Success Allowed

```python
async def parallel_operation_partial_ok(items: List[str]) -> List[Optional[Any]]:
    """
    Return partial results, None for failures
    
    Use for non-critical operations (e.g., reporting)
    """
    
    async def process_item_safe(item: str) -> Optional[Any]:
        try:
            return await do_something(item)
        except Exception as exc:
            logger.error(f"Failed to process {item}: {exc}")
            return None  # Continue with others
    
    tasks = [process_item_safe(item) for item in items]
    return await asyncio.gather(*tasks)
```

---

## Pattern 7: FastAPI Integration

### Async Endpoints

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/wallets/status")
async def get_wallets_status():
    """Async endpoint for concurrent checks"""
    
    wallets = ["0xA", "0xB", "0xC"]
    
    # This runs concurrently
    results = await check_all_wallets(wallets)
    
    return {
        "wallets": wallets,
        "health_factors": results
    }
```

### Dependency Injection with Async

```python
from fastapi import Depends

async def get_monitoring_service() -> MonitoringService:
    """Async dependency"""
    service = MonitoringService()
    await service.initialize()
    return service

@app.get("/status")
async def get_status(
    monitoring: MonitoringService = Depends(get_monitoring_service)
):
    status = await monitoring.get_current_status()
    return status
```

---

## Pattern 8: Testing Async Code

### pytest-asyncio

```python
import pytest

@pytest.mark.asyncio
async def test_check_wallets_concurrent():
    """Test async function"""
    
    wallets = ["0xA", "0xB"]
    results = await check_all_wallets(wallets)
    
    assert len(results) == 2
    assert all(r is not None for r in results)
```

### Mock Async Functions

```python
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_with_async_mock():
    """Test with mocked async dependency"""
    
    mock_check = AsyncMock(return_value=2.0)
    
    # Inject mock
    result = await some_function(check_func=mock_check)
    
    mock_check.assert_called_once()
    assert result == 2.0
```

---

## Ultra AutoTrade Use Cases

### Phase 5: Monitoring Service

```python
# backend/app/automation/monitoring_service.py

class MonitoringService:
    """Async monitoring with concurrent checks"""
    
    async def check_all_positions_concurrent(self) -> bool:
        """Check multiple positions in parallel"""
        
        positions = self._get_active_positions()
        
        async def check_position(pos: Position) -> bool:
            hf = await asyncio.to_thread(
                self.aave_client.get_health_factor,
                pos.wallet
            )
            return hf is not None and hf >= 1.6
        
        tasks = [check_position(p) for p in positions]
        results = await asyncio.gather(*tasks)
        
        # Fail-closed: Return False if any position is unsafe
        return all(results)
```

### Phase 6: Background Reporting

```python
# backend/app/automation/jobs.py

async def run_daily_jobs_async():
    """Async daily jobs with concurrent operations"""
    
    # Run multiple reports concurrently
    tasks = [
        generate_health_report(),
        generate_trade_summary(),
        generate_risk_analysis()
    ]
    
    reports = await asyncio.gather(*tasks)
    
    # Send all reports concurrently
    await send_notifications(reports)
```

---

## Performance Comparison

### Sequential vs Concurrent

```python
import time

# Sequential: 3 seconds
def sequential():
    start = time.time()
    for i in range(3):
        time.sleep(1)  # Simulate RPC call
    print(f"Sequential: {time.time() - start:.2f}s")

# Concurrent: 1 second
async def concurrent():
    start = time.time()
    tasks = [asyncio.sleep(1) for _ in range(3)]
    await asyncio.gather(*tasks)
    print(f"Concurrent: {time.time() - start:.2f}s")

sequential()  # 3.00s
asyncio.run(concurrent())  # 1.00s
```

---

## Best Practices

### 1. **Don't Block the Event Loop**

```python
# ❌ Bad: Blocks event loop
async def bad():
    time.sleep(10)  # Blocks everything!

# ✅ Good: Use asyncio.sleep
async def good():
    await asyncio.sleep(10)  # Other tasks can run
```

### 2. **Always Handle Cancellation**

```python
async def task():
    try:
        await long_running_operation()
    except asyncio.CancelledError:
        # Cleanup
        logger.info("Task cancelled, cleaning up")
        raise  # Re-raise to propagate
```

### 3. **Avoid Mixing Sync and Async in Same Function**

```python
# ❌ Bad: Mixing sync and async
async def mixed():
    result = sync_function()  # Blocks event loop
    await async_function()

# ✅ Good: Wrap sync in executor
async def unmixed():
    result = await asyncio.to_thread(sync_function)
    await async_function()
```

---

## References

- Python asyncio: https://docs.python.org/3/library/asyncio.html
- FastAPI async: https://fastapi.tiangolo.com/async/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- Ultra AutoTrade: `docs/08_automation_rules.md`

---

**Next Steps**:
1. Identify I/O-bound operations in Phase 5-6
2. Add async wrappers for Web3 calls
3. Implement concurrent monitoring checks
4. Test with pytest-asyncio
5. Measure performance improvements
