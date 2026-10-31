# -*- coding: utf-8 -*-
"""pytest 入口：复用 unittest 风格的用例，并统一测试期环境。

``python -m unittest discover -s tests`` 与 ``pytest`` 两种方式都应该能跑通，
所以真正的路径注入放在 ``_helpers.py`` 里，这里只补充 pytest 专属设置。
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("BUDDY_STATION_HOME", tempfile.mkdtemp(prefix="buddy-station-test-"))
