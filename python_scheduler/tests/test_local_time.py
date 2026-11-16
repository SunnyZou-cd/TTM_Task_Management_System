"""System-clock rules and opt-in GUI migration, using only synthetic files."""

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from academic_scheduler.gui import _local_input, _local_text
from academic_scheduler.models import InputError, parse_datetime, parse_request, parse_result, resolve_timezone
from academic_scheduler.storage import StorageError, WorkspaceStore
from academic_scheduler.terminal import _time
from academic_scheduler.workspace import Workspace


def chicago_system():
    """Model OS wall/UTC conversion without changing the machine's timezone."""
    zone = ZoneInfo("America/Chicago")
    stack = ExitStack()
    stack.enter_context(patch("academic_scheduler.models._system_localize", side_effect=lambda value: value.replace(tzinfo=zone)))
    stack.enter_context(patch("academic_scheduler.models._system_fromutc", side_effect=lambda value: value.replace(tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)))
    return stack


class LocalTimeTests(unittest.TestCase):
    def test_system_zone_matches_native_conversion_for_each_date(self):
        local = resolve_timezone("local")
        for month in (1, 3, 7, 11):
            for hour in (0, 6, 7, 8, 12, 23):
                value = datetime(2027, month, 7, hour, tzinfo=timezone.utc)
                expected = value.astimezone()
                actual = value.astimezone(local)
                self.assertEqual(actual.replace(tzinfo=None), expected.replace(tzinfo=None))
                self.assertEqual(actual.utcoffset(), expected.utcoffset())
                self.assertEqual(actual.astimezone(timezone.utc), value)

    def test_local_is_independent_of_zoneinfo_package(self):
        with patch("academic_scheduler.models.ZoneInfo", side_effect=ZoneInfoNotFoundError("missing")):
            request = Workspace.new(datetime(2030, 1, 1, tzinfo=timezone.utc)).snapshot
            self.assertEqual(parse_request(request).timezone, "local")

    def test_rules_change_by_date_and_preserve_both_fold_instants(self):
        with chicago_system():
            zone = resolve_timezone("local")
            january = datetime(2027, 1, 1, 12, tzinfo=timezone.utc).astimezone(zone)
            july = datetime(2027, 7, 1, 12, tzinfo=timezone.utc).astimezone(zone)
            self.assertEqual(january.utcoffset(), timedelta(hours=-6))
            self.assertEqual(july.utcoffset(), timedelta(hours=-5))
            for hour, fold in ((6, 0), (7, 1)):
                value = datetime(2027, 11, 7, hour, 30, tzinfo=timezone.utc)
                wall = value.astimezone(zone)
                self.assertEqual((wall.hour, wall.minute, wall.fold), (1, 30, fold))
                self.assertEqual(wall.astimezone(timezone.utc), value)
            for value in ("2027-03-14 02:30", "2027-11-07 01:30"):
                with self.assertRaises(ValueError):
                    _time(value, "local")
            self.assertEqual(_time("2027-07-01 09:00", "local"), "2027-07-01T09:00-05:00")
            # Unchanged existing fold times remain editable without moving them.
            self.assertEqual(_local_text("2027-11-07T07:30Z"), "2027-11-07 01:30")
            self.assertEqual(_local_input("2027-11-07 01:30", "2027-11-07T07:30Z"), "2027-11-07T07:30Z")

    def test_native_date_range_error_has_input_error_boundary(self):
        request = Workspace.new(datetime(2030, 1, 1, tzinfo=timezone.utc)).snapshot
        with patch("academic_scheduler.models._system_fromutc", side_effect=OSError("out of range")):
            with self.assertRaisesRegex(InputError, "display timezone"):
                parse_request(request)

    def test_legacy_load_only_migrates_memory_and_preserves_plan_and_locks(self):
        now = datetime(2030, 1, 1, 9, tzinfo=timezone.utc)
        workspace = Workspace.new(now)
        a, b = now.isoformat(), (now + timedelta(hours=4)).isoformat()
        workspace.set_window(a, b, "America/Chicago")
        workspace.add_interval("availability", a, b)
        workspace.add_interval("busy_events", a, (now + timedelta(minutes=30)).isoformat())
        workspace.add_task(title="Synthetic", estimated_minutes=60, remaining_minutes=60, importance=3, earliest_start=a, deadline=b, splittable=True)
        workspace.generate(now=now)
        workspace.lock_block(0, now=now)
        original = workspace.to_document()
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / "work") as directory, chicago_system():
            path = Path(directory) / "legacy.json"
            content = json.dumps(original).encode()
            path.write_bytes(content)
            store = WorkspaceStore(path)
            with patch("academic_scheduler.models.ZoneInfo", side_effect=ZoneInfoNotFoundError("missing")):
                loaded = store.load(local_time=True)
                with self.assertRaises(StorageError):
                    WorkspaceStore(path).load()
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            expected = {**original["request"], "timezone":"local"}
            self.assertEqual(loaded.snapshot, expected)
            self.assertEqual(parse_result(loaded.result), parse_result(original["result"]))
            self.assertEqual(loaded.result["blocks"][0]["start"], "2030-01-01T03:30:00-06:00")
            self.assertEqual(_local_text(loaded.snapshot["tasks"][0]["earliest_start"]), "2030-01-01 03:00")
            store.save(loaded)
            self.assertEqual(Path(str(path)+".bak").read_bytes(), content)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["request"]["timezone"], "local")
            self.assertEqual(parse_datetime(saved["request"]["now"], "now"), now)


if __name__ == "__main__":
    unittest.main()
