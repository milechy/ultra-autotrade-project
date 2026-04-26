#!/usr/bin/env python3
"""TimesFM PoC: Aave V3 USDC supply APY forecasting (Asana 1214077580922982).

DeFiLlama daily APY history → forecast next 24h (1d) and 7d → compare against
real values and ARIMA / Prophet baselines. Records inference time and peak
RSS. Designed to be invoked outside of verify.sh (heavy ML deps).

Data source pivot: spec called for Base Sepolia, but Sepolia testnet has no
meaningful APY history. Switched to Aave V3 USDC on Base mainnet via
DeFiLlama yields chart (pool 7e0661bf-8cf3-45e6-9424-31916d4c7b84). Same
contract logic; mainnet provides ~750 days of real signal needed to evaluate
the modeling technique. See docs/51_timesfm_poc_report.md.

Usage (with dedicated venv):
    uv venv --python 3.11 /tmp/timesfm-poc-venv
    VIRTUAL_ENV=/tmp/timesfm-poc-venv uv pip install \\
        "timesfm[torch]" prophet statsmodels pandas requests
    /tmp/timesfm-poc-venv/bin/python scripts/timesfm_poc.py \\
        --output docs/timesfm_poc_results.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import resource
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

DEFILLAMA_POOL_ID = "7e0661bf-8cf3-45e6-9424-31916d4c7b84"  # Aave V3 USDC Base
DEFILLAMA_CHART_URL = f"https://yields.llama.fi/chart/{DEFILLAMA_POOL_ID}"
HORIZON_SHORT = 1  # next 1 day  (proxy for "next 24h" at daily resolution)
HORIZON_LONG = 7  # next 7 days
TRAIN_DAYS = 30  # spec: "過去30日" — used for the test windows below
TIMESFM_REPO = "google/timesfm-2.0-500m-pytorch"
TIMESFM_BACKEND = os.environ.get("TIMESFM_BACKEND", "cpu")  # cpu | gpu | tpu


@dataclasses.dataclass
class ForecastResult:
    name: str
    horizon: int
    actual: list[float]
    predicted: list[float]
    mse: float
    mae: float
    direction_accuracy: float
    inference_seconds: float
    peak_rss_mb: float


def _peak_rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kilobytes.
    return usage / (1024 * 1024) if sys.platform == "darwin" else usage / 1024


def fetch_apy_history() -> pd.DataFrame:
    print(f"[fetch] GET {DEFILLAMA_CHART_URL}", flush=True)
    response = requests.get(DEFILLAMA_CHART_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data", [])
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["apy"] = df["apy"].astype(float)
    print(
        f"[fetch] {len(df)} daily points "
        f"({df['timestamp'].min().date()} → {df['timestamp'].max().date()})",
        flush=True,
    )
    return df[["timestamp", "apy"]]


def _direction_accuracy(actual: np.ndarray, predicted: np.ndarray, last_train: float) -> float:
    if actual.size == 0:
        return 0.0
    actual_dir = np.sign(actual - last_train)
    pred_dir = np.sign(predicted - last_train)
    matches = int(np.sum(actual_dir == pred_dir))
    return matches / actual.size


def _metrics(
    name: str,
    horizon: int,
    actual: np.ndarray,
    predicted: np.ndarray,
    last_train: float,
    elapsed: float,
    peak_mb: float,
) -> ForecastResult:
    err = predicted - actual
    return ForecastResult(
        name=name,
        horizon=horizon,
        actual=actual.tolist(),
        predicted=predicted.tolist(),
        mse=float(np.mean(err**2)),
        mae=float(np.mean(np.abs(err))),
        direction_accuracy=_direction_accuracy(actual, predicted, last_train),
        inference_seconds=elapsed,
        peak_rss_mb=peak_mb,
    )


def run_timesfm(train: np.ndarray, horizon: int) -> tuple[np.ndarray, float, float]:
    import timesfm

    hparams = timesfm.TimesFmHparams(
        backend=TIMESFM_BACKEND,
        per_core_batch_size=1,
        horizon_len=max(horizon, 32),  # multiple of output_patch_len(=128) preferred
        context_len=512,
        num_layers=50,  # 2.0-500m architecture
        use_positional_embedding=False,
    )
    checkpoint = timesfm.TimesFmCheckpoint(huggingface_repo_id=TIMESFM_REPO)
    print(f"[timesfm] loading {TIMESFM_REPO} on {TIMESFM_BACKEND} ...", flush=True)
    load_start = time.perf_counter()
    model = timesfm.TimesFm(hparams=hparams, checkpoint=checkpoint)
    print(f"[timesfm] loaded in {time.perf_counter() - load_start:.1f}s", flush=True)

    start = time.perf_counter()
    point, _quantile = model.forecast(
        inputs=[train.astype(np.float32)],
        freq=[0],  # 0 = high-frequency / daily
    )
    elapsed = time.perf_counter() - start
    return point[0, :horizon].astype(float), elapsed, _peak_rss_mb()


def run_arima(train: np.ndarray, horizon: int) -> tuple[np.ndarray, float, float]:
    from statsmodels.tsa.arima.model import ARIMA

    start = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ARIMA(train, order=(2, 1, 2)).fit()
        forecast = np.asarray(model.forecast(steps=horizon))
    elapsed = time.perf_counter() - start
    return forecast.astype(float), elapsed, _peak_rss_mb()


def run_prophet(train_df: pd.DataFrame, horizon: int) -> tuple[np.ndarray, float, float]:
    import logging

    from prophet import Prophet

    logging.getLogger("prophet").setLevel(logging.ERROR)
    logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

    history = train_df.rename(columns={"timestamp": "ds", "apy": "y"})
    history["ds"] = history["ds"].dt.tz_localize(None)

    start = time.perf_counter()
    model = Prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=False)
    model.fit(history)
    future = model.make_future_dataframe(periods=horizon, freq="D", include_history=False)
    forecast = model.predict(future)["yhat"].to_numpy()
    elapsed = time.perf_counter() - start
    return forecast.astype(float), elapsed, _peak_rss_mb()


def run_naive(train: np.ndarray, horizon: int) -> tuple[np.ndarray, float, float]:
    """Persistence baseline: predict the last observed value forward."""
    start = time.perf_counter()
    out = np.full(horizon, train[-1], dtype=float)
    elapsed = time.perf_counter() - start
    return out, elapsed, _peak_rss_mb()


def evaluate(df: pd.DataFrame, horizon: int, *, skip_timesfm: bool) -> list[ForecastResult]:
    train_df = df.iloc[:-horizon].copy()
    actual = df["apy"].iloc[-horizon:].to_numpy()
    train = train_df["apy"].to_numpy()
    last_train = float(train[-1])

    print(
        f"\n=== Horizon {horizon}d (train={len(train)} pts, "
        f"actual range {actual.min():.3f}-{actual.max():.3f}%) ===",
        flush=True,
    )

    results: list[ForecastResult] = []

    naive_pred, naive_t, naive_mb = run_naive(train, horizon)
    results.append(
        _metrics("Naive (persistence)", horizon, actual, naive_pred, last_train, naive_t, naive_mb)
    )

    arima_pred, arima_t, arima_mb = run_arima(train, horizon)
    results.append(
        _metrics("ARIMA(2,1,2)", horizon, actual, arima_pred, last_train, arima_t, arima_mb)
    )

    prophet_pred, prophet_t, prophet_mb = run_prophet(train_df, horizon)
    results.append(
        _metrics("Prophet", horizon, actual, prophet_pred, last_train, prophet_t, prophet_mb)
    )

    if not skip_timesfm:
        tfm_pred, tfm_t, tfm_mb = run_timesfm(train, horizon)
        results.append(
            _metrics(
                f"TimesFM ({TIMESFM_REPO.split('/')[-1]})",
                horizon,
                actual,
                tfm_pred,
                last_train,
                tfm_t,
                tfm_mb,
            )
        )

    for r in results:
        print(
            f"  {r.name:36s}  MSE={r.mse:7.4f}  MAE={r.mae:6.4f}  "
            f"dir_acc={r.direction_accuracy:4.2f}  "
            f"t={r.inference_seconds:6.2f}s  peak={r.peak_rss_mb:6.1f}MB",
            flush=True,
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON output path (e.g. docs/timesfm_poc_results.json)",
    )
    parser.add_argument(
        "--skip-timesfm", action="store_true", help="Skip TimesFM (run baselines only)"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=TRAIN_DAYS * 6,
        help="Use only the last N days of history (default: 180)",
    )
    args = parser.parse_args()

    df = fetch_apy_history()
    if args.lookback_days > 0:
        df = df.tail(args.lookback_days).reset_index(drop=True)
        print(f"[trim] using last {len(df)} days for the experiment", flush=True)

    all_results: dict[str, list[dict[str, Any]]] = {}
    for horizon in (HORIZON_SHORT, HORIZON_LONG):
        results = evaluate(df, horizon, skip_timesfm=args.skip_timesfm)
        all_results[f"horizon_{horizon}d"] = [dataclasses.asdict(r) for r in results]

    summary = {
        "ran_at_utc": datetime.now(UTC).isoformat(),
        "data_source": {
            "provider": "DeFiLlama",
            "pool_id": DEFILLAMA_POOL_ID,
            "asset": "Aave V3 USDC on Base (mainnet)",
            "points_used": len(df),
            "first": df["timestamp"].min().isoformat(),
            "last": df["timestamp"].max().isoformat(),
        },
        "timesfm_repo": TIMESFM_REPO,
        "timesfm_backend": TIMESFM_BACKEND,
        "results": all_results,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2))
        print(f"\n[output] wrote {args.output}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
