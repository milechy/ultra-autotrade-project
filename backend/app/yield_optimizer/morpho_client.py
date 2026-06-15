# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/yield_optimizer/morpho_client.py
"""
Privy Wallet Actions "Earn" REST API ラッパー。

Privy Earn API は Morpho Vaults へのデポジット/引出しをサーバーサイドで行う。
API エンドポイント:
  - GET  https://api.privy.io/v1/apps/{app_id}/wallets/{wallet_id}/earn/positions
  - GET  https://api.privy.io/v1/apps/{app_id}/earn/vaults
  - POST https://api.privy.io/v1/apps/{app_id}/wallets/{wallet_id}/earn/deposit
  - POST https://api.privy.io/v1/apps/{app_id}/wallets/{wallet_id}/earn/withdraw

認証: Basic auth (app_id:app_secret) + privy-app-id ヘッダー

NOTE (フラグ): Privy Earn API のエンドポイント仕様は 2026-06-15 時点で公式ドキュメント
未確定。本実装は Privy の Wallet Actions REST API の一般パターンに基づく。
本番配線前に https://docs.privy.io/guide/server/wallets/usage/earn を確認すること。
ENV: PRIVY_APP_ID / PRIVY_APP_SECRET (従来の PRIVY_APP_ID と同じ app_id を使用)。

金融計算: Decimal のみ使用 (float 禁止)。
外部 API 失敗時は fail-open (空リスト / ゼロ値を返す)。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import httpx

from .schemas import MorphoVault, TxResult, VaultListResponse, YieldPosition

logger = logging.getLogger(__name__)

# Privy Earn API ベース URL
_PRIVY_API_BASE = "https://api.privy.io/v1"

# デフォルトタイムアウト秒
_DEFAULT_TIMEOUT_SECONDS = 15


def _decimal_from_str(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """文字列 / 数値を安全に Decimal 変換する。失敗時は default を返す。"""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


class MorphoClient:
    """
    Privy Earn REST API クライアント。

    単一 wallet を対象として Morpho Vault への入出金・ポジション取得を行う。

    Args:
        app_id: Privy App ID (env: PRIVY_APP_ID)
        app_secret: Privy App Secret (env: PRIVY_APP_SECRET)
        wallet_id: 操作対象の Privy Wallet ID (env: PRIVY_MANAGED_WALLET_ID)
        timeout: HTTP タイムアウト秒
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        wallet_id: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._app_id: str = app_id or os.getenv("PRIVY_APP_ID") or ""
        self._app_secret: str = app_secret or os.getenv("PRIVY_APP_SECRET") or ""
        self._wallet_id: str = wallet_id or os.getenv("PRIVY_MANAGED_WALLET_ID") or ""
        self._timeout = timeout

        if not self._app_id:
            logger.warning("MorphoClient: PRIVY_APP_ID not set — API calls will fail gracefully")
        if not self._wallet_id:
            logger.warning(
                "MorphoClient: PRIVY_MANAGED_WALLET_ID not set — wallet operations unavailable"
            )

    # ------------------------------------------------------------------ helpers

    def _headers(self) -> dict[str, str]:
        """Privy API 認証ヘッダーを返す。"""
        return {
            "privy-app-id": self._app_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _auth(self) -> tuple[str, str]:
        """Basic 認証タプル (app_id, app_secret) を返す。"""
        return (self._app_id, self._app_secret)

    def _base_url(self) -> str:
        return f"{_PRIVY_API_BASE}/apps/{self._app_id}"

    # ------------------------------------------------------------------ public

    def list_vaults(self) -> list[MorphoVault]:
        """
        利用可能な Morpho Vault 一覧を取得する。

        Returns:
            MorphoVault リスト。API 失敗時は空リスト (fail-open)。
        """
        if not self._app_id or not self._app_secret:
            logger.warning("list_vaults: Privy credentials not set, returning empty list")
            return []

        url = f"{self._base_url()}/earn/vaults"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, headers=self._headers(), auth=self._auth())
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("list_vaults: Privy API error (fail-open): %s", exc)
            return []

        vaults: list[MorphoVault] = []
        raw_vaults: list[Any] = []
        if isinstance(data, dict) and "vaults" in data:
            raw_vaults = data["vaults"]
        elif isinstance(data, list):
            raw_vaults = data

        for item in raw_vaults:
            if not isinstance(item, dict):
                continue
            try:
                vault = MorphoVault(
                    vault_address=str(item.get("vault_address") or item.get("address") or ""),
                    name=str(item.get("name") or item.get("vault_name") or "Unknown Vault"),
                    apy=str(_decimal_from_str(item.get("apy") or item.get("current_apy") or "0")),
                    tvl_usd=str(_decimal_from_str(item.get("tvl_usd") or item.get("tvl") or "0")),
                )
                vaults.append(vault)
            except Exception as parse_exc:
                logger.debug("list_vaults: skipping malformed vault item: %s", parse_exc)

        logger.info("list_vaults: fetched %d vaults", len(vaults))
        return vaults

    def get_best_apy_vault(self) -> Optional[MorphoVault]:
        """
        最高 APY の Vault を返す。Vault が存在しない場合は None。

        Returns:
            最高 APY の MorphoVault、または None。
        """
        vaults = self.list_vaults()
        if not vaults:
            return None
        return max(vaults, key=lambda v: _decimal_from_str(v.apy))

    def deposit_to_vault(self, vault_address: str, amount_usdc: Decimal) -> TxResult:
        """
        Morpho Vault へ USDC を入金する (admin 専用操作)。

        Args:
            vault_address: 入金先 Vault アドレス
            amount_usdc: 入金 USDC 数量 (Decimal、正の値)

        Returns:
            TxResult (tx_hash を含む)

        Raises:
            RuntimeError: Privy 認証情報未設定 / API エラー時
        """
        if not self._app_id or not self._app_secret or not self._wallet_id:
            raise RuntimeError(
                "MorphoClient: PRIVY_APP_ID / PRIVY_APP_SECRET / PRIVY_MANAGED_WALLET_ID "
                "must be set for deposit operations"
            )

        url = f"{self._base_url()}/wallets/{self._wallet_id}/earn/deposit"
        payload: dict[str, Any] = {
            "vault_address": vault_address,
            "amount": str(amount_usdc),
            "asset": "USDC",
        }

        logger.info("deposit_to_vault: vault=%s amount=%s USDC", vault_address, amount_usdc)

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, headers=self._headers(), auth=self._auth(), json=payload)
            resp.raise_for_status()
            data = resp.json()

        tx_hash = str(data.get("tx_hash") or data.get("transaction_hash") or "")
        if not tx_hash:
            raise RuntimeError(f"deposit_to_vault: no tx_hash in Privy response: {data}")

        now_iso = datetime.now(timezone.utc).isoformat()
        result = TxResult(
            tx_hash=tx_hash,
            vault_address=vault_address,
            operation="deposit",
            amount=str(amount_usdc),
            submitted_at=now_iso,
        )
        logger.info(
            "deposit_to_vault: submitted tx=%s vault=%s amount=%s",
            tx_hash,
            vault_address,
            amount_usdc,
        )
        return result

    def withdraw_from_vault(self, vault_address: str, amount: Decimal) -> TxResult:
        """
        Morpho Vault から USDC を引き出す (admin 専用操作)。

        Args:
            vault_address: 引き出し元 Vault アドレス
            amount: 引き出し USDC 数量 (Decimal、正の値)

        Returns:
            TxResult (tx_hash を含む)

        Raises:
            RuntimeError: Privy 認証情報未設定 / API エラー時
        """
        if not self._app_id or not self._app_secret or not self._wallet_id:
            raise RuntimeError(
                "MorphoClient: PRIVY_APP_ID / PRIVY_APP_SECRET / PRIVY_MANAGED_WALLET_ID "
                "must be set for withdraw operations"
            )

        url = f"{self._base_url()}/wallets/{self._wallet_id}/earn/withdraw"
        payload: dict[str, Any] = {
            "vault_address": vault_address,
            "amount": str(amount),
            "asset": "USDC",
        }

        logger.info("withdraw_from_vault: vault=%s amount=%s USDC", vault_address, amount)

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, headers=self._headers(), auth=self._auth(), json=payload)
            resp.raise_for_status()
            data = resp.json()

        tx_hash = str(data.get("tx_hash") or data.get("transaction_hash") or "")
        if not tx_hash:
            raise RuntimeError(f"withdraw_from_vault: no tx_hash in Privy response: {data}")

        now_iso = datetime.now(timezone.utc).isoformat()
        result = TxResult(
            tx_hash=tx_hash,
            vault_address=vault_address,
            operation="withdraw",
            amount=str(amount),
            submitted_at=now_iso,
        )
        logger.info(
            "withdraw_from_vault: submitted tx=%s vault=%s amount=%s",
            tx_hash,
            vault_address,
            amount,
        )
        return result

    def get_position(self, vault_address: str) -> Optional[YieldPosition]:
        """
        指定 Vault のポジション情報を取得する。

        Args:
            vault_address: 対象 Vault アドレス

        Returns:
            YieldPosition、または見つからない場合 None (fail-open)。
        """
        if not self._app_id or not self._app_secret or not self._wallet_id:
            logger.warning("get_position: Privy credentials not set, returning None")
            return None

        url = f"{self._base_url()}/wallets/{self._wallet_id}/earn/positions"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, headers=self._headers(), auth=self._auth())
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("get_position: Privy API error (fail-open): %s", exc)
            return None

        positions_raw = data.get("positions") or (data if isinstance(data, list) else [])
        if isinstance(data, dict) and "positions" in data:
            positions_raw = data["positions"]

        for item in positions_raw:
            if not isinstance(item, dict):
                continue
            item_addr = str(item.get("vault_address") or item.get("address") or "")
            if item_addr.lower() != vault_address.lower():
                continue
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                return YieldPosition(
                    vault_address=vault_address,
                    deposited_amount=str(
                        _decimal_from_str(
                            item.get("deposited_amount") or item.get("principal") or "0"
                        )
                    ),
                    current_value=str(
                        _decimal_from_str(item.get("current_value") or item.get("balance") or "0")
                    ),
                    earned_usd=str(
                        _decimal_from_str(item.get("earned_usd") or item.get("yield_usd") or "0")
                    ),
                    last_updated=now_iso,
                )
            except Exception as parse_exc:
                logger.debug("get_position: parse error for vault=%s: %s", vault_address, parse_exc)
                return None

        logger.debug("get_position: vault=%s not found in positions", vault_address)
        return None

    def get_all_positions(self) -> list[YieldPosition]:
        """
        全 Vault ポジション一覧を取得する。API 失敗時は空リスト (fail-open)。

        Returns:
            YieldPosition リスト。
        """
        if not self._app_id or not self._app_secret or not self._wallet_id:
            logger.warning("get_all_positions: Privy credentials not set, returning []")
            return []

        url = f"{self._base_url()}/wallets/{self._wallet_id}/earn/positions"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, headers=self._headers(), auth=self._auth())
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("get_all_positions: Privy API error (fail-open): %s", exc)
            return []

        positions_raw: list[Any] = []
        if isinstance(data, dict) and "positions" in data:
            positions_raw = data["positions"]
        elif isinstance(data, list):
            positions_raw = data

        result: list[YieldPosition] = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for item in positions_raw:
            if not isinstance(item, dict):
                continue
            try:
                result.append(
                    YieldPosition(
                        vault_address=str(item.get("vault_address") or item.get("address") or ""),
                        deposited_amount=str(
                            _decimal_from_str(
                                item.get("deposited_amount") or item.get("principal") or "0"
                            )
                        ),
                        current_value=str(
                            _decimal_from_str(
                                item.get("current_value") or item.get("balance") or "0"
                            )
                        ),
                        earned_usd=str(
                            _decimal_from_str(
                                item.get("earned_usd") or item.get("yield_usd") or "0"
                            )
                        ),
                        last_updated=now_iso,
                    )
                )
            except Exception as parse_exc:
                logger.debug("get_all_positions: skipping malformed item: %s", parse_exc)

        return result

    def get_vault_list_response(self) -> VaultListResponse:
        """
        Vault 一覧を VaultListResponse 形式で返す。

        Returns:
            VaultListResponse (vaults + best_apy_vault + fetched_at)
        """
        vaults = self.list_vaults()
        best: Optional[MorphoVault] = None
        if vaults:
            best = max(vaults, key=lambda v: _decimal_from_str(v.apy))

        return VaultListResponse(
            vaults=vaults,
            best_apy_vault=best,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
