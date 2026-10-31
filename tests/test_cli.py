# -*- coding: utf-8 -*-
"""CLI 外壳：分发、退出码、全局参数。"""

from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import _helpers as H

cli = H.cli


class DispatchTest(unittest.TestCase):
    def test_version(self) -> None:
        code, out = H.capture_cli(["version"])
        self.assertEqual(code, 0)
        self.assertRegex(out.strip(), r"^\d+\.\d+\.\d+$")

    def test_no_args_prints_help(self) -> None:
        code, out = H.capture_cli([])
        self.assertEqual(code, 0)
        self.assertIn("buddy-station", out)
        self.assertIn("退出码", out)

    def test_help_flag(self) -> None:
        code, out = H.capture_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("acquire-rt", out)

    def test_unknown_command_exits_2(self) -> None:
        with redirect_stdout(io.StringIO()):
            with mock.patch("sys.stderr", io.StringIO()):
                code = cli.main(["not-a-command"])
        self.assertEqual(code, 2)

    def test_login_dispatches_to_device_login(self) -> None:
        called = {}

        def _fake(argv):
            called["argv"] = argv
            return 0

        with mock.patch.object(H.device_login, "main", _fake):
            code = cli.main(["login", "status"])
        self.assertEqual(code, 0)
        self.assertEqual(called["argv"], ["status"])

    def test_notify_dispatches(self) -> None:
        called = {}

        def _fake(argv):
            called["argv"] = argv
            return 0

        with mock.patch.object(H.notify, "main", _fake):
            code = cli.main(["notify", "--status"])
        self.assertEqual(code, 0)
        self.assertEqual(called["argv"], ["--status"])

    def test_doctor_aliases_diagnose(self) -> None:
        seen = {}

        def _fake(argv):
            seen["argv"] = argv
            return 0

        with mock.patch.object(H.checkin, "main", _fake):
            code = cli.main(["doctor"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["argv"], ["diagnose"])


class GlobalOptionTest(unittest.TestCase):
    def test_data_dir_sets_env(self) -> None:
        code, _ = H.capture_cli(["version", "--data-dir", "/tmp/bsg-portable"])
        self.assertEqual(code, 0)
        self.assertEqual(os.environ.get("BUDDY_STATION_HOME"),
                         os.path.abspath("/tmp/bsg-portable"))

    def test_data_dir_equals_form(self) -> None:
        code, _ = H.capture_cli(["version", "--data-dir=/tmp/bsg-x"])
        self.assertEqual(code, 0)
        self.assertEqual(os.environ.get("BUDDY_STATION_HOME"),
                         os.path.abspath("/tmp/bsg-x"))


class PathsTest(unittest.TestCase):
    def test_data_dir_honours_env(self) -> None:
        with mock.patch.dict(os.environ, {"BUDDY_STATION_HOME": "/tmp/bsg-paths"}):
            self.assertEqual(H.paths.data_dir(), os.path.abspath("/tmp/bsg-paths"))

    def test_logs_dir_is_under_data_dir(self) -> None:
        with mock.patch.dict(os.environ, {"BUDDY_STATION_HOME": "/tmp/bsg-paths2"}):
            self.assertTrue(H.paths.logs_dir().endswith("logs"))

    def test_version_is_not_placeholder(self) -> None:
        self.assertRegex(H.paths.package_version(), r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
