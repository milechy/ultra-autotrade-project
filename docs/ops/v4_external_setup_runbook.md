# v4 外部セットアップ runbook（人間専権 / 小林さん）

> v4 を前進させる残作業のうち、**Claude Code が実行できない外部セットアップ**を1枚に集約する。
> いずれも「dev VPS のコーディング」ではなく、ダッシュボード操作・ベンダー契約・本番 VPS の env/再ビルド。
> 各ブロックを解除すると、対応する実装スライスに Claude が即着手できる（「解除後に動くもの」を明記）。
>
> 作成: 2026-06-17 / 関連: `docs/privy-aa-paymaster-design.md`, Asana 1215697060370824 / 1215079129137410 / 1215312700483149

---

## 全体像（依存関係）

```
A. Pimlico キー ──→ スライス7 PoC 実行 ──→ (PASS) ──→ スライス2-6 実装 ┐
                                                                        ├─→ ガス肩代わり完成
C. Privy Smart Wallet 有効化 ───────────────────────→ スライス4 配線 ──┘

B. LINE LIFF アプリ作成 ──→ staging-v4 に LIFF_ID 投入 ──→ v4 LINE 配布の実機検証
```

A と C は paymaster（ETH 不要化）系。B は LINE 配布系。独立に進められる。

---

## A. Pimlico セットアップ（Paymaster PoC を回す）★最優先

**目的**: スライス7 PoC（`frontend/scripts/poc/paymaster-poc.mjs`）を実行し、Base Sepolia 上で
sponsored UserOp が `status=1` を返し `actualGasCost` が取れることを確認する。これがスライス4 承認ゲートの前提。

**手順**
1. https://dashboard.pimlico.io でアカウント作成（GitHub ログイン可）
2. API キーを発行（ネットワーク: **Base Sepolia** を含むもの）
3. （任意）Sponsorship Policy を作成（verifying paymaster で sponsor する場合。テストネットは無くても通ることが多い）

**取得する値と置き場所**
| 値 | 置き場所 |
|---|---|
| Pimlico API キー | 実行時に環境変数で渡すだけ（どの .env にも保存不要）|
| (任意) Sponsorship Policy ID | 同上（`PIMLICO_SPONSORSHIP_POLICY_ID`）|

**実行（dev VPS でも Mac でも可。本番 VPS 不要）**
```bash
cd frontend
PIMLICO_API_KEY=pim_xxxxxxxx node scripts/poc/paymaster-poc.mjs
# 任意: PIMLICO_SPONSORSHIP_POLICY_ID=sp_xxx を併せて渡す
```

**期待結果**
```
✅ PASS: sponsored UserOp が status=1 で確定。paymaster 経路 OK。
  actualGasCost: <wei> ( <eth> ETH )
```

**完了後に Claude に渡すもの**: 上記出力（success / actualGasCost / txHash / SCW address）をそのまま貼る。

**これが解除すると Claude が即着手できること**:
スライス2（UserOp receipt 検証 helper）→ 3（onBehalfOf→SCW + migration）→ 6（F-9 expense 再設計）。
各々 HUMAN-REVIEW-REQUIRED（`docs/privy-aa-paymaster-design.md` §7 承認ゲート）なので、PoC 結果を見て承認 → 実装。

---

## B. LINE LIFF アプリ作成（staging-v4 で v4 LINE 配布を検証）

**目的**: staging-v4 を LINE Mini App（LIFF）として開けるようにし、v4 の LINE 配布経路を実機検証する。

> 【重要】これは **staging-v4 のみ**。**production の `NEXT_PUBLIC_LIFF_ID` は空のままにすること**。
> production に値を入れると PWA ブラウザ利用者が「LINEアプリでのみ利用可能」でブロックされ v3 が壊れる
> （`frontend/app/(liff)/layout.tsx` ガード）。production は v3 = PWA 配布。

**手順（LINE Developers Console）**
1. https://developers.line.biz で Provider を選択（無ければ作成）
2. **LINE Login** チャネルを作成（Mini App/LIFF は LINE Login チャネル配下）
3. チャネル内 **LIFF** タブ → LIFF アプリを追加:
   - Endpoint URL: `https://staging-v4.ultra-auto-trade.com/liff-chat`
   - Size: Full
   - Scope: `profile`, `openid`（idToken を使うため openid 必須）
   - Bot link 機能: 任意
4. 発行された **LIFF ID**（`xxxxxxxxxx-xxxxxxxx` 形式）を控える

**取得する値と置き場所（本番 VPS `/opt/ultra-autotrade`）**
```bash
# staging-v4 env に LIFF ID を投入（LIFF_APP_URL は PR #791 マージ後）
printf '\nNEXT_PUBLIC_LIFF_ID=<発行された-liff-id>\n' >> /opt/ultra-autotrade/.env.staging-v4
```
> `NEXT_PUBLIC_*` はビルド時埋め込み → **frontend 再ビルド＆再デプロイが必須**（`scripts/deploy_staging_v4.sh`）。

**検証**
- LINE アプリから LIFF URL を開き、LINE ログイン → `/liff-chat` が表示される
- ブラウザで `https://staging-v4.ultra-auto-trade.com/liff-chat` を開くと従来どおり PWA degrade で表示される（LIFF_ID 設定後も degrade 経路は維持）

**これが解除すると検証できること**: v4 の LINE LIFF 入口・LINE ログイン→JWT 発行→liff-chat 表示の一連。
（コード側の配線は実装済み。残るは LIFF アプリの実体と LIFF_ID 投入のみ。）

---

## C. Privy Dashboard Smart Wallet 有効化（スライス4 の前提）

**目的**: Privy embedded EOA を **Smart Wallet（ERC-4337 SCW）** に切り替えられるようにする。
paymaster（A）でガスを肩代わりするには SCW が必須（EOA に paymaster は適用不可）。

> 【不変条件】SCW の owner は **ユーザー EOA のみ**。UATa のサーバー鍵を owner にしない。
> （`docs/privy-aa-paymaster-design.md` §1.5）。環境分離: staging / production で別 Privy プロジェクト・別 paymaster。

**手順（Privy Dashboard）**
1. https://dashboard.privy.io で対象アプリを選択
2. **Smart Wallets** を有効化（実装は Coinbase Smart Account 想定 / PoC と整合）
3. paymaster ベンダーを接続（PoC で確定したもの = 既定 Pimlico）。bundler/paymaster URL をプロジェクトに設定
4. staging と production で**別プロジェクト・別 paymaster 原資**にする

**完了後に Claude に渡すもの**: 「staging の Privy で Smart Wallet 有効化済み + paymaster 接続済み」の確認。
（API キー等の秘密は env 投入のみで、チャットには貼らない）

**これが解除すると Claude が即着手できること**: スライス4（`PrivyRootClient.tsx` に SmartWalletsProvider 配線
+ 全署名4経路を UserOp 化）。PoC PASS（A）+ 本セットアップ + §7 承認ゲートが揃った時点で実装。

---

## 進捗チェックリスト

- [ ] **A**: Pimlico キー発行 → PoC 実行 → PASS 出力を Claude に共有
- [ ] **B**: LINE LIFF アプリ作成 → staging-v4 に LIFF_ID 投入 → 再ビルド → LINE 実機表示
- [ ] **C**: Privy Smart Wallet 有効化（staging）→ paymaster 接続 → Claude に共有
- [ ] PR #791（LIFF_APP_URL compose 配線）マージ後に staging-v4 再ビルド

## Claude 側が完了済み（参考）
- スライス7 PoC harness 実装（PR #789）
- liff-chat 半自動実行 + 資産推移/holdings（PR #787・本番反映済）
- LIFF_APP_URL compose 配線 + env example 整備（PR #791）
- 設計 doc（`docs/privy-aa-paymaster-design.md`）スライス1 + 署名経路4箇所更新
