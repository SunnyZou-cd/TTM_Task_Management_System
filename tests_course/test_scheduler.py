"""固定整数分钟的手算案例；不访问真实任务和笔记。"""

from copy import deepcopy
from datetime import datetime
import unittest

from course_demo.scheduler import new_data, make_plan, validate_data, parse_time, format_time


def task(task_id=1, minutes=65, deadline=120, importance=3, splittable=True):
    return {"id": task_id, "title": "Task " + str(task_id), "total": minutes,
            "remaining": minutes, "importance": importance, "start": 0,
            "deadline": deadline, "splittable": splittable}


class SchedulerTests(unittest.TestCase):
    def test_split_tail_and_input_unchanged(self):
        data = new_data()
        data["tasks"] = [task()]
        before = deepcopy(data)
        result = make_plan(data, now=0)
        self.assertEqual([(b["start"], b["end"]) for b in result["blocks"]], [(0, 60), (60, 65)])
        self.assertEqual(result["metrics"], {"requested": 65, "scheduled": 65,
            "unscheduled": 0, "complete": 1, "tasks": 1, "weighted_ratio": 1})
        self.assertEqual(data, before)

    def test_busy_union_and_minimum_fragment(self):
        data = new_data()
        data["tasks"] = [task(minutes=30, deadline=70)]
        data["busy"] = [{"start": 10, "end": 25}, {"start": 20, "end": 40}]
        result = make_plan(data, now=0)
        self.assertEqual([(b["start"], b["end"]) for b in result["blocks"]], [(40, 70)])

    def test_nonsplittable_needs_contiguous_capacity_but_ignores_max(self):
        data = new_data()
        data["tasks"] = [task(minutes=90, deadline=100, splittable=False)]
        self.assertEqual(make_plan(data, now=0)["blocks"][0]["end"], 90)
        data["busy"] = [{"start": 40, "end": 50}]
        result = make_plan(data, now=0)
        self.assertEqual(result["blocks"], [])
        self.assertEqual(result["unscheduled"][0]["reason"], "insufficient_contiguous_capacity")

    def test_three_strategies_with_hand_calculated_risk(self):
        data = new_data()
        data["tasks"] = [task(1, 60, 120, 1), task(2, 60, 180, 5)]
        first = {}
        for strategy in ("edf", "importance", "risk"):
            data["settings"]["strategy"] = strategy
            first[strategy] = make_plan(data, now=0)["blocks"][0]["task_id"]
        # risk1=(1/3 + 1/5 + 1/2)/3，risk2=(1/4 + 1 + 1/3)/3。
        self.assertEqual(first, {"edf": 1, "importance": 2, "risk": 2})

    def test_risk_is_recomputed_after_every_block(self):
        data = new_data()
        data["tasks"] = [task(1, 120, 180, 3), task(2, 90, 180, 3)]
        data["settings"]["strategy"] = "risk"
        # 首块后1剩60、2剩90，压力排序反转；不重新排序就会得到1、1、2。
        self.assertEqual([b["task_id"] for b in make_plan(data, now=0)["blocks"]], [1, 2, 1])

    def test_locks_count_against_remaining_and_reserve_time(self):
        data = new_data()
        data["tasks"] = [task(minutes=65)]
        data["locks"] = [{"task_id": 1, "start": 30, "end": 60, "locked": True}]
        result = make_plan(data, now=0)
        self.assertEqual(result["metrics"]["scheduled"], 65)
        self.assertEqual(sum(b["end"] - b["start"] for b in result["blocks"]), 65)
        self.assertIn(data["locks"][0], result["blocks"])
        data["plan"] = result["blocks"]
        validate_data(data)
        with self.assertRaisesRegex(ValueError, "past"):
            make_plan(data, now=31)

    def test_horizon_is_now_plus_days(self):
        data = new_data()
        data["tasks"] = [task(minutes=2000, deadline=5000)]
        data["settings"]["days"] = 1
        result = make_plan(data, now=100)
        self.assertEqual(result["metrics"]["scheduled"], 1440)
        self.assertEqual(max(b["end"] for b in result["blocks"]), 1540)

    def test_metrics_only_count_active_work_and_weight_fully_scheduled(self):
        data = new_data()
        data["tasks"] = [task(1, 30, 30, 5), task(2, 30, 30, 1), task(3)]
        data["tasks"][2]["remaining"] = 0
        metrics = make_plan(data, now=0)["metrics"]
        self.assertEqual(metrics["weighted_ratio"], 5 / 6)
        self.assertEqual((metrics["tasks"], metrics["complete"], metrics["unscheduled"]), (2, 1, 30))
        self.assertIsNone(make_plan(new_data(), now=0)["metrics"]["weighted_ratio"])

    def test_invalid_fields_locks_and_plan_conflicts(self):
        base = new_data()
        base["tasks"] = [task()]
        invalid = []
        for key, value in (("id", True), ("remaining", 66), ("importance", 6), ("splittable", 1), ("title", " ")):
            data = deepcopy(base)
            data["tasks"][0][key] = value
            invalid.append(data)
        duplicate = deepcopy(base)
        duplicate["tasks"].append(task())
        invalid.append(duplicate)
        overlap = deepcopy(base)
        overlap["locks"] = [{"task_id": 1, "start": 0, "end": 30, "locked": True},
                            {"task_id": 1, "start": 20, "end": 40, "locked": True}]
        invalid.append(overlap)
        excess = deepcopy(base)
        excess["locks"] = [{"task_id": 1, "start": 0, "end": 66, "locked": True}]
        invalid.append(excess)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_data(data)

    def test_time_roundtrip(self):
        self.assertEqual(format_time(parse_time("2026-11-16 14:25")), "2026-11-16 14:25")
        for text in ("not a date", "2026-02-30 12:00", "2026-11-16 14:25:30"):
            with self.assertRaises(ValueError):
                parse_time(text)

    def test_local_fold_follows_native_timezone(self):
        # 测试机器可以处于任意本机时区；根据本机实际是否回拨决定预期。
        text = "2026-11-01 01:30"
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M")
        candidates = set()
        for fold in (0, 1):
            minute = int(parsed.replace(fold=fold).timestamp() // 60)
            if datetime.fromtimestamp(minute * 60).strftime("%Y-%m-%d %H:%M") == text:
                candidates.add(minute)
        if len(candidates) == 1:
            self.assertEqual(parse_time(text), candidates.pop())
        else:
            with self.assertRaises(ValueError):
                parse_time(text)


if __name__ == "__main__":
    unittest.main()
