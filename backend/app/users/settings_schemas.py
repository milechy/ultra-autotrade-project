# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/settings_schemas.py
"""ユーザー設定APIのスキーマ定義。"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 委譲枠の上限ハードキャップ（risk_limiter STRICT と一致。これを超える値は受け付けない）。
# 実行時にも risk_limiter で二重クランプするが、入力段階でも fail-fast で弾く。
DELEGATION_MAX_SINGLE_TRADE_PCT = Decimal("10")
DELEGATION_MAX_DAILY_TRADE_PCT = Decimal("30")
DELEGATION_MIN_HF_FLOOR = Decimal("1.6")
DELEGATION_MAX_EXPIRES_DAYS = 365


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    is_active: bool
    notification_email: Optional[str]
    notification_frequency: str
    max_single_trade_usd: Optional[Decimal]
    max_daily_trade_usd: Optional[Decimal]
    user_mode: str
    execution_policy: str
    line_monthly_opt_in: bool = False
    # 重要事項確認同意日時（User.terms_accepted_at を公開）
    terms_agreed_at: Optional[datetime] = None
    # 同意時の規約バージョン（フロントエンドの再同意判定に使用）
    terms_version: Optional[str] = None
    # Phase-D D5b: aggressive ティアのリスク開示/同意日時（未同意なら None）。
    aggressive_ack_at: Optional[datetime] = None
    # リスクモード（conservative / balanced / aggressive）。「完全おまかせ」の運用方針表示に使う。
    # 提案生成側のプロトコル選択 (RISK_MODE_PROTOCOLS) はこの値で決まるため、委譲枠
    # (allowed_protocols) と併せて初めて実効スコープが決まる。
    risk_mode: Optional[str] = None
    # 法人決算月 (1-12)。NULL=個人ユーザー。設定済みで TAX & REPORTS 法人モードを解放する。
    corporate_fiscal_month: Optional[int] = None
    # ユーザーロール（admin / viewer / partner）。フロントエンドの権限分岐に使用する。
    role: str = "viewer"
    # EOA ウォレットアドレス（Privy embedded wallet 等）。未設定なら None。
    wallet_address: Optional[str] = None
    # Smart Wallet (ERC-4337) アドレス。設定済みなら Aave 実行の実体はこちら
    # (backend/app/proposals/router.py の smart_wallet_address 優先ロジックと対応)。
    smart_wallet_address: Optional[str] = None


class UserSettingsUpdate(BaseModel):
    notification_email: Optional[str] = None
    notification_frequency: Optional[str] = None
    max_single_trade_usd: Optional[Decimal] = None
    max_daily_trade_usd: Optional[Decimal] = None
    user_mode: Optional[str] = None
    execution_policy: Optional[str] = None
    line_monthly_opt_in: Optional[bool] = None
    # 法人決算月 (1-12)。設定すると TAX & REPORTS 法人モードが解放される。
    corporate_fiscal_month: Optional[int] = None
    # ユーザー名（本人による表示名変更）。auth/schemas.py の登録時 validator と同一規則。
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)

    @field_validator("corporate_fiscal_month")
    @classmethod
    def validate_corporate_fiscal_month(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if not (1 <= v <= 12):
            raise ValueError("corporate_fiscal_month は 1〜12 の整数で指定してください")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("ユーザー名は空白のみにできません")
        if not (v[0].isalpha() or v[0].isdigit()):
            raise ValueError(
                "ユーザー名は文字か数字で始まる必要があります (must start with a letter or number)"
            )
        if not re.match(r"^[\w\s\-]+$", v):
            raise ValueError("ユーザー名には文字・数字・スペース・_・- のみ使用できます")
        return v.lower()


class DelegationGrantRequest(BaseModel):
    """事前枠承認（委譲枠）の作成リクエスト。

    上限は % で指定。ハードキャップ（単一≤10% / 日次≤30% / HF≥1.6）を超える値は
    入力段階で 422 にする（実行時にも risk_limiter で二重クランプ）。
    """

    max_single_trade_pct: Decimal = Field(..., gt=0)
    max_daily_trade_pct: Decimal = Field(..., gt=0)
    hf_floor: Decimal = Field(default=DELEGATION_MIN_HF_FLOOR)
    allowed_protocols: list[str] = Field(..., min_length=1)
    allowed_assets: list[str] = Field(..., min_length=1)
    expires_in_days: int = Field(..., ge=1, le=DELEGATION_MAX_EXPIRES_DAYS)
    # L1/L3: frontend が consent(addSessionSigners) 後に渡す Privy 識別子（任意・後方互換）。
    # /delegation/prepare で作成した policy_id と SERVER_SIGNER_ID を grant 確定時に保存する。
    privy_policy_id: Optional[str] = Field(default=None, max_length=255)
    privy_signer_id: Optional[str] = Field(default=None, max_length=255)
    # Privy 内部 wallet ID（アドレスではない）。ログイン時点(wallet-connect)では embedded wallet
    # が未委譲のため常に null（Privy SDK 仕様）で取得できず、addSigners 成功後（＝本エンドポイント
    # 呼び出し時）に初めて解決可能になる。委譲(SCW)執行の wallet_sendCalls が要求する識別子で、
    # users.privy_wallet_id へ保存する（2026-07-16、per-user 解決の唯一の確実な経路）。
    privy_wallet_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("max_single_trade_pct")
    @classmethod
    def _validate_single(cls, v: Decimal) -> Decimal:
        if v > DELEGATION_MAX_SINGLE_TRADE_PCT:
            raise ValueError(
                f"max_single_trade_pct は {DELEGATION_MAX_SINGLE_TRADE_PCT}% 以下にしてください"
            )
        return v

    @field_validator("max_daily_trade_pct")
    @classmethod
    def _validate_daily(cls, v: Decimal) -> Decimal:
        if v > DELEGATION_MAX_DAILY_TRADE_PCT:
            raise ValueError(
                f"max_daily_trade_pct は {DELEGATION_MAX_DAILY_TRADE_PCT}% 以下にしてください"
            )
        return v

    @field_validator("hf_floor")
    @classmethod
    def _validate_hf(cls, v: Decimal) -> Decimal:
        if v < DELEGATION_MIN_HF_FLOOR:
            raise ValueError(f"hf_floor は {DELEGATION_MIN_HF_FLOOR} 以上にしてください")
        return v

    @field_validator("allowed_protocols")
    @classmethod
    def _validate_protocols(cls, v: list[str]) -> list[str]:
        """委譲可能集合で検証し、正規化（trim + 小文字）+ 重複排除する。

        prepare は `resolve_protocol_contracts` で写像不能なら 502 になるが、grant 側は本
        validator を入れるまで**素通し**だった（`min_length=1` のみ）。そのため
        `prepare(["aave"])` → `grant(["aave","pendle"])` で「grant は pendle を主張するが
        Privy policy は Aave 限定」という乖離を作れた（routing は broadcast を試み TEE が拒否）。
        両 leg が本 schema を共有するのでここで揃える。

        正規化する理由: `_should_use_scw_route`（proposals/router.py）は grant 値を lower する
        が strip はしないため、`" pendle"` は policy 側を通って routing 側だけで落ちる。
        """
        # 委譲可能集合の正は policy_mapper（写像の実装元）。ここで再定義しない。
        from app.privy.policy_mapper import SUPPORTED_DELEGATION_PROTOCOLS

        normalized: list[str] = []
        for raw in v:
            protocol = raw.strip().lower()
            if not protocol:
                raise ValueError("allowed_protocols に空の要素は指定できません")
            if protocol not in SUPPORTED_DELEGATION_PROTOCOLS:
                raise ValueError(
                    f"{raw!r} は委譲できません (対応: {sorted(SUPPORTED_DELEGATION_PROTOCOLS)})"
                )
            if protocol not in normalized:
                normalized.append(protocol)
        return normalized


class DelegationGrantResponse(BaseModel):
    """委譲枠のレスポンス。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    wallet_address: Optional[str]
    max_single_trade_pct: Decimal
    max_daily_trade_pct: Decimal
    hf_floor: Decimal
    allowed_protocols: list[str]
    allowed_assets: list[str]
    consent_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime]
    privy_policy_id: Optional[str] = None
    privy_signer_id: Optional[str] = None


class SetupIntentResponse(BaseModel):
    """カード登録用 SetupIntent のレスポンス。frontend は client_secret を
    Stripe.js の confirmSetup() に渡す。"""

    client_secret: str


class PaymentMethodResponse(BaseModel):
    """登録済みカードの表示用情報（PAN 等の機微情報は含まない）。"""

    registered: bool
    brand: Optional[str] = None
    last4: Optional[str] = None


class PaymentMethodConfirmRequest(BaseModel):
    setup_intent_id: str = Field(..., min_length=1)


class DelegationPrepareResponse(BaseModel):
    """委譲 policy 作成（L1 / prepare）のレスポンス。

    frontend はこの ``privy_signer_id`` / ``privy_policy_id`` を
    ``addSessionSigners({signers:[{signerId, policyIds:[policyId]}]})`` に渡し、consent 後に
    ``/delegation/grant`` へ同じ値を返して枠を確定する。
    """

    privy_policy_id: str
    privy_signer_id: str
    chain_name: str
    expires_at: datetime
