# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/rpc_provider.py
"""RPC Provider with automatic failover."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from web3 import Web3
except ImportError:
    Web3 = None  # type: ignore[assignment,misc]


class RPCProvider:
    """プライマリ → セカンダリRPCの自動切替"""

    def __init__(
        self,
        primary_url: str,
        secondary_url: Optional[str] = None,
        web3_cls: Optional[Any] = None,
    ):
        self.primary_url = primary_url
        self.secondary_url = secondary_url
        # web3_cls を外部から注入できるようにする（テスト・モック用）
        self._web3_cls = web3_cls
        self._current: Optional[object] = None
        self._using_secondary = False

    def _get_web3_cls(self) -> Any:
        """使用する Web3 クラスを返す（注入済みなら優先）。"""
        if self._web3_cls is not None:
            return self._web3_cls
        if Web3 is None:
            raise RuntimeError("web3 package is required. Install with: pip install web3")
        return Web3

    def get_web3(self) -> "Web3":
        """接続可能なWeb3インスタンスを返す"""
        web3_cls = self._get_web3_cls()

        if self._current is not None and self._is_connected(self._current):
            return self._current  # type: ignore[return-value]

        # プライマリを試行
        w3 = web3_cls(web3_cls.HTTPProvider(self.primary_url))
        if self._is_connected(w3):
            self._current = w3
            if self._using_secondary:
                logger.info("RPC: restored to primary")
                self._using_secondary = False
            return w3  # type: ignore[no-any-return]

        logger.warning("RPC: primary failed, trying secondary")

        # セカンダリを試行
        if self.secondary_url:
            w3 = web3_cls(web3_cls.HTTPProvider(self.secondary_url))
            if self._is_connected(w3):
                self._current = w3
                self._using_secondary = True
                logger.info("RPC: using secondary")
                return w3  # type: ignore[no-any-return]

        # 両方失敗
        logger.error("RPC: both primary and secondary failed")
        raise ConnectionError("All RPC endpoints unavailable")

    def _is_connected(self, w3: object) -> bool:
        try:
            w3.eth.block_number  # type: ignore[attr-defined]
            return True
        except Exception:
            return False
