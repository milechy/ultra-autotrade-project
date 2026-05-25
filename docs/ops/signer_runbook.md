# Signer Operation Runbook (P0-17.3)

> **Scope:** Operator wallet を Safe multisig (3 of N) で運用するための実機手順。signer 選定そのもの (P0-17.1) は別タスクで決定済みと仮定し、本書は **「日々どう署名し、異常時にどう rotate するか」** に集中する。
>
> **Related Asana:** P0-17.3 (Signer 運用 runbook + 復旧手順), P0-17 (Operator wallet 確保), P0-17.1 (3 signer 選定)
> **Owner:** Owner + 2 signers
> **Coupling:** `docs/ops/backup_restore_runbook.md §3` (wallet 鍵 restore)

---

## 0. 構成サマリ (placeholder — P0-17.1 確定後に更新)

| 項目 | 値 | 出典 |
|---|---|---|
| Multisig 種別 | Safe (旧 Gnosis Safe) v1.4.1+ | https://safe.global |
| Threshold | 3 of N (N ≥ 3、通常 N = 3) | P0-17.1 で決定 |
| Network | Base mainnet (chainId 8453) | `.env.production` `NEXT_PUBLIC_DEFAULT_CHAIN_ID` |
| Operator wallet address | (P0-17 確定後に記入) | `.env.production` `OPERATOR_WALLET_ADDRESS` |
| Signer 1 / 2 / 3 EOA | (P0-17.1 確定後に記入) | 暗号 vault |

> **Threshold = N 厳禁。** N - 1 (最低 1 名脱落許容) は最低条件。本 MVP は 3-of-3 を許容するが、4-of-5 が推奨。

---

## 1. 日常運用 (Routine Signing)

### 1.1 Operator wallet が受け取る tx の種類

| Tx 種別 | 起票元 | 例 |
|---|---|---|
| Fee withdrawal | backend (P0-19 yield_excess) | user vault → operator wallet 送金後の operator → treasury 集約 |
| Parameter update | Owner manual | `FeeConfigV10` の monthly_cap 更新 |
| Emergency move | On-call | 鍵流出疑いで全額 cold wallet に退避 |

### 1.2 Signing flow (Safe UI)

1. **Proposer** が Safe Web UI で tx 起票
   - Receiver address は必ず allowlist (`docs/ops/treasury_allowlist.md` — 別途整備) から
   - Amount は小数 4 桁まで確認、桁誤り防止に `0.01 USDC` でテスト送金を先行
2. **Signer 1/2/3** が各 HW wallet で署名
   - 署名前に **Safe UI の Decoded Data タブで関数名と引数を必ず確認**
   - 不一致 (関数 transfer のはずが multicall になっている 等) なら即停止 → §3 escalation
3. Threshold 到達後、誰でも Execute 可能
4. Tx hash を Slack #ops に貼り、Etherscan 確認

### 1.3 署名直前チェックリスト

- [ ] HW wallet のディスプレイで **Receiver / Amount / Token** を目視確認
- [ ] Receiver が allowlist に存在
- [ ] Nonce が Safe UI 表示と一致 (replay / front-run 防止)
- [ ] gasPrice が現状の Base ガス価格 ±50% 以内
- [ ] 4-byte selector を https://www.4byte.directory/ で逆引きし関数名一致

---

## 2. Quarterly Health Check (四半期)

| # | 項目 | 担当 | 期待 |
|---|---|---|---|
| 1 | Owner + 各 signer の HW wallet 起動・ファームウェア更新 | 各 signer | latest |
| 2 | 残高確認 (operator wallet, multisig) | Owner | 想定 ±5% |
| 3 | Safe contract 自体のアップグレード有無確認 | Owner | v1.4.1+ |
| 4 | Allowlist 棚卸し | Owner | 不要 address 削除 |
| 5 | 監視ボット (alert on outgoing tx) の動作確認 | On-call | 1 円送金 → アラート受信 |
| 6 | 本 runbook の Drill Log (§7) 1 回更新 | Owner | drill PASS |

---

## 3. Incident — Signer Compromised / Lost

### 3.1 検知条件 (いずれか 1 つで Tier S)

- HW wallet 物理紛失 (signer 申告)
- vault 復号 passphrase 漏洩疑い
- Operator wallet または multisig からの **想定外 outgoing tx** (P0-11 Aave Oracle monitor / alert bot で検知)
- Signer EOA が phishing 兆候 (suspicious sign request の報告)

### 3.2 対応フロー (15 分以内)

```
[T+0]   Slack #ops に "SIGNER INCIDENT — <severity> — <signer_id>" 宣言
[T+5]   On-call が backend を emergency_stop (state.json OR-logic ON)
        ※ docs/ops/backup_restore_runbook.md §4 参照
[T+10]  残 signer (threshold 満たすメンバー) で集合通話
[T+15]  rotate 要否決定 (rotate / 監視継続 / 様子見)
```

### 3.3 Signer Rotate 手順 (Safe `swapOwner`)

```
1. 新 signer 候補の EOA を vault から生成 (Ledger 等で新規 path)
2. Safe Web UI > Settings > Owners > "Replace owner"
   旧 signer EOA → 新 signer EOA
3. 既存 threshold で署名 (旧 signer は使わない)
4. Execute → tx hash を Etherscan 確認
5. 旧 signer 鍵を破棄 (HW wallet wipe / 紙 backup シュレッダー)
6. .env.production の OPERATOR_WALLET_ADDRESS は変えない (multisig address は不変)
   ただし alert bot の許可 signer リストは更新
7. backup_restore_runbook §3.1 の表を更新
8. Slack #ops に "ROTATE COMPLETE — <tx_hash>" 宣言
```

### 3.4 Operator wallet 自体を replace する場合 (multisig 流出)

- multisig contract 自体を新規 deploy (旧から全資産 transfer 後)
- `.env.production` `OPERATOR_WALLET_ADDRESS` 更新 → backup_restore_runbook §2 で反映
- DB の operator_address 参照を migration で更新

---

## 4. 鍵管理 (3 拠点冗長)

| 拠点 | 媒体 | 暗号 | 復号鍵保管 | 触る人 |
|---|---|---|---|---|
| プライマリ | HW wallet (Ledger/Trezor) | デバイス標準 | 持ち主物理 | 各 signer 自身のみ |
| セカンダリ | Encrypted file (`age` or `gpg`) | passphrase | Recovery sheet (封緘) | Owner + Backup signer |
| 紙バックアップ | Steel plate (Cryptosteel 等) | 24-word mnemonic | 物理金庫 | Owner のみ閲覧可 |

### 4.1 禁止事項 (ABSOLUTE)

- ❌ Mnemonic を平文で写真撮影
- ❌ Mnemonic を任意のクラウド storage (iCloud / Google Photos / Notion / Dropbox / GitHub) に保存
- ❌ Mnemonic を任意のチャット (Slack / Telegram / LINE / Email) に送信
- ❌ `pbcopy` / `xclip` / clipboard manager に mnemonic を載せる
- ❌ Private key を `.env` 以外のファイルに書く
- ❌ Production の `.env.production` を staging container と共有

CLAUDE.md security rules #1, #7, #8 と完全整合。

---

## 5. Escalation

| 重大度 | 条件 | 通知 | SLA |
|---|---|---|---|
| Tier S | 鍵流出疑い、想定外 outgoing tx 検出 | Owner phone (B-2 経路) + Slack #ops | 15 min |
| Tier A | Signer 1 名物理紛失 (流出兆候なし) | Slack #ops | 1 h |
| Tier B | HW wallet ファームウェア要更新 / quarterly drill 未実施 | Slack #ops daily summary | 翌営業日 |

---

## 6. 関連実装 / コード接点

| 領域 | 場所 | 役割 |
|---|---|---|
| Operator wallet address | `.env.production` `OPERATOR_WALLET_ADDRESS` | backend が fee transfer 先として参照 |
| Outgoing tx alert | (P0-11 W2-15 で実装) backend/app/aave/oracle_monitor.py 隣接 | 想定外 tx で emergency_stop |
| Fee transfer 経路 | P0-19 (Tier S) yield_excess transfer | user → operator wallet |
| Scoped signing | P0-15 (Tier S) Privy scoped delegated | fee transfer のみ自動署名 |

---

## 7. Drill Log

| 実施日 | Drill 種別 | 結果 | 担当 | 備考 |
|---|---|---|---|---|
| (template) 2026-MM-DD | Signing flow / Rotate / Lost-key | ✅/❌ | name | - |

---

## 参照

- `docs/ops/backup_restore_runbook.md` — wallet 鍵 restore (W0-1)
- `docs/13_security_design.md §10` — 鍵管理セキュリティ要件
- `docs/33_emergency_stop_governance.md` — 緊急停止ガバナンス
- Safe (Gnosis) docs: https://docs.safe.global/
- Asana P0-17 / P0-17.1 / P0-17.3
