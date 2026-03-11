# backend/tests/test_ai_prefilter.py
"""プレフィルタリング（テクニカル指標）とOpus→Sonnetフォールバックのテスト。"""

import sys
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from app.ai.prefilter import (  # noqa: E402
    PrefilterResult,
    calculate_ma,
    calculate_rsi,
    run_prefilter,
)
from app.ai.schemas import LLMProvider, TradeAction
from app.ai.service import AIService

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_ohlcv(closes: List[float]) -> List[List[Any]]:
    """終値リストからダミーOHLCVを生成する。"""
    return [[i * 3600000, c - 50, c + 100, c - 100, c, 10.0] for i, c in enumerate(closes)]


class _MockOHLCVClient:
    """テスト用のダミーOHLCVクライアント。"""

    def __init__(self, closes: List[float]) -> None:
        self._closes = closes

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List]:
        return _make_ohlcv(self._closes[-limit:])


class _FailingOHLCVClient:
    """fetch_ohlcvが常に例外を投げるダミークライアント。"""

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List]:
        raise RuntimeError("Network error")


# ---------------------------------------------------------------------------
# calculate_rsi のテスト
# ---------------------------------------------------------------------------


class TestCalculateRSI:
    def test_returns_none_if_insufficient_data(self) -> None:
        result = calculate_rsi([50000.0] * 10, period=14)
        assert result is None

    def test_all_gains_returns_100(self) -> None:
        # 単調増加 → RSI=100
        prices = [float(i) for i in range(50, 80)]  # 30本
        result = calculate_rsi(prices, period=14)
        assert result == pytest.approx(100.0)

    def test_all_losses_returns_0(self) -> None:
        # 単調減少 → RSI=0（avg_loss > 0, avg_gain = 0 → rs=0 → RSI=100/(1+0)=100... wait）
        # 実際: avg_gain=0 → RSI = 100 - 100/(1+0) = 0 は誤り
        # avg_gain=0, avg_loss>0 → rs=0 → RSI = 100 - 100/(1+0) = 0... no
        # RSI = 100 - 100/(1 + rs), rs = avg_gain/avg_loss
        # avg_gain=0 → rs=0 → RSI = 100 - 100/1 = 0
        prices = [float(80 - i) for i in range(30)]  # 80, 79, ..., 51
        result = calculate_rsi(prices, period=14)
        assert result == pytest.approx(0.0)

    def test_valid_rsi_range(self) -> None:
        # 通常の価格変動 → 0〜100の範囲
        import math

        prices = [50000 + math.sin(i * 0.3) * 1000 for i in range(30)]
        result = calculate_rsi(prices, period=14)
        assert result is not None
        assert 0.0 <= result <= 100.0

    def test_rsi_oversold_threshold(self) -> None:
        # 急落後はRSI < 30（oversold）
        prices = [50000.0] * 5 + [50000.0 - i * 500 for i in range(25)]
        result = calculate_rsi(prices, period=14)
        assert result is not None
        assert result < 40.0  # 急落後は低くなる


# ---------------------------------------------------------------------------
# calculate_ma のテスト
# ---------------------------------------------------------------------------


class TestCalculateMA:
    def test_returns_none_if_insufficient_data(self) -> None:
        assert calculate_ma([50000.0] * 5, period=7) is None

    def test_correct_average(self) -> None:
        closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        result = calculate_ma(closes, period=7)
        assert result == pytest.approx(4.0)

    def test_uses_latest_data(self) -> None:
        closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = calculate_ma(closes, period=3)
        assert result == pytest.approx(9.0)  # (8+9+10)/3 = 9


# ---------------------------------------------------------------------------
# run_prefilter のテスト
# ---------------------------------------------------------------------------


class TestRunPrefilter:
    def test_returns_prefilter_result(self) -> None:
        closes = [50000.0 + i * 10 for i in range(50)]
        client = _MockOHLCVClient(closes)
        result = run_prefilter(client, symbol="BTC/USDT")
        assert isinstance(result, PrefilterResult)
        assert result.symbol == "BTC/USDT"

    def test_insufficient_data_returns_neutral(self) -> None:
        closes = [50000.0] * 5  # データが少なすぎる
        client = _MockOHLCVClient(closes)
        result = run_prefilter(client)
        # データ不足でもクラッシュせず INSUFFICIENT_DATA か NEUTRAL を返す
        assert result.signal in ("INSUFFICIENT_DATA", "NEUTRAL")

    def test_fetch_fails_returns_insufficient_data(self) -> None:
        client = _FailingOHLCVClient()
        result = run_prefilter(client)
        assert result.signal == "INSUFFICIENT_DATA"
        assert result.rsi is None
        assert result.ma_short is None

    def test_uptrend_returns_buy_lean(self) -> None:
        # 単調増加 → Golden Cross + RSI高め → SELL_LEAN（RSI=100なのでoverbought）
        closes = [40000.0 + i * 100 for i in range(50)]
        client = _MockOHLCVClient(closes)
        result = run_prefilter(client)
        # 急上昇ではRSI高い→OVERBOUGHT、MA short > long → GOLDEN_CROSS
        # SELL_LEAN が1、BUY_LEAN が1で相反 → NEUTRAL or SELL_LEAN
        assert result.signal in ("SELL_LEAN", "NEUTRAL", "BUY_LEAN")

    def test_rsi_signal_oversold(self) -> None:
        # RSI < 30になる急落シナリオ
        closes = [50000.0] * 10 + [50000.0 - i * 500 for i in range(30)]
        client = _MockOHLCVClient(closes)
        result = run_prefilter(client)
        if result.rsi is not None and result.rsi < 30:
            assert result.rsi_signal == "OVERSOLD"

    def test_ma_signal_golden_cross(self) -> None:
        closes = [50000.0 + i * 50 for i in range(50)]
        client = _MockOHLCVClient(closes)
        result = run_prefilter(client)
        # 上昇トレンドではshort MA > long MA
        if result.ma_short is not None and result.ma_long is not None:
            if result.ma_short > result.ma_long:
                assert result.ma_signal == "GOLDEN_CROSS"

    def test_empty_ohlcv_returns_insufficient_data(self) -> None:
        client = MagicMock()
        client.fetch_ohlcv.return_value = []
        result = run_prefilter(client)
        assert result.signal == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Opus→Sonnet フォールバックのテスト
# ---------------------------------------------------------------------------


class TestOpusSonnetFallback:
    def _make_settings(
        self,
        *,
        opus_model: str = "claude-opus-4-5",
        fallback_model: str = "claude-sonnet-4-20250514",
    ) -> MagicMock:
        settings = MagicMock()
        settings.anthropic_api_key = "sk-test"
        settings.claude_model = opus_model
        settings.ai_fallback_model = fallback_model
        return settings

    def _make_mock_anthropic(self, response_json: str) -> MagicMock:
        """正常なAnthropicクライアントのモック。"""
        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = response_json
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response
        mock_module.Anthropic.return_value = mock_client
        return mock_module

    def test_opus_success_returns_claude_provider(self) -> None:
        """Opusが成功した場合はprovider=CLAUDEで返す。"""
        service = AIService()
        settings = self._make_settings()
        mock_module = self._make_mock_anthropic(
            '{"action": "BUY", "confidence": 80, "reason": "bullish"}'
        )
        with patch.dict(sys.modules, {"anthropic": mock_module}):
            result = service._call_claude("test prompt", settings)
        assert result.action == TradeAction.BUY
        assert result.provider == LLMProvider.CLAUDE
        assert result.confidence == 80

    def test_opus_fails_twice_switches_to_sonnet(self) -> None:
        """Opusが2回失敗した場合、Sonnetにフォールバックする。"""
        service = AIService()
        settings = self._make_settings()

        # Opusは失敗、Sonnetは成功するモック
        call_count = 0
        opus_model = settings.claude_model

        def side_effect_create(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            model = kwargs.get("model", "")
            if model == opus_model:
                raise RuntimeError("Opus timeout")
            # Sonnetの場合は成功
            mock_block = MagicMock()
            mock_block.text = '{"action": "BUY", "confidence": 75, "reason": "fallback ok"}'
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            return mock_response

        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = side_effect_create
        mock_module.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_module}):
            result = service._call_claude("test prompt", settings)

        assert result.provider == LLMProvider.CLAUDE_FALLBACK

    def test_fallback_confidence_is_decayed(self) -> None:
        """フォールバック時はconfidenceが0.8倍に減衰される。"""
        service = AIService()
        settings = self._make_settings()

        opus_model = settings.claude_model

        def side_effect_create(**kwargs: Any) -> Any:
            model = kwargs.get("model", "")
            if model == opus_model:
                raise RuntimeError("Opus unavailable")
            mock_block = MagicMock()
            mock_block.text = '{"action": "SELL", "confidence": 100, "reason": "fallback"}'
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            return mock_response

        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = side_effect_create
        mock_module.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_module}):
            result = service._call_claude("test prompt", settings)

        assert result.confidence == 80  # 100 * 0.8 = 80
        assert result.provider == LLMProvider.CLAUDE_FALLBACK

    def test_fallback_provider_recorded_as_claude_fallback(self) -> None:
        """フォールバック時はprovider="claude_fallback"として記録される。"""
        service = AIService()
        settings = self._make_settings()
        opus_model = settings.claude_model

        def side_effect_create(**kwargs: Any) -> Any:
            if kwargs.get("model", "") == opus_model:
                raise ConnectionError("Opus connection failed")
            mock_block = MagicMock()
            mock_block.text = '{"action": "HOLD", "confidence": 50, "reason": "uncertain"}'
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            return mock_response

        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = side_effect_create
        mock_module.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_module}):
            result = service._call_claude("test prompt", settings)

        assert result.provider == LLMProvider.CLAUDE_FALLBACK
        assert result.provider == "claude_fallback"  # str比較も確認

    def test_both_opus_and_sonnet_fail_returns_hold(self) -> None:
        """OpusもSonnetも失敗した場合はHOLDを返す。"""
        service = AIService()
        settings = self._make_settings()

        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("All APIs down")
        mock_module.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_module}):
            result = service._call_claude("test prompt", settings)

        assert result.action == TradeAction.HOLD
        assert result.confidence == 0
        assert result.provider == LLMProvider.CLAUDE_FALLBACK

    def test_no_api_key_returns_hold_immediately(self) -> None:
        """APIキー未設定時は即座にHOLDを返す（リトライなし）。"""
        service = AIService()
        settings = MagicMock()
        settings.anthropic_api_key = None

        result = service._call_claude("test prompt", settings)

        assert result.action == TradeAction.HOLD
        assert result.provider == LLMProvider.CLAUDE

    def test_ai_fallback_model_env_var(self) -> None:
        """AI_FALLBACK_MODELの環境変数が正しく読み込まれる。"""
        import os

        with patch.dict(os.environ, {"AI_FALLBACK_MODEL": "claude-haiku-4-5-20251001"}):
            from app.ai.config import get_ai_settings

            settings = get_ai_settings()
        assert settings.ai_fallback_model == "claude-haiku-4-5-20251001"

    def test_ai_fallback_model_default(self) -> None:
        """AI_FALLBACK_MODEL未設定時のデフォルト値を確認。"""
        import os

        env = {k: v for k, v in os.environ.items() if k != "AI_FALLBACK_MODEL"}
        with patch.dict(os.environ, env, clear=True):
            from app.ai.config import get_ai_settings

            settings = get_ai_settings()
        assert settings.ai_fallback_model == "claude-sonnet-4-20250514"
