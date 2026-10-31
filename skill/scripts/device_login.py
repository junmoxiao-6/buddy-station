#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能形态的设备授权入口：转发到 ``buddy_station.device_login``。

等价于 ``buddy-station login <start|adopt|poll|status>``。
"""

from __future__ import annotations

import os
import sys


def _ensure_importable() -> None:
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
        from buddy_station.device_login import main as dl_main
    except ImportError:
        sys.stderr.write(
            "找不到 buddy_station 包。请先 pip install buddy-station\n")
        return 20
    return dl_main(argv)


if __name__ == "__main__":
    sys.exit(main())
