"""Workspace lifecycle tests use fixed clocks and synthetic in-memory tasks."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from academic_scheduler.models import InputError, parse_datetime, parse_request, resolve_timezone
from academic_scheduler.workspace import Workspace, WorkspaceError


NOW = datetime(2030, 1, 1, 9, tzinfo=timezone.utc)


def at(minutes):
    return (NOW + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def configured(minutes=150):
    workspace = Workspace.new(NOW)
    workspace.set_window(at(0), at(480), "UTC")
    workspace.add_interval("availability", at(60), at(480))
    task_id = workspace.add_task(title="复习数学", estimated_minutes=minutes, remaining_minutes=minutes, importance=4, deadline=at(480), earliest_start=at(0), splittable=True)
    return workspace, task_id


class WorkspaceTests(unittest.TestCase):
    def test_calendar_schedules_without_manual_availability_and_excludes_busy(self):
        workspace, _ = configured(90)
        workspace.remove_interval("availability", 0)
        workspace.add_interval("busy_events", at(0), at(60))
        result = workspace.generate_calendar(now=NOW)
        self.assertEqual(result["metrics"]["scheduled_minutes"], 90)
        self.assertGreaterEqual(parse_datetime(result["blocks"][0]["start"], "start"), NOW + timedelta(minutes=60))
        self.assertEqual(workspace.snapshot["tasks"][0]["remaining_minutes"], 90)

    def test_calendar_comparison_is_read_only_and_replanning_preserves_locks(self):
        workspace, _ = configured(150)
        workspace.generate_calendar(now=NOW)
        workspace.lock_block(1, now=NOW)
        locked = deepcopy(workspace.snapshot["locked_blocks"])
        before = workspace.to_document()
        self.assertEqual(len(workspace.compare_calendar(now=NOW)), 3)
        self.assertEqual(workspace.to_document(), before)
        result = workspace.generate_calendar(now=NOW)
        self.assertEqual(workspace.snapshot["locked_blocks"], locked)
        self.assertEqual(result["metrics"]["scheduled_minutes"], 150)

    def test_calendar_event_edit_failure_keeps_original_event_and_plan(self):
        workspace, _ = configured()
        workspace.add_interval("busy_events", at(0), at(30))
        workspace.generate_calendar(now=NOW)
        before = workspace.to_document()
        with self.assertRaises(WorkspaceError):
            workspace.update_interval("busy_events", 0, at(60), at(30))
        self.assertEqual(workspace.to_document(), before)
        workspace.update_interval("busy_events", 0, at(30), at(60))
        self.assertIsNone(workspace.result)
        self.assertEqual(workspace.snapshot["busy_events"][0], {"start": at(30), "end": at(60)})

    def test_new_is_empty_and_rounds_up_clock(self):
        workspace = Workspace.new(NOW + timedelta(seconds=1))
        self.assertEqual(parse_datetime(workspace.snapshot["now"], "now"), NOW + timedelta(minutes=1))
        self.assertEqual(parse_datetime(workspace.snapshot["horizon_end"], "end"), NOW + timedelta(minutes=1, days=7))
        self.assertEqual(workspace.snapshot["tasks"], [])
        self.assertEqual(workspace.snapshot["availability"], [])
        self.assertIsNone(workspace.result)
        with self.assertRaises(WorkspaceError):
            Workspace.new(datetime(2030, 1, 1))

    def test_utc_works_when_zoneinfo_data_missing(self):
        with patch("academic_scheduler.models.ZoneInfo", side_effect=ZoneInfoNotFoundError("missing")):
            self.assertIs(resolve_timezone("UTC"), timezone.utc)
            workspace, _ = configured()
            result = workspace.generate(now=NOW)
            self.assertTrue(result["blocks"])
            with self.assertRaisesRegex(InputError, "tzdata"):
                resolve_timezone("America/Chicago")

    def test_properties_and_documents_are_deep_copies(self):
        workspace, _ = configured()
        workspace.generate(now=NOW)
        original = workspace.to_document()
        snapshot = workspace.snapshot
        snapshot["tasks"][0]["title"] = "变更"
        result = workspace.result
        result["blocks"].clear()
        document = workspace.to_document()
        document["request"]["tasks"].clear()
        self.assertEqual(workspace.to_document(), original)
        self.assertEqual(Workspace.from_document(original).to_document(), original)

    def test_document_rejects_wrong_metadata_and_stale_result(self):
        workspace, _ = configured()
        workspace.generate(now=NOW)
        original = workspace.to_document()
        invalid = []
        for field, value in (("format", "wrong"), ("version", True), ("result", []), ("extra", 1)):
            document = deepcopy(original)
            document[field] = value
            invalid.append(document)
        document = deepcopy(original)
        document["request"]["input_revision"] = "changed"
        invalid.append(document)
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(WorkspaceError):
                Workspace.from_document(document)
        with self.assertRaises(WorkspaceError):
            Workspace.from_document(workspace.snapshot)

    def test_document_normalizes_parameter_defaults(self):
        document = Workspace.new(NOW).to_document()
        document["request"]["parameters"] = {}
        self.assertEqual(Workspace.from_document(document).snapshot["parameters"], {"min_block_minutes": 15, "max_block_minutes": 60})

    def test_edits_change_revision_and_invalidate_result_without_completing(self):
        workspace, task_id = configured()
        workspace.generate(now=NOW)
        revision = workspace.snapshot["input_revision"]
        workspace.update_task(task_id, remaining_minutes=100)
        self.assertNotEqual(workspace.snapshot["input_revision"], revision)
        self.assertEqual(workspace.snapshot["tasks"][0]["remaining_minutes"], 100)
        self.assertIsNone(workspace.result)
        with self.assertRaisesRegex(WorkspaceError, "先生成"):
            workspace.lock_block(0, now=NOW)

    def test_invalid_edit_keeps_entire_state(self):
        workspace, task_id = configured()
        workspace.generate(now=NOW)
        before = workspace.to_document()
        actions = [lambda: workspace.update_task(task_id, task_id="replacement"), lambda: workspace.update_task(task_id, title="changed", remaining_minutes=151), lambda: workspace.set_parameters(60, 15), lambda: workspace.set_strategy("unknown"), lambda: workspace.add_interval("busy_events", at(70), at(60)), lambda: workspace.remove_interval("availability", True), lambda: workspace.delete_task("missing")]
        for action in actions:
            with self.assertRaises(WorkspaceError):
                action()
            self.assertEqual(workspace.to_document(), before)

    def test_generate_uses_effective_current_time_without_recording_completion(self):
        workspace, _ = configured()
        result = workspace.generate(now=NOW + timedelta(minutes=75, seconds=1))
        self.assertEqual(parse_datetime(workspace.snapshot["now"], "now"), NOW + timedelta(minutes=76))
        self.assertGreaterEqual(parse_datetime(result["blocks"][0]["start"], "start"), NOW + timedelta(minutes=76))
        self.assertEqual(workspace.snapshot["tasks"][0]["remaining_minutes"], 150)
        workspace.set_window(at(120), at(480), "UTC")
        workspace.generate(now=NOW)
        self.assertEqual(parse_datetime(workspace.snapshot["now"], "now"), NOW + timedelta(minutes=120))

    def test_generate_failure_keeps_request_revision_and_existing_result(self):
        workspace, _ = configured()
        workspace.generate(now=NOW)
        before = workspace.to_document()
        with self.assertRaisesRegex(WorkspaceError, "窗口已经结束"):
            workspace.generate(now=NOW + timedelta(days=1))
        self.assertEqual(workspace.to_document(), before)
        from academic_scheduler.engine import schedule
        invalid = replace(schedule(parse_request(workspace.snapshot)), input_revision="stale")
        with patch("academic_scheduler.workspace.schedule", return_value=invalid):
            with self.assertRaisesRegex(WorkspaceError, "校验失败"):
                workspace.generate(now=NOW)
        self.assertEqual(workspace.to_document(), before)

    def test_compare_preserves_saved_plan_and_strategy(self):
        workspace, _ = configured()
        workspace.set_strategy("importance")
        workspace.generate(now=NOW)
        before = workspace.to_document()
        results = workspace.compare(now=NOW + timedelta(minutes=80))
        self.assertEqual([result["strategy"] for result in results], ["edf", "importance", "risk"])
        self.assertEqual(len({result["input_revision"] for result in results}), 1)
        self.assertEqual(workspace.to_document(), before)

    def test_multiple_locks_preserve_other_blocks_and_replanning(self):
        workspace, _ = configured()
        before_blocks = workspace.generate(now=NOW)["blocks"]
        first = workspace.lock_block(0, now=NOW)
        second = workspace.lock_block(1, now=NOW)
        self.assertNotEqual(first, second)
        result = workspace.result
        self.assertEqual([block["source"] for block in result["blocks"]], ["locked", "locked", "edf"])
        self.assertEqual(result["blocks"][2], before_blocks[2])
        self.assertEqual(result["input_revision"], workspace.snapshot["input_revision"])
        replanned = workspace.generate(now=NOW)
        self.assertEqual({block["locked_id"] for block in replanned["blocks"] if block["source"] == "locked"}, {first, second})
        workspace.unlock(first)
        self.assertIsNone(workspace.result)
        self.assertEqual(len(workspace.snapshot["locked_blocks"]), 1)

    def test_lock_rejection_is_atomic_and_started_locks_require_manual_progress(self):
        workspace, _ = configured()
        workspace.generate(now=NOW)
        before = workspace.to_document()
        for action in (lambda: workspace.lock_block(-1, now=NOW), lambda: workspace.lock_block(True, now=NOW), lambda: workspace.lock_block(0, now=NOW + timedelta(minutes=60))):
            with self.assertRaises(WorkspaceError):
                action()
            self.assertEqual(workspace.to_document(), before)
        workspace.lock_block(0, now=NOW)
        before = workspace.to_document()
        with self.assertRaisesRegex(WorkspaceError, "已经锁定"):
            workspace.lock_block(0, now=NOW)
        with self.assertRaisesRegex(WorkspaceError, "手动核对"):
            workspace.generate(now=NOW + timedelta(minutes=70))
        self.assertEqual(workspace.to_document(), before)
        self.assertEqual(workspace.snapshot["tasks"][0]["remaining_minutes"], 150)

    def test_conflicting_edits_preserve_locks_but_delete_complete_remove_them(self):
        for complete in (False, True):
            workspace, task_id = configured()
            workspace.generate(now=NOW)
            workspace.lock_block(0, now=NOW)
            before = workspace.to_document()
            for action in (lambda: workspace.update_task(task_id, remaining_minutes=1), lambda: workspace.remove_interval("availability", 0), lambda: workspace.add_interval("busy_events", at(60), at(70))):
                with self.assertRaises(WorkspaceError):
                    action()
                self.assertEqual(workspace.to_document(), before)
            if complete:
                workspace.complete_task(task_id)
                self.assertEqual(workspace.snapshot["tasks"][0]["status"], "completed")
                self.assertEqual(workspace.snapshot["tasks"][0]["remaining_minutes"], 0)
            else:
                workspace.delete_task(task_id)
                self.assertEqual(workspace.snapshot["tasks"], [])
            self.assertEqual(workspace.snapshot["locked_blocks"], [])
            self.assertIsNone(workspace.result)


if __name__ == "__main__":
    unittest.main()
