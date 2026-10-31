# -*- coding: utf-8 -*-
"""setup / auth 的编排测试：端探测、授权分支、定时任务参数。

这里只验"编排是否正确"，不验网络：
  * 有凭据 → 必须真的去签到
  * 没凭据 → 必须给出可执行的授权路径，且 ``ok=False``（不假装完成）
  * 定时任务 → 只输出参数，绝不自己注册
"""

from __future__ import annotations

import unittest
from unittest import mock

import _helpers as H

checkin = H.checkin
device_login = H.device_login


def env(endpoint: str, scheduler: str, has_wbipc: bool, token: bool) -> dict:
    return {"endpoint": endpoint, "platform": "linux" if "cloud" in endpoint else "win32",
            "python": "3.13.0", "uid_env": [], "has_wbipc": has_wbipc,
            "scheduler": scheduler, "token_file_present": token}


class EnvironmentTest(unittest.TestCase):
    def test_shape(self) -> None:
        info = checkin.detect_environment()
        for key in ("endpoint", "scheduler", "has_wbipc", "token_file_present", "uid_env"):
            self.assertIn(key, info)
        self.assertIsInstance(info["uid_env"], list)

    def test_scheduler_is_known_value(self) -> None:
        info = checkin.detect_environment()
        self.assertIn(info["scheduler"],
                      {"windows-task", "systemd", "launchd", "cron",
                       "workbuddy-automation", "none"})


class ExtractStateTest(unittest.TestCase):
    """``adopt`` 要吃用户从各种地方复制来的字符串，形态必须都认。"""

    CASES = [
        ("https://copilot.tencent.com/login?platform=CLI&state=cead0ce7-ac9d-4d21-b1d1-91a59d597836&x=1",
         "cead0ce7-ac9d-4d21-b1d1-91a59d597836"),
        ("  \"cead0ce7-ac9d-4d21-b1d1-91a59d597836\"  ",
         "cead0ce7-ac9d-4d21-b1d1-91a59d597836"),
        ("CEAD0CE7-AC9D-4D21-B1D1-91A59D597836", "cead0ce7-ac9d-4d21-b1d1-91a59d597836"),
        ("https://www.workbuddy.cn/login?state=11111111-2222-4333-8444-555555555555",
         "11111111-2222-4333-8444-555555555555"),
        ("https://example.com/no-state", ""),
        ("", ""),
    ]

    def test_all_forms(self) -> None:
        for raw, want in self.CASES:
            with self.subTest(raw=raw[:48]):
                self.assertEqual(device_login._extract_state(raw), want)

    def test_none_is_safe(self) -> None:
        self.assertEqual(device_login._extract_state(""), "")


class AutomationPromptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.params = checkin.automation_prompt()["params"]

    def test_schedule_is_six_hourly(self) -> None:
        # 猫旅途 1-4 小时；6 小时间隔能保证"到店后必被领"，再短纯烧额度
        self.assertEqual(self.params["rrule"], "FREQ=HOURLY;INTERVAL=6")
        self.assertEqual(self.params["mode"], "create")

    def test_prompt_is_non_blocking_and_self_aware(self) -> None:
        prompt = self.params["prompt"]
        self.assertIn("auth", prompt)
        self.assertIn("禁止 poll --wait", prompt)      # 不允许阻塞等扫码
        self.assertIn("跳过任何", prompt)               # 防止自己再建一条定时任务

    def test_prompt_carries_no_secret(self) -> None:
        prompt = self.params["prompt"]
        for needle in ("eyJ", "Bearer", "refresh_token", "access_token"):
            self.assertNotIn(needle, prompt)

    def test_prompt_does_not_self_install(self) -> None:
        """定时任务里不该出现下载安装动作（包管理应交给用户）。"""
        prompt = self.params["prompt"]
        self.assertNotIn(".zip", prompt)
        self.assertNotIn("curl ", prompt)


class SetupOrchestrationTest(unittest.TestCase):
    def _setup(self, *, endpoint, scheduler, has_wbipc, token, configured,
               auth_url=None):
        patches = {
            "detect_environment": lambda: env(endpoint, scheduler, has_wbipc, token),
            "do_auth": lambda: {"ok": True, "action": "auth",
                                "configured": configured,
                                **({"auth_url": auth_url} if auth_url else {})},
            "guard_uid": lambda *a, **k: None,
            "open_channel": lambda *a, **k: (object(), {"selected": "stub"}),
            "do_run_full": lambda ch, loc: {"ok": True, "summary": "签到:already / 猫猫:traveling"},
            "append_record": lambda rec: None,
            "schedule_spec": lambda: {"supported": True, "type": "windows-task",
                                      "name": "BuddyStationGuardian-Daily",
                                      "times": ["00:05", "06:05", "12:05", "18:05"]},
        }
        with mock.patch.multiple(checkin, **patches):
            return checkin.do_setup()

    def test_cloud_without_credential_gives_auth_path(self) -> None:
        res = self._setup(endpoint="cloud", scheduler="workbuddy-automation",
                          has_wbipc=False, token=False, configured=False,
                          auth_url="https://copilot.tencent.com/login?state=x")
        steps = " ".join(res["next_steps"])
        self.assertFalse(res["ok"])            # 没签到就绝不能说自己 ok
        self.assertNotIn("run", res)
        self.assertIn("adopt", steps)          # 云端正路
        self.assertIn("buddy-station login start", steps)   # 备选
        self.assertTrue(res["auth_url"])
        self.assertEqual(res["schedule"]["suggestion"]["tool"], "automation_update")

    def test_desktop_with_credential_runs_and_reports_manual_spec(self) -> None:
        res = self._setup(endpoint="desktop", scheduler="windows-task",
                          has_wbipc=True, token=True, configured=True)
        self.assertTrue(res["run"]["ok"])
        self.assertIsInstance(res["schedule"]["manual"], dict)
        self.assertIn("凭据:已有", res["summary"])
        self.assertIn("定时:命令已给", res["summary"])
        self.assertTrue(res["ok"])

    def test_no_persistent_scheduler_falls_back_to_automation(self) -> None:
        res = self._setup(endpoint="cloud", scheduler="none",
                          has_wbipc=False, token=True, configured=True)
        self.assertIsNotNone(res["schedule"]["suggestion"])
        self.assertTrue(res["ok"])


class AuthEndpointAwarenessTest(unittest.TestCase):
    """云端自建的授权码会被服务端拒收，所以要先推 adopt；桌面端不用推。"""

    class _FakeDeviceLogin:
        @staticmethod
        def start_state():
            return {"ok": True, "step": "start",
                    "auth_url": "https://copilot.tencent.com/login?state=fake"}

    class _NoToken:
        available = False

        def describe(self) -> str:
            return "stub: 无令牌"

    def setUp(self) -> None:
        self._patches = [
            mock.patch.object(checkin, "TokenFileChannel", self._NoToken),
            mock.patch.object(checkin, "_load_module",
                              lambda name: self._FakeDeviceLogin
                              if name == "device_login" else None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()

    def test_cloud_prefers_adopt(self) -> None:
        with mock.patch.object(checkin, "detect_environment",
                               lambda: {"endpoint": "cloud", "has_wbipc": False}):
            res = checkin.do_auth()
        self.assertEqual(res.get("recommended"), "adopt")
        self.assertTrue(res.get("adopt_hint"))
        self.assertTrue(res.get("auth_url"))

    def test_desktop_does_not_push_adopt(self) -> None:
        with mock.patch.object(checkin, "detect_environment",
                               lambda: {"endpoint": "desktop", "has_wbipc": True}):
            res = checkin.do_auth()
        self.assertNotIn("recommended", res)
        self.assertFalse(res["configured"])
        self.assertTrue(res.get("auth_url"))


if __name__ == "__main__":
    unittest.main()
