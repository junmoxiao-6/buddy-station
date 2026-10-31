# -*- coding: utf-8 -*-
"""通知层：渠道筛选、密钥脱敏、推送判定、失败隔离。

原则：通知是**增强项**，任何渠道坏掉都不能拖垮签到主流程，也不能把密钥写进日志。
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import _helpers as H

notify = H.notify


class ChannelFilterTest(unittest.TestCase):
    CFG = {
        "enabled": True,
        "success_notify": False,
        "channels": [
            {"type": "bark", "url": "https://api.day.app/SECRETKEY123"},
            {"type": "unknown", "url": "x"},
            {"type": "feishu", "webhook": "https://open.feishu.cn/x", "enabled": False},
        ],
    }

    def test_filters_unknown_and_disabled(self) -> None:
        chans = notify.enabled_channels(self.CFG)
        self.assertEqual([c["type"] for c in chans], ["bark"])

    def test_supported_set_is_documented_size(self) -> None:
        # 12 个渠道：bark/feishu/wecom/dingtalk/telegram/slack/discord/
        # pushplus/serverchan/smtp/webhook/desktop
        self.assertGreaterEqual(len(notify.SUPPORTED), 12)
        for name in ("bark", "feishu", "wecom", "dingtalk", "telegram", "slack",
                     "discord", "pushplus", "serverchan", "smtp", "webhook", "desktop"):
            self.assertIn(name, notify.SUPPORTED)


class MaskTest(unittest.TestCase):
    def test_query_param_style(self) -> None:
        masked = notify.mask_secret("https://open.feishu.cn/open-apis/bot/v2/hook/abcdef123456")
        self.assertNotIn("abcdef123456", masked)

    def test_path_style_bark_key(self) -> None:
        """Bark 的密钥整段就在路径里，脱敏必须认得。"""
        masked = notify.mask_secret("https://api.day.app/SECRETKEY123")
        self.assertNotIn("SECRETKEY123", masked)

    def test_empty_is_safe(self) -> None:
        self.assertEqual(notify.mask_secret(""), "")


class ShouldNotifyTest(unittest.TestCase):
    def test_matrix(self) -> None:
        cases = [
            ({"ok": False, "exit_code": 10, "reason": "token_expired"}, True, "error"),
            ({"ok": False, "exit_code": 30, "failed": ["travel"]}, True, "error"),
            ({"ok": False, "exit_code": 20, "reason": "channel_unavailable"}, True, "error"),
            ({"ok": True, "streak": {"days_to_bonus": 1}}, True, "warn"),
            ({"ok": True, "streak": {"days_to_bonus": 5}}, False, ""),
        ]
        with mock.patch.object(notify, "load_config",
                               lambda path=None: {"enabled": True, "success_notify": False}):
            for out, want_send, want_level in cases:
                with self.subTest(exit_code=out.get("exit_code"), streak=out.get("streak")):
                    send, level, _ = notify.should_notify("run", out)
                    self.assertEqual(send, want_send)
                    if send:
                        self.assertEqual(level, want_level)

    def test_success_notify_opt_in(self) -> None:
        with mock.patch.object(notify, "load_config",
                               lambda path=None: {"enabled": True, "success_notify": True}):
            send, level, _ = notify.should_notify(
                "run", {"ok": True, "streak": {"days_to_bonus": 5}})
        self.assertTrue(send)
        self.assertEqual(level, "info")

    def test_disabled_master_switch(self) -> None:
        with mock.patch.object(notify, "load_config",
                               lambda path=None: {"enabled": False, "channels": []}):
            send, _, _ = notify.should_notify("run", {"ok": False, "exit_code": 30})
        self.assertFalse(send)


class FailureIsolationTest(unittest.TestCase):
    def test_unreachable_webhook_returns_structured_failure(self) -> None:
        """推送失败只能返回结构，不能抛异常（否则签到结果会被通知错误覆盖）。"""
        cfg = {"enabled": True,
               "channels": [{"type": "webhook", "url": "http://127.0.0.1:9/hook"}]}
        with mock.patch.object(notify, "load_config", lambda path=None: cfg):
            res = notify.notify("t", "b", level="info", force=True)
        self.assertIsInstance(res, dict)
        self.assertFalse(res["ok"])


class ConfigPathTest(unittest.TestCase):
    def test_candidates_order(self) -> None:
        cands = notify.config_candidates()
        self.assertTrue(cands)
        self.assertTrue(cands[0].endswith("notify_config.json"))
        # 至少包含标准数据目录的一份
        self.assertTrue(any(H.paths.data_dir() in c for c in cands))

    def test_env_override_wins(self) -> None:
        with mock.patch.dict(os.environ,
                             {"BUDDY_STATION_NOTIFY_CONFIG": "/tmp/custom.json"}):
            self.assertTrue(notify.config_candidates()[0].endswith("custom.json"))

    def test_missing_config_is_empty_dict(self) -> None:
        self.assertEqual(notify.load_config("/nonexistent/x.json"), {})


if __name__ == "__main__":
    unittest.main()
