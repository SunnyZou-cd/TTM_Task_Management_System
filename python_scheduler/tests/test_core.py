"""Contract boundary and allocation tests; no persistent user data involved."""

import copy
from dataclasses import FrozenInstanceError
import unittest

from academic_scheduler.availability import duration_minutes, free_intervals, merge_intervals, subtract_intervals
from academic_scheduler.engine import schedule
from academic_scheduler.models import InputError, Interval, parse_datetime, parse_request, parse_result, result_to_dict


def stamp(hour, minute=0):
    return f"2026-11-13T{hour:02}:{minute:02}:00Z"


def task(task_id="a", minutes=60, importance=3, deadline=13, splittable=True, earliest=9):
    return {"task_id": task_id, "title": task_id, "estimated_minutes": minutes, "remaining_minutes": minutes, "importance": importance, "deadline": stamp(deadline), "earliest_start": stamp(earliest), "splittable": splittable}


def snapshot(tasks=None, availability=None, **updates):
    raw = {"schema_version": "1", "request_id": "demo", "input_revision": "revision-1", "now": stamp(9), "timezone": "UTC", "horizon_end": stamp(13), "tasks": [task()] if tasks is None else tasks, "availability": [{"start": stamp(9), "end": stamp(13)}] if availability is None else availability, "busy_events": [], "locked_blocks": [], "strategy": "edf", "parameters": {}}
    raw.update(updates)
    return raw


def lock(start, end, task_id="a", locked_id="lock"):
    return {"locked_id": locked_id, "task_id": task_id, "start": start, "end": end}


class ModelTests(unittest.TestCase):
    def test_immutable_and_roundtrip(self):
        request = parse_request(snapshot())
        with self.assertRaises(FrozenInstanceError):
            request.now = request.horizon_end
        result = schedule(request)
        self.assertEqual(parse_result(result_to_dict(result, request.timezone)), result)

    def test_strict_types_fields_and_paths(self):
        cases = []
        for field, value in (("tasks", ()), ("availability", {}), ("strategy", " edf"), ("schema_version", 1), ("timezone", "Invalid/Zone")):
            raw = snapshot()
            raw[field] = value
            cases.append(raw)
        for field, value in (("estimated_minutes", True), ("remaining_minutes", -1), ("importance", False), ("importance", 6), ("splittable", 1), ("title", " "), ("title", "\ud800"), ("extra", 1)):
            raw = snapshot()
            raw["tasks"][0][field] = value
            cases.append(raw)
        raw = snapshot()
        raw["extra"] = 1
        cases.append(raw)
        raw = snapshot(parameters={"risk_weight": 1})
        cases.append(raw)
        raw = snapshot(parameters={"min_block_minutes": 61, "max_block_minutes": 60})
        cases.append(raw)
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaisesRegex(InputError, r"\$"):
                parse_request(raw)

    def test_missing_duplicate_and_status(self):
        raw = snapshot()
        del raw["input_revision"]
        with self.assertRaisesRegex(InputError, "input_revision"):
            parse_request(raw)
        with self.assertRaisesRegex(InputError, "unique"):
            parse_request(snapshot(tasks=[task(), task()]))
        for status in ("completed", "deleted"):
            raw = snapshot()
            raw["tasks"][0]["status"] = status
            with self.assertRaisesRegex(InputError, "remaining_minutes"):
                parse_request(raw)
            raw["tasks"][0]["remaining_minutes"] = 0
            self.assertFalse(schedule(parse_request(raw)).blocks)

    def test_time_format_and_utc(self):
        self.assertEqual(parse_datetime("2026-11-13T09:00-06:00", "time"), parse_datetime("2026-11-13T15:00:00Z", "time"))
        for value in ("2026-11-13T09:00", "2026-11-13T09:00:01Z", "2026-11-13T09:00:00.000Z", "2026-11-13T09:00+00:60", "2026-11-13T09:00+24:00", "2026-02-30T09:00Z"):
            with self.subTest(value=value), self.assertRaises(InputError):
                parse_datetime(value, "time")

    def test_dst_actual_elapsed_time_and_display(self):
        fall_start = parse_datetime("2026-11-01T01:30-05:00", "start")
        fall_end = parse_datetime("2026-11-01T01:30-06:00", "end")
        self.assertEqual(duration_minutes(fall_start, fall_end), 60)
        self.assertEqual(duration_minutes(parse_datetime("2026-03-08T01:30-06:00", "start"), parse_datetime("2026-03-08T03:30-05:00", "end")), 60)
        raw = snapshot(now="2026-11-01T01:30-05:00", horizon_end="2026-11-01T01:30-06:00", timezone="America/Chicago", availability=[{"start": "2026-11-01T01:30-05:00", "end": "2026-11-01T01:30-06:00"}])
        raw["tasks"][0].update(earliest_start=raw["now"], deadline=raw["horizon_end"])
        output = result_to_dict(schedule(parse_request(raw)), "America/Chicago")
        self.assertEqual(output["blocks"][0]["start"], "2026-11-01T01:30:00-05:00")
        self.assertEqual(output["blocks"][0]["end"], "2026-11-01T01:30:00-06:00")

    def test_unsupported_historical_seconds_offset_and_display_overflow(self):
        raw = snapshot(tasks=[], now="1900-01-01T00:00Z", horizon_end="1900-01-02T00:00Z", timezone="Europe/Paris", availability=[])
        with self.assertRaisesRegex(InputError, "historical seconds offset"):
            parse_request(raw)
        raw = snapshot(tasks=[], now="0001-01-01T00:00Z", horizon_end="0001-01-02T00:00Z", timezone="America/Chicago", availability=[])
        with self.assertRaisesRegex(InputError, "supported datetime range"):
            parse_request(raw)

    def test_lock_validation(self):
        cases = [
            [lock(stamp(8), stamp(9))],
            [lock(stamp(12), stamp(14))],
            [lock(stamp(9), stamp(10), task_id="unknown")],
            [lock(stamp(9), stamp(10)), lock(stamp(10), stamp(11))],
            [lock(stamp(9), stamp(10)), lock(stamp(9), stamp(10), task_id=None, locked_id="other")],
            [lock(stamp(9), stamp(10, 1))],
        ]
        for locks in cases:
            with self.subTest(locks=locks), self.assertRaises(InputError):
                parse_request(snapshot(locked_blocks=locks))
        with self.assertRaisesRegex(InputError, "busy"):
            parse_request(snapshot(locked_blocks=[lock(stamp(9), stamp(10))], busy_events=[{"start": stamp(9, 30), "end": stamp(10, 30)}]))
        with self.assertRaisesRegex(InputError, "covered"):
            parse_request(snapshot(locked_blocks=[lock(stamp(9), stamp(10))], availability=[{"start": stamp(9, 1), "end": stamp(13)}]))
        raw = snapshot(tasks=[task(earliest=10)], locked_blocks=[lock(stamp(9), stamp(10))])
        with self.assertRaisesRegex(InputError, "earliest_start"):
            parse_request(raw)

    def test_unsplittable_locks_must_cover_all(self):
        raw = snapshot(tasks=[task(splittable=False)], locked_blocks=[lock(stamp(10), stamp(10, 30))])
        with self.assertRaisesRegex(InputError, "unsplittable"):
            parse_request(raw)
        raw["locked_blocks"] = [lock(stamp(10), stamp(10, 30)), lock(stamp(10, 30), stamp(11), locked_id="other")]
        with self.assertRaisesRegex(InputError, "one lock"):
            parse_request(raw)
        raw["locked_blocks"] = [lock(stamp(10), stamp(11))]
        self.assertEqual(len(schedule(parse_request(raw)).blocks), 1)

    def test_result_schema_rejects_extra_and_wrong_types(self):
        output = result_to_dict(schedule(parse_request(snapshot())), "UTC")
        for field, value in (("blocks", ()), ("metrics", [])):
            raw = copy.deepcopy(output)
            raw[field] = value
            with self.assertRaises(InputError):
                parse_result(raw)
        for field, value in (("minutes", True), ("minutes", 0), ("unknown", 1)):
            raw = copy.deepcopy(output)
            raw["blocks"][0][field] = value
            with self.assertRaises(InputError):
                parse_result(raw)


class IntervalTests(unittest.TestCase):
    def interval(self, start, end):
        return Interval(parse_datetime(start, "start"), parse_datetime(end, "end"))

    def test_merge_overlap_and_adjacency(self):
        intervals = [self.interval(stamp(10), stamp(11)), self.interval(stamp(9), stamp(10)), self.interval(stamp(9, 30), stamp(10, 30))]
        self.assertEqual(merge_intervals(intervals), (self.interval(stamp(9), stamp(11)),))

    def test_subtract_merged_exclusions_across_gaps(self):
        available = [self.interval(stamp(9), stamp(10)), self.interval(stamp(11), stamp(13))]
        excluded = [self.interval(stamp(9, 30), stamp(11, 30)), self.interval(stamp(12), stamp(12, 30)), self.interval(stamp(12, 15), stamp(14))]
        self.assertEqual(subtract_intervals(available, excluded), (self.interval(stamp(9), stamp(9, 30)), self.interval(stamp(11, 30), stamp(12))))

    def test_free_clips_and_deducts_all_locks(self):
        raw = snapshot(availability=[{"start": stamp(8), "end": stamp(14)}], busy_events=[{"start": stamp(9), "end": stamp(10)}], locked_blocks=[lock(stamp(10), stamp(11), task_id=None)])
        self.assertEqual(free_intervals(parse_request(raw)), (self.interval(stamp(11), stamp(13)),))


class EngineTests(unittest.TestCase):
    def test_edf_and_importance_order(self):
        raw = snapshot(tasks=[task("later", importance=5), task("earlier", deadline=12)], availability=[{"start": stamp(9), "end": stamp(10)}])
        self.assertEqual(schedule(parse_request(raw)).blocks[0].task_id, "earlier")
        raw["strategy"] = "importance"
        self.assertEqual(schedule(parse_request(raw)).blocks[0].task_id, "later")

    def test_tie_break_and_determinism(self):
        raw = snapshot(tasks=[task("z"), task("a")])
        for strategy in ("edf", "importance", "risk"):
            raw["strategy"] = strategy
            first = schedule(parse_request(raw))
            self.assertEqual(first, schedule(parse_request(raw)))
            self.assertEqual(first.blocks[0].task_id, "a")

    def test_risk_updates_remaining_and_capacity_each_block(self):
        raw = snapshot(tasks=[task("a", 120, 5), task("b", 90, 5)], strategy="risk")
        result = schedule(parse_request(raw))
        self.assertEqual([block.task_id for block in result.blocks], ["a", "b", "a", "b"])
        self.assertEqual([block.minutes for block in result.blocks], [60, 60, 60, 30])

    def test_skip_unassignable_candidate_and_preserve_unsplittable(self):
        raw = snapshot(tasks=[task("a", 100, deadline=11, splittable=False), task("b", 30)], busy_events=[{"start": stamp(10), "end": stamp(10, 30)}])
        result = schedule(parse_request(raw))
        self.assertEqual([block.task_id for block in result.blocks], ["b"])
        self.assertEqual(result.unscheduled[0].reasons, ("insufficient_contiguous_capacity",))
        raw = snapshot(tasks=[task(minutes=100, splittable=False)], parameters={"max_block_minutes": 30})
        self.assertEqual([block.minutes for block in schedule(parse_request(raw)).blocks], [100])

    def test_split_min_max_and_final_tail(self):
        raw = snapshot(tasks=[task(minutes=70)], parameters={"min_block_minutes": 15, "max_block_minutes": 30})
        result = schedule(parse_request(raw))
        self.assertEqual([block.minutes for block in result.blocks], [30, 30, 10])
        self.assertFalse(result.unscheduled)

    def test_final_allocation_tail_may_backfill_earlier_fragment(self):
        raw = snapshot(tasks=[task(minutes=20)], availability=[{"start": stamp(9), "end": stamp(9, 5)}, {"start": stamp(11), "end": stamp(11, 15)}])
        result = schedule(parse_request(raw))
        self.assertEqual([block.minutes for block in result.blocks], [5, 15])
        self.assertFalse(result.unscheduled)

    def test_locks_count_once_and_allow_early_short_final_auto_block(self):
        raw = snapshot(tasks=[task(minutes=50)], locked_blocks=[lock(stamp(11), stamp(11, 40))])
        result = schedule(parse_request(raw))
        self.assertEqual([(block.source, block.minutes) for block in result.blocks], [("edf", 10), ("locked", 40)])
        self.assertFalse(result.unscheduled)
        self.assertEqual(result.metrics["scheduled_minutes"], 50)

    def test_reserved_locks_consume_capacity_without_completion(self):
        raw = snapshot(tasks=[task(minutes=240)], locked_blocks=[lock(stamp(10), stamp(11), task_id=None)])
        result = schedule(parse_request(raw))
        self.assertEqual(sum(block.minutes for block in result.blocks), 240)
        self.assertEqual(result.unscheduled[0].minutes, 60)
        self.assertEqual(result.metrics["reserved_minutes"], 60)

    def test_unscheduled_reason_precedence(self):
        cases = [
            (snapshot(tasks=[task(deadline=9)]), "deadline_passed"),
            (snapshot(tasks=[task(deadline=14, earliest=13)]), "outside_window"),
            (snapshot(availability=[]), "no_available_capacity"),
            (snapshot(tasks=[task(minutes=60, splittable=False)], availability=[{"start": stamp(9), "end": stamp(9, 30)}]), "insufficient_contiguous_capacity"),
            (snapshot(availability=[{"start": stamp(9), "end": stamp(9, 10)}]), "below_min_block"),
            (snapshot(tasks=[task(minutes=10)], availability=[{"start": stamp(9), "end": stamp(9, 5)}]), "insufficient_capacity"),
        ]
        for raw, reason in cases:
            with self.subTest(reason=reason):
                result = schedule(parse_request(raw))
                self.assertEqual(result.unscheduled[0].reasons, (reason,))

    def test_earliest_deadline_horizon_and_short_fragment_skip(self):
        raw = snapshot(tasks=[task(minutes=20, earliest=10, deadline=12)], availability=[{"start": stamp(9), "end": stamp(10, 5)}, {"start": stamp(11), "end": stamp(13)}])
        result = schedule(parse_request(raw))
        self.assertEqual(result.blocks[0].start, parse_datetime(stamp(11), "start"))
        self.assertEqual(result.blocks[0].minutes, 20)


if __name__ == "__main__":
    unittest.main()
