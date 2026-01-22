from datetime import datetime, timedelta, timezone

from app.bots.schemas import (
    OctoBotSignal,
    OctoBotSignalRequest,
)
from app.bots.service import OctoBotService


class DummyClient:
    """
    実際の OctoBotClient の代わりに使用するテスト用クライアント。
    """

    def __init__(self) -> None:
        self.payloads = []

    def send_signal(self, payload):
        self.payloads.append(payload)


def _build_signal(confidence: int = 50, ts: datetime | None = None) -> OctoBotSignal:
    """
    テスト用の OctoBotSignal を生成するヘルパー。
    """
    if ts is None:
        ts = datetime.now(timezone.utc)

    return OctoBotSignal(
        id="test-id",
        url="https://example.com",
        action="BUY",  # TradeAction Enum でも OK。ここでは簡易に文字列。
        confidence=confidence,
        reason="test",
        timestamp=ts,
    )


def test_process_signals_skips_low_confidence():
    """
    信頼度がしきい値未満のシグナルが skipped 扱いになることを確認する。
    """
    client = DummyClient()
    service = OctoBotService(client=client, min_confidence=60)

    request = OctoBotSignalRequest(
        signals=[_build_signal(confidence=50)],
        count=1,
    )

    response = service.process_signals(request)

    assert response.success_count == 0
    assert response.skipped_count == 1
    assert response.failed_count == 0
    assert response.details[0].status.value == "skipped"
    assert len(client.payloads) == 0


def test_process_signals_sends_high_confidence():
    """
    信頼度がしきい値以上のシグナルが送信されることを確認する。
    """
    client = DummyClient()
    service = OctoBotService(client=client, min_confidence=40)

    request = OctoBotSignalRequest(
        signals=[_build_signal(confidence=80)],
        count=1,
    )

    response = service.process_signals(request)

    assert response.success_count == 1
    assert response.skipped_count == 0
    assert response.failed_count == 0
    assert len(client.payloads) == 1


def test_process_signals_rate_limit_skips_after_threshold():
    """
    1時間以内に同一アクションがしきい値を超えた場合に、
    余剰分が skipped 扱いになることを確認する。
    """
    client = DummyClient()
    # テストでは分かりやすく、1時間に同一アクション2回まで許可とする
    service = OctoBotService(
        client=client,
        min_confidence=0,
        max_same_action_per_hour=2,
    )

    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    signals = [
        _build_signal(confidence=80, ts=base_time + timedelta(minutes=0)),
        _build_signal(confidence=80, ts=base_time + timedelta(minutes=10)),
        _build_signal(confidence=80, ts=base_time + timedelta(minutes=20)),
    ]

    request = OctoBotSignalRequest(signals=signals, count=3)

    response = service.process_signals(request)

    # 2件までは送信され、3件目がレート制限でスキップされる想定
    assert response.success_count == 2
    assert response.skipped_count == 1
    assert response.failed_count == 0

    # 実際に送信された payload は 2件のみ
    assert len(client.payloads) == 2

    statuses = [d.status.value for d in response.details]
    assert statuses.count("sent") == 2
    assert statuses.count("skipped") == 1
