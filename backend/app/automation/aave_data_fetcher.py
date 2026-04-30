# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Aave マーケットデータを fail-open で取得する同期ヘルパー。

ai_judgment_scheduler.run_ai_judgment_job (sync, executor 上で呼ばれる)
から利用される。個別フィールドの取得失敗は None を返し、scheduler 全体は
継続させる (落とさない)。

実装方針 (2026-05-01 V2 REST → V3 web3 移行):
- HF: Web3AaveClient.get_health_factor() を流用 (変更なし)
- utilization / supply_apy / borrow_apy: Aave V3 Pool.getReserveData() を直接呼出
  + aToken.totalSupply / variableDebtToken.totalSupply で utilization を計算
- 旧 V2 REST API (https://aave-api-v2.aave.com) は V3 へ 301 リダイレクトされ
  httpx の follow_redirects=False で取得失敗していた → 全 None で隠れバグ化していた
- utilization は % 表記 (0-100) で返す。indicator_agent (`> 80` 比較) と整合
  (旧 V2 経路は 0.85 のような小数を返していた疑いあり = もう一つの隠れバグ)

Decimal 型を使用 (CLAUDE.md セキュリティルール 11: 金融計算は Decimal 必須)。
"""

import logging
from decimal import Decimal
from typing import Optional, TypedDict

from app.aave.chains import CHAIN_REGISTRY, get_active_chains
from app.aave.client import AaveClientError, get_default_aave_client

logger = logging.getLogger(__name__)

# web3 はオプション依存。未インストール時は None にして fail-open する。
try:
    from web3 import Web3
except ImportError:
    Web3 = None  # type: ignore[assignment,misc]


_RAY = Decimal(10) ** 27
_SECONDS_PER_YEAR = 31_536_000


# Aave V3 IPool ABI (最小限) — getReserveData(asset)
# DataTypes.ReserveData struct (configuration から isolationModeTotalDebt まで)
# V3 全バージョンで安定 (deprecated stable-related フィールドも struct 上は残置)
_POOL_ABI_MINIMAL = [
    {
        "name": "getReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {
                        "name": "configuration",
                        "type": "tuple",
                        "components": [{"name": "data", "type": "uint256"}],
                    },
                    {"name": "liquidityIndex", "type": "uint128"},
                    {"name": "currentLiquidityRate", "type": "uint128"},
                    {"name": "variableBorrowIndex", "type": "uint128"},
                    {"name": "currentVariableBorrowRate", "type": "uint128"},
                    {"name": "currentStableBorrowRate", "type": "uint128"},
                    {"name": "lastUpdateTimestamp", "type": "uint40"},
                    {"name": "id", "type": "uint16"},
                    {"name": "aTokenAddress", "type": "address"},
                    {"name": "stableDebtTokenAddress", "type": "address"},
                    {"name": "variableDebtTokenAddress", "type": "address"},
                    {"name": "interestRateStrategyAddress", "type": "address"},
                    {"name": "accruedToTreasury", "type": "uint128"},
                    {"name": "unbacked", "type": "uint128"},
                    {"name": "isolationModeTotalDebt", "type": "uint128"},
                ],
            }
        ],
    }
]


# 最小 ERC20 ABI — totalSupply のみ (utilization 計算用)
_ERC20_TOTAL_SUPPLY_ABI = [
    {
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]


class AaveMarketData(TypedDict):
    utilization_rate: Optional[Decimal]
    supply_apy: Optional[Decimal]
    borrow_apy: Optional[Decimal]
    health_factor: Optional[Decimal]


def _empty_result() -> AaveMarketData:
    return {
        "utilization_rate": None,
        "supply_apy": None,
        "borrow_apy": None,
        "health_factor": None,
    }


def _ray_to_apy_pct(rate_ray: int) -> Decimal:
    """Aave V3 の ray (1e27) スケール APR を APY (%) に変換する。

    Aave 公式式: APY = ((1 + APR / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100

    Decimal で計算精度を維持 (float は禁止: CLAUDE.md セキュリティルール 11)。
    """
    if rate_ray <= 0:
        return Decimal("0")
    rate = Decimal(rate_ray) / _RAY
    base = Decimal(1) + rate / Decimal(_SECONDS_PER_YEAR)
    apy = base**_SECONDS_PER_YEAR - Decimal(1)
    return apy * Decimal(100)


def _fetch_health_factor() -> Optional[Decimal]:
    """Aave V3 Pool から Health Factor を同期取得。

    Web3AaveClient はコンストラクタ時の wallet_private_key (AAVE_WALLET_PRIVATE_KEY)
    から導出した self.account.address をデフォルトで読む。production は単一ウォレット
    運用なので追加の wallet 引数は不要。

    取得失敗 / Decimal("inf") (借入なし) の場合は None を返す。
    """
    try:
        client = get_default_aave_client()
        hf = client.get_health_factor()
        if hf is None or hf == Decimal("inf"):
            return None
        return hf
    except AaveClientError as exc:
        logger.warning("aave_health_factor_fetch_failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("aave_health_factor_fetch_unexpected_error: %s", exc)
        return None


def _fetch_reserve_data_via_pool(
    asset_symbol: str = "USDC",
) -> dict[str, Optional[Decimal]]:
    """Aave V3 Pool.getReserveData() + ERC20.totalSupply で reserve data を取得する。

    1. Pool.getReserveData(asset) → currentLiquidityRate / currentVariableBorrowRate /
       aTokenAddress / variableDebtTokenAddress
    2. aToken.totalSupply() → totalAToken (= 預入総量)
    3. variableDebtToken.totalSupply() + stableDebtToken.totalSupply() → totalDebt
    4. utilization = totalDebt / totalAToken (% 表記, Aave 公式定義: vdebt + sdebt)
       ※ V3.3 以降 stable debt は deprecated (多くの reserve で 0) だが定義上は含める
    5. APY 換算: ray → APY (%)

    例外時は全 None で fail-open。
    """
    none_result: dict[str, Optional[Decimal]] = {
        "utilization_rate": None,
        "supply_apy": None,
        "borrow_apy": None,
    }

    if Web3 is None:
        logger.warning("web3 package not available, skipping aave reserve fetch")
        return none_result

    try:
        client = get_default_aave_client()
        w3 = client.w3  # type: ignore[attr-defined]

        # P1: resolve chain from client's actual settings to avoid mismatch
        # between the pool the client connects to and get_active_chains()[0]
        client_settings = getattr(client, "settings", None)
        _chain_key = getattr(client_settings, "chain_name", None) or getattr(
            client_settings, "network", None
        )
        chain = CHAIN_REGISTRY.get(_chain_key) if _chain_key else None
        if chain is None:
            chains = get_active_chains()
            if not chains:
                logger.warning("aave_active_chains_empty")
                return none_result
            chain = chains[0]
            if _chain_key:
                logger.warning(
                    "aave_chain_registry_miss: key=%s fallback=%s",
                    _chain_key,
                    chain.chain_name,
                )

        usdc_addr = chain.tokens.get(asset_symbol)
        if not usdc_addr:
            logger.warning(
                "aave_asset_not_in_chain_tokens: chain=%s asset=%s",
                chain.chain_name,
                asset_symbol,
            )
            return none_result

        pool_contract = w3.eth.contract(
            address=Web3.to_checksum_address(chain.pool_address),
            abi=_POOL_ABI_MINIMAL,
        )
        reserve_data = pool_contract.functions.getReserveData(
            Web3.to_checksum_address(usdc_addr)
        ).call()

        # tuple index (DataTypes.ReserveData):
        # 0: configuration (tuple), 1: liquidityIndex, 2: currentLiquidityRate,
        # 3: variableBorrowIndex, 4: currentVariableBorrowRate, 5: stableBorrowRate,
        # 6: lastUpdateTimestamp, 7: id, 8: aTokenAddress, 9: stableDebtTokenAddress,
        # 10: variableDebtTokenAddress, ...
        current_liquidity_rate = int(reserve_data[2])
        current_variable_borrow_rate = int(reserve_data[4])
        atoken_addr = reserve_data[8]
        vdebt_addr = reserve_data[10]

        atoken_contract = w3.eth.contract(
            address=Web3.to_checksum_address(atoken_addr),
            abi=_ERC20_TOTAL_SUPPLY_ABI,
        )
        atoken_total = int(atoken_contract.functions.totalSupply().call())

        vdebt_contract = w3.eth.contract(
            address=Web3.to_checksum_address(vdebt_addr),
            abi=_ERC20_TOTAL_SUPPLY_ABI,
        )
        vdebt_total = int(vdebt_contract.functions.totalSupply().call())

        # P2: include stable debt per Aave official definition
        # utilization = (totalVariableDebt + totalStableDebt) / totalAToken
        # sdebt is deprecated in V3.3+ but defined as 0 for most reserves
        sdebt_addr = reserve_data[9]  # stableDebtTokenAddress
        sdebt_contract = w3.eth.contract(
            address=Web3.to_checksum_address(sdebt_addr),
            abi=_ERC20_TOTAL_SUPPLY_ABI,
        )
        sdebt_total = int(sdebt_contract.functions.totalSupply().call())
        total_debt = vdebt_total + sdebt_total

        if atoken_total <= 0:
            utilization_pct = Decimal(0)
        else:
            utilization_pct = Decimal(total_debt) / Decimal(atoken_total) * Decimal(100)

        return {
            "utilization_rate": utilization_pct,
            "supply_apy": _ray_to_apy_pct(current_liquidity_rate),
            "borrow_apy": _ray_to_apy_pct(current_variable_borrow_rate),
        }
    except AaveClientError as exc:
        logger.warning("aave_reserve_data_fetch_failed (client): %s", exc)
        return none_result
    except Exception as exc:  # noqa: BLE001
        logger.warning("aave_reserve_data_fetch_failed: %s", exc)
        return none_result


def fetch_aave_market_data_safe(asset_symbol: str = "USDC") -> AaveMarketData:
    """fail-open で Aave マーケットデータを取得する。

    個別失敗 → そのフィールドのみ None。全失敗 → 全 None dict。
    例外を呼び出し側に投げないことで scheduler の継続性を担保する。

    Returns:
        AaveMarketData (utilization_rate / supply_apy / borrow_apy / health_factor)
        utilization_rate / supply_apy / borrow_apy は % 表記 (0-100)。
    """
    result = _empty_result()
    result["health_factor"] = _fetch_health_factor()

    pool_data = _fetch_reserve_data_via_pool(asset_symbol)
    if pool_data.get("utilization_rate") is not None:
        result["utilization_rate"] = pool_data["utilization_rate"]
    if pool_data.get("supply_apy") is not None:
        result["supply_apy"] = pool_data["supply_apy"]
    if pool_data.get("borrow_apy") is not None:
        result["borrow_apy"] = pool_data["borrow_apy"]

    return result
