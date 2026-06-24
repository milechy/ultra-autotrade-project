# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/privy/policy_mapper.py
"""委譲枠（delegation_grants）→ Privy server policy 写像（v4 Phase 2-D-B.2 / L1）。

ユーザーが consent した委譲枠を **Privy policy engine（TEE enforce）** の JSON に変換する
純関数群。Privy API 呼び出し・秘密鍵・tx 送信は一切含まない（`rest_client.create_policy`
に渡す body を組み立てるだけ）。生成した dict は `PrivyRestClient.create_policy()` へ渡す。

二層ガードにおける enforcement の分担（[[consent flow design]] の「二重ガード維持」）::

    Privy policy(本モジュール / TEE enforce):
        - `to` allowlist  = 委譲対象プロトコルのコントラクト（Aave V3 Pool）に限定
        - chain_type（allowlist 方式）
    backend ゲート(2-D-A / risk_limiter / PolicyEngine Rule8):
        - 単一 ≤ 委譲枠% / 日次 ≤ 委譲枠% / HF floor（総資産 × % の絶対額クランプ）
        - allowed_assets の検証・出金経路の除外（proposal routing）
        - 委譲枠 expires_at の期限チェック（Privy policy は field=current_unix_timestamp を
          未サポートのため backend 側で enforce する）

**% 上限を Privy policy の value cap に写像しない理由**: 委譲枠は **%** で持ち、絶対額は
執行時の総資産に依存する（grant 時点では未確定）。よって絶対額クランプは backend
risk_limiter（2-D-A 配線済）が担う。Privy policy は構造的エンベロープ（宛先 allowlist +
chain）を TEE で enforce し、両者の積集合で被害上限を縛る。

**出金除外**: Phase 2-D の AUTO は SUPPLY 中心。出金（withdraw）は本人署名を維持する不変条件
のため、委譲経路（scw_executor）が SUPPLY proposal のみを通す（routing で担保）。本 policy の
`to` は Aave Pool だが、supply/withdraw の判別は Privy 静的条件では困難（calldata 動的参照は
Privy 未サポート＝wallet_policy.py 注記）。よって出金除外は backend routing で enforce する。

**Privy policy schema 出典**: Privy API reference「Create policy」（実機検証 2026-06-23）。
有効な condition field は `to | value | chain_id` のみ。`default_action` キーは未サポート。
本 module は dormant（L1 で実 Privy に投げる前に live 受理検証する。rest_client と同じ運用）。
"""

from __future__ import annotations

from typing import Any

from app.aave.chains import get_chain_config

# Privy policy engine v1 定数（Privy API reference / 実機検証 2026-06-23 準拠）
_POLICY_VERSION = "1.0"
_CHAIN_TYPE = "ethereum"
_FIELD_SOURCE_TX = "ethereum_transaction"
_ACTION_ALLOW = "ALLOW"

# 委譲経路が署名する method（UserOp 署名 = 経路A の本丸 / 直 tx も許容）
_DELEGATED_METHODS = ("eth_signUserOperation", "eth_sendTransaction")

# 委譲可能なプロトコル → コントラクト解決関数（Phase 2-D は Aave のみ）。
# Lido / Pendle はコントラクトレジストリ未整備のため Phase 3（マルチプロトコル executor）で追加する。
_SUPPORTED_PROTOCOLS: frozenset[str] = frozenset({"aave"})


class PolicyMappingError(ValueError):
    """委譲枠を Privy policy に写像できない（fail-closed で grant を拒否する）。"""


def resolve_protocol_contracts(allowed_protocols: list[str], chain_name: str) -> list[str]:
    """委譲対象プロトコル → 許可コントラクトアドレス（小文字・重複排除・安定順）。

    解決できないプロトコルは PolicyMappingError（over-broad な policy を作らず fail-closed）。
    """
    if not allowed_protocols:
        raise PolicyMappingError("allowed_protocols must not be empty")

    contracts: list[str] = []
    for raw in allowed_protocols:
        protocol = raw.strip().lower()
        if protocol not in _SUPPORTED_PROTOCOLS:
            raise PolicyMappingError(
                f"protocol {raw!r} is not delegatable in Phase 2-D "
                f"(supported: {sorted(_SUPPORTED_PROTOCOLS)}; Lido/Pendle は Phase 3)"
            )
        if protocol == "aave":
            try:
                config = get_chain_config(chain_name)
            except ValueError as exc:
                raise PolicyMappingError(str(exc)) from exc
            addr = config.pool_address.lower()
            if addr not in contracts:
                contracts.append(addr)
    return contracts


def _to_condition(contracts: list[str]) -> dict[str, Any]:
    """宛先 allowlist 条件。1 件なら eq、複数なら in。"""
    base = {"field_source": _FIELD_SOURCE_TX, "field": "to"}
    if len(contracts) == 1:
        return {**base, "operator": "eq", "value": contracts[0]}
    return {**base, "operator": "in", "value": contracts}


def build_delegation_policy(
    *,
    wallet_address: str,
    allowed_protocols: list[str],
    chain_name: str,
    policy_name: str | None = None,
) -> dict[str, Any]:
    """委譲枠 → Privy policy 作成 body（`PrivyRestClient.create_policy()` 入力）。

    生成される policy は「許可コントラクト宛」の署名のみ ALLOW（宛先 allowlist）。
    % 上限・allowed_assets・出金除外・期限 enforce は backend ゲート側で担う（module
    docstring 参照）。写像不能（未対応プロトコル / 不正チェーン）は PolicyMappingError。

    :param wallet_address: 委譲対象ウォレット（policy name の監査用識別子）
    :param allowed_protocols: 委譲枠の許可プロトコル（Phase 2-D は ["aave"] のみ解決可能）
    :param chain_name: 執行チェーン名（"base" 本番 / "base_sepolia" staging）
    :param policy_name: 任意の policy 表示名（未指定なら wallet 短縮形/chain から生成、50文字以内）
    """
    if not wallet_address.strip():
        raise PolicyMappingError("wallet_address must not be empty")

    contracts = resolve_protocol_contracts(allowed_protocols, chain_name)
    conditions = [_to_condition(contracts)]

    # Privy policy name は 50 文字制限。wallet を先頭 6 + 末尾 4 文字に短縮して収める。
    wallet_abbrev = f"{wallet_address[:6]}...{wallet_address[-4:]}".lower()
    name = policy_name or f"uata-delegation-{wallet_abbrev}-{chain_name}"
    rules = [
        {
            "name": f"allow-{method}-within-scope",
            "method": method,
            "conditions": conditions,
            "action": _ACTION_ALLOW,
        }
        for method in _DELEGATED_METHODS
    ]
    return {
        "version": _POLICY_VERSION,
        "name": name,
        "chain_type": _CHAIN_TYPE,
        "rules": rules,
    }
