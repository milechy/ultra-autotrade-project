# Copyright (c) Ultra AutoTrade. All rights reserved.
"""PendleWebClient の chain 解決 / expiry パース（実 API 不要のユニットテスト）。

2026-07-17 に見つかった 2 件の回帰防止:

1. **chain map に "base" が無く 42161(Arbitrum) に既定化していた** → market data が 404 →
   except 節のフォールバック（stETH / tvl=0 / APY 5.2% の架空値）が返る。
   `tvl_usd=0` は流動性ガードが全 block する値なので、Pendle は「静かに常時 block」だった。
2. **expiry を int() でパースしていた** が実 API は ISO8601 文字列 → 必ず ValueError →
   これ単体でもフォールバックに落ちていた。

いずれも全経路 dormant + テストが HTTP をモックしていたため未検出だった。
実 API との整合は `test_pendle_convert_api_contract.py`（live・opt-in）が担保する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.protocols.pendle.client import PendleWebClient
from app.protocols.pendle.config import PendleConfig


def _client(chain: str) -> PendleWebClient:
    config = PendleConfig(sandbox=False)
    config.chain = chain
    return PendleWebClient(config)


class TestChainIdResolution:
    def test_base_resolves_to_8453(self) -> None:
        """PENDLE_CHAIN=base が Base Mainnet を指すこと（Arbitrum に既定化しない）。"""
        assert _client("base")._chain_id == "8453"

    def test_arbitrum_and_ethereum_unchanged(self) -> None:
        assert _client("arbitrum")._chain_id == "42161"
        assert _client("ethereum")._chain_id == "1"

    def test_unknown_chain_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """未知 chain は既定化するが**必ず警告**する（黙って別チェーンを見に行かない）。"""
        with caplog.at_level("WARNING"):
            client = _client("bogus_chain")
        assert client._chain_id == "42161"
        assert any("未知の chain" in r.getMessage() for r in caplog.records)


class TestExpiryParsing:
    def test_iso8601_with_z(self) -> None:
        """実 API の形式（"2026-09-24T00:00:00.000Z"）を解釈できること。"""
        parsed = PendleWebClient._parse_expiry("2026-09-24T00:00:00.000Z")
        assert parsed == datetime(2026, 9, 24, tzinfo=timezone.utc)

    def test_unix_seconds_int(self) -> None:
        """UNIX 秒（int）でも解釈できること（後方互換）。"""
        ts = int(datetime(2026, 9, 24, tzinfo=timezone.utc).timestamp())
        assert PendleWebClient._parse_expiry(ts) == datetime(2026, 9, 24, tzinfo=timezone.utc)

    def test_unix_seconds_digit_string(self) -> None:
        ts = int(datetime(2026, 9, 24, tzinfo=timezone.utc).timestamp())
        assert PendleWebClient._parse_expiry(str(ts)) == datetime(2026, 9, 24, tzinfo=timezone.utc)

    @pytest.mark.parametrize("bad", [None, "", "   ", "not-a-date", {}])
    def test_unparseable_raises(self, bad: object) -> None:
        """解釈不能なら例外 → 呼び出し側のフォールバック（tvl=0 で block）に落ちる。"""
        with pytest.raises(ValueError):
            PendleWebClient._parse_expiry(bad)
