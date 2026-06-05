# 49. 非カストディ Aave supply — DoD 機械判定 & 出荷後ゲート検証手順

対象: Asana P0-1「非カストディ on-chain Aave (USDC supply) opt-in」(1215363789384766)

このドキュメントは、非カストディ supply の **DoD 1-4 を実 tx から機械判定する手順**と、本番成立に必須の**出荷後ゲート2項目の検証手順**を明文化する。DoD は「basescan/実 tx で機械判定」が要件であり、コード+ログでの担保では不可。

---

## 0. 背景 (§14a custodial 事故の再発防止)

旧 custodial 経路では、サーバー長期鍵が `onBehalfOf=サーバー` で署名し、partner 資産がサーバー帰属で混在する事故が発生した。本線は CEX auto のまま、opt-in の高コントロールモードとして Privy Session Signer + off-chain Policy Engine + **partner 本人署名**で supply を実行する。サーバー長期鍵は一切署名しない。

- サーバー長期鍵 (出現禁止): `0x04666D72D4eB21C2336FE360FB20C093Da291016`
- 署名主体: partner の Privy embedded wallet (秘密鍵はサーバーに渡らない)
- supply の `onBehalfOf` = partner wallet (aToken は partner に mint)

---

## 1. DoD 1-4 (実 tx 機械判定)

| # | 判定項目 | 機械判定方法 |
|---|----------|--------------|
| 1 | `from` = 登録済 Privy Session Key 群 または partner wallet | receipt.from を allowed 集合と照合 |
| 2 | supply の `onBehalfOf` = 当該 partner の Privy wallet と完全一致 | tx.input (supply calldata 第3引数) をデコード |
| 3 | aUSDC mint 先 = partner | receipt.logs の aToken `Transfer(from=0x0 → partner)` を検出 |
| 4 | サーバー長期鍵が `from` / `msg.sender` / 全 internal tx 署名者に一切出現しない | tx 内全アドレス集合にサーバー鍵が非出現 |

### 判定ツール

```bash
# 既存の supply tx ハッシュを入力に DoD 1-4 を機械判定 (鍵不要・読み取り専用)
python3 scripts/verify_dod_onchain.py \
    --tx <SUPPLY_TX_HASH> \
    --partner <PARTNER_WALLET> \
    --atoken <aUSDC_ADDRESS> \
    [--session-key <PRIVY_SESSION_KEY> ...] \
    [--server-key <SERVER_KEY> ...] \
    [--rpc <RPC_URL>]
# 終了コード 0 = DoD 1-4 ALL PASS、1 = いずれか FAIL
```

ロジックは `backend/app/aave/dod_verifier.py` (ネットワーク非依存の純関数) に実装。
RPC なしのユニットテストは `backend/tests/test_dod_verifier.py`。

### staging 実証 (Base Sepolia) — 完了

参照 tx `0xc819b1407a9e9ecedc36b823543b423cf281c73e5573b8b2bca1d8bccf1aa2eb` に対し DoD 1-4 ALL PASS を機械判定済み。

```
[PASS] DoD1_from:            from=0x7f93...a0ff (partner)
[PASS] DoD2_onBehalfOf:      onBehalfOf=0x7f93...a0ff = partner 完全一致
[PASS] DoD3_aUSDC_mint:      aToken mint(from=0x0)→0x7f93...a0ff を検出
[PASS] DoD4_server_key_absent: サーバー鍵 0x04666d72... は tx 内アドレスに非出現
```

- partner: `0x7f93e7D52428A33cA36acD5D7B1C576d5182a0Ff`
- aUSDC (Base Sepolia): `0x10F1A9D11CDf50041f3f8cB7191CBE2f31750ACC`
- basescan: https://sepolia.basescan.org/tx/0xc819b1407a9e9ecedc36b823543b423cf281c73e5573b8b2bca1d8bccf1aa2eb

---

## 2. 出荷後ゲート (必須 — 未達なら本番 non-custodial 成立としない)

staging PASS だけでは本番成立としない。本番 deploy は別フロー (§22) で実施した後、以下2ゲートを**実 tx で**通過して初めて non-custodial 成立とする。

### ゲートA: 本番 Mainnet 初 supply 実 tx の DoD 1-4 再検証

本番 (Base Mainnet, chain 8453) で最初の partner supply 実 tx に対し DoD 1-4 を再判定する。

```bash
python3 scripts/verify_dod_onchain.py \
    --tx <MAINNET_FIRST_SUPPLY_TX> \
    --partner <PARTNER_WALLET_MAINNET> \
    --atoken <aUSDC_MAINNET_ADDRESS> \
    --rpc <BASE_MAINNET_RPC>
# 期待: 終了コード 0 (DoD 1-4 ALL PASS)
```

- aUSDC (Base Mainnet) と Pool アドレスは `backend/app/aave/config.py` の mainnet 設定を使用すること。
- basescan (mainnet: https://basescan.org/tx/<hash>) で from / onBehalfOf / aToken mint 先 / サーバー鍵非出現を**目視でも**裏取りする。
- **合格条件**: ツール exit 0 かつ basescan 表示と一致。

### ゲートB: 2 partner 以上 × SUPPLY/WITHDRAW の帰属分離・非混在

「橋口 approve で山本 wallet 執行になる」致命構造の排除を実 tx で確認する。最低 2 partner、各 partner について SUPPLY と WITHDRAW の両方の実 tx を用意する。

各 tx について:

```bash
# SUPPLY: from/onBehalfOf=当該 partner、aToken mint 先=当該 partner
python3 scripts/verify_dod_onchain.py --tx <SUPPLY_TX_P1> --partner <P1> --atoken <aUSDC> --rpc <RPC>
python3 scripts/verify_dod_onchain.py --tx <SUPPLY_TX_P2> --partner <P2> --atoken <aUSDC> --rpc <RPC>
```

WITHDRAW は `withdraw(asset, amount, to)` であり、`to` = 当該 partner、`from` = 当該 partner を basescan + receipt で確認する (本ツールは supply 専用のため WITHDRAW は basescan 目視 + receipt.from 照合で判定)。

**帰属分離・非混在チェックリスト** (2 partner P1/P2 で実施):

- [ ] P1 SUPPLY: from=P1, onBehalfOf=P1, aUSDC mint 先=P1
- [ ] P1 WITHDRAW: from=P1, withdraw `to`=P1
- [ ] P2 SUPPLY: from=P2, onBehalfOf=P2, aUSDC mint 先=P2
- [ ] P2 WITHDRAW: from=P2, withdraw `to`=P2
- [ ] **クロス非混在**: P1 の tx に P2 アドレスが onBehalfOf/mint 先として出現しない (逆も同様)
- [ ] 全 tx でサーバー長期鍵 `0x04666D72...` が非出現 (DoD4)

**合格条件**: 全チェックボックス green。1つでも他 partner / サーバー鍵への帰属があれば不合格 → 本番 non-custodial 成立としない。

---

## 3. 一切しないこと (スコープ外)

- Safe / ERC-4337 必須構成の実装 (研究トラック)
- CEX 経路への変更
- 本番 deploy 自体 (別フロー §22)

---

## 4. 関連

- 実装: `backend/app/aave/client.py` `build_deposit_txs()` / `build_withdraw_tx()` (未署名 tx 構築, onBehalfOf=partner)
- API: `backend/app/proposals/router.py` `build-tx` / `submit-tx` (`AUTO_EXECUTION_ENABLED=false` で custodial 自動実行を無効化)
- Policy: `backend/app/policy/engine.py` (USDC 限定 / velocity / cooldown / HF floor)
- ライブ実証 (新規 tx 発行型): `scripts/verify_non_custodial_staging.py`
- DoD 機械判定 (既存 tx 入力型): `scripts/verify_dod_onchain.py` + `backend/app/aave/dod_verifier.py`
