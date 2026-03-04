# Anti-Slop パターン辞書

LLMが学習データの分布に引きずられて生成しがちなNGパターンを定義。

## FastAPI

- ❌ `async def` でブロッキングI/O (`time.sleep`, `open()`, `requests.get()`) → ✅ `def` を使うか `asyncio.to_thread()` で包む
  - なぜ: async def 内のブロッキングはイベントループを止める
- ❌ `ORJSONResponse` / `UJSONResponse` → ✅ `response_model` (Pydantic v2) を使う
  - なぜ: Pydantic v2のシリアライザで十分高速
- ❌ `@app.on_event("startup")` → ✅ `lifespan` context manager を使う
  - なぜ: on_event は FastAPI で deprecated

## SQLAlchemy

- ❌ `session.query(Model)` (1.x style) → ✅ `select(Model)` (2.0 style)
  - なぜ: SQLAlchemy 2.0 で query() は legacy
- ❌ `Column(Integer, primary_key=True)` → ✅ `mapped_column(Integer, primary_key=True)` (Mapped typing)
  - なぜ: 2.0 の型安全パターン

## Pydantic

- ❌ `class Config:` (v1 style) → ✅ `model_config = ConfigDict(...)` (v2 style)
  - なぜ: Pydantic v2 で Config class は deprecated
- ❌ `orm_mode = True` → ✅ `from_attributes = True`
  - なぜ: v2 でリネーム済み

## ccxt / Exchange

- ❌ `exchange.fetch_balance()` を毎回呼ぶ → ✅ キャッシュ(TTL 30s)して再利用
  - なぜ: レート制限に引っかかる
- ❌ `float` で金額計算 → ✅ `Decimal` で計算、ccxt に渡す直前に `float()` 変換
  - なぜ: 浮動小数点の丸め誤差

## Python General

- ❌ `except Exception: pass` → ✅ 具体的な例外 + ログ + 再送出
  - なぜ: サイレントに握りつぶすと障害調査不能
- ❌ `os.path.join()` → ✅ `pathlib.Path()` を使う
  - なぜ: 型安全で可読性が高い
