---
name: defi-aave-review
description: Review Aave V3 related code changes for security and correctness. Use when modifying files in backend/app/aave/, reviewing Health Factor logic, Decimal calculations, approve/supply transactions, or rebalance operations.
---

# Aave V3 Code Review Skill

## When to Use
- Any change to `backend/app/aave/` files
- Health Factor calculation or threshold logic
- Decimal vs float operations in financial code
- approve + supply transaction flows
- Rebalance service modifications

## Review Checklist

### 1. Health Factor Safety
- [ ] HF取得失敗時は即NOOP（fail-safe）。`health_factor is None` → NOOP
- [ ] WITHDRAW後の推定HFを計算しているか（`min_health_factor_post`は事後HF）
- [ ] HF < 1.6 → HARD_STOP が維持されているか
- [ ] HF計算にDecimal型を使用しているか（floatは禁止）

### 2. Transaction Safety
- [ ] nonce はトランザクション直前に取得しているか（stale nonce防止）
- [ ] gas推定が適切か（ハードコード値の妥当性確認）
- [ ] approve → supply の順序が正しいか

### 3. Decimal Precision
- [ ] 金額計算は全てDecimal型か
- [ ] `float` が混在していないか（`grep -n "float" <file>`で確認）
- [ ] APIレスポンスのDecimalがJSON文字列化される前提でフロントが対応しているか

### 4. Emergency Stop Logic
- [ ] emergency_stop フラグはOR論理か（手動停止を自動が上書きしない）
- [ ] state.json のパーミッションが適切か
- [ ] SAFE_MODE → HARD_STOP の遷移が正しいか

### 5. Authentication & Authorization
- [ ] /auth/register はINITIAL_ADMIN_EMAIL環境変数で制限されているか
- [ ] JWT検証でDB引き直しがあるか（roleのclaim信用禁止）
- [ ] REBALANCE_TOKEN_SECRETが空文字デフォルトでないか

## Known Patterns
- HF < 1.6 → 自動HARD_STOP（Security Rule #2）
- クールダウン: Aave操作間10分（Security Rule #5）
- 単一取引上限: 総資産の10%（Security Rule #3）
- Polygon/Arbitrum の V3 コントラクトアドレスを使用
