# -*- coding: utf-8 -*-
"""测试共享脚手架：路径注入、隔离的数据目录、捕获一处 JSON 输出。

设计约束（很重要）：
  * **不联网**。任何真实 HTTP 都必须被打桩，否则 CI 会在无网络环境随机失败。
  * **不碰用户真实数据**。``BUDDY_STATION_HOME`` 指向临时目录，
    绝不写到 ``~/.local/share/buddy-station`` 或 ``%LOCALAPPDATA%``。
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 在导入被测模块之前就把数据目录钉到临时位置
if "BUDDY_STATION_HOME" not in os.environ:
    os.environ["BUDDY_STATION_HOME"] = tempfile.mkdtemp(prefix="buddy-station-test-")

from buddy_station import checkin, cli, device_login, notify, paths, self_update  # noqa: E402

__all__ = [
    "ROOT", "SRC", "checkin", "cli", "device_login", "notify", "paths",
    "self_update", "run_main", "capture_main", "capture_cli",
]


def capture_main(module, argv: list[str]) -> tuple[int, dict]:
    """跑一次 ``module.main(argv)``，返回 (退出码, 最后一行 JSON)。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = module.main(argv)
    lines = [ln for ln in buf.getvalue().strip().splitlines() if ln.strip()]
    payload: dict = {}
    for line in reversed(lines):
        if line.lstrip().startswith("{"):
            payload = json.loads(line)
            break
    return code, payload


def run_main(argv: list[str]) -> tuple[int, dict]:
    """跑 ``buddy_station.checkin.main``（业务动作）。"""
    return capture_main(checkin, argv)


def capture_cli(argv: list[str]) -> tuple[int, str]:
    """跑 ``cli.main``，返回 (退出码, 全部 stdout)。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


def travel_state(state: str, limit: bool = False, arrive: int = 1792000000) -> dict:
    return {"state": state, "arrive_at": arrive, "daily_limit_reached": limit,
            "record_id": 1}
