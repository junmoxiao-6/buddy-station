# -*- coding: utf-8 -*-
"""路径与版本解析：把「技能目录」与「数据目录」解耦。

为什么单独一层：
    早期实现把日志写在自己所在目录（`<skill>/logs/`）。这在 WorkBuddy 技能沙箱里没问题，
    但一旦用 `pip install buddy-station` 装进 site-packages，往包目录写文件会失败
    （无权限 / 只读 / 被包管理器视为损坏）。所以运行时数据统一放到用户数据目录。

数据目录优先级：
    1. 环境变量 ``BUDDY_STATION_HOME``（CI / 测试 / 便携模式用）
    2. 平台标准目录：
       - Windows : ``%LOCALAPPDATA%\\buddy-station``
       - macOS   : ``~/Library/Application Support/buddy-station``
       - Linux   : ``$XDG_DATA_HOME/buddy-station`` 或 ``~/.local/share/buddy-station``

注意：WorkBuddy 的**令牌**路径（``~/.workbuddy/auth/workbuddy.json``）不在这里决定，
      那是上游协议的固定位置，由 ``checkin.token_file_path()`` 负责。
"""

from __future__ import annotations

import os
import sys

APP_NAME = "buddy-station"


def data_dir() -> str:
    """返回运行数据目录（日志、结果快照、更新状态都在这里）。

    只计算路径，**不创建目录**——调用方写文件前自己建，避免只读环境下 import 就报错。
    """
    override = (os.environ.get("BUDDY_STATION_HOME") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))

    home = os.path.expanduser("~")
    if sys.platform == "win32":
        base = (os.environ.get("LOCALAPPDATA") or "").strip() or os.path.join(home, "AppData", "Local")
        return os.path.join(base, APP_NAME)
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", APP_NAME)
    base = (os.environ.get("XDG_DATA_HOME") or "").strip() or os.path.join(home, ".local", "share")
    return os.path.join(base, APP_NAME)


def logs_dir() -> str:
    return os.path.join(data_dir(), "logs")


def package_dir() -> str:
    """包自身所在目录（只读；用于读内置资源，不用于写）。"""
    return os.path.dirname(os.path.abspath(__file__))


def package_version() -> str:
    """单一版本真相源：优先已安装的发行版元数据，其次包内 ``__version__``。"""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version(APP_NAME)
        except PackageNotFoundError:
            pass
    except Exception:  # pragma: no cover - 极旧的 Python / 受限环境
        pass
    try:
        from . import __version__

        return __version__
    except Exception:  # noqa: BLE001 - 作为剧本运行时没有包上下文
        return "0.0.0"
