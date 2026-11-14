"""Contract checks for the three synthetic CLI walkthrough inputs."""

import json
from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from academic_scheduler.engine import schedule  # noqa: E402
from academic_scheduler.models import parse_request  # noqa: E402
from academic_scheduler.validation import validate_result  # noqa: E402


EXAMPLES = PACKAGE_ROOT / "examples"


def load_scheduled(name: str):
    raw = json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))
    request = parse_request(raw)
    result = schedule(request)
    assert validate_result(request, result) == []
    return request, result


class ExampleAcceptanceTests(unittest.TestCase):
    def test_feasible_example_schedules_every_active_task(self):
        _, result = load_scheduled("feasible")

        self.assertEqual(result.unscheduled, ())
        self.assertEqual(result.metrics["eligible_tasks"], 2)
        self.assertEqual(result.metrics["fully_scheduled_tasks"], 2)
        self.assertEqual(result.metrics["unscheduled_minutes"], 0)

    def test_overloaded_example_exposes_capacity_gap(self):
        _, result = load_scheduled("overloaded")

        self.assertTrue(result.unscheduled)
        self.assertGreater(result.metrics["unscheduled_minutes"], 0)
        self.assertEqual(result.metrics["requested_minutes"], 180)
        self.assertEqual(result.metrics["available_minutes"], 120)

    def test_replan_keeps_locks_and_never_schedules_before_now(self):
        request, result = load_scheduled("replan")

        locked = {block.locked_id: block for block in result.blocks if block.source == "locked"}
        self.assertEqual(set(locked), {"keep-draft-session", "reserved-appointment"})
        self.assertEqual(locked["keep-draft-session"].task_id, "write-draft")
        self.assertEqual(locked["keep-draft-session"].minutes, 30)
        self.assertIsNone(locked["reserved-appointment"].task_id)
        self.assertEqual(locked["reserved-appointment"].minutes, 30)
        self.assertEqual(result.metrics["reserved_minutes"], 30)
        self.assertTrue(all(block.start >= request.now for block in result.blocks))


if __name__ == "__main__":
    unittest.main()
