# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
Exchange モジュール（Bybit Sandbox via ccxt）。

ccxt ライブラリを使って Bybit サンドボックス環境での取引注文を管理する。

責務:
- Bybit Sandbox への成行注文（BUY / SELL）の送信
- 日次取引上限・クールダウン・最大注文金額のルールチェック
- DummyExchangeClient によるテスト用スタブ提供
"""
