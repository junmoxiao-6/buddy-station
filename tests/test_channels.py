# -*- coding: utf-8 -*-
"""通道选择与失败语义。

覆盖的是**最容易静默出错**的地方：
  * 一条通道都没有时必须 exit 20（而不是"跑成功但什么都没做"）
  * 强制通道不可用时必须报错，不能悄悄换通道
  * 子任务失败必须反映到退出码（定时任务只看退出码）

不联网：全部用打桩替身。
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import _helpers as H

checkin = H.checkin


class _Unavailable:
    """任何"不可用通道"的最小替身。"""

    name = "stub"

    def __init__(self, *a, **k):
        self.available = False
        self.rec: dict = {}

    def describe(self) -> str:
        return "stub: 不可用"


def unavailable_named(name: str) -> type:
    """构造一个 ``name`` 正确、但 ``available=False`` 的通道替身。

    名字必须对得上：``open_channel("token_file")`` 是按 ``ch.name`` 匹配的，
    替身名字不对会让"强制不可用"这条断言变成假阴性。
    """
    return type("Unavailable_" + name, (_Unavailable,), {"name": name})


class ChannelSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = dict(os.environ)
        # 令牌文件指向确定不存在的位置，避免本机真实令牌把判据带偏
        os.environ["WORKBUDDY_TOKEN_FILE"] = os.path.join(
            os.environ.get("TEMP", "/tmp"), "__definitely_missing_token__.json")
        for key in ("X_SKILL_TOKEN", "WORKBUDDY_SKILL_TOKEN", "SKILL_TOKEN",
                    "WORKBUDDY_RT"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_no_channel_exits_20(self) -> None:
        with mock.patch.object(checkin, "WbipcChannel", _Unavailable), \
                mock.patch.object(checkin, "SkillTokenChannel", _Unavailable), \
                mock.patch.object(checkin, "TokenFileChannel", _Unavailable):
            with self.assertRaises(checkin.ApiError) as ctx:
                checkin.open_channel()
        err = ctx.exception
        self.assertEqual(err.exit_code, 20)
        self.assertEqual(err.code, "channel_unavailable")

    def test_skill_token_selected_when_no_ipc(self) -> None:
        os.environ["X_SKILL_TOKEN"] = "fake-token-for-test"
        with mock.patch.object(checkin, "WbipcChannel", _Unavailable), \
                mock.patch.object(checkin, "TokenFileChannel", _Unavailable):
            channel, diag = checkin.open_channel()
        self.assertEqual(channel.name, "skill_token")
        self.assertEqual(diag.get("selected"), "skill_token")

    def test_forced_channel_unavailable_is_loud(self) -> None:
        with mock.patch.object(checkin, "TokenFileChannel",
                               unavailable_named("token_file")):
            with self.assertRaises(checkin.ApiError) as ctx:
                checkin.open_channel("token_file")
        self.assertEqual(ctx.exception.exit_code, 20)
        self.assertIn("token_file", ctx.exception.message)

    def test_unknown_channel_is_human_error(self) -> None:
        with self.assertRaises(checkin.ApiError) as ctx:
            checkin.open_channel("carrier-pigeon")
        self.assertEqual(ctx.exception.exit_code, 10)


class ExitCodeTest(unittest.TestCase):
    def test_travel_failure_makes_run_exit_30(self) -> None:
        """签到成功但猫没派出去，必须是失败——否则定时任务会把"猫丢了"当成功吞掉。"""
        fake_channel = object()
        with mock.patch.object(checkin, "guard_uid", lambda *a, **k: None), \
                mock.patch.object(checkin, "open_channel",
                                  lambda *a, **k: (fake_channel, {"selected": "stub"})), \
                mock.patch.object(checkin, "do_checkin",
                                  lambda ch: {"result": "ok", "credit": 100, "streak_days": 3}), \
                mock.patch.object(checkin, "fetch_travel_status",
                                  lambda ch: H.travel_state("idle")), \
                mock.patch.object(checkin, "do_travel",
                                  lambda ch, loc: {"result": "error", "code": 500,
                                                   "reason": "派遣被拒（模拟）"}), \
                mock.patch.object(checkin, "append_record", lambda *a, **k: None):
            code, out = H.run_main(["run"])
        self.assertEqual(code, 30)
        self.assertFalse(out.get("ok"))
        self.assertIn("travel", out.get("failed") or [])

    def test_checkin_failure_makes_checkin_exit_30(self) -> None:
        fake_channel = object()
        with mock.patch.object(checkin, "guard_uid", lambda *a, **k: None), \
                mock.patch.object(checkin, "open_channel",
                                  lambda *a, **k: (fake_channel, {"selected": "stub"})), \
                mock.patch.object(checkin, "do_checkin",
                                  lambda ch: {"result": "error", "code": 500,
                                              "reason": "上游 500"}), \
                mock.patch.object(checkin, "fetch_checkin_status",
                                  lambda ch: {"total_credits": None, "streak_days": 0}), \
                mock.patch.object(checkin, "append_record", lambda *a, **k: None):
            code, out = H.run_main(["checkin"])
        self.assertEqual(code, 30)
        self.assertFalse(out.get("ok"))


if __name__ == "__main__":
    unittest.main()
