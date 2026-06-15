# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/notifications/test_line_push_integration.py
"""LINE Push 通知 + monitor.py HF 連携テスト。

テスト方針:
- LINE Messaging API への実際の HTTP 通信は httpx.post を mock する
- push_text() が正しいエンドポイントへ HTTPS リクエストを発行することを確認
- monitor.get_health_factor() で HF < 1.8 のとき push_text が呼ばれることを確認
- LINE API 失敗時に fail-open（HF 監視が止まらない）ことを確認
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# push_text — LINE API HTTPS リクエスト確認
# ---------------------------------------------------------------------------


class TestPushText:
    """push_text() のユニットテスト。"""

    def test_push_text_sends_https_request(self) -> None:
        """push_text が LINE Push API に POST リクエストを発行する。"""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch.dict(
                "os.environ",
                {
                    "LINE_CHANNEL_ACCESS_TOKEN": "test_token_abc",
                    "LINE_USER_ID": "U12345678",
                },
            ),
            patch("httpx.post", return_value=mock_response) as mock_post,
        ):
            from app.notifications.line_push import push_text

            result = push_text("U12345678", "テストメッセージ")

        assert result is True
        assert mock_post.called
        call_kwargs = mock_post.call_args
        called_url = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("url", "")
        assert "api.line.me" in called_url, f"LINE API URL が含まれていない: {called_url}"

    def test_push_text_returns_false_when_token_missing(self) -> None:
        """LINE_CHANNEL_ACCESS_TOKEN 未設定のとき False を返す（fail-open）。"""
        with patch.dict("os.environ", {}, clear=False):
            # トークンを消す
            import os

            os.environ.pop("LINE_CHANNEL_ACCESS_TOKEN", None)
            os.environ.pop("LINE_USER_ID", None)

            # キャッシュリセット（モジュール再ロード対策）
            import importlib

            import app.notifications.line_push as lp

            importlib.reload(lp)

            result = lp.push_text("U12345678", "メッセージ")

        assert result is False

    def test_push_text_falls_back_to_env_user_id(self) -> None:
        """user_line_id が空文字のとき env LINE_USER_ID にフォールバックする。"""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch.dict(
                "os.environ",
                {
                    "LINE_CHANNEL_ACCESS_TOKEN": "test_token_xyz",
                    "LINE_USER_ID": "Ufallback000",
                },
            ),
            patch("httpx.post", return_value=mock_response) as mock_post,
        ):
            from app.notifications.line_push import push_text

            result = push_text("", "フォールバックテスト")

        assert result is True
        # 送信ペイロードに env の user_id が含まれる
        call_json = mock_post.call_args.kwargs.get("json", {})
        assert call_json.get("to") == "Ufallback000"

    def test_push_text_returns_false_on_http_error(self) -> None:
        """LINE API が HTTP エラーを返すとき False を返す（fail-open）。"""
        import httpx

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400 Bad Request",
            request=MagicMock(),
            response=MagicMock(status_code=400),
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "LINE_CHANNEL_ACCESS_TOKEN": "test_token_err",
                    "LINE_USER_ID": "U99999999",
                },
            ),
            patch("httpx.post", return_value=mock_response),
        ):
            from app.notifications.line_push import push_text

            result = push_text("U99999999", "エラーテスト")

        assert result is False


# ---------------------------------------------------------------------------
# monitor.get_health_factor — HF < 1.8 で push_text 呼び出し
# ---------------------------------------------------------------------------


class TestMonitorHFNotification:
    """monitor.get_health_factor() の HF 警告通知テスト。"""

    def test_hf_below_18_calls_push_text(self) -> None:
        """HF = 1.79 のとき push_text が呼ばれる。"""
        with (
            patch(
                "app.aave.monitor._client_type",
                return_value="dummy",
            ),
            patch(
                "app.aave.client.DummyAaveClient.get_health_factor",
                return_value=Decimal("1.79"),
            ),
            patch(
                "app.notifications.line_push.push_text",
                return_value=True,
            ) as mock_push,
        ):
            from app.aave import monitor

            result = monitor.get_health_factor("0xDEAD")

        assert result == Decimal("1.79")
        mock_push.assert_called_once()
        # メッセージに HF 値が含まれる
        call_msg = mock_push.call_args.args[1]
        assert "1.79" in call_msg

    def test_hf_above_18_does_not_call_push_text(self) -> None:
        """HF = 2.0 のとき push_text は呼ばれない。"""
        with (
            patch(
                "app.aave.monitor._client_type",
                return_value="dummy",
            ),
            patch(
                "app.aave.client.DummyAaveClient.get_health_factor",
                return_value=Decimal("2.0"),
            ),
            patch(
                "app.notifications.line_push.push_text",
                return_value=True,
            ) as mock_push,
        ):
            from app.aave import monitor

            result = monitor.get_health_factor("0xDEAD")

        assert result == Decimal("2.0")
        mock_push.assert_not_called()

    def test_hf_exactly_18_does_not_call_push_text(self) -> None:
        """HF = 1.8 (境界値) のとき push_text は呼ばれない（< 1.8 が条件）。"""
        with (
            patch(
                "app.aave.monitor._client_type",
                return_value="dummy",
            ),
            patch(
                "app.aave.client.DummyAaveClient.get_health_factor",
                return_value=Decimal("1.8"),
            ),
            patch(
                "app.notifications.line_push.push_text",
                return_value=True,
            ) as mock_push,
        ):
            from app.aave import monitor

            result = monitor.get_health_factor("0xDEAD")

        assert result == Decimal("1.8")
        mock_push.assert_not_called()

    def test_push_text_failure_does_not_stop_hf_monitoring(self) -> None:
        """LINE API 失敗時も HF 値が正常に返却される（fail-open）。"""
        with (
            patch(
                "app.aave.monitor._client_type",
                return_value="dummy",
            ),
            patch(
                "app.aave.client.DummyAaveClient.get_health_factor",
                return_value=Decimal("1.5"),
            ),
            patch(
                "app.notifications.line_push.push_text",
                side_effect=RuntimeError("LINE API 障害"),
            ),
        ):
            from app.aave import monitor

            # fail-open: 例外が上がらず HF が返却される
            result = monitor.get_health_factor("0xDEAD")

        assert result == Decimal("1.5")


# ---------------------------------------------------------------------------
# templates — 新規テンプレートのスモークテスト
# ---------------------------------------------------------------------------


class TestNewTemplates:
    """新規追加テンプレート 5種のスモークテスト。"""

    def test_health_factor_warning_returns_payload(self) -> None:
        from app.notifications.templates import health_factor_warning

        payload = health_factor_warning(Decimal("1.75"))
        assert "1.750" in payload.body
        assert payload.severity == "warning"

    def test_trade_executed_returns_payload(self) -> None:
        from app.notifications.templates import trade_executed

        payload = trade_executed("BUY", Decimal("1000"), "USDC")
        assert "USDC" in payload.body
        assert payload.severity == "info"

    def test_morpho_apy_alert_returns_payload(self) -> None:
        from app.notifications.templates import morpho_apy_alert

        payload = morpho_apy_alert(Decimal("5.25"))
        assert "5.25" in payload.body
        assert payload.severity == "info"

    def test_monthly_report_returns_payload(self) -> None:
        from app.notifications.templates import monthly_report

        metrics = {
            "period": "2026年6月",
            "net_profit": Decimal("12345"),
            "fee_amount": Decimal("500"),
            "win_rate": Decimal("65.5"),
            "total_trades": 42,
        }
        payload = monthly_report(metrics)
        assert "2026年6月" in payload.title
        assert "12345" in payload.body
        assert payload.severity == "info"

    def test_oracle_alert_returns_payload(self) -> None:
        from app.notifications.templates import oracle_alert

        payload = oracle_alert(Decimal("3.7"))
        assert "3.7" in payload.body
        assert payload.severity == "alert"

    def test_trade_executed_no_float_values(self) -> None:
        """取引金額の計算で float が混入していないことを確認。"""
        from app.notifications.templates import trade_executed

        amount = Decimal("9999.99")
        payload = trade_executed("SELL", amount, "ETH")
        # Decimal の文字列表現が本文に含まれる
        assert str(amount) in payload.body
