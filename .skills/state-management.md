# state.json 管理ガイド

## state.json の役割
- **モード管理**: NORMAL / SAFE_MODE / HARD_STOP
- **緊急停止**: emergency_stop フラグ
- **回路制御**: circuit_closed フラグ
- **履歴**: ヘルスファクター履歴

## Best Practice: Explicit State Transitions

### Bad: 暗黙の状態遷移
```python
if hf < 1.6:
    mode = "HARD_STOP"  # どこで設定されたか不明瞭
```

### Good: 明示的な状態遷移
```python
def record_health_factor(self, value: Decimal) -> HealthFactorStatus:
    """
    HFを記録し、状態遷移を明示的に実行。

    状態遷移:
    - HF >= 1.8 -> NORMAL
    - 1.6 <= HF < 1.8 -> SAFE_MODE
    - HF < 1.6 -> HARD_STOP (emergency_stop=True)
    """
    if value < self._hf_emergency_threshold:
        self._trading_paused = True
        self._sync_state_file()  # 即座に永続化
        logger.critical("Emergency stop activated: HF=%s", value)
        return HealthFactorStatus(is_emergency=True)
```

## 読み取りルール
1. **ファイル不在** -> `get_default_state()` (emergency_stop=False)
2. **パースエラー** -> `get_safe_default_state()` (emergency_stop=True, fail-closed)
3. **古いタイムスタンプ** -> `is_stale()=True`

## リトライポリシー
```
エラー回数 | 動作
----------|------
1-2回     | 即座に再読み取り
3回以上   | 60秒ごとにリトライ
回復成功  | エラーカウンタリセット
```

## Best Practice: Error Surfacing

### Bad: エラーを隠蔽
```python
def read_state(self):
    try:
        return parse_json(file)
    except:
        return default_state  # どんなエラーか分からない
```

### Good: エラーを明確に区別
```python
def read_state(self) -> AaveSystemState:
    try:
        return read_system_state(self._path)
    except StateFileNotFoundError:
        logger.info("state.json not found; using default")
        return get_default_state()
    except StateFileParseError as exc:
        logger.error("Parse error: %s; using SAFE default", exc)
        self._consecutive_errors += 1
        return get_safe_default_state()
```

## 使用例
```python
from app.aave.state_manager import get_default_state_manager

manager = get_default_state_manager()

# 明示的なエラーチェック
if manager.is_stale():
    logger.warning("state.json is stale; forcing NOOP")
    return noop_result()

# 例外は呼び出し側で処理
try:
    state = manager.read_state()
except StateFileParseError as exc:
    # 安全側に倒す
    activate_emergency_stop(reason=str(exc))
```

## AaveSystemState スキーマ
```python
class AaveSystemState(BaseModel):
    emergency_stop: bool = False
    mode: AaveOperationMode = AaveOperationMode.NORMAL
    health_factor: Optional[Decimal] = None
    last_update: datetime
    reason: Optional[str] = None
    circuit_closed: bool = True
    stale_threshold_seconds: int = 300
```

## モード遷移表
| 条件 | emergency_stop | mode | circuit_closed | 結果 |
|------|----------------|------|----------------|------|
| HF >= 1.8 | False | NORMAL | True | 全操作許可 |
| 1.6 <= HF < 1.8 | False | SAFE_MODE | True | SELL のみ許可 |
| HF < 1.6 | True | HARD_STOP | True | 全操作禁止 |
| パースエラー | True | HARD_STOP | False | 全操作禁止 (fail-closed) |
