# 52. Decision Layer — 4軸 weighted 合議設計 (2軸 AND 置換案)

> Status: DRAFT (Phase 0 / 設計レビュー)
> Owner: 小林 浩紀 / Claude (Opus 4.7)
> Date: 2026-05-26
> Asana: TBD (本 PR description にリンク予定)
> 関連教訓: `CLAUDE.lessons.md` 2026-05-21 SELL-spam / 2026-05-26 staging soak 三重故障

---

## 0. Summary

`MultiAgentContext.consensus_bias()` / `average_confidence()` を最終判定ロジックに組み込み、
現行の **Indicator + Macro 2軸 AND-condition** を **Indicator/Pattern/Risk/Macro の 4軸 weighted 合議** に
置き換える。LLM はベト権 (HARD STOP / 矛盾時 HOLD veto) を保持しつつ、決定論レイヤーが
4 軸の信号を取りこぼさないようにする。Shadow → A/B → 既定切替の 4 Phase で段階移行する。

**本ドキュメントは設計のみ。実装は別 PR (Phase 1 以降) で行う。**

---

## 1. 背景: 現状の決定論レイヤー

### 1.1 構成要素 (現行: 2026-05-21 PR 以降)

`backend/app/ai/service.py:208-324` (`judge_with_rag`) の rule engine:

| Guard | 判定 | 入力 | 動作 |
|---|---|---|---|
| Guard 1 (Pre-LLM) | COMPOUND RISK | `risk_signal.reasoning` に "COMPOUND RISK" 含む | 即 HOLD (LLM call せず) |
| Guard 2 (Pre-LLM フラグ) | 2軸 AND-condition | `indicator_and_macro_agree_bearish()` / `_bullish()` の結果 | `_and_condition_failed` フラグを立てて LLM call は実施 |
| Post-LLM clamp | AND-condition 後段 | LLM が SELL/BUY を出した + Guard 2 で AND-condition 失敗 | SELL/BUY → HOLD, confidence ≤ 45 にクランプ |

`MultiAgentContext.indicator_and_macro_agree_bearish()` (agents.py:145-163) の判定:

```python
return (
    ind.bias == Bias.BEARISH and ind.confidence >= 70
    and mac.bias == Bias.BEARISH and mac.confidence >= 70
)
```

`_DIRECTIONAL_THRESHOLD = 70` は hardcode。`indicator_and_macro_agree_bullish()` は対称版。

### 1.2 既に存在するが「使われていない」関数 (agents.py)

| 関数 | 何をする | 現状の利用先 |
|---|---|---|
| `consensus_bias()` (agents.py:98-120) | 4軸の多数決で BULLISH / BEARISH / NEUTRAL | `app/data_feeds/router.py:69,96` で外向け API レスポンスに含めるのみ |
| `average_confidence()` (agents.py:122-136) | 4軸の単純算術平均 | 同上、外向け API レスポンスのみ |

つまり **4 軸の集約結果を計算する API は既に揃っているが、判定ロジックから完全に切り離されている**。
判定ロジックは Indicator + Macro しか見ていない。

### 1.3 経緯 (なぜ 2軸 AND になったか)

- **v4 初版 (2026-05-XX)**: 「Indicator OR Macro が BEARISH ≥70%」で SELL — 単一エージェント発火を許す OR 条件
- **問題**: Macro Agent が外部ニュースに引っ張られて連続 BEARISH (25% 固着) → SELL-spam 発生
- **2026-05-21 修正**: v4 prompt + Python Guard 2 を **AND-condition** に変更
- **副作用**: Pattern / Risk Agent の信号は決定論層では完全無視。`indicator_and_macro` のみ評価

教訓 (`CLAUDE.lessons.md` 2026-05-21): _"単一エージェント暴走を OR→AND で塞いだが、3-4 エージェント目の信号を捨てた"_

---

## 2. 現状の課題

### 2.1 構造的問題

| # | 課題 | 影響 |
|---|---|---|
| C1 | **情報損失**: Pattern / Risk の決定論層への寄与なし | Risk Agent が高 confidence で BEARISH 警告しても、Indicator/Macro が NEUTRAL なら HOLD 一辺倒 |
| C2 | **二値判定**: AND は全か無か | Indicator 71% + Macro 69% で AND 失敗 → 直近の境界事例で BUY/SELL 取り逃し |
| C3 | **重要度均等**: Indicator と Macro が同重み | on-chain 実態 (Indicator) と外部経済環境 (Macro) を同等扱いするのは過剰補正 |
| C4 | **過剰 HOLD**: AND clamp が confidence を 45 で頭打ちにする | 2026-05-26 staging soak 全 HOLD 三重故障の一因 |
| C5 | **不可観測性**: 各軸の寄与がログに残らない | 「なぜ HOLD?」を事後検証する材料が `_and_condition_failed` フラグ 1bit のみ |

### 2.2 LLM 側との二重防衛の不整合

- v4/v5 prompt は LLM に対しても _"BOTH Indicator AND Macro >= 70%"_ を要求 (prompts.py:139-145, 183-192)
- LLM が weighted 的な合議で BUY を出しても、Python Guard 2 が AND で HOLD に clamp する
- **prompt の "Weight for confidence calculation: Risk 40% / Indicator 25% / Macro 20% / Pattern 15%"** (prompts.py:147, 198) と現実の判定ロジックが矛盾している (重み記述があるのに使っていない)

---

## 3. 設計目標

1. **4 軸全使用**: Indicator + Pattern + Risk + Macro の signal を決定論層で評価する
2. **重み付き**: 各 agent に重み (既定: Risk 0.40 / Indicator 0.25 / Macro 0.20 / Pattern 0.15) — prompt 記載の重みと整合
3. **連続スコア**: weighted directional score ∈ [-1, +1] と weighted confidence ∈ [0, 100] を導出
4. **二重防衛維持**: LLM 出力に対する veto 経路を保持 (LLM=BUY, deterministic=HOLD → HOLD)
5. **単一暴走防止**: 単一軸が confidence 100 でも、他 3 軸が NEUTRAL なら BUY/SELL を出さない (Macro stuck SELL-spam の再発防止)
6. **可観測性**: 各軸の寄与度を judgment ログに残す
7. **段階移行**: Shadow → A/B → 既定切替で本番影響を制御

---

## 4. 設計案 — 4軸 weighted 合議

### 4.1 入力変換

各 agent の (`bias`, `confidence`) を次のように数値化:

| `Bias` | direction value |
|---|---|
| `BULLISH` | +1 |
| `NEUTRAL` | 0 |
| `BEARISH` | −1 |

`confidence` は 0-100 の整数 (現行通り)。

### 4.2 重み

| Agent | 既定重み | 根拠 |
|---|---:|---|
| Risk Agent | 0.40 | 安全側の最重視。COMPOUND RISK は別経路 HARD STOP だが、COMPOUND 未満の地政学/stablecoin risk もここで効かせる |
| Indicator Agent | 0.25 | on-chain 実態 (HF / utilization / APY) は判定の柱 |
| Macro Agent | 0.20 | 外部要因 (FED stance / news sentiment) は単独支配しない上限 |
| Pattern Agent | 0.15 | 履歴ベースの行動補正。低重みだが flip-flop 検知などで実値 |
| **合計** | **1.00** | env 上書きでも合計 1.0 ± 0.01 を強制 |

env 上書き例:

```bash
AGENT_WEIGHTS_JSON='{"risk":0.40,"indicator":0.25,"macro":0.20,"pattern":0.15}'
```

起動時 validation で合計が 1.0 ± 0.01 を外れていれば backend boot を fail-closed (起動拒否)。

### 4.3 計算式

#### weighted_directional_score

```
score = Σ_i  w_i × direction_i × (confidence_i / 100)
```

範囲: `[-1, +1]`。全 agent が BULLISH conf=100 なら +1.0、全 agent BEARISH conf=100 なら −1.0。

#### weighted_confidence

```
weighted_conf = round( Σ_i  w_i × confidence_i )
```

範囲: `[0, 100]`。confidence の重み付き平均。direction とは独立 (反対方向同士の対立でも値は高くなる点に注意)。

#### directional_consensus_strength

```
strength = | weighted_directional_score |
```

「どれだけ片方向に偏っているか」の指標。

### 4.4 判定ルール (deterministic verdict)

```
HARD STOP (既存維持):
    if risk_agent_signal contains "COMPOUND RISK" → HOLD
    if health_factor < 1.6                          → HOLD

4-axis weighted verdict (Guard 2 置換):
    score = weighted_directional_score
    conf  = weighted_confidence

    if score >= +SCORE_BUY_THRESHOLD  and conf >= CONF_THRESHOLD:
        verdict = BUY
    elif score <= -SCORE_SELL_THRESHOLD and conf >= CONF_THRESHOLD:
        verdict = SELL
    else:
        verdict = HOLD

Single-agent runaway 抑止:
    if verdict in (BUY, SELL):
        agreeing_count = #{ i : sign(direction_i × score) > 0 and conf_i >= 50 }
        if agreeing_count < 2:
            verdict = HOLD     # 単一軸暴走を強制 HOLD
```

#### 既定閾値

| 定数 | 既定値 | 根拠 |
|---|---:|---|
| `SCORE_BUY_THRESHOLD` | 0.40 | 重み 0.40 (Risk) 単独 conf=100 では BUY しないが、Risk 0.40 + Indicator 0.25 = 0.65 で conf=70 なら通る |
| `SCORE_SELL_THRESHOLD` | 0.40 | 対称 |
| `CONF_THRESHOLD` | 65 | 旧 `_DIRECTIONAL_THRESHOLD=70` から 5pt 緩和 (連続値で評価する分、binary 70 より低くて良い) |
| `agreeing_count` 最低数 | 2 | 単一軸では BUY/SELL を出さない (C5 対策) |

閾値はすべて env (`CONSENSUS_SCORE_THRESHOLD`, `CONSENSUS_CONF_THRESHOLD`) で上書き可能。

### 4.5 Post-LLM 整合 (LLM ベト経路)

LLM 出力 (`llm_action`) と deterministic verdict (`det_verdict`) を比較:

| `llm_action` | `det_verdict` | 採用 | 理由 |
|---|---|---|---|
| HOLD | * | **HOLD** | LLM が HOLD なら全 HOLD (既存挙動踏襲) |
| BUY | BUY | **BUY** | 一致 |
| SELL | SELL | **SELL** | 一致 |
| BUY | HOLD | **HOLD** | deterministic veto (現行 clamp と同等) |
| SELL | HOLD | **HOLD** | deterministic veto |
| BUY | SELL | **HOLD + WARN** | 衝突は HOLD で安全側、警告ログ |
| SELL | BUY | **HOLD + WARN** | 衝突は HOLD で安全側、警告ログ |

採用される confidence:

```
final_confidence = min(llm_conf, weighted_conf)
```

clamp 発生時 (HOLD + 衝突警告時) は `final_confidence = min(llm_conf, weighted_conf, 50)` でさらに抑える。

### 4.6 ログ・可観測性

各 judgment record に以下を追加保存:

```jsonc
{
  "deterministic": {
    "score": "0.612",                // Decimal 文字列
    "weighted_confidence": 78,
    "verdict": "BUY",
    "score_threshold": "0.40",
    "conf_threshold": 65,
    "per_agent_contribution": {
      "indicator": {"direction": +1, "confidence": 80, "weight": 0.25, "contribution": "+0.200"},
      "pattern":   {"direction":  0, "confidence": 40, "weight": 0.15, "contribution":  "0.000"},
      "risk":      {"direction": +1, "confidence": 75, "weight": 0.40, "contribution": "+0.300"},
      "macro":     {"direction": +1, "confidence": 70, "weight": 0.20, "contribution": "+0.112"}
    }
  },
  "llm": { "action": "BUY", "confidence": 75 },
  "final": { "action": "BUY", "confidence": 75, "veto_applied": false }
}
```

格納先: `judgment_logs` テーブルに JSONB カラム `deterministic_breakdown` を追加 (Phase 1 migration)。

### 4.7 単体メソッド API 案 (`agents.py` 追加)

```python
class MultiAgentContext(BaseModel):
    # 既存 consensus_bias() / average_confidence() は wrapper として残し、
    # 内部実装は新ロジックを呼ぶ

    DEFAULT_WEIGHTS: ClassVar[dict[str, Decimal]] = {
        "risk": Decimal("0.40"),
        "indicator": Decimal("0.25"),
        "macro": Decimal("0.20"),
        "pattern": Decimal("0.15"),
    }

    def weighted_directional_score(
        self,
        weights: Optional[dict[str, Decimal]] = None,
    ) -> Decimal: ...

    def weighted_confidence(
        self,
        weights: Optional[dict[str, Decimal]] = None,
    ) -> int: ...

    def evaluate_4axis_consensus(
        self,
        *,
        weights: Optional[dict[str, Decimal]] = None,
        score_threshold: Decimal = Decimal("0.40"),
        conf_threshold: int = 65,
    ) -> "DeterministicVerdict": ...


class DeterministicVerdict(BaseModel):
    action: TradeAction              # BUY / SELL / HOLD
    score: Decimal
    weighted_confidence: int
    agreeing_count: int
    per_agent_contribution: dict[str, AgentContribution]
    reasoning: str                   # 人間可読サマリ
```

`Decimal` 型強制は CLAUDE.md §Financial calculations (Decimal type ONLY) に準拠。

---

## 5. 既存実装との対応マップ

| 既存 | 役割 | 4軸合議導入後の扱い |
|---|---|---|
| `consensus_bias()` (agents.py:98-120) | 多数決 (binary) | `weighted_directional_score()` ベースで再実装。score の符号で BULLISH/BEARISH 判定。後方互換 API として維持 |
| `average_confidence()` (agents.py:122-136) | 単純平均 | `weighted_confidence()` を呼ぶ薄い wrapper に変更。既存呼び出し元 (`data_feeds/router.py`) は無変更で動く |
| `indicator_and_macro_agree_bearish()` (agents.py:145-163) | 2軸 AND | **Phase 4 で削除**。Phase 1-3 は legacy guard 用に維持 |
| `indicator_and_macro_agree_bullish()` (agents.py:165-179) | 同上 | 同上 |
| `_DIRECTIONAL_THRESHOLD = 70` | hardcode 閾値 | Phase 4 で削除。新 `CONSENSUS_CONF_THRESHOLD` env |
| Guard 2 (`service.py:253-266`) | AND-condition フラグ立て | Phase 3 で `evaluate_4axis_consensus()` 呼び出しに置換 |
| Post-LLM clamp (`service.py:282-310`) | SELL/BUY → HOLD clamp | Phase 3 で「Post-LLM 整合表」(本ドキュメント 4.5) に置換 |
| prompts.py v4/v5 SYSTEM | 「BOTH Indicator AND Macro」 | Phase 3 で **v6 prompt** を新設、weighted score を入力に明示。v4/v5 は legacy 維持 |

---

## 6. 段階移行計画

> 各 Phase は **別 PR** で実装する。本ドキュメントは Phase 0 (設計レビュー) の成果物。

### Phase 0 — 設計レビュー (本 PR)

- 本ドキュメント (`docs/52_decision_layer_4axis_consensus_design.md`) を merge
- claude.ai PM レビュー + 小林さん READY
- **DoD**:
  - [x] design doc 作成
  - [ ] claude.ai approve
  - [ ] 未決事項 (§10) を Asana で起票

### Phase 1 — Shadow 並走実装 (Tier B / PR分離)

| 項目 | 内容 |
|---|---|
| Scope | `weighted_directional_score()` / `weighted_confidence()` / `evaluate_4axis_consensus()` 追加。既存 Guard 2 は維持。新結果は log のみ |
| 設定 | `CONSENSUS_4AXIS_MODE=shadow` (既定) / `off` / `shadow` |
| Migration | `judgment_logs.deterministic_breakdown` JSONB カラム追加 (NULL 許容) |
| テスト | unit test §7.1 全件 + regression §7.2 全 pass |
| **DoD** | shadow log が staging で 24h 観測可能、エラー率 0% |
| **切替 Trigger** | 7 日間 staging で旧/新 判定の一致率 ≥ 90% (BUY/SELL/HOLD クラス一致) |
| Tier 区分 | B (新規ファイル + JSONB カラム追加のみ。Guard 2 ロジックには触れない) |

### Phase 2 — staging A/B (Tier B / PR分離)

| 項目 | 内容 |
|---|---|
| Scope | env `CONSENSUS_4AXIS_MODE=a_b` で `judgment_id % 2` 抽選。50/50 で旧 (legacy AND) と新 (4軸) を交互に採用 |
| 設定 | staging のみ `a_b`。production は引き続き `shadow` |
| 監視 | A/B 別の `final_action` 分布、`final_confidence` 分布、SELL-spam 再発有無を計測 |
| テスト | `test_macro_stuck_no_sell` (Macro 連続 BEARISH 単独で SELL が出ないこと) を新規追加 |
| **DoD** | staging で 14 日経過 + chaos test (`scripts/uata-stuck-detector.sh` の inject path) pass |
| **切替 Trigger** | A/B 期間中の SELL/BUY の比率が旧側と比較して ±20% 以内 |
| Tier 区分 | B |

### Phase 3 — 既定切替 (Tier S / PR分離)

| 項目 | 内容 |
|---|---|
| Scope | `CONSENSUS_4AXIS_MODE=on` を既定値に。旧 Guard 2 ロジックは `CONSENSUS_LEGACY_AND=on` 設定時のみ復活 |
| Prompt | v6 prompt 新設 (weighted score を入力に含める)。`AI_PROMPT_VERSION` 既定値を v5 → v6 へ |
| Migration | なし (Phase 1 で済) |
| 本番反映条件 | staging soak 48h で全 BUY/SELL/HOLD 分布が想定範囲内、HF 安全 |
| **DoD** | staging 48h soak pass、prod 反映後 1h human watch、エラー率 0% |
| **Rollback** | `CONSENSUS_4AXIS_MODE=off` + `CONSENSUS_LEGACY_AND=on` を `.env.production` に追記して `docker compose up -d --no-deps backend-*` |
| Tier 区分 | S (`service.py` / `prompts.py` 両方触る。1日1PR ルール厳守) |

### Phase 4 — 旧コード削除 (Tier B / PR分離)

| 項目 | 内容 |
|---|---|
| Scope | `indicator_and_macro_agree_bearish/bullish` 削除、`_DIRECTIONAL_THRESHOLD` 削除、Guard 2 旧 path 削除、v4 prompt 削除 (v5 は LLM 後方互換のため残す検討) |
| Pre-condition | Phase 3 本番反映から 30 日以上、`CONSENSUS_LEGACY_AND` を有効化した本番事例なし |
| テスト | orphan check (`docs/ops/orphan_detection.md`) + 既存 `test_ai_sell_and_condition.py` の削除 / 4軸版へ置換 |
| **DoD** | Gate 1-7 全 pass、関連 docs 更新 (本ドキュメントは「Closed」へ) |
| Tier 区分 | B (削除のみで本番挙動は変化しない想定) |

#### Gate チェック表

| Phase | Gate 1-3 verify.sh | Gate 4 E2E | Gate 5 orphan | Gate 6 Codex | Gate 7 chrome |
|---|:-:|:-:|:-:|:-:|:-:|
| 0 (本 PR) | n/a (docs only) | n/a | n/a | optional | n/a |
| 1 | pass 必須 | pass 必須 | n/a | adversarial review 必須 (Aave 安全装置の延長) | n/a |
| 2 | pass | pass | n/a | review | n/a |
| 3 | pass | pass | pass | adversarial 必須 | UI 変更があれば必須 |
| 4 | pass | pass | **必須** | review | n/a |

---

## 7. テスト戦略

### 7.1 Unit tests (Phase 1 で新規追加)

`backend/tests/test_consensus_4axis.py` (新規 file):

| Test | 入力 | 期待 |
|---|---|---|
| `test_weighted_score_all_bullish_max` | 4軸 BULLISH conf=100 | score = +1.0, conf = 100 |
| `test_weighted_score_all_bearish_max` | 4軸 BEARISH conf=100 | score = −1.0, conf = 100 |
| `test_weighted_score_cancellation` | Indicator BULLISH 90 + Macro BEARISH 90 + Risk NEUTRAL + Pattern NEUTRAL | score ≈ 0.225 − 0.180 = +0.045 (HOLD) |
| `test_weighted_score_risk_dominant` | Risk BEARISH 80 単独 | score = −0.32, agreeing_count = 1, verdict = HOLD (単一暴走抑止) |
| `test_weighted_conf_arithmetic` | 異なる weight × confidence | 算術検証 |
| `test_evaluate_consensus_buy` | Indicator+Risk BULLISH 75 + Macro BULLISH 65 + Pattern NEUTRAL | BUY |
| `test_evaluate_consensus_sell` | Indicator+Risk BEARISH 80 + Macro BEARISH 70 | SELL |
| `test_evaluate_consensus_macro_stuck_no_sell` | Macro BEARISH 95 単独 | HOLD (再発防止のキーテスト) |
| `test_post_llm_veto_llm_buy_det_hold` | LLM=BUY, det=HOLD | HOLD |
| `test_post_llm_conflict_buy_vs_sell` | LLM=BUY, det=SELL | HOLD + warning |
| `test_weight_env_override` | env で weight 変更 | 計算に反映 |
| `test_weight_validation_fails` | weight 合計 = 1.5 | startup で raise (boot fail-closed) |

### 7.2 Regression (Phase 1-3 通して維持)

- COMPOUND RISK → HOLD は変わらず通る (`test_codex_p0_fail_closed.py` 既存)
- HF < 1.6 → HOLD は変わらず通る
- shadow mode で旧/新 一致率を CI で測定する pytest marker `@pytest.mark.consensus_shadow`

### 7.3 Property / chaos (Phase 2 で追加)

- `hypothesis` で agent signals を random sampling → score が `[-1, +1]`, conf が `[0, 100]` に収まる不変条件
- chaos: Macro Agent を BEARISH 90 で 24h 連続発火させ、SELL が出ないことを E2E で確認

### 7.4 Staging soak

- Phase 1: 7日 shadow → 旧/新一致率 ≥ 90% で次 phase
- Phase 2: 14日 A/B → SELL/BUY 比率 ±20% 以内で次 phase
- Phase 3: 48h soak → HF 安全 + 全 action 分布想定内

---

## 8. リスク・トレードオフ

| ID | リスク | 影響 | 対策 |
|---|---|---|---|
| R1 | 4軸統合で SELL/BUY 頻度が増えすぎる | 過剰取引で fee 超過 | Phase 1 shadow で観測。threshold (score 0.40 / conf 65) を env で調整可能 |
| R2 | Risk Agent 0.40 が bias を支配 | Risk が連続 BEARISH で SELL spam (新パターン) | (a) COMPOUND RISK は別経路 HARD STOP / (b) 単一軸暴走抑止 (agreeing_count ≥ 2) / (c) Risk 単独 BEARISH 80 でも weighted score −0.32 < threshold で HOLD |
| R3 | 重み env 設定ミス | 想定外の判定 | 起動時 validation で 1.0 ± 0.01 を強制、外れたら boot fail-closed |
| R4 | LLM と決定論層の不一致頻発 | trade 機会損失 | Phase 1 shadow で不一致率を測定。不一致 → HOLD veto で安全側 |
| R5 | migration 中の二重判定 latency | judgment 周期 (15-30s) への影響 | 4軸計算は O(4) で <1ms。shadow phase でも問題なし |
| R6 | Phase 3 切替直後の予期しない挙動 | 本番 trade 影響 | `CONSENSUS_LEGACY_AND=on` 1 行 env 追加で即時 rollback |
| R7 | Pattern Agent 0.15 が低すぎて flip-flop 検知が効かない | 連続誤判定の防止が弱まる | Pattern 自身が flip-flop 検知時に bias = NEUTRAL を返すため、weighted score の絶対値が下がる → HOLD に倒れる |
| R8 | 重み調整が「政治的」になる | 議論が決着しない | 重み変更は env のみで Phase 3 反映後は変更しない原則。次回見直しは Phase 4 完了後 30 日 |

---

## 9. セキュリティ・本番運用観点 (CLAUDE.md §Security Rules 準拠)

- 重み・閾値はすべて `.env.production` の env で制御 → 緊急 rollback がコード変更不要
- 重み変更は `.env.production` 書き換え → CLAUDE.md ABSOLUTE「Hetzner pull only / ローカル merge only」に従い、ローカル Mac で `.env.production` を edit → push → Hetzner で `git pull` + `deploy_production.sh` (本番直接編集禁止)
- 4軸 weighted へ切替時は `MONITORING_SERVICE_STOP=true` で 1h 観察を runbook に明記 (Phase 3 PR で `docs/22_production_release_checklist.md` 更新)
- Decimal 型を強制 (CLAUDE.md §Financial calculations) — `weighted_directional_score` は `Decimal`、`confidence` のみ `int`
- Health Factor < 1.6 → HARD_STOP は本変更で**触らない** (CLAUDE.md §Security Rules 2)

---

## 10. 未決事項 (人間判断待ち)

| # | 議題 | 既定提案 | 影響 Phase |
|---|---|---|---|
| Q1 | 既定重み (Risk 0.40 / Indicator 0.25 / Macro 0.20 / Pattern 0.15) — Pattern が低すぎないか? | 現行 v4/v5 prompt 記載値と整合させる優先 | Phase 1 着手前に確定 |
| Q2 | `SCORE_BUY_THRESHOLD = 0.40` / `CONF_THRESHOLD = 65` の妥当性 | 旧 binary 70 から 5pt 緩めた値。Phase 1 shadow で再評価可 | Phase 1 着手前 |
| Q3 | Phase 4 で `indicator_and_macro_agree_*` を削除 vs deprecated 維持 | 削除して `test_ai_sell_and_condition.py` も削除 | Phase 4 |
| Q4 | LLM=SELL / det=BUY の不一致時、HOLD veto で良いか (それとも LLM 側採用?) | HOLD veto + WARN ログ (安全側に倒す) | Phase 1 |
| Q5 | v6 prompt 新設 vs v5 流用 | 新設し、weighted score を入力に含める | Phase 3 |
| Q6 | `judgment_logs.deterministic_breakdown` JSONB を既存テーブルに追加 vs 別テーブル切出し | 既存テーブルへ追加 (1 PR で完結) | Phase 1 |

---

## 11. 関連リソース

### 11.1 コード参照

- `backend/app/ai/agents.py:98-179` — 現行 `consensus_bias` / `average_confidence` / `indicator_and_macro_agree_*` / `_DIRECTIONAL_THRESHOLD`
- `backend/app/ai/service.py:208-324` — `judge_with_rag` 内 Guard 1 / Guard 2 / post-LLM clamp
- `backend/app/ai/prompts.py:120-198` — v4 / v5 prompt の AND-condition ルール記述
- `backend/app/data_feeds/router.py:69,96` — `consensus_bias` / `average_confidence` を外向け API で公開している箇所
- `backend/tests/test_ai_sell_and_condition.py` — 既存 2軸 AND テスト
- `backend/tests/test_agents.py:203-` — 既存 `consensus_bias` テスト

### 11.2 教訓・先行ドキュメント

- `CLAUDE.lessons.md` 2026-05-21 SELL-spam (Macro Agent 25% 固着 / AND-condition 修正)
- `CLAUDE.lessons.md` 2026-05-26 staging soak 全 HOLD 三重故障 (AND clamp の HOLD bias を 1 つの原因として記録)
- `docs/05_ai_judgement_rules.md` — 上位の AI 判定ルール (本ドキュメントはここを実装層で具体化)
- `docs/13_security_design.md` — Security Rules / Decimal 強制
- `docs/14_test_strategy.md` — Gate 1-7 定義

### 11.3 オーナーシップ

- **アーキ承認**: claude.ai (PM)
- **実装承認 (Phase 1-3)**: 小林 浩紀
- **本番反映承認 (Phase 3)**: 小林 浩紀 (CLAUDE.md ABSOLUTE: main 直 push 禁止 / PR 必須)

---

## Appendix A: 計算例

### A.1 BUY 候補 (典型 bullish)

| Agent | bias | conf | direction | weight | contribution |
|---|---|---:|---:|---:|---:|
| Indicator | BULLISH | 75 | +1 | 0.25 | +0.1875 |
| Pattern | NEUTRAL | 40 | 0 | 0.15 | 0.0000 |
| Risk | BULLISH | 80 | +1 | 0.40 | +0.3200 |
| Macro | BULLISH | 65 | +1 | 0.20 | +0.1300 |
| **合計** | | | | **1.00** | **+0.6375** |

- `weighted_directional_score = +0.6375` ≥ +0.40 ✓
- `weighted_confidence = 0.25×75 + 0.15×40 + 0.40×80 + 0.20×65 = 18.75 + 6 + 32 + 13 = 69.75 → 70` ≥ 65 ✓
- `agreeing_count = 3` (Indicator + Risk + Macro が同方向 conf≥50) ≥ 2 ✓
- **Verdict: BUY**

### A.2 Macro stuck (single agent runaway, 旧 SELL-spam 再発防止確認)

| Agent | bias | conf | direction | weight | contribution |
|---|---|---:|---:|---:|---:|
| Indicator | NEUTRAL | 50 | 0 | 0.25 | 0.000 |
| Pattern | NEUTRAL | 35 | 0 | 0.15 | 0.000 |
| Risk | NEUTRAL | 45 | 0 | 0.40 | 0.000 |
| Macro | BEARISH | 95 | −1 | 0.20 | −0.190 |
| **合計** | | | | **1.00** | **−0.190** |

- `|score| = 0.190 < 0.40` → 閾値未達
- **Verdict: HOLD** ← 単一 Macro 暴走で SELL は出ない (C5 / 設計目標 5 達成)

### A.3 境界事例 (現行 2軸 AND では取り逃すケース)

Indicator BEARISH conf=69 / Macro BEARISH conf=72 / Risk BEARISH conf=80 / Pattern NEUTRAL conf=40

- 現行 2軸 AND: Indicator が 70 未満 → AND fail → HOLD
- 4軸 weighted:
  - direction contribution: 0.25×(−1)×0.69 + 0.20×(−1)×0.72 + 0.40×(−1)×0.80 + 0.15×0×0.40 = −0.1725 − 0.144 − 0.32 + 0 = **−0.6365**
  - weighted_conf: 0.25×69 + 0.20×72 + 0.40×80 + 0.15×40 = 17.25 + 14.4 + 32 + 6 = **69.65 → 70**
  - agreeing_count = 3
  - **Verdict: SELL** ← 3 軸が一致 BEARISH しているので取り逃さない

---

## Appendix B: ロールバック手順 (Phase 3 反映後)

1. `.env.production` をローカル Mac で edit:
   ```
   CONSENSUS_4AXIS_MODE=off
   CONSENSUS_LEGACY_AND=on
   ```
2. `git add .env.production && git commit && git push`
3. Hetzner で `git pull origin main`
4. `./scripts/deploy_production.sh --frontend-only=false` (backend 再起動)
5. Slack `#ultra-auto-project` に rollback 完了通知

所要時間: 約 5 分 (deploy script 内訳)。

---

## Appendix C: 変更履歴

| Date | Author | Change |
|---|---|---|
| 2026-05-26 | Claude (Opus 4.7) / 小林 浩紀 | 初版 (Phase 0 設計レビュー) |
