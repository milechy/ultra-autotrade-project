# 51. TimesFM PoC レポート — 時系列予測モデルの DeFi 適用可能性検証

- **Asana タスク**: 1214077580922982
- **担当**: hkobayashi
- **実施日**: 2026-04-26
- **ブランチ**: `poc/timesfm-1214077580922982`
- **後続タスク**: GID 1214077372680383（統合設計、Due 08-31）

---

## 1. 結論（推奨判定）

**採用推奨（条件付き）**。
TimesFM 2.0 (500M) は AI Optimizer の ENB（Expected Net Benefit）計算に組み込む価値が
ベンチマークで明確に確認できた。ただし以下の3条件を満たすこと:

1. **メモリ予算 4GB 以上の専用ワーカー**を用意する（バックエンド本体プロセスに同居させない）
2. **モデルロードはアプリ起動時に1回**（cold load 約5分のため、リクエスト毎ロード禁止）
3. **Phase 1 では「補助スコア」として導入**（取引判定の主因子にせず、ENB の信頼度補正に使う）

代替案を検討する場合は **Prophet** が次点（精度は劣るが、軽量・依存物が少ない）。

---

## 2. ベンチマーク結果

### 2.1 データセット

| 項目 | 値 |
|------|----|
| 提供元 | DeFiLlama yields chart |
| プール | `7e0661bf-8cf3-45e6-9424-31916d4c7b84`（Aave V3 USDC on Base mainnet） |
| 期間 | 2025-10-29 〜 2026-04-26（直近180日 / 全778日中） |
| 解像度 | daily |
| テスト分割 | walk-forward: train = 直近180日 − 予測ホライズン、test = 残り |

> **データソース変更（PoC ピボット）**: 仕様書では Base **Sepolia** を指定していたが、
> Sepolia testnet は APY が常時 0 付近で時系列としての評価信号にならないため、
> 同じ Aave V3 + USDC 契約ロジックを共有する **Base mainnet** に切り替え。
> 評価対象は「モデルが Aave APY 系列を学習・予測できるか」であり、
> ネットワーク差はモデル評価に影響しない。本番統合時は実 RPC 経由の任意チェーン APY を
> そのまま入力可能。

### 2.2 精度

| ホライズン | モデル | MSE | MAE | 方向一致率 |
|-----------|--------|-----|-----|-----------|
| 1d | Naive (persistence) | 0.0002 | 0.0128 | 0.00 |
| 1d | ARIMA(2,1,2) | 0.0961 | 0.3099 | 1.00 |
| 1d | Prophet | 0.0969 | 0.3113 | 0.00 |
| 1d | **TimesFM 2.0-500m** | **0.0002** | **0.0137** | **1.00** |
| 7d | Naive (persistence) | 85.8315 | 9.2476 | 0.00 |
| 7d | ARIMA(2,1,2) | 4.4968 | 1.9755 | 1.00 |
| 7d | Prophet | 1.2555 | 0.9369 | 1.00 |
| 7d | **TimesFM 2.0-500m** | **0.3330** | **0.3855** | **1.00** |

**読み方**:
- 1d ホライズンでは APY が前日と概ね同値だったため Naive がほぼ最適、TimesFM はそれに同等
- **7d ホライズンでは 2026-04-19 に APY が 13% に瞬間スパイク**（utilization spike 由来）
  したため、Naive は壊滅的（MSE=85.83）。ARIMA/Prophet/TimesFM は全て mean revert を
  正しく学習し、TimesFM が **Prophet 比 3.8× 高精度・ARIMA 比 13.5× 高精度** を達成
- 方向一致率 1.0 は「次の値が直近観測値より上か下か」を全てのテスト点で当てたことを示す

### 2.3 推論コスト（Apple Silicon CPU バックエンド、`per_core_batch_size=1`）

| モデル | コールドロード | ウォーム推論（1d） | ウォーム推論（7d） | 推論ピークRSS |
|--------|-------------|-------------------|------------------|----------------|
| Naive | < 1ms | < 1ms | < 1ms | 82 MB |
| ARIMA(2,1,2) | — | 47 ms | 213 ms | +74 MB |
| Prophet | — | 56 ms | 218 ms | +23 MB |
| **TimesFM 2.0-500m** | **324 s（HF DL含む）** | **236 ms** | **604 ms** | **+3,651 MB** |

**注釈**:
- TimesFM のコールドロードは HuggingFace 初回ダウンロード約 2GB 込みの実測値
- 同一プロセス内 2 回目のロードは 4.3 秒（チェックポイントキャッシュヒット）
- ピーク RSS はプロセス全体の RUSAGE 計測。差分が TimesFM 純増分の目安
- GPU バックエンド（CUDA / Metal）での測定は本 PoC 範囲外（Hetzner 環境では CPU 想定）

---

## 3. ライブラリ調査サマリ

| 項目 | 値 |
|------|----|
| 公式リポジトリ | https://github.com/google-research/timesfm |
| ライセンス | **Apache-2.0**（MIT 互換、商用利用可） |
| PyPI パッケージ | `timesfm`（最新 1.3.0、 PyTorch + JAX 両対応） |
| 推奨モデル | `google/timesfm-2.0-500m-pytorch`（500M params, HuggingFace 配布） |
| 軽量モデル | `google/timesfm-1.0-200m-pytorch`（200M params、精度トレードオフ） |
| 最新世代 | TimesFM 2.5 (200M, 2025-09-15) — PyPI 1.3.0 では未対応、要 source install |
| バックエンド | CPU / GPU / TPU / Apple Silicon すべて対応（PyTorch or Flax/JAX） |
| Python 要件 | 3.10–3.13（**3.14 は未対応** — PoC では `uv venv --python 3.11` で構築） |
| コンテキスト長 | 最大 16k tokens（2.5）/ 512 tokens（2.0） |
| 予測ホライズン | 連続 quantile 出力で最大 1k step |

---

## 4. AI Optimizer (ENB) 統合の擬似コード

`backend/app/aave/net_benefit_calculator.py` および
`backend/app/protocols/risk/` にあるリスクスコア計算は、現在 **直近観測値**を APY の
点推定として使用している。TimesFM の 7 日予測を組み込むことで、ENB を「期待 APY × 信頼区間」
で重み付けでき、APY 急変動時のオーバートレード抑制が期待できる。

```python
# backend/app/forecasting/timesfm_service.py（新設想定）
from __future__ import annotations
from decimal import Decimal
from typing import Sequence
import numpy as np

class TimesFMForecaster:
    """シングルトン想定。プロセス起動時に load() を1回だけ呼ぶ。"""

    def __init__(self, repo_id: str = "google/timesfm-2.0-500m-pytorch") -> None:
        self._repo_id = repo_id
        self._model = None  # 遅延ロード

    def load(self) -> None:
        import timesfm
        hparams = timesfm.TimesFmHparams(
            backend="cpu", per_core_batch_size=1,
            horizon_len=128, context_len=512,
            num_layers=50, use_positional_embedding=False,
        )
        ckpt = timesfm.TimesFmCheckpoint(huggingface_repo_id=self._repo_id)
        self._model = timesfm.TimesFm(hparams=hparams, checkpoint=ckpt)

    def forecast_apy(self, history_pct: Sequence[float], horizon_days: int = 7
                     ) -> tuple[np.ndarray, np.ndarray]:
        """直近の日次 APY 系列を入力 → 点予測と quantile (10/50/90) を返す。"""
        assert self._model is not None, "call load() at startup"
        point, quantile = self._model.forecast(
            inputs=[np.asarray(history_pct, dtype=np.float32)], freq=[0])
        return point[0, :horizon_days], quantile[0, :horizon_days]


# backend/app/aave/net_benefit_calculator.py の差分（疑似コード）
def expected_net_benefit(
    deposit_usd: Decimal,
    current_apy_pct: Decimal,
    forecaster: TimesFMForecaster | None,  # ← 追加（任意）
    apy_history_pct: Sequence[float],       # ← 追加（直近 N 日）
) -> NetBenefitDecision:
    if forecaster is not None and len(apy_history_pct) >= 64:
        point, quantile = forecaster.forecast_apy(apy_history_pct, horizon_days=7)
        # 7日平均と quantile band を信頼区間として使用
        expected_apy = Decimal(float(np.mean(point))) / Decimal("100")
        # quantile[:, 4] = p50, quantile[:, 0] = p10, quantile[:, 8] = p90
        lower = Decimal(float(np.mean(quantile[:, 0]))) / Decimal("100")
        upper = Decimal(float(np.mean(quantile[:, 8]))) / Decimal("100")
        # 既存ロジックの current_apy を expected_apy に差し替え + 信頼幅で割引
        confidence_factor = Decimal("1") - (upper - lower) / max(expected_apy, Decimal("0.001"))
        adjusted_apy = expected_apy * max(confidence_factor, Decimal("0.5"))
    else:
        adjusted_apy = current_apy_pct / Decimal("100")  # フォールバック（現行挙動）
    # ... ガス代・スリッページ控除 ENB 計算は既存ロジック踏襲 ...
```

**統合時の注意（次タスクの設計事項）**:
1. `TimesFMForecaster` は **アプリ起動時シングルトン**（`get_monitoring_service()` パターン踏襲）
2. **ヘルス系統と同一プロセスに乗せない**（4GB 占有は致命的）→ 別ワーカー or 別コンテナ
3. ENB 計算で TimesFM 予測を採用する閾値: `len(apy_history_pct) >= 64`（TimesFM 2.0 の input_patch_len）
4. **API 不可達時の fail-open**: `forecaster is None` パスで現行ロジック継続
5. **ガード**: `confidence_factor < 0.5` の場合は HOLD（信頼区間が広すぎる場合に取引抑制）

---

## 5. 統合設計タスクの前提条件リスト（GID 1214077372680383 への引継ぎ）

### 5.1 確定事項
- ライセンスは Apache-2.0、商用利用 OK
- モデルチェックポイント約 2GB、HuggingFace 経由で配布
- 推論時間（CPU, M-series）はウォーム状態で 1d 予測 0.24s / 7d 予測 0.60s — リアルタイム判定許容範囲内
- 7 日 APY 予測精度は MAE 0.39%（=39 bps）— ガス代と同オーダー、有意なシグナル

### 5.2 設計タスクで決めるべきこと
- [ ] **デプロイ形態**: バックエンドコンテナに同居 vs 専用 forecasting サービス（gRPC/HTTP）
- [ ] **メモリ予算**: Hetzner 本番 VPS の RAM 構成確認（現状 16GB 程度？） → 専用コンテナなら 4–6GB 確保
- [ ] **モデル更新サイクル**: TimesFM 2.5 への移行タイミング（精度 vs 安定性トレードオフ）
- [ ] **入力データの正規化**: 複数チェーン（Polygon / Arbitrum / Base / Optimism）の APY 系列を
      単一モデルに食わせるか、チェーン毎に独立予測するか
- [ ] **共変量入力**: Pendle/Lido など他プロトコルの APY を共変量として入れるか（`forecast_with_covariates` API）
- [ ] **オフライン評価パイプライン**: 週次で walk-forward backtest を回す Cron（既存
      `scripts/backtest_weekly.py` への統合可能性）
- [ ] **GPU バックエンド評価**: GPU 化で推論を 10× 速くする価値があるか（コスト対効果）
- [ ] **HF_TOKEN 設定**: 匿名 DL は rate limit あり。本番では `HF_TOKEN` を `.env.production` に追加
- [ ] **モニタリング**: 予測値と実測値の継続検証（データドリフト検出 → アラート）

### 5.3 やらないこと（明示）
- 短期トレード（1h / 15min 単位）への適用は本 PoC 範囲外
  （日次の APY スイートポット判断のみ評価）
- TimesFM のファインチューニングは行わない（zero-shot 利用）

---

## 6. 代替案（採用しなかった場合の次善策）

| 順位 | 候補 | 利点 | 欠点 |
|------|------|------|------|
| 1 | **Prophet** | 軽量（+23MB）、依存少、解釈容易 | 7d 予測 MAE 0.94% — TimesFM の 2.4 倍 |
| 2 | **ARIMA(p,d,q)** | 標準ライブラリ、超軽量 | パラメータチューニングが市場ごとに必要、7d MAE 1.98% |
| 3 | LSTM（自前学習） | カスタム調整可 | 学習データ収集・運用コスト高、PoC 範囲外 |
| 4 | xgboost（lag 特徴） | 解釈容易、共変量扱いやすい | 系列固有のパターン学習能力が劣る |

**判断ロジック**: メモリ予算が確保できない場合は Prophet で開始 → 余裕ができたら TimesFM へスイッチ。

---

## 7. 再現手順

```bash
# 1. ブランチ取得
git checkout poc/timesfm-1214077580922982

# 2. PoC 用 Python 3.11 venv 作成（プロジェクト venv とは別）
uv venv --python 3.11 /tmp/timesfm-poc-venv

# 3. 依存インストール（約 5 分、約 2GB ダウンロード）
VIRTUAL_ENV=/tmp/timesfm-poc-venv uv pip install \
    "timesfm[torch]" "prophet>=1.1" "statsmodels>=0.14" \
    "pandas>=2.0" "numpy>=2.0,<3" "requests>=2.31"

# 4. 実行（初回は HF からのチェックポイント DL で +5 分）
/tmp/timesfm-poc-venv/bin/python scripts/timesfm_poc.py \
    --output docs/timesfm_poc_results.json

# 5. ベースライン比較のみ（軽量チェック用）
/tmp/timesfm-poc-venv/bin/python scripts/timesfm_poc.py --skip-timesfm
```

raw 結果: `docs/timesfm_poc_results.json`

---

## 8. 残課題

- TimesFM 2.5（最新世代）の精度評価 — PyPI `timesfm 1.3.0` 未対応のため source install が必要
- GPU バックエンドの推論時間計測 — Hetzner GPU プランの可否次第
- Pendle YT / Lido stETH への同手法適用 — 別ホライズン特性かもしれず再評価必要
- `forecast_with_covariates` を使った gas price / 為替 共変量モデリングの検証

---

## 9. 参考

- [TimesFM GitHub](https://github.com/google-research/timesfm)
- [TimesFM 2.0 HuggingFace](https://huggingface.co/google/timesfm-2.0-500m-pytorch)
- [DeFiLlama Yields API](https://defillama.com/docs/api)
- 既存実装: `backend/app/aave/utilization_monitor.py`, `backend/app/aave/net_benefit_calculator.py`
