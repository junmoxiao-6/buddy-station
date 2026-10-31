#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 技能形态的入口：转发到 ``buddy_station`` 包。

为什么用引导脚本而不是在这里复制一份业务代码：
    仓库里只保留 `src/buddy_station/` 这一份实现，技能形态通过这里转发过去，
    两边行为永远一致（复制副本必然会漂移，历史上就吃过"打包内容与源码不同步"的亏）。

运行前提（满足任一即可）：
    1. 已 ``pip install buddy-station``
    2. 本文件仍在仓库内（往上两级能找到 ``src/buddy_station``）

用法与 CLI 完全一致：
    python checkin.py run
    python checkin.py setup
    python checkin.py diagnose
"""

from __future__ import annotations

import os
import sys


def _ensure_importable() -> None:
    """把仓库的 ``src/`` 或已安装包接进 sys.path。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in ("../../src", "../src", "src"):
        candidate = os.path.abspath(os.path.join(here, rel))
        if os.path.isdir(os.path.join(candidate, "buddy_station")):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return


def main(argv: list[str] | None = None) -> int:
    _ensure_importable()
    try:
        from buddy_station.cli import main as cli_main
    except ImportError:
        sys.stderr.write(
            "找不到 buddy_station 包。请二选一：\n"
            "  1) pip install buddy-station\n"
            "  2) 在本仓库根目录执行 pip install -e .\n")
        return 20
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
