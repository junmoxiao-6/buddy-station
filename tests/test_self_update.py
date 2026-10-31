# -*- coding: utf-8 -*-
"""版本检查：解析、版本源白名单、只读承诺。

重点验证两条安全属性：
  1. 只允许白名单域名（防止配置被改成恶意地址）
  2. 检查过程不写任何文件（"只检查不自动覆盖"必须是真的）
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import _helpers as H

su = H.self_update


class ParseVersionTest(unittest.TestCase):
    def test_plain(self) -> None:
        self.assertEqual(su.parse_version("2.0.0"), (2, 0, 0))

    def test_v_prefix(self) -> None:
        self.assertEqual(su.parse_version("v1.2.3"), (1, 2, 3))

    def test_prerelease_suffix_tolerated(self) -> None:
        self.assertEqual(su.parse_version("2.1.0-rc1"), (2, 1, 0))

    def test_invalid(self) -> None:
        self.assertIsNone(su.parse_version("abc"))
        self.assertIsNone(su.parse_version(""))
        self.assertIsNone(su.parse_version(None))


class FeedResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = dict(os.environ)
        for key in ("BUDDY_STATION_UPDATE_FEED", "GITHUB_REPOSITORY"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_default_is_pypi(self) -> None:
        self.assertIn("pypi.org", su.resolve_feed())

    def test_github_repository_env_wins_over_pypi(self) -> None:
        os.environ["GITHUB_REPOSITORY"] = "me/buddy-station"
        self.assertIn("api.github.com/repos/me/buddy-station", su.resolve_feed())

    def test_explicit_feed_has_priority(self) -> None:
        self.assertEqual(su.resolve_feed("https://pypi.org/pypi/x/json"),
                         "https://pypi.org/pypi/x/json")


class TrustBoundaryTest(unittest.TestCase):
    def test_untrusted_host_rejected(self) -> None:
        res = su.check("https://evil.example.com/releases/latest")
        self.assertFalse(res["ok"])
        self.assertIn("不受信任", res["error"])

    def test_http_only_host_also_rejected(self) -> None:
        res = su.check("http://pypi.org.evil.example.com/json")
        self.assertFalse(res["ok"])


class CheckResultTest(unittest.TestCase):
    def test_newer_remote_reported(self) -> None:
        with mock.patch.object(su, "local_version", lambda: "2.0.0"), \
                mock.patch.object(su, "_get_json",
                                  lambda url: (200, {"info": {"version": "2.1.0"}})):
            res = su.check("https://pypi.org/pypi/buddy-station/json")
        self.assertTrue(res["ok"])
        self.assertFalse(res["up_to_date"])
        self.assertIn("pip install", res["how_to_update"])

    def test_same_version_is_up_to_date(self) -> None:
        with mock.patch.object(su, "local_version", lambda: "2.0.0"), \
                mock.patch.object(su, "_get_json",
                                  lambda url: (200, {"info": {"version": "2.0.0"}})):
            res = su.check("https://pypi.org/pypi/buddy-station/json")
        self.assertTrue(res["up_to_date"])

    def test_github_tag_parsed(self) -> None:
        with mock.patch.object(su, "local_version", lambda: "2.0.0"), \
                mock.patch.object(su, "_get_json",
                                  lambda url: (200, {"tag_name": "v2.2.0"})):
            res = su.check("https://api.github.com/repos/me/x/releases/latest")
        self.assertEqual(res["remote"], "v2.2.0")
        self.assertFalse(res["up_to_date"])
        self.assertIn("git pull", res["how_to_update"])

    def test_network_down_never_claims_update(self) -> None:
        with mock.patch.object(su, "local_version", lambda: "2.0.0"), \
                mock.patch.object(su, "_get_json", lambda url: (0, {})):
            res = su.check("https://pypi.org/pypi/buddy-station/json")
        self.assertTrue(res["up_to_date"])
        self.assertIsNone(res["remote"])

    def test_note_states_read_only(self) -> None:
        with mock.patch.object(su, "_get_json", lambda url: (200, {"info": {"version": "2.0.0"}})):
            res = su.check("https://pypi.org/pypi/buddy-station/json")
        self.assertIn("不下载", res["note"])


class NoWriteCapabilityTest(unittest.TestCase):
    """结构性断言：模块不带任何"下载/解压/覆盖"的能力。"""

    def test_no_archive_or_overwrite_imports(self) -> None:
        src = (H.SRC / "buddy_station" / "self_update.py").read_text(encoding="utf-8")
        for banned in ("zipfile", "shutil", "extractall", "os.remove"):
            self.assertNotIn(banned, src, "self_update 不应具备 {}".format(banned))

    def test_no_apply_or_rollback_api(self) -> None:
        self.assertFalse(hasattr(su, "apply"))
        self.assertFalse(hasattr(su, "rollback"))


if __name__ == "__main__":
    unittest.main()
