# v4 AA (Smart Wallet + paymaster) staging-v4 実機検証 runbook

> Privy Smart Wallet (ERC-4337) + paymaster のガス肩代わり実行が **実際に動くか**を
> staging-v4 で検証する手順。消費者経路 (liff-chat) を主対象とする。
> 「ETH を持たない消費者が supply を完走できる」= 検証ゴール。
>
> 作成: 2026-06-19 / 関連: docs/privy-aa-paymaster-design.md / Asana 1215697060370824

---

## 0. 前提（コードは main に揃っている）

| 要素 | PR | 状態 |
|---|---|---|
| slice5 permissionless / 4a Provider / 4b 登録 / 3b backend / 7 PoC | #799/#800/#801/(#794/#796)/#789 | ✅ main |
| 4c-1 消費者署名 UserOp 化 (liff-chat) | #802 | ✅ main |
| 4c-2 partner 2経路 | #803 | ⏳ 未マージ（消費者検証には不要） |

→ **main を staging-v4 にデプロイすれば消費者経路を検証できる**。

## 1. 小林さん外部セットアップ（前提・未完なら先に）

- [ ] Pimlico: Base Sepolia 用 paymaster の **sponsorship policy 作成 + 原資チャージ**（実 sponsor に必要）
- [ ] Privy Dashboard: Smart Wallet 有効化 + Pimlico 接続（track C 済のはず）

## 2. staging-v4 への env 投入 + デプロイ（本番 VPS `/opt/ultra-autotrade`）

```bash
# (a) backend: SCW ユーザーの submit-tx 検証に使う bundler URL（未設定だと SCW 経路は 503）
printf '\nBUNDLER_RPC_URL=https://api.pimlico.io/v2/84532/rpc?apikey=pim_xxx\n' \
  >> /opt/ultra-autotrade/.env.staging-v4

# (b) main を pull してデプロイ（NEXT_PUBLIC_* はビルド時埋め込み → frontend 再ビルド必須）
cd /opt/ultra-autotrade && git pull origin main
./scripts/deploy_staging_v4.sh

# (c) 稼働確認
curl http://127.0.0.1:8083/health   # → 200
```

> ⚠️ `BUNDLER_RPC_URL` が未設定だと、SCW ユーザーの submit-tx は **503**（fail-closed / slice3b）。

## 3. 検証手順（消費者 AA フロー）

### 3.1 テスト消費者を用意
1. staging-v4 の liff-chat（`https://staging-v4.ultra-auto-trade.com/liff-chat`）に**新規消費者**としてログイン
   （Privy email/SNS → embedded EOA + Smart Wallet 自動生成 → `SmartWalletRegistrar` が backend に自動登録）
2. **SCW 登録確認**（staging-v4 DB）:
   ```bash
   docker exec ultra-autotrade-postgres-staging-v4 psql -U ultra -d ultra_autotrade_staging_v4 \
     -c "SELECT id, email, wallet_address, smart_wallet_address FROM users ORDER BY id DESC LIMIT 3;"
   ```
   → `smart_wallet_address` が埋まっていること（NULL なら Registrar 未動作＝EOA 経路になる）
3. **SCW が ETH ゼロ**であること（= ガス肩代わりの検証点）。BaseScan(sepolia) で SCW アドレスの ETH 残高 0 を確認

### 3.2 supply を実行
4. SCW に **テスト USDC**（Base Sepolia faucet）を入れる（supply には USDC 残高が要る。ガスは paymaster が肩代わり＝ETH 不要）
5. その消費者向けに **SUPPLY proposal**（少額）を作成（admin が `/api/proposals` で `user_id=<消費者>` 指定）
6. liff-chat で proposal を **承認** → `ProposalSignSheet` → 署名（ETH 不要のまま完走するはず）

### 3.3 結果検証（success の定義）
7. liff-chat が「実行しました」表示 / proposal が `executed`:
   ```bash
   docker exec ultra-autotrade-postgres-staging-v4 psql -U ultra -d ultra_autotrade_staging_v4 \
     -c "SELECT id, status, tx_hash, expected_from FROM proposals ORDER BY id DESC LIMIT 3;"
   ```
   → `status='executed'` / `expected_from` = SCW アドレス
8. **Pimlico ダッシュボード**で sponsored UserOp が記録され、`actualGasCost` が表示される
9. backend ログに `submit-tx: proposal N UserOp verified via bundler` が出る:
   ```bash
   docker logs ultra-autotrade-backend-staging-v4 2>&1 | grep -i "UserOp verified"
   ```

## 4. 合格基準（これが揃えば「経路は動く」）
- [ ] SCW が ETH ゼロのまま supply が `executed` になった
- [ ] `verify_userop_receipt` が success / sender==SCW を確認（backend ログ）
- [ ] Pimlico に sponsored UserOp + actualGasCost が記録された

## 5. トラブルシュート
| 症状 | 原因 | 対処 |
|---|---|---|
| submit-tx が 503 | `BUNDLER_RPC_URL` 未設定 | 2.(a) を設定し再デプロイ |
| UserOp が paymaster で弾かれる | sponsorship policy / 原資未設定 | 1. の Pimlico 設定 |
| EOA 経路になる（ETH を要求される）| `smart_wallet_address` 未登録 | 3.1-2 で NULL → Registrar / Privy SW 設定を確認 |
| `useSmartWallets().client` が undefined | Privy Dashboard で Smart Wallet 未有効化 | track C 確認 |

## 6. 検証後に Claude に渡すもの
- 合格基準 4 の各 ✅/❌ + backend ログ該当行 + Pimlico の actualGasCost 値
- 失敗時はエラー文面（submit-tx レスポンス / backend ログ / Pimlico ダッシュボード）

→ 動作確認できたら、残り（user/withdraw の SCW 化 / slice6 F-9 expense 再設計 / partner 経路 #803 マージ）に進む。
