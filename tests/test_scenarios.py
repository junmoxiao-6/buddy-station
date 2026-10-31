# -*- coding: utf-8 -*-
"""幂等矩阵：签到状态 × 猫猫状态的所有组合。

判据是 ``main()`` 的**退出码**与输出 JSON，不是内部函数返回值——
否则又会出现"函数说 error、main 判成功"这种定时任务最怕的错。

不联网：通道、状态、领取/派遣全部打桩。
"""

from __future__ import annotations

import unittest
from unittest import mock

import _helpers as H

checkin = H.checkin


class _StubChannel:
    """只会返回固定结构的假通道，用来喂 fetch_checkin_status（余额查询）。"""

    def call(self, method, path, body=None, timeout=30):
        return {"data": {"total_credits": 1234, "streak_days": 3}}

    def describe(self) -> str:
        return "stub"


def run_case(*, checkin_result: dict, travel_states: list[dict],
             claim_error: bool = False, depart_error: bool = False):
    """跑一次 ``run``，返回 (退出码, 输出 JSON)。"""

    def _status(_ch):
        return travel_states.pop(0) if len(travel_states) > 1 else travel_states[0]

    class _Ch:
        name = "stub"

        def call(self, method, path, body=None, timeout=30):
            if path == checkin.P_TRAVEL_CLAIM and claim_error:
                raise checkin.BizError(20001, "已被领取")
            if path == checkin.P_TRAVEL_DEPART and depart_error:
                raise checkin.BizError(30001, "派遣被拒")
            return {"data": {"record_id": 99}}

    with mock.patch.object(checkin, "guard_uid", lambda *a, **k: None), \
            mock.patch.object(checkin, "open_channel",
                              lambda *a, **k: (_Ch(), {"selected": "stub"})), \
            mock.patch.object(checkin, "do_checkin", lambda ch: checkin_result), \
            mock.patch.object(checkin, "fetch_travel_status", _status), \
            mock.patch.object(checkin, "append_record", lambda *a, **k: None):
        return H.run_main(["run"])


class IdempotencyMatrixTest(unittest.TestCase):
    def test_not_checked_in_cat_idle(self) -> None:
        code, out = run_case(checkin_result={"result": "ok", "credit": 100, "streak_days": 3},
                             travel_states=[H.travel_state("idle"),
                                            H.travel_state("traveling")])
        self.assertEqual(code, 0)
        self.assertEqual(out["travel"]["result"], "traveling")
        self.assertEqual(out["checkin"]["result"], "ok")

    def test_already_checked_in_cat_idle(self) -> None:
        code, out = run_case(checkin_result={"result": "already", "message": "今天已签到"},
                             travel_states=[H.travel_state("idle"),
                                            H.travel_state("traveling")])
        self.assertEqual(code, 0)
        self.assertEqual(out["travel"]["result"], "traveling")

    def test_already_checked_in_cat_traveling(self) -> None:
        """最常见的日常组合：不能报错，也不能重复派遣。"""
        code, out = run_case(checkin_result={"result": "already", "message": "今天已签到"},
                             travel_states=[H.travel_state("traveling")])
        self.assertEqual(code, 0)
        self.assertEqual(out["checkin"]["result"], "already")
        self.assertEqual(out["travel"]["result"], "traveling")

    def test_cat_arrived_claims_then_dispatches(self) -> None:
        """先领后派：到店必须先把奖励领掉，再派新的。"""
        code, out = run_case(
            checkin_result={"result": "already", "message": "今天已签到"},
            travel_states=[H.travel_state("arrived"), H.travel_state("idle"),
                           H.travel_state("traveling")])
        self.assertEqual(code, 0)
        self.assertEqual(out["travel"]["result"], "traveling")

    def test_claim_rejected_exits_30(self) -> None:
        code, out = run_case(
            checkin_result={"result": "already", "message": "今天已签到"},
            travel_states=[H.travel_state("arrived")], claim_error=True)
        self.assertEqual(code, 30)
        self.assertEqual(out["travel"]["result"], "error")

    def test_daily_limit_is_not_an_error(self) -> None:
        """达到每日上限是服务端规则，不是故障，必须 exit 0。"""
        code, out = run_case(
            checkin_result={"result": "already", "message": "今天已签到"},
            travel_states=[H.travel_state("idle", limit=True)])
        self.assertEqual(code, 0)
        self.assertEqual(out["travel"]["result"], "daily_limit")

    def test_checkin_error_exits_30(self) -> None:
        code, _ = run_case(checkin_result={"result": "error", "code": 500,
                                           "reason": "上游 500"},
                           travel_states=[H.travel_state("traveling")])
        self.assertEqual(code, 30)

    def test_depart_rejected_exits_30(self) -> None:
        code, out = run_case(
            checkin_result={"result": "already", "message": "今天已签到"},
            travel_states=[H.travel_state("idle")], depart_error=True)
        self.assertEqual(code, 30)
        self.assertEqual(out["travel"]["result"], "error")


class StreakReportTest(unittest.TestCase):
    def test_days_to_bonus_cycles_within_week(self) -> None:
        """大奖按 7 天一个周期：刚拿过（streak=7）要再等 7 天，不是 0。"""
        self.assertEqual(checkin._days_to_bonus(0), 7)
        self.assertEqual(checkin._days_to_bonus(1), 6)
        self.assertEqual(checkin._days_to_bonus(6), 1)
        self.assertEqual(checkin._days_to_bonus(7), 7)
        self.assertEqual(checkin._days_to_bonus(9), 5)

    def test_report_shape(self) -> None:
        rep = checkin.streak_report(server_streak=5)
        for key in ("streak", "days_to_bonus"):
            self.assertIn(key, rep)


if __name__ == "__main__":
    unittest.main()
