# Flash Loan 自己清算保護 — 配線（トリガー統合）設計提案書

- 作成日: 2026-07-07
- 作成者: Planner（investigation-only, Asana Task3 GID 1216346333278165, Tier B）
- 対象 Asana 親タスク: 1215620828227794（Flash Loan 自己清算保護）
- ステータス: **提案のみ。コード変更なし。実装は別タスク（Tier S / HUMAN-REVIEW 相当）として要人間承認。**

## 1. 背景・現状

`backend/app/aave/self_liquidation.py`（第1スライス, PR #839）と
`backend/app/aave/flash_loan_service.py`（第2スライス, PR #871）は、それぞれ以下を提供する
完成済みコンポーネントである。

- `self_liquidation.py`: 副作用のない純計算層。`should_protect(current_hf, trigger_hf=1.3)` で
  発動要否を判定し、`compute_deleverage_quote(...)` で目標 HF（既定 1.8）まで回復する
  Flash Loan デレバレッジ額を解析的に求める。fail-closed 分岐（debt無し／HF既に安全／
  担保不足／target到達不能）を持つ。
- `flash_loan_service.py`: `FlashLoanSelfLiquidator.execute_self_liquidation(wallet, dry_run=True)`
  が `AaveClientBase.get_account_data()`（read-only）で実アカウントの HF/担保/債務/
  liquidation_threshold を取得し、上記純計算層に委譲する orchestration。`dry_run=False` は
  `NotImplementedError`（on-chain 実行は意図的に未実装＝別 HUMAN-REVIEW スライス）。

いずれのクラスも `backend/app/main.py` のどの API エンドポイントからも、
`scheduled_tasks.py` / `workflow.py` のどのジョブからも呼び出されていない。
テスト（`backend/tests/aave/test_self_liquidation.py` 18件、
`backend/tests/aave/test_flash_loan_service.py` 9件）は単体で完結しており、
呼び出し元の統合テストは存在しない。PR #839 のコミットメッセージ自身が
「後続スライス（別 PR・別タスク化推奨）: … dashboard 履歴カード + admin トグル +
workflow 統合（Tier S）」と明記しており、配線が意図的に切り離されていたことが分かる。

HF 危機時の保護機構が「実装済みだが誰も呼ばない」状態は、本番で HF が 1.3 を割り込んでも
この保護が一切発火しないことを意味し、ドキュメント化すべき実質的なギャップである。
ただし配線自体は秘密鍵・on-chain write 経路に触れる安全域の変更であり、本タスクの
スコープ外（investigation only）。以下は次の判断のための設計選択肢の提示に留める。

## 2. 既存の類似安全システムの実パターン

配線案は憶測ではなく、リポジトリに実在する2つの類似パターンを土台にする。

### 2.1 自動トリガー: `CompoundRiskAssessor` → `AutoEvacuator`
- `backend/app/protocols/risk/compound_risk.py`: `CompoundRiskAssessor.assess()` が
  プロトコルリスク・ペグ・満期を統合し `risk_score`（0-100）と `should_evacuate: bool` を
  算出。`risk_score >= 80` またはいずれかが CRITICAL で `should_evacuate=True`。
- `backend/app/protocols/risk/auto_evacuate.py`: `AutoEvacuator.create_evacuation_plan(assessment)`
  は `should_evacuate=False` なら **None を返すだけ**（何もしない）。`execute_evacuation()` は
  `dry_run: bool = True` が既定で、実行前に2段のガードを持つ:
  - Guard 1: `emergency_stop_active=True` なら即ブロック（"Manual override required"）。
  - Guard 2: `dry_run=False` のときのみ、`priority=="immediate" and operation_mode=="managed"`
    の自動実行許可以外は `manual_approval` 必須。
- `backend/app/automation/safety_gate.py` の `evaluate_hard_stop()` はこの
  `CompoundRiskAssessor` を呼び出し元（`workflow.py` の CEX 経路）と Aave 経路の両方から
  同一ロジックで参照する「真実源」的な位置づけ。fail-open/fail-closed の使い分けが
  明示されている（MacroSafeMode 失敗=fail-closed, CompoundRiskAssessor 失敗=fail-open,
  StressController 失敗=skip）。

この構造をなぞるなら、`FlashLoanSelfLiquidator` は「HF 版の `AutoEvacuator`」として、
`should_protect()` の bool を `CompoundRiskAssessor.assess().should_evacuate` と同格に扱い、
`safety_gate.evaluate_hard_stop()` の評価チェーンに5番目のチェックとして追加する形が
最も既存パターンに忠実。

### 2.2 手動トリガー: admin 限定 API エンドポイント
- `backend/app/automation/automation_router.py` に実例が2つある:
  - `POST /api/ai/trigger`（`Depends(require_admin)`）— AI 判定ジョブを手動即時実行。
  - `POST /automation/emergency-stop`（`Depends(require_active_user)`）— 全自動取引を即停止。
- `require_admin` / `require_active_user` は `app/auth/dependencies.py` の既存 FastAPI
  dependency で、そのまま流用可能。

## 3. 選択肢

### オプション (a) 自動トリガー — HF 閾値越えで `CompoundRiskAssessor`/`AutoEvacuator` 相当の経路から自動発火

案: `safety_gate.evaluate_hard_stop()` の評価チェーン（rule_engine → stress →
macro → compound_risk）の後段に「self_liquidation」チェックを追加し、
`hf < DEFAULT_TRIGGER_HF(1.3)` かつ `quote.feasible=True` のとき
`FlashLoanSelfLiquidator.execute_self_liquidation(dry_run=False)` を呼ぶ
（現状 `dry_run=False` は `NotImplementedError` なので、これ自体が別スライスで
on-chain 実行を実装しない限り機能しない）。

**リスク評価:**
- 発動精度: `should_protect` は HF のみで判定し、`compute_deleverage_quote` の
  fail-closed 分岐（担保不足・target 到達不能）により誤って実行される確率は低い
  （数値ロジックはテスト18件で検算済み）。ただし **オラクル遅延・一時的な価格スパイクで
  瞬間的に HF<1.3 を記録した場合**、その瞬間だけで Flash Loan を発火させると、
  価格が数秒後に戻っても手数料（0.05%）分の担保を実際に失う。`workflow.py` の
  `check_rule_engine` は `oracle_stale` チェック（`is_oracle_fresh()`）を fail-closed で
  持つが、`FlashLoanSelfLiquidator` 自体には無い。
- **HARD_STOP (HF<1.6) との相互作用**: `DEFAULT_TRIGGER_HF=1.3` は HARD_STOP の 1.6 より
  低いため、自己清算が発火する頃には既に `workflow.py:582`
  （`HF emergency override: always auto_execute if HF < 1.6`）や `risk_limiter.py` の
  `HF_HARD_MIN=1.2` 域に入っている。つまり自己清算は HARD_STOP の**内側**で動く
  最終防衛ラインであり、HARD_STOP のロジックを変更・迂回するものではない設計は妥当。
  ただし HARD_STOP は「手動操作のみ」（`AaveOperationMode.HARD_STOP` docstring）を
  意図しているため、この内側で新たな自動 write 経路を作ることは HARD_STOP の哲学
  （危険域では自動操作を止める）と緊張関係にあり、要文書化・要合意。
- **10分クールダウン (`risk_limiter.py` `COOLDOWN_STRICT_DEFAULT_SECONDS=600`,
  ハード最小 `COOLDOWN_HARD_MIN_SECONDS=60`) との相互作用**: 現状このクールダウンは
  `service.py` の `_is_in_cooldown()` で通常の deposit/withdraw/borrow/repay に適用される。
  Flash Loan 自己清算はこの経路を通らないため、**そのままではクールダウンの対象外**。
  HF が乱高下する相場で連続して自己清算が発火すると、Flash Loan 手数料が複利的に
  担保を削る「デス・スパイラル」リスクがある。自動トリガー案を採用する場合、
  自己清算にも独立したクールダウン（例: 同一 wallet に対し 600 秒以内の再発火を禁止）
  を新設する必要がある — これは未解決の設計課題として明記する。
- **Emergency Stop の OR ロジックとの相互作用**: `monitoring_service.py` の
  `final_emergency_stop = existing_emergency or hf_triggered_emergency`（244行目）は
  手動停止が絶対に上書きされないことを保証する。`AutoEvacuator.execute_evacuation()` の
  Guard 1 と同様に、自己清算トリガーも `emergency_stop_active` を最優先でチェックし、
  真なら発火自体をブロックすべき（これも CLAUDE.md Security Rule 6 の要件）。
  現状の `FlashLoanSelfLiquidator` にはこのチェックが一切なく、配線時に
  必須で追加すべき最重要ガードである。
- 総合: 自動トリガーは「保護漏れ」を解消する一方、新規の自動 write 経路・新規の
  クールダウン設計・オラクル鮮度チェック・emergency_stop ガードを同時に要求し、
  かつ `dry_run=False` の on-chain 実装自体が未着手。実装コストと安全検証コストが高い。

### オプション (b) 手動トリガー — admin 専用 API エンドポイント（自動発火なし）

案: `automation_router.py` の `POST /api/ai/trigger` と同型で
`POST /api/aave/self-liquidation/trigger`（`Depends(require_admin)`）を新設し、
管理者が対象 wallet を指定して `execute_self_liquidation(wallet, dry_run=True)` を
手動実行・結果（quote と reason）を確認できるようにする。`dry_run=False` の
on-chain 実行は将来スライスで別途 human-in-the-loop 承認 UI を挟む前提。

**リスク評価:**
- 発動精度: 人間が能動的に叩かない限り発火しないため、オラクルの瞬間的な乱れによる
  誤発動リスクは実質ゼロ。誤操作の唯一の経路は「管理者が誤って押す」ことだが、
  `dry_run=True` を既定にしておけば実害はシミュレーション結果の閲覧のみ。
- HARD_STOP との相互作用: HARD_STOP は「手動操作のみ」を許容する設計であり
  （`AaveOperationMode.HARD_STOP` docstring: "完全停止（手動操作のみ）"）、
  本オプションは HARD_STOP 発動中でも admin が明示的に操作するという、
  既存の設計意図とむしろ整合する。
- 10分クールダウンとの相互作用: 手動トリガーであっても、実際に on-chain 実行する
  スライスでは `service.py` の `_is_in_cooldown()` と同じ仕組みを later 適用すべきだが、
  `dry_run=True` の閲覧のみであればクールダウンは不要（副作用がないため）。
- Emergency Stop OR ロジックとの相互作用: `require_admin` は認可のみでビジネスロジックの
  ガードではないため、エンドポイント実装時に `monitoring_service.is_trading_allowed()`
  を明示的にチェックし、`emergency_stop_active` なら `dry_run=False` 相当の実行
  （将来スライス）を拒否するロジックを追加する必要がある。これは
  `POST /automation/emergency-stop` の実装（`require_active_user`）と対になる形で
  自然に設計できる。
- 総合: 実装・レビューコストが低く、Security Rule 6（emergency stop は決して
  上書きされない）を壊すリスクが小さい。ただし「HF 危機を自動で救う」という
  本来の保護目的（外部清算業者による 5-10% ペナルティ回避）は、admin が
  タイムリーに気づいて押さない限り達成されない — 監視ダッシュボードでの
  HF アラート通知と併設しない限り実効性が低い。

## 4. 所見のまとめ（結論は出さない — 人間の判断事項）

| 観点 | (a) 自動トリガー | (b) 手動 admin エンドポイント |
|---|---|---|
| 保護の実効性（HF危機に間に合うか） | 高い（無人でも発火） | 低い（人が気づく前提） |
| 誤発動リスク（オラクル瞬間乱れ等） | 中〜高（要オラクル鮮度チェック追加） | ほぼゼロ |
| 既存 HARD_STOP 哲学との整合性 | 緊張あり（危険域での新規自動 write） | 整合的（手動操作のみ） |
| 10分クールダウンとの整合性 | 未対応（新設必須） | 影響小（dry_run閲覧のみなら不要） |
| Emergency Stop OR ロジック対応 | 必須で新規実装（現状皆無） | 実装時に必須で新規追加 |
| 実装・安全レビューコスト | 高（Tier S 相当） | 中（既存パターン流用で低め） |
| `dry_run=False` on-chain 実行への依存 | あり（このスライスなしでは無意味） | 将来スライスに先送り可能 |

いずれのオプションも、on-chain 実行（`dry_run=False`）スライスと
「emergency_stop フラグ・オラクル鮮度・クールダウン」への対応を新規実装する
別タスクが前提であり、本タスクではその設計判断の材料提示のみを行う。
配線自体の実装可否・優先度・どちらのオプションを採るかは人間の承認を要する。

## 5. 参照ソース

- `backend/app/aave/self_liquidation.py`, `backend/app/aave/flash_loan_service.py`
- `backend/tests/aave/test_self_liquidation.py`, `backend/tests/aave/test_flash_loan_service.py`
- コミット: `23bc2fb0`（#839, 第1スライス）, `a27dd6d3`（#871, 第2スライス）
- `backend/app/protocols/risk/compound_risk.py`, `backend/app/protocols/risk/auto_evacuate.py`
- `backend/app/automation/safety_gate.py`
- `backend/app/automation/workflow.py`（317, 580-584行: HF<1.6 HARD_STOP / override）
- `backend/app/aave/risk_limiter.py`（`COOLDOWN_STRICT_DEFAULT_SECONDS=600`,
  `COOLDOWN_HARD_MIN_SECONDS=60`, `HF_HARD_MIN=1.2`）
- `backend/app/automation/monitoring_service.py`（244行: emergency_stop OR ロジック）
- `backend/app/automation/automation_router.py`（`POST /api/ai/trigger`,
  `POST /automation/emergency-stop`）
- `CLAUDE.md` Security Rules 2, 5, 6（HF<1.6 HARD_STOP / 10分クールダウン /
  emergency stop OR ロジック）
