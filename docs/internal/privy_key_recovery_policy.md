# Privy Embedded Wallet 鍵リカバリ方針 (P1 MVP)

最終更新: 2026-05-23
オーナー: backend / wallet stream
関連 PR: feat/privy-embedded-wallet-mvp
関連 Asana: P1 (Privy 完全統合 MVP)

---

## 1. 背景

Ultra AutoTrade は Privy embedded wallet を採用し、user に EVM 秘密鍵を直接保管させない。
代わりに Privy がユーザー側 (= LINE / Email アカウント) を recovery factor として鍵を MPC で保護する。

本ドキュメントは「LINE / Email アカウントを失った場合の鍵リカバリ方針」と「ユーザー向け FAQ 雛形」を定義する。

## 2. ID プロバイダ と recovery 機構

| login method | identity provider | recovery factor (Privy 側) | recovery factor (UAT 側) |
|--------------|-------------------|----------------------------|--------------------------|
| LINE         | LINE Login OAuth  | LINE sub (line_user_id) を Privy が保持 | `users.privy_did`, `users.line_sub` を DB 保管 |
| Email (OTP)  | Privy Email OTP / magic link | Email アドレス  | `users.privy_did`, `users.email` を DB 保管 |
| Passkey      | WebAuthn (FIDO2)  | platform authenticator     | (UAT 側では privy_did 経由でのみ参照) |

Privy 内部では MPC 方式 (Shamir's Secret Sharing + TEE) で秘密鍵を分散保管しており、
`privy_did` が同一であれば LINE / Email / Passkey のいずれの login でも
同じ embedded wallet address に到達できる。

### 2.1 Privy が提供する recovery 機構の実情報

- **Email magic link** — Privy Email login の主たる recovery 経路。再ログイン時に
  `<random>@privy.io` から magic link を送付し、デバイス独立で鍵 share を再構築する。
- **Passkey** — 2024 年以降の Privy default 推奨。WebAuthn を活用し、
  platform authenticator (Touch ID / Face ID / Windows Hello) に share を保管。
  Email/LINE recovery の補強として「あれば使う」位置付け (Privy console で ON/OFF 可).
- **iCloud Keychain / Google Password Manager** — passkey の同期 (Apple/Google エコシステム内).
  UAT が直接制御するものではなく、user 環境依存。
- **Recovery password** (deprecated 系) — 旧 SDK 互換のオプション。本 MVP では使わない。
- **Embedded wallet export** — user が Privy UI から秘密鍵 / mnemonic を export 可能。
  ただし export 実行後の秘密鍵管理は user 自身に帰属し、UAT は責任を負わない (FAQ Q4 参照).

## 3. リカバリ シナリオ別ポリシー

### 3.1 LINE アカウントを失った (削除 / 凍結 / 機種変未引継ぎ)

- **同じ `privy_did` を保持していれば** Privy 側で email を 2nd factor として登録していた user は email login で復旧可。
- email を未登録の user は **鍵への access を喪失** する (Privy の MPC 仕様上 UAT 側で再生成不可)。
- UAT 側の対応:
  - 鍵 access が失われても DB 上の取引履歴・PnL は user 単位で残り続ける (read-only).
  - 新しい LINE アカウントで login し直すと **別 user (= 別 privy_did) として作成** される。資産紐付けは行わない (なりすまし防止).
  - 旧 user の資産取り戻しは KYC + 法的本人確認を経た support フロー (手動) でのみ対応 → P5 で SOP 整備.

### 3.2 Email アドレスを失った (アクセス不可)

- Privy 側 UI から email を再設定可能 (LINE login で再認証 → email 差し替え) ならば自動復旧.
- LINE login も持っていない user は **3.1 と同じく鍵 access 喪失**.

### 3.3 端末を紛失したが LINE / Email account は健在

- 新端末で再 login すれば Privy が MPC share を再配布し、**同じ wallet address** に access 復旧.
- UAT 側は `privy_did` を一意キーとしているため特別な操作は不要 (`/auth/privy/session` callback が同 `privy_did` を返す).

### 3.4 user が任意で wallet を「廃棄」したい

- Privy 側で「unlink wallet」を実施 → UAT 側は `users.wallet_address` を NULL に戻す (将来 P4 で UI 提供).
- DB 上の `privy_did` は監査ログ保存のため残置.

## 4. UAT 側 invariant

- **`users.privy_did` は一意** (migration `f6a7b8c9d0e1`). 別 user が同じ DID を持つことは無い.
- **`users.wallet_address` は一意** (migration `b2c3d4e5f6a7`). 同じ embedded wallet が複数 user に紐付くことは無い.
- `/auth/privy/session` callback は上記 invariant を守るため、衝突時は 409 を返す.
- delegated signing (= UAT bot が user 鍵で署名する) は P3 PoC で扱い、本 MVP では実装しない.

## 5. 関連 PR / 仕様

- 本 MVP: `feat/privy-embedded-wallet-mvp`
  - `PrivyProvider` を `createOnLogin: 'all-users'` + `loginMethods: ['line', 'email', 'wallet']` に
  - `usePrivyEmbeddedWallet` hook で viem WalletClient を提供
  - `POST /auth/privy/session` で `privy_did` ↔ `wallet_address` を同期
- P3 delegated signing PoC: 本 doc の rev2 を作成し、recovery 失敗時の delegated 経路 (UAT bot が代理署名で資産を救済) の境界を再定義する.
- P5 support SOP: 鍵喪失 user 向けの法的本人確認フローを別 doc で整備.

## 6. ユーザー向け FAQ (雛形)

### Q1. LINE アカウントを消したら wallet にアクセスできなくなりますか?

A. はい、Privy の鍵リカバリは LINE / Email を「本人証明」として使うため、
両方とも失うと wallet への access ができなくなります。
**LINE login を有効化した時点で必ず email も追加登録すること**を強く推奨します。

### Q2. 端末を変えたら wallet はどうなりますか?

A. 同じ LINE / Email で login すれば、同じ wallet address に自動で復旧します。
秘密鍵を端末ローカルに保管しているわけではないので、安心して機種変できます。

### Q3. 別の LINE アカウントでログインしたら同じ wallet が見られますか?

A. いいえ、別 LINE アカウントは UAT 上で別 user として扱われます。
これはなりすまし防止のための制約で、Privy 仕様としても同一 `privy_did` に到達できないためです。

### Q4. 秘密鍵をエクスポートしたい

A. Privy UI から手動 export 可能ですが、UAT は秘密鍵の保管責任を負わなくなる為、
export 後の自衛 (HW wallet 等への移管) は user 責任となります。
export 後も UAT 側の自動運用は継続可能ですが、Privy 側 wallet が deactivate されると
`/auth/privy/session` から新 wallet を発行する必要があります (= 旧資産の自動移管はしない).

### Q5. wallet を完全に消したい (退会)

A. UAT 退会フロー (将来 P5) からリクエストすると、DB 上の wallet_address を null に
戻し、Privy 側でも unlink します。`privy_did` は監査保存のため一定期間残ります。

### Q6. Passkey (Touch ID / Face ID) を登録するとどう変わりますか?

A. Privy console から passkey を有効化すると、再ログイン時に LINE / Email magic link を
受け取らずとも、端末の生体認証だけで wallet に access できるようになります。
ただし passkey は端末ローカル (もしくは Apple/Google アカウント経由の同期) に
紐付くため、**LINE / Email も併用する** ことで端末喪失時の復旧経路を確保してください。

### Q7. 鍵がロックされて何もできなくなりました。サポートに復旧してもらえますか?

A. UAT 側では Privy の MPC share を再生成できないため、Privy 自身の recovery
(magic link / passkey / passwordless 等) を試した上でも wallet にアクセスできない場合は、
UAT support に KYC + 法的本人確認 (運転免許 / マイナンバーカード等) を提出いただき、
**新しい wallet に資産を移し替えるリカバリ手続き** (手動・有償・SLA 数営業日) を実施します。
詳細は P5 で公開する support SOP を参照してください。

---

(本ドキュメントは P3 完了時点で更新予定。delegated signing と recovery の境界が確定する.

関連: [[privy-delegated-signing-poc-design]] / [[paste-verbatim-not-summary]])
