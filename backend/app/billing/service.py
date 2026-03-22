# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/billing/service.py
"""
Billing サービスロジック。

管理報酬・成果報酬の計算、HWM 追跡、バッチ処理を担当する。
全ての数値計算は decimal.Decimal で行い、float は一切使用しない。
"""

import logging
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import FeeCalculation, FeeConfig, HighWaterMark
from .schemas import BatchResult, FeeSummaryResponse

logger = logging.getLogger(__name__)

# デフォルトの手数料設定値
_DEFAULT_MANAGEMENT_FEE_RATE = Decimal("0.005")
_DEFAULT_PERFORMANCE_FEE_RATE = Decimal("0.10")
_DEFAULT_MINIMUM_AUM = Decimal("3000")
_DEFAULT_HWM_ENABLED = True

# 年間日数（日割り計算用）
_DAYS_IN_YEAR = Decimal("365")

# 小数点以下丸め精度
_QUANTIZE_UNIT = Decimal("0.000001")


class BillingServiceError(Exception):
    """Billing サービス固有の例外。"""

    pass


class BillingService:
    """
    手数料計算・記録サービス。

    全ての計算は Decimal のみ使用。float は禁止。
    """

    def calculate_daily_management_fee(
        self,
        aum: Decimal,
        rate: Decimal,
    ) -> Decimal:
        """
        日次管理報酬を計算する。

        日割り計算: aum * rate / 365, ROUND_HALF_UP

        Args:
            aum: AUM（Assets Under Management）
            rate: 年率管理報酬率

        Returns:
            日次管理報酬額（Decimal）
        """
        result = aum * rate / _DAYS_IN_YEAR
        return result.quantize(_QUANTIZE_UNIT, rounding=ROUND_HALF_UP)

    def calculate_performance_fee(
        self,
        current_value: Decimal,
        hwm: Decimal,
        rate: Decimal,
    ) -> Decimal:
        """
        成果報酬を計算する。

        current_value > hwm の場合のみ手数料が発生する。
        それ以外は Decimal('0')。

        Args:
            current_value: 現在の資産額
            hwm: High Water Mark
            rate: 成果報酬率

        Returns:
            成果報酬額（Decimal）
        """
        if current_value > hwm:
            profit = current_value - hwm
            result = profit * rate
            return result.quantize(_QUANTIZE_UNIT, rounding=ROUND_HALF_UP)
        return Decimal("0")

    def get_or_create_hwm(
        self,
        db: Session,
        user_id: int,
        initial_value: Decimal,
    ) -> HighWaterMark:
        """
        HWM を取得、または初回作成する。

        Args:
            db: データベースセッション
            user_id: ユーザー ID
            initial_value: 初回作成時の HWM 値

        Returns:
            HighWaterMark レコード
        """
        hwm = db.query(HighWaterMark).filter(HighWaterMark.user_id == user_id).first()
        if hwm is None:
            hwm = HighWaterMark(
                user_id=user_id,
                hwm_value=initial_value,
                updated_at=datetime.now(timezone.utc),
            )
            db.add(hwm)
            db.flush()
            logger.info("HWM created for user_id=%d, initial_value=%s", user_id, initial_value)
        return hwm

    def update_hwm(
        self,
        db: Session,
        user_id: int,
        new_value: Decimal,
    ) -> HighWaterMark:
        """
        HWM を更新する。

        新値が既存の HWM より大きい場合のみ更新する。

        Args:
            db: データベースセッション
            user_id: ユーザー ID
            new_value: 新しい HWM 候補値

        Returns:
            更新後の HighWaterMark レコード

        Raises:
            BillingServiceError: HWM レコードが存在しない場合
        """
        hwm = db.query(HighWaterMark).filter(HighWaterMark.user_id == user_id).first()
        if hwm is None:
            raise BillingServiceError(
                f"HighWaterMark not found for user_id={user_id}. Call get_or_create_hwm first."
            )
        if new_value > hwm.hwm_value:
            hwm.hwm_value = new_value
            hwm.updated_at = datetime.now(timezone.utc)
            db.flush()
            logger.info(
                "HWM updated for user_id=%d: %s -> %s",
                user_id,
                hwm.hwm_value,
                new_value,
            )
        return hwm

    def record_fee_calculation(
        self,
        db: Session,
        user_id: int,
        calculation_date: date,
        period_type: str,
        aum_snapshot: Decimal,
        management_fee: Decimal,
        performance_fee: Decimal,
        profit_since_hwm: Decimal,
        hwm_value: Decimal,
    ) -> FeeCalculation:
        """
        手数料計算レコードを作成・保存する。

        Args:
            db: データベースセッション
            user_id: ユーザー ID
            calculation_date: 計算日
            period_type: 期間種別（'daily' or 'monthly'）
            aum_snapshot: AUM スナップショット
            management_fee: 管理報酬
            performance_fee: 成果報酬
            profit_since_hwm: HWM 以降の利益
            hwm_value: 計算時の HWM 値

        Returns:
            作成された FeeCalculation レコード
        """
        total_fee = management_fee + performance_fee
        calc = FeeCalculation(
            user_id=user_id,
            calculation_date=calculation_date,
            period_type=period_type,
            aum_snapshot=aum_snapshot,
            management_fee=management_fee,
            performance_fee=performance_fee,
            total_fee=total_fee,
            profit_since_hwm=profit_since_hwm,
            high_water_mark=hwm_value,
            created_at=datetime.now(timezone.utc),
        )
        db.add(calc)
        db.flush()
        return calc

    def run_daily_fee_batch(
        self,
        db: Session,
        user_aum_map: dict[int, Decimal],
        fee_config: FeeConfig | None = None,
    ) -> BatchResult:
        """
        日次手数料バッチを実行する。

        user_aum_map の各ユーザーについて日次手数料を計算・記録する。
        minimum_aum 未満のユーザーはスキップする。

        Args:
            db: データベースセッション
            user_aum_map: {user_id: current_aum} の辞書
            fee_config: 手数料設定（None なら DB から最新取得、なければデフォルト値）

        Returns:
            BatchResult（processed_count, failed_count, errors）
        """
        if fee_config is None:
            fee_config = self.get_active_fee_config(db)

        today = date.today()
        processed = 0
        failed = 0
        errors: list[str] = []

        for user_id, aum in user_aum_map.items():
            try:
                # minimum_aum 未満はスキップ
                if aum < fee_config.minimum_aum:
                    logger.debug(
                        "Skipping user_id=%d: aum=%s < minimum_aum=%s",
                        user_id,
                        aum,
                        fee_config.minimum_aum,
                    )
                    continue

                # HWM 取得または初回作成
                hwm_record = self.get_or_create_hwm(db, user_id, aum)
                hwm_value = hwm_record.hwm_value

                # 管理報酬計算
                mgmt_fee = self.calculate_daily_management_fee(aum, fee_config.management_fee_rate)

                # 成果報酬計算（HWM 有効時のみ）
                if fee_config.high_water_mark_enabled:
                    profit_since_hwm = max(aum - hwm_value, Decimal("0"))
                    perf_fee = self.calculate_performance_fee(
                        aum, hwm_value, fee_config.performance_fee_rate
                    )
                else:
                    profit_since_hwm = Decimal("0")
                    perf_fee = Decimal("0")

                # 計算レコード保存
                self.record_fee_calculation(
                    db=db,
                    user_id=user_id,
                    calculation_date=today,
                    period_type="daily",
                    aum_snapshot=aum,
                    management_fee=mgmt_fee,
                    performance_fee=perf_fee,
                    profit_since_hwm=profit_since_hwm,
                    hwm_value=hwm_value,
                )

                # HWM 更新（成果報酬計算後に更新）
                if fee_config.high_water_mark_enabled:
                    self.update_hwm(db, user_id, aum)

                processed += 1
                logger.info(
                    "Fee calculated for user_id=%d: mgmt=%s, perf=%s",
                    user_id,
                    mgmt_fee,
                    perf_fee,
                )

            except Exception as exc:
                failed += 1
                error_msg = f"user_id={user_id}: {exc}"
                errors.append(error_msg)
                logger.error("Failed to calculate fee for %s", error_msg)

        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise BillingServiceError(f"Batch commit failed: {exc}") from exc

        return BatchResult(
            processed_count=processed,
            failed_count=failed,
            errors=errors,
        )

    def get_user_fee_history(
        self,
        db: Session,
        user_id: int,
        period_type: str | None = None,
    ) -> list[FeeCalculation]:
        """
        ユーザーの手数料履歴を返す。

        Args:
            db: データベースセッション
            user_id: ユーザー ID
            period_type: 期間種別フィルタ（None なら全件）

        Returns:
            FeeCalculation のリスト（calculation_date 降順）
        """
        query = db.query(FeeCalculation).filter(FeeCalculation.user_id == user_id)
        if period_type is not None:
            query = query.filter(FeeCalculation.period_type == period_type)
        return query.order_by(FeeCalculation.calculation_date.desc()).all()

    def get_user_fee_summary(
        self,
        db: Session,
        user_id: int,
    ) -> FeeSummaryResponse:
        """
        ユーザーの手数料累計サマリーを返す。

        Args:
            db: データベースセッション
            user_id: ユーザー ID

        Returns:
            FeeSummaryResponse（累計管理報酬・成果報酬・合計・件数）
        """
        result = (
            db.query(
                func.coalesce(func.sum(FeeCalculation.management_fee), Decimal("0")).label(
                    "total_management_fee"
                ),
                func.coalesce(func.sum(FeeCalculation.performance_fee), Decimal("0")).label(
                    "total_performance_fee"
                ),
                func.coalesce(func.sum(FeeCalculation.total_fee), Decimal("0")).label("total_fee"),
                func.count(FeeCalculation.id).label("calculation_count"),
            )
            .filter(FeeCalculation.user_id == user_id)
            .one()
        )

        return FeeSummaryResponse(
            user_id=user_id,
            total_management_fee=Decimal(str(result.total_management_fee)),
            total_performance_fee=Decimal(str(result.total_performance_fee)),
            total_fee=Decimal(str(result.total_fee)),
            calculation_count=result.calculation_count,
        )

    def get_active_fee_config(self, db: Session) -> FeeConfig:
        """
        最新の FeeConfig を返す。

        レコードが存在しない場合はデフォルト値で新規作成する。

        Args:
            db: データベースセッション

        Returns:
            FeeConfig レコード
        """
        config = db.query(FeeConfig).order_by(FeeConfig.id.desc()).first()
        if config is None:
            config = FeeConfig(
                management_fee_rate=_DEFAULT_MANAGEMENT_FEE_RATE,
                performance_fee_rate=_DEFAULT_PERFORMANCE_FEE_RATE,
                high_water_mark_enabled=_DEFAULT_HWM_ENABLED,
                minimum_aum=_DEFAULT_MINIMUM_AUM,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(config)
            db.commit()
            db.refresh(config)
            logger.info("Default FeeConfig created.")
        return config
