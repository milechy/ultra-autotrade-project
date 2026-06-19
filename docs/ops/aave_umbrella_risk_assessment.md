# Aave V3 Umbrella ステーキング リスク評価（GO/NO-GO）

> 作成日: 2026-06-19 / Asana GID: 1215620430710861
> 種別: 意思決定ドキュメント（コード変更なし）
> 参照: `docs/13_security_design.md` / `CLAUDE.md §Security Rules` / Aave 公式ドキュメント（WebFetch 取得、末尾「出典」参照）
>
> **本ドキュメントの数値は推測ではなく、Aave 公式ドキュメント・ガバナンスフォーラム・一次報道の WebFetch 取得結果に基づく（2026-06-19 時点）。**

---

## 概要

Aave は 2025-06-05 に旧 Safety Module を **Umbrella** へ置き換えた。Umbrella は
aToken（aUSDC / aUSDT / aWETH のラップ版 = stkwaUSDC / stkwaUSDT / stkwaWETH）または GHO を
ステークして「プロトコルの bad debt（焦げ付き）を補填する保険原資」を提供し、見返りに
追加報酬（Safety Incentives）を得る仕組みである。

旧 Safety Module との最大の違いは **スラッシングの自動化**。旧来は bad debt 発生時に
DAO ガバナンス投票で対応していたが、Umbrella は `UmbrellaCore` がオンチェーンの deficit
（赤字）を直接監視し、設定された閾値（deficitOffset）を超えると **ガバナンス投票を経ずに
自動でステーカー資産を削減（スラッシュ）** する。

本評価の結論を先に述べると **NO-GO（現時点では UATa 運用資産での Umbrella ステーキングを採用しない）**。
理由は「追加 APY が小さい」「スラッシングが UATa の Health Factor ベース安全設計の制御外」
「20 日クールダウンが緊急退避（AutoEvacuator）と両立しない」「2026-04-20 に実際にスラッシング
発動寸前まで至った near-miss が発生し、しかも本来対象外の他チェーン由来損失へ波及しかけた」の 4 点。
詳細と再評価条件は後述。

---

## Umbrella ステーキングの仕組み

| 項目 | 内容 |
|---|---|
| ステーク可能資産 | ラップ aToken（stkwaUSDC / stkwaUSDT / stkwaWETH）または GHO |
| 報酬構造 | aToken ステーカーは「原資産 aToken の利回り（自動）＋ Safety Incentives（要 claim）」の二重利回り。GHO ステーカーは Safety Incentives のみ |
| 報酬カーブ | piecewise linear emission。最小ステーク時の最大 APY は target liquidity 時 APY の **2 倍**。target を超えると過剰ステーク抑制のため逓減 |
| 補償スコープ | 各ステーク資産は「同一ネットワーク上の対応する借入資産」の赤字のみを補填する（例: WETH ステークは当該チェーンの WETH コア市場をカバー） |
| クールダウン | **20 日**（ガバナンスで変更可）。その後 **2 日**の unstake window。window を逃すと最初からやり直し |
| クールダウン中の扱い | 「報酬は引き続き発生するが、資金はスラッシュ対象のまま」= **退避中も削減され得る** |
| スラッシング契機 | `UmbrellaCore` が deficit を検知し、設定 offset（deficitOffset）を超えた瞬間に自動発動。share value を比例的に減額 |
| deficitOffset | DAO が「first-loss（最初の損失）」を一定額まで肩代わりするバッファ。これを超過した分がステーカーへ及ぶ |

---

## スラッシングリスク（条件・上限・過去実績）

### 発生条件
- 対応する Aave プールに bad debt（deficit）が発生し、その累計が **deficitOffset を超過**した時点で自動発動。
- ガバナンス投票は不要（旧 Safety Module との決定的な違い）。検知 → 即時実行。

### 上限（cap）
公式・ガバナンス資料から確認できた設定値:

| 資産 | 最大スラッシング率 |
|---|---|
| stkAAVE / stkABPT（旧 SM 継続分） | **最大 20%**（Umbrella 活性化提案で旧 30% から変更） |
| stkGHO（Umbrella） | **0%（スラッシング無効）** |
| stkwaUSDC / stkwaUSDT / stkwaWETH（aToken vault） | 固定 cap は公式に明示されず。設計上は **「極端なシナリオでは全額（100%）スラッシュ可能」**。deficitOffset が first-loss バッファとして実害確率を下げるが、上限保証はない |

> **重要**: UATa が運用で扱うのは主に **ステーブル/aToken 系**であり、これらは「0% 上限が保証された stkGHO」ではなく、
> 「理論上全額スラッシュ可能」な aToken vault に該当する。cap が無いことが本評価の重大論点。

### 過去実績（極めて重要）

1. **旧 Safety Module は 5 年以上の歴史で一度もスラッシュされていない。**
   - 累計 bad debt は約 **$2.25M**。最大の事案は 2022-11 の CRV 攻撃で $1.6M（価格回復後 $400k まで縮小）。
   - 2023-11 にも CRV 関連で約 $1.6M。**いずれも DAO トレジャリーで補填し、Safety Module はスラッシュせず**（2022 分は $280k を Gauntlet insolvency fund が補助）。
   - Aave v3.3 稼働初月の deficit は約 **$400**、対する outstanding borrows は約 **$9.5B**（= 約 **0.000004%**）。

2. **しかし Umbrella では「near-miss」が実際に発生済み（2026-04-20）。**
   - ガバナンスに **stkwaWETH の一時停止（pause）提案**が提出された。理由は rsETH（Kelp）関連損失の確定前に
     WETH Umbrella module が「live coverage surface（実発動対象）」になり、**まだ Umbrella 資金が必要と
     確定していない deficit に反応して資金がスラッシュされるのを防ぐため**。
   - 論点: aWETH ステーカーは「Ethereum V3 Core Market のみカバー」のつもりが、**別チェーン由来（rsETH/Kelp）の
     損失に巻き込まれかけた**。フォーラムでも「他チェーンの損失をカバーする契約はしていない」との反発。
   - 教訓: (a) スラッシングは自動かつ即時で、(b) **補償スコープが当初前提を超えて拡大しうる**、
     (c) 損失確定までステーカー資本が**長期凍結**され得る（クールダウン 20 日に加え、ガバナンス審議中の pause）。

> 結論: 「過去 5 年スラッシュ無し」は旧 Safety Module の実績であり、**Umbrella の自動スラッシング設計には
> そのまま適用できない**。むしろ移行後 1 年弱で実発動寸前の事案が出ている。

---

## Safety Incentives APY 実績

| 商品 | APY（2026 時点の観測値） | 備考 |
|---|---|---|
| sGHO（リスクフリー、ERC-4626 vault） | 約 **7%**（Merit Program 経由） | クールダウン無し・スラッシング無し・rehypothecation 無し |
| stkGHO（Umbrella、スラッシングあり） | 約 **5%**（base 0.56% + Merit 等で実質 7.7% 試算もあり） | 活性化前は 13% だったが大幅低下。「リスクフリーの sGHO より低い」とユーザー不満・フォーラム議論化 |
| stkwaUSDC / stkwaUSDT / stkwaWETH | 「原資産 aToken 利回り＋ Safety Incentives」。Safety Incentives 部分は emission カーブ依存で**変動が大きい**。固定値は公式に非公開、`app.aave.com/staking` で都度確認が必要 | target liquidity 充足度で逓減。最小ステーク時のみ高 APY |
| stkGHO emission パラメータ例 | target liquidity **$12M** / maxEmissionPerYear **$1.2M** | emission 上限が固定のため TVL 増で APY は希薄化 |

要点: **追加で得られる「スラッシングの対価」部分の APY は小さく（stkGHO で base 0.56%、実質上乗せでも数 %）、
かつ TVL 増加で逓減する**。リスクフリーの sGHO（約 7%）がスラッシング商品より高利回りという逆転すら起きている。

---

## リスク/リターン試算

金融計算は `Decimal` 型で記載（`CLAUDE.md §Security Rules 11` 準拠 / float 禁止）。
以下は **保守シナリオの期待損失モデル**。実数値は公式 APY 変動に応じて再計算すること。

### 前提（Decimal）

```python
from decimal import Decimal

# 追加 APY（aToken を「ただ supply する」より上乗せされる Safety Incentives 分）
# stkGHO base 0.56% 〜 aToken vault 数% を保守的に中央値 3% と置く
additional_apy = Decimal("0.03")          # +3.0% / 年

# スラッシング年間発生確率（保守側）
# 旧 SM 実績は 5 年で 0 回だが、Umbrella は自動化 + 2026-04 near-miss を踏まえ非ゼロに置く
p_slash_per_year = Decimal("0.05")        # 5% / 年

# 発生時の平均削減率（部分スラッシュ想定。全額シナリオは別途 tail で評価）
loss_given_slash = Decimal("0.20")        # 20% 削減

# 期待損失（年率）
expected_annual_loss = p_slash_per_year * loss_given_slash
# = Decimal("0.05") * Decimal("0.20") = Decimal("0.0100")  → 1.00% / 年

# ネットエッジ（期待値ベース）
net_edge = additional_apy - expected_annual_loss
# = Decimal("0.03") - Decimal("0.0100") = Decimal("0.0200")  → +2.00% / 年
```

期待値だけ見ると **+2.0%/年のプラス**で一見「GO」に見える。しかしこのモデルには
**期待値に押し込めない 3 つの非対称リスク**がある。

### Tail（裾）リスク — 期待値では捉えられない損失

```python
# 1) 全額スラッシュシナリオ（aToken vault は cap 保証なし）
tail_loss_given_slash = Decimal("1.00")   # 最大 100%
tail_expected = p_slash_per_year * tail_loss_given_slash
# = Decimal("0.05") * Decimal("1.00") = Decimal("0.0500")  → 5.00% / 年
# → additional_apy 3% を上回る。最悪系では期待値すら負。

# 2) 資本凍結（流動性リスク）: クールダウン 20 日 + unstake 2 日 + pause 審議
#    → 退避判断から最短でも 22 日、ガバナンス pause 時は無期限。金額化困難だが UATa の
#      「10 分クールダウンで機動的退避」設計と桁が違う。

# 3) スコープ拡大リスク（2026-04 実例）: 当初前提外（他チェーン由来）損失への巻き込み。
#    確率・規模ともモデル化困難 = Knightian uncertainty（測れない不確実性）。
```

**判定根拠**: 中心シナリオは +2%/年だが、(1) cap 無し全額系で期待値が負転、(2)(3) は確率分布すら
引けない測れない不確実性。**得られる上乗せ（数 %）に対し、下方は principal 全損 + 長期凍結 + 想定外スコープ**
という強い非対称性。UATa の保守設計と整合しない。

---

## UATa 安全設計との整合評価

`CLAUDE.md §Security Rules` / `docs/13_security_design.md` の安全装置と Umbrella リスクの突き合わせ:

| UATa 安全装置 | Umbrella スラッシングに効くか | 評価 |
|---|---|---|
| Health Factor < 1.6 → 自動 HARD_STOP | **効かない** | HF は「自分の借入ポジションの清算」を守る指標。Umbrella スラッシングは借入でも HF でもなく、**他者の bad debt を肩代わりする保険損失**。HF シグナルが存在せず、HARD_STOP の制御面が無い |
| 単一取引上限 10% / 日次 30% | 部分的にしか効かない | 投下額は制限できるが、投下後はスラッシュで principal が削られる。HF と違い「閾値で止める」介入点が無い |
| Aave 操作間 10 分クールダウン / AutoEvacuator | **真っ向から矛盾** | Umbrella は退避に 20 日クールダウン + 2 日 window。緊急退避の機動性（10 分単位）と桁が 3 桁違う。退避中もスラッシュ対象 |
| 緊急停止フラグ（OR ロジック、上書き不可） | **効かない** | 手動停止しても既ステーク分は cooldown を待つしかなく、その間も自動スラッシュ対象 |
| Decimal 型での金融計算 | 適用可 | 本評価も Decimal 準拠。これは満たせる |
| fail-safe / fail-open 設計 | 不整合 | Umbrella は「保険提供者＝損失の受け手」になる構造で、UATa の「ユーザー資産を守る」第一原則と利益相反 |

**結論**: UATa の中核安全装置（HF HARD_STOP・緊急停止・高速退避）は **いずれも Umbrella スラッシングに対して
無力**。Umbrella は UATa の安全アーキテクチャに「制御面（control surface）を一つも持たない新規リスク」を
持ち込む。これは「Simplicity First / ユーザー資産保護第一」の設計思想に反する。

---

## ユーザー向けリスク開示文案

> 採用しない場合は不要だが、将来「条件付き GO」へ移行する際の必須開示として用意する。

```
【Aave Umbrella ステーキングに関する重要なリスク説明】

本機能は、Aave プロトコルの保険原資（Umbrella）に資産をステークし、追加の報酬を
得るものです。ご利用前に以下のリスクを必ずご確認ください。

1. 元本削減（スラッシング）リスク
   Aave に焦げ付き（bad debt）が発生し一定額を超えた場合、ステークした資産は
   ガバナンスの投票を経ず「自動的に」削減されます。削減の上限は資産により異なり、
   ステーブル/ETH 系では理論上「全額」削減され得ます。

2. 出金まで最短 22 日かかります
   出金にはクールダウン 20 日＋出金可能期間 2 日が必要です。この期間中も資産は
   削減の対象であり、相場急変時に即時退避することはできません。

3. 想定外の損失に巻き込まれる可能性
   2026 年 4 月には、本来対象外であった他チェーン由来の損失が、ETH ステーカーへ
   波及しかける事案が実際に発生しました。補償の範囲は将来のガバナンスで変わり得ます。

4. 当社の自動安全装置（Health Factor 監視・緊急停止）は、このスラッシングを
   防ぐことができません。これは借入の清算とは異なる種類のリスクです。

以上にご同意いただける場合のみ、本機能をご利用ください。元本を失う可能性があります。
```

---

## GO/NO-GO 判断

### 判断: **NO-GO**（現時点で UATa 運用資産による Aave Umbrella ステーキングは採用しない）

### 推奨理由

1. **リスク/リターンの非対称性**: 上乗せ APY は小さく（stkGHO base 0.56%、実質でも数 %）、TVL 増で逓減。
   一方の下方は cap 無し（aToken vault は理論上全額）+ 22 日以上の資本凍結 + 想定外スコープ。
   中心シナリオ +2%/年に対し、tail では期待値すら負転（cap 無し全額系で −2%/年）。

2. **UATa 安全設計との非整合**: HF<1.6 HARD_STOP・緊急停止フラグ・高速退避という中核安全装置が
   いずれもスラッシングに無力。Umbrella は「制御面を持たない新規リスク」を持ち込む。

3. **実害 near-miss の存在**: 「過去 5 年スラッシュ無し」は旧 Safety Module の実績で、自動化された
   Umbrella には適用できない。移行後 1 年弱の 2026-04-20 に stkwaWETH 一時停止提案＝発動寸前事案が発生。

4. **代替の存在**: 同等以上の利回りは、スラッシングの無い sGHO（約 7%）や通常の aToken supply で得られる。
   UATa は「リスクフリー側」を選べる立場にある。

### 条件付き再評価（将来 GO へ転じる可能性のある前提）

以下が**すべて**満たされた場合に限り「Shadow Mode での観測 → 少額本番」を再検討する:

- [ ] aToken vault に**明示的なスラッシング上限 cap**（例: ≤10%）がガバナンスで恒久設定される
- [ ] 補償スコープが「単一チェーン・単一資産」に契約上限定され、クロスチェーン波及（2026-04 型）が構造的に排除される
- [ ] クールダウンが UATa の退避要件と両立する水準（≤数日）になる、もしくは UATa 側で「Umbrella 分は別枠・退避対象外」と明確に隔離運用できる
- [ ] 上乗せ APY が tail 期待損失を継続的に上回る（`additional_apy > p_slash * loss_given_slash` を Decimal で定期再計算）
- [ ] ユーザー向けリスク開示（本書の文案）を実装し、opt-in 同意フローを通す

それまでは **Aave 上の運用はスラッシング非対象の経路（通常 supply / sGHO 等）に限定**する。

---

## 出典（WebFetch / WebSearch 取得、2026-06-19）

- [Umbrella | Aave Protocol Documentation](https://aave.com/docs/aave-v3/umbrella) — スラッシング機構・クールダウン 20+2 日・報酬カーブ・補償スコープ
- [Stake | Aave Help](https://aave.com/help/umbrella/stake) — ステーク対象資産・自動スラッシング概要
- [Aave Umbrella officially passed: stkGHO APY 13% … | PANews](https://www.panewslab.com/en/articles/tokgsdxly5zz) — 活性化日 2025-06-05・stkGHO APY 13%→7.7%・target liquidity $12M・maxEmissionPerYear $1.2M・旧 SM cap 30%/99%
- [Direct-to-AIP] Pause stkwaWETH Umbrella Staked Token on Ethereum V3 — Aave Governance](https://governance.aave.com/t/direct-to-aip-pause-stkwaweth-umbrella-staked-token-on-ethereum-v3/24595) — 2026-04-20 near-miss・rsETH/Kelp クロスチェーン波及・資本凍結
- [Umbrella reshapes Aave staking | Blockworks](https://blockworks.com/news/umbrella-reshapes-aave-staking) — stkAAVE/stkABPT 20%・stkGHO 0%・自動スラッシング
- [Feature or Flaw? Aave Left With $1.7M in Bad Debt | Blockworks](https://blockworks.co/news/aave-curve-bad-debt) / [State of Aave Q4 2022 | Messari](https://messari.io/report/state-of-aave-q4-2022) — 2022/2023 CRV bad debt をトレジャリー補填（SM 未スラッシュ）
- 内部参照: `docs/13_security_design.md` / `CLAUDE.md §Security Rules`（HF<1.6 HARD_STOP・Decimal 必須・緊急停止 OR ロジック）
