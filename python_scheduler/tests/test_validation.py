"""Independent checker tests, including deliberately corrupted plans."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import random
import unittest

from academic_scheduler.engine import schedule
from academic_scheduler.models import parse_request, parse_result, result_to_dict, UnscheduledTask
from academic_scheduler.validation import validate_result


def snapshot():
    return {
        "schema_version": "1", "request_id": "checker", "input_revision": "revision-1",
        "now": "2026-11-13T09:00:00Z", "timezone": "UTC",
        "horizon_end": "2026-11-13T12:00:00Z", "strategy": "edf", "parameters": {},
        "tasks": [{"task_id": "a", "title": "Synthetic task", "estimated_minutes": 70,
                   "remaining_minutes": 70, "importance": 3, "earliest_start": "2026-11-13T09:00:00Z",
                   "deadline": "2026-11-13T12:00:00Z", "splittable": True}],
        "availability": [{"start": "2026-11-13T09:00:00Z", "end": "2026-11-13T12:00:00Z"}],
        "busy_events": [], "locked_blocks": [],
    }


class IndependentValidationTests(unittest.TestCase):
    def setUp(self):
        self.request = parse_request(snapshot())
        self.result = schedule(self.request)

    def assertRejected(self, result, fragment):
        errors = validate_result(self.request, result)
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_valid_round_trip_and_hand_calculated_metrics(self):
        self.assertEqual(validate_result(self.request, self.result), [])
        self.assertEqual(validate_result(self.request, parse_result(result_to_dict(self.result, "UTC"))), [])
        self.assertEqual(self.result.metrics["scheduled_minutes"], 70)
        self.assertEqual(self.result.metrics["available_minutes"], 180)
        self.assertEqual(self.result.metrics["completion_ratio"], 1)
        self.assertAlmostEqual(self.result.metrics["utilization_ratio"], 70 / 180)

    def test_empty_zero_work_and_busy_cover_have_explicit_metrics(self):
        raw = snapshot()
        raw["tasks"] = []
        request = parse_request(raw)
        result = schedule(request)
        self.assertEqual(validate_result(request, result), [])
        self.assertIsNone(result.metrics["completion_ratio"])
        self.assertIsNone(result.metrics["weighted_completion_ratio"])
        self.assertEqual(result.metrics["scheduled_minutes"], 0)
        raw = snapshot()
        raw["tasks"][0]["remaining_minutes"] = 0
        result = schedule(parse_request(raw))
        self.assertEqual((result.blocks, result.unscheduled, result.metrics["eligible_tasks"]), ((), (), 0))
        raw["tasks"][0]["remaining_minutes"] = 70
        raw["busy_events"] = raw["availability"] * 2
        request = parse_request(raw)
        result = schedule(request)
        self.assertEqual(validate_result(request, result), [])
        self.assertIsNone(result.metrics["utilization_ratio"])
        self.assertEqual(result.unscheduled[0].minutes, 70)

    def test_cross_midnight_and_exact_deadline(self):
        raw = snapshot()
        raw.update(now="2026-11-13T23:30:00Z", horizon_end="2026-11-14T01:00:00Z")
        raw["availability"] = [{"start": raw["now"], "end": "2026-11-14T00:40:00Z"}]
        raw["tasks"][0].update(earliest_start=raw["now"], deadline="2026-11-14T00:40:00Z")
        request = parse_request(raw)
        result = schedule(request)
        self.assertEqual(validate_result(request, result), [])
        self.assertEqual(result.blocks[-1].end, request.tasks[0].deadline)

    def test_short_tail_can_backfill_an_earlier_gap(self):
        raw = snapshot()
        raw["tasks"][0].update(estimated_minutes=20, remaining_minutes=20)
        raw["availability"] = [{"start": "2026-11-13T09:00:00Z", "end": "2026-11-13T09:05:00Z"},
                               {"start": "2026-11-13T10:00:00Z", "end": "2026-11-13T10:15:00Z"}]
        request = parse_request(raw)
        result = schedule(request)
        self.assertEqual([b.minutes for b in result.blocks], [5, 15])
        self.assertEqual(validate_result(request, result), [])

    def test_stale_request_revision_and_strategy(self):
        for field in ("request_id", "input_revision", "strategy", "strategy_version"):
            with self.subTest(field=field):
                self.assertRejected(replace(self.result, **{field: "changed"}), field)

    def test_wrong_minutes_unknown_task_source_and_metrics(self):
        first = self.result.blocks[0]
        for change, fragment in (({"minutes": 59}, ".minutes"),
                                 ({"task_id": "missing"}, "unknown task_id"),
                                 ({"source": "importance"}, "source"),
                                 ({"locked_id": "invented"}, "locked_id")):
            with self.subTest(change=change):
                self.assertRejected(replace(self.result, blocks=(replace(first, **change), *self.result.blocks[1:])), fragment)
        for value in (999, True, float("nan")):
            with self.subTest(value=value):
                self.assertRejected(replace(self.result, metrics={**self.result.metrics, "scheduled_minutes": value}), "metrics.scheduled_minutes")
        self.assertRejected(replace(self.result, metrics={**self.result.metrics, "completion_ratio": 10**400}), "metrics.completion_ratio")

    def test_overlap_past_deadline_capacity_and_extra_work(self):
        first = self.result.blocks[0]
        self.assertRejected(replace(self.result, blocks=(first, first)), "overlapping")
        self.assertRejected(replace(self.result, blocks=(*self.result.blocks, replace(first, start=first.start - timedelta(hours=1), end=first.end - timedelta(hours=1)))), "outside planning")
        self.assertRejected(replace(self.result, blocks=(*self.result.blocks, replace(first, start=first.start + timedelta(hours=3), end=first.end + timedelta(hours=3)))), "deadline")
        self.assertRejected(replace(self.result, blocks=(*self.result.blocks, replace(first, start=first.start + timedelta(hours=2), end=first.end + timedelta(hours=2)))), "exceeds remaining")
        raw = snapshot()
        raw["busy_events"] = [{"start": "2026-11-13T09:00:00Z", "end": "2026-11-13T09:15:00Z"}]
        self.assertTrue(any("busy" in e for e in validate_result(parse_request(raw), self.result)))

    def test_unscheduled_missing_wrong_minutes_reason_and_omitted_work(self):
        raw = snapshot()
        raw["availability"] = []
        request = parse_request(raw)
        result = schedule(request)
        for changed in (replace(result, unscheduled=()),
                        replace(result, unscheduled=(UnscheduledTask("a", 69, ("no_available_capacity",)),)),
                        replace(result, unscheduled=(UnscheduledTask("a", 70, ("insufficient_capacity",)),)),
                        replace(result, unscheduled=result.unscheduled * 2)):
            self.assertTrue(validate_result(request, changed))
        # Correct counts alone must not disguise an unfinished task that still fits.
        omitted = replace(self.result, blocks=(), unscheduled=(UnscheduledTask("a", 70, ("insufficient_capacity",)),))
        self.assertRejected(omitted, "still fits")

    def test_changed_missing_and_duplicate_locked_blocks(self):
        raw = snapshot()
        raw["locked_blocks"] = [{"locked_id": "keep", "task_id": "a", "start": "2026-11-13T10:00:00Z", "end": "2026-11-13T10:30:00Z"}]
        request = parse_request(raw)
        result = schedule(request)
        locked = next(b for b in result.blocks if b.source == "locked")
        self.assertEqual(validate_result(request, result), [])
        for blocks in (tuple(b for b in result.blocks if b != locked),
                       (*result.blocks, locked),
                       tuple(replace(b, task_id=None) if b == locked else b for b in result.blocks)):
            self.assertTrue(validate_result(request, replace(result, blocks=blocks)))

    def test_nonsplittable_and_incomplete_short_block_rejected(self):
        raw = snapshot()
        raw["tasks"][0]["splittable"] = False
        self.assertTrue(any("nonsplittable" in e for e in validate_result(parse_request(raw), self.result)))
        first, tail = self.result.blocks
        malformed = (replace(first, end=first.start + timedelta(minutes=10), minutes=10),
                     replace(tail, start=first.start + timedelta(minutes=10), end=first.end, minutes=50))
        self.assertRejected(replace(self.result, blocks=malformed), "short block")

    def test_two_short_blocks_rejected_even_when_total_is_complete(self):
        first, tail = self.result.blocks
        malformed = (replace(tail, start=first.start, end=first.start + timedelta(minutes=5), minutes=5),
                     replace(tail, start=first.start + timedelta(minutes=5), end=first.start + timedelta(minutes=10), minutes=5),
                     replace(first, start=first.start + timedelta(minutes=10), end=first.end + timedelta(minutes=10)))
        self.assertRejected(replace(self.result, blocks=malformed), "short block")

    def test_seeded_synthetic_scenarios_all_strategies(self):
        """Diverse finite snapshots checked without allocator helper reuse."""
        rng = random.Random(71113)
        origin = datetime(2026, 11, 13, 9, tzinfo=timezone.utc)
        def stamp(minutes):
            return (origin + timedelta(minutes=minutes)).isoformat()
        for case in range(160):
            raw = snapshot()
            raw["parameters"] = {"min_block_minutes": rng.choice((1, 5, 15, 30)), "max_block_minutes": 60}
            raw["tasks"] = []
            for number in range(rng.randrange(9)):
                release = rng.randrange(-30, 121)
                deadline = rng.randrange(max(release, 0), 241)
                minutes = rng.randrange(121)
                raw["tasks"].append({"task_id": f"t{number}", "title": "Synthetic",
                                     "estimated_minutes": minutes, "remaining_minutes": minutes,
                                     "importance": rng.randrange(1, 6), "earliest_start": stamp(release),
                                     "deadline": stamp(deadline), "splittable": bool(rng.randrange(2))})
            raw["availability"] = []
            for _ in range(rng.randrange(6)):
                start = rng.randrange(-30, 180)
                raw["availability"].append({"start": stamp(start), "end": stamp(start + rng.randrange(1, 121))})
            raw["busy_events"] = [{"start": stamp(80), "end": stamp(95)}] if case % 3 == 0 else []
            for strategy in ("edf", "importance", "risk"):
                with self.subTest(case=case, strategy=strategy):
                    raw["strategy"] = strategy
                    request = parse_request(raw)
                    result = schedule(request)
                    self.assertEqual(validate_result(request, result), [])
                    self.assertEqual(schedule(request), result)


if __name__ == "__main__":
    unittest.main()
