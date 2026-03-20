# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
reports テスト専用の conftest。

app.main (JWT 等の外部依存) をロードせず、reports モジュールのみテストする。
sys.path だけ設定する。
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)