---
name: defi-security-audit
description: Run security audit checklist for Ultra AutoTrade. Use when reviewing Aikido/Snyk scan results, preparing for external security audit, checking code for vulnerabilities, or evaluating dependency updates.
---

# Security Audit Skill

## When to Use
- Aikido/Snyk スキャン結果の評価
- 外部監査準備
- 依存パッケージの脆弱性対応
- コードセキュリティレビュー

## Severity Classification

### 🔴 即修正必須（ブロッカー）
- Critical / High の脆弱性
- 認証・認可の欠陥（認証バイパス、JWT偽造）
- SQLインジェクション / XSS / SSRF
- 秘密鍵・APIキーのハードコード

### 🟡 次スプリントで対応
- Medium の脆弱性
- 依存パッケージの古いバージョン

### ⚪ 許容（理由を記録）
- Low / Informational
- OctoBot 内部コードの問題（Ultra AutoTrade非管轄）
- テストファイルのダミー値

## 対応済み既知脆弱性
- `python-jose` → `PyJWT` に移行済み（CVE-2024-33663 等）
- `elliptic` — overrides で 6.6.1 に固定
- `openai` — >=2.28.0（ログ漏洩対応）
- `pino` — overrides で ^9.0.0 に固定
- Flask debug=False、Cookie Secure 属性設定済み

## False Positive の分類
- `test_auth.py` 等のハードコードパスワード → テスト用ダミー値
- OctoBot の `configuration.py`, `tentacles_config.py` → Ultra AutoTrade 非管轄

## Security Rules チェック（CLAUDE.md 準拠）
- [ ] #1: Private keys — 環境変数のみ、ハードコード・ログ出力禁止
- [ ] #2: HF < 1.6 → 自動HARD_STOP
- [ ] #3: 単一取引上限 — 総資産の10%
- [ ] #4: 日次取引上限 — 総資産の30%
- [ ] #5: クールダウン — Aave操作間10分
- [ ] #6: emergency_stop — OR論理（手動停止は上書き不可）
- [ ] #7: .env.staging と .env.production で物理的に別キーを使用
- [ ] #8: ログのトークン/キーマスク（先頭6文字+末尾4文字）
- [ ] #9: main ブランチへの直接push禁止
- [ ] #10: LLM出力 — JSON Schema バリデーション必須

## §14a Non-Custodial 検証（誰の資産が動くか）— custodial 見落とし再発防止

> **背景 (2026-05-31 RCA)**: Aave `supply()` の `onBehalfOf` にパートナーの `wallet_address` が
> 渡らず、サーバー共通鍵アドレスが使われる custodial 実装が 5 ゲートを全スルーしてローンチ直前まで
> 検出されなかった。本セクションはその再発防止のための必須監査項目。

### 対象操作

money が動くすべての操作で本セクションのチェックを実施する:
- Aave: `supply()` / `withdraw()` / `repay()` / `borrow()`
- ERC-20: `transfer()` / `transferFrom()` / `approve()`
- その他 DeFi: LP deposit/withdraw、staking、vault deposit/withdraw

---

### チェックリスト（コードレビュー）

#### 呼び出し経路の `wallet_address` 伝播確認
- [ ] `service.py` → `client.deposit/withdraw` の呼び出しで `wallet_address` 引数を渡しているか
  ```bash
  grep -n "self\._client\.\(deposit\|withdraw\|supply\|repay\|borrow\)" backend/app/aave/service.py
  # NG 例: self._client.deposit(token, amount)  ← wallet_address 未渡し
  # OK 例: self._client.deposit(token, amount, wallet_address, private_key)
  ```
- [ ] `wallet_address` が `None` / デフォルト値で `self.account.address`（サーバー鍵）に fall-back しないか
  ```bash
  grep -n "self\.account\.address\|AAVE_WALLET_ADDRESS" backend/app/aave/client.py
  # fall-back パスが存在する場合: 必ず呼び出し側で wallet_address を渡しているか確認
  ```
- [ ] Protocol / ABC インターフェースのシグネチャ差異を確認
  ```bash
  grep -nE "def (deposit|withdraw|supply)\(" backend/app/aave/client.py
  # 2 引数 Protocol と 5 引数 Base が混在 → どちらが実際に使われているか追跡
  ```

#### `onBehalfOf` の値確認
- [ ] `Web3AaveClient.deposit()` が Aave pool の `supply(asset, amount, onBehalfOf, referralCode)` を呼ぶ際に `onBehalfOf = wallet_address` か
  ```bash
  grep -n "onBehalfOf\|supply(" backend/app/aave/client.py | head -20
  ```
- [ ] `onBehalfOf` に `self.account.address`（サーバー共通鍵）が直接ハードコードされていないか

#### テストの wallet_address 検証
- [ ] `FakeAaveClient.deposit()` が `wallet_address` を `deposit_calls` に記録しているか
  ```bash
  grep -n "deposit_calls\|wallet_address" backend/tests/test_aave_service.py
  ```
- [ ] `test_aave_client.py` に `pool_mock.functions.supply.assert_called_once_with(...)` の `onBehalfOf` 引数 assert があるか
  ```bash
  grep -n "assert_called\|onBehalfOf\|supply" backend/tests/test_aave_client.py
  ```
- [ ] E2E スクリプトが `Web3AaveClient` を直接呼ばず `AaveService` 経由か（AaveService bypass は custodial バグを隠蔽する）
  ```bash
  grep -n "Web3AaveClient\|AaveService" scripts/e2e_aave_sepolia.py scripts/aave_e2e_base.py 2>/dev/null
  ```

---

### チェックリスト（basescan 実 tx 確認）

**実行タイミング**: dry run、UAT、本番 launch 前に必ず実施。

#### Step 1: 対象 tx_hash を取得
```sql
-- staging / production: 実行済み提案を取得
SELECT p.id, p.user_id, u.wallet_address AS partner_wallet, p.tx_hash, p.executed_at
FROM proposals p
JOIN users u ON u.id = p.user_id
WHERE p.status = 'executed' AND p.tx_hash IS NOT NULL
ORDER BY p.executed_at DESC
LIMIT 5;
```

#### Step 2: basescan.org で tx を開く
`https://basescan.org/tx/<tx_hash>` を開き、以下を **目視確認**:

| 確認項目 | 期待値 | 実際の値（記録） |
|---------|--------|-----------------|
| `From` アドレス | サーバー共通鍵 (`AAVE_WALLET_ADDRESS`) | — |
| Aave supply イベントの `onBehalfOf` | **パートナーの `wallet_address`** | — |
| トークン転送の `from` | パートナーの `wallet_address` OR サーバー鍵 (approve 済みなら可) | — |
| `status` | Success | — |

> **判定基準**:
> - `onBehalfOf` = パートナー wallet → **non-custodial 正常**
> - `onBehalfOf` = サーバー共通鍵アドレス → **custodial バグ、ローンチブロッカー**

#### basescan で onBehalfOf を探す方法
1. tx ページの "Input Data" タブを開く
2. `Decode Input Data` をクリック → `onBehalfOf` 引数の値を確認
3. または "Logs" タブで `Supply` イベント → `onBehalfOf` トピックを確認

---

### 5 ゲートで見落とす構造的リスク（参考: 2026-05-31 RCA）

| ゲート | 見落とし理由 | 対策 |
|--------|-------------|------|
| pytest unit | FakeAaveClient が 2 引数で wallet 未記録 | FakeAaveClient に `wallet_address` を記録・assert 必須化 |
| pytest Web3 | `supply()` の `call_args` を assert しない | `pool_mock.functions.supply.assert_called_once_with(...)` で `onBehalfOf` 検証 |
| E2E スクリプト | AaveService を bypass して Web3AaveClient 直呼び | E2E は必ず AaveService 経由 |
| Production dry run | Aave SUPPLY 確認が「任意」かつ basescan 確認項目なし | 本セクションの Step 2 を dry run DoD に追加 |
| UAT DoD | `status=Success` のみ確認、`onBehalfOf` 確認なし | 上記 basescan チェック表を UAT DoD 条件4 に追記 |

---

### サーバー共通鍵不在チェック（コード全体）

```bash
# サーバー共通鍵アドレスが onBehalfOf / recipient に直接使われていないか
grep -rn "AAVE_WALLET_ADDRESS\|self\.account\.address" backend/app/ \
  | grep -v "# server-key-ok\|# from-address"
# ヒットした行を精査: 資産帰属の文脈で使われていれば要修正
```

## ASH (Automated Security Helper) Integration

### Running ASH Locally
```bash
# Quick scan (precommit mode)
ash --mode precommit --source-dir .

# Full scan (local mode)
ash --mode local --source-dir .

# View results
cat .ash/ash_output/reports/ash.summary.txt
open .ash/ash_output/reports/ash.html
```

### ASH Scanners
- **Bandit**: Python SAST（SQLi、ハードコードパスワード、exec呼び出し）
- **Semgrep**: 多言語パターンマッチング
- **Grype**: SCA（依存関係の脆弱性）
- **Checkov**: IaC セキュリティ（Dockerfile、docker-compose）

### CI/CD Integration
- GitHub Actions: `.github/workflows/ash-security-scan.yml`
- pre-commit: `.pre-commit-config.yaml`
- MCP: `.claude/mcp-ash.json`

### Excluded from Scan
- `octobot/` — OctoBot upstream code（責任範囲外）
- `tests/cassettes/` — VCR テストフィクスチャ
- `node_modules/`, `.next/`, `__pycache__/`
