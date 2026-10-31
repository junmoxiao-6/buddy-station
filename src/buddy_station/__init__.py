# -*- coding: utf-8 -*-
"""buddy-station —— WorkBuddy「Buddy 加油站」每日签到 + 猫猫旅行自动化。

设计要点（都写在对应模块的 docstring 里，这里只列结论）：

* 四通道取凭据，任一可用即可跑：``wbipc`` / ``token_file`` / ``rt`` / ``skill_token``
* 输出恒为一行 JSON，并落盘 ``<data-dir>/logs/last_result.json``，方便定时任务与上层自动化消费
* 语义化退出码 ``0 / 10 / 20 / 30``，区分「幂等成功 / 要人 / 通道不通 / 上游故障」
* 零第三方依赖（纯标准库），因此任何有 Python 3.9+ 的机器都能直接跑

版本谱系：本项目由 WorkBuddy 技能 ``buddy-station-guardian`` 演进而来，
技能形态（``skill/`` 目录）与 CLI 形态共用同一套 ``src/buddy_station`` 源码。
"""

from __future__ import annotations

__version__ = "2.0.0"
__all__ = ["__version__"]
