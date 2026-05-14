# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/billing/__init__.py
"""
Billing モジュール (v10)。

v9 実装 (models.py / router.py / service.py / schemas.py / dynamic_fee.py) は
F-13 で物理削除済み。残存するのは v10 ORM のみ。

F-16 (本番リリース) で V10Base を app.database.Base に統合後、本モジュールを廃止予定。
トレード時点の手数料ゲートは app.fees.trade_gate に移行済み。
"""
