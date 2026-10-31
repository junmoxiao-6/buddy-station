# -*- coding: utf-8 -*-
"""命令行入口：把内部动作统一成 ``buddy-station <command>``。

为什么还要薄薄一层 CLI：
    ``checkin.main()`` 只认业务动作（run / probe / ...）。但用户还需要
    ``login``（授权）、``notify``（配置自检）、``version``（版本）这类入口，
    以及一个 ``--data-dir`` 让便携模式跑在 U 盘/临时目录。这些属于"外壳"，
    不该塞进业务引擎，所以放在这里做分发。

Usage:
    buddy-station run                 # 签到 + 遛猫（幂等，可反复跑）
    buddy-station checkin             # 只签到
    buddy-station travel              # 只处理猫猫旅行（先领后派）
    buddy-station probe               # 只读：通道 / 状态 / 身份
    buddy-station diagnose            # 只读全量自检（别名 doctor）
    buddy-station auth                # 凭据自助：给一次性授权链接
    buddy-station setup               # 一键引导：端探测 → 凭据 → 签到 → 定时参数
    buddy-station acquire-rt --show    # 导出长效 refresh token（云端 secret）
    buddy-station update              # 只读检查有没有新版
    buddy-station login poll          # 设备授权：start / adopt / poll / status
    buddy-station notify --status     # 通知渠道就绪情况
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__

USAGE = """buddy-station —— WorkBuddy 加油站签到 + 猫猫旅行自动化

常用命令：
  buddy-station run                  签到 + 遛猫（幂等，随时可跑）
  buddy-station setup                一键引导：环境探测 → 凭据 → 签到 → 定时参数
  buddy-station diagnose             只读自检：版本 / 通道 / 令牌 / 通知 / 今日状态
  buddy-station acquire-rt --show    导出长效令牌（放进 CI secret 用）
  buddy-station login start|adopt|poll|status
                                     设备授权（扫码一次，之后自动续期）
  buddy-station notify --status      通知渠道自检

全部动作：
  run / checkin / travel / probe / report / auth / setup /
  diagnose(doctor) / acquire-rt / update / login / notify / version

全局选项：
  --data-dir DIR    运行数据目录（默认平台标准目录，也可用 BUDDY_STATION_HOME）
  -h, --help        显示本帮助

退出码：
  0 成功或幂等跳过   10 需要人工介入   20 没有可用凭据通道   30 上游异常
"""

ACTIONS = (
    "run", "checkin", "travel", "probe", "report", "auth", "setup",
    "diagnose", "doctor", "acquire-rt", "update", "login", "notify", "version",
)


def _extract_global(argv: list[str]) -> tuple[list[str], str | None]:
    """取出全局 ``--data-dir``（可放任意位置），返回 (剩余参数, 目录)。"""
    rest: list[str] = []
    data_dir: str | None = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--data-dir":
            if i + 1 < len(argv):
                data_dir = argv[i + 1]
                i += 2
                continue
            raise SystemExit("--data-dir 需要一个目录参数")
        if tok.startswith("--data-dir="):
            data_dir = tok.split("=", 1)[1]
            i += 1
            continue
        rest.append(tok)
        i += 1
    return rest, data_dir


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass

    args, data_dir = _extract_global(list(argv if argv is not None else sys.argv[1:]))
    if data_dir:
        os.environ["BUDDY_STATION_HOME"] = os.path.abspath(os.path.expanduser(data_dir))

    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    if args[0] == "--selftest":
        return _self_test()

    cmd, tail = args[0], args[1:]

    if cmd in ("-V", "--version", "version"):
        print(__version__)
        return 0

    if cmd not in ACTIONS:
        print("未知命令：{}\n".format(cmd), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    # 延迟导入：--help / version 不需要加载整套业务模块
    if cmd == "login":
        from . import device_login

        return device_login.main(tail)
    if cmd == "notify":
        from . import notify

        return notify.main(tail)
    if cmd == "doctor":
        cmd = "diagnose"

    from . import checkin

    return checkin.main([cmd] + tail)


def _self_test() -> int:
    """``python -m buddy_station --selftest``：不联网的快速冒烟。"""
    from . import checkin

    ok = True
    checks = [
        ("parse version", bool(checkin._manifest_version())),
        ("channel names", all(hasattr(checkin, n) for n in
                              ("WbipcChannel", "TokenFileChannel",
                               "RtChannel", "SkillTokenChannel"))),
        ("exit codes", (checkin.EX_OK, checkin.EX_NEED_HUMAN,
                        checkin.EX_NO_CHANNEL, checkin.EX_UPSTREAM) == (0, 10, 20, 30)),
        ("actions wired", callable(checkin.main)),
    ]
    for name, cond in checks:
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and bool(cond)
    print("RESULT:", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
