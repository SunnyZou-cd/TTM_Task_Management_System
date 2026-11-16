"""所有存档都放在 work 内的独立临时目录，绝不访问真实工作区。"""

import json
from pathlib import Path
import tempfile
import unittest

from course_demo.scheduler import new_data
from course_demo.storage import load, save, import_legacy


class StorageTests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[1] / "work" / "course-tests"
        work.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "workspace.json"

    def test_save_reload_backup_and_no_temporary_leftover(self):
        data = new_data()
        first = save(self.path, data)
        self.assertEqual(load(self.path), data)
        data["settings"]["strategy"] = "risk"
        second = save(self.path, data, first)
        self.assertEqual(self.path.read_bytes(), second)
        self.assertEqual(Path(str(self.path) + ".bak").read_bytes(), first)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_external_edit_delete_and_unloaded_overwrite_rejected(self):
        first = save(self.path, new_data())
        with self.assertRaises(ValueError):
            save(self.path, new_data())
        changed = first + b" "
        self.path.write_bytes(changed)
        with self.assertRaises(ValueError):
            save(self.path, new_data(), first)
        self.assertEqual(self.path.read_bytes(), changed)
        self.path.unlink()
        with self.assertRaises(ValueError):
            save(self.path, new_data(), first)

    def test_bom_and_corrupt_or_foreign_documents(self):
        raw = save(self.path, new_data())
        self.path.write_bytes(b"\xef\xbb\xbf" + raw)
        self.assertEqual(load(self.path)["format"], "course-demo-1")
        for raw in (b"{", b"[]", b'{"format":"other"}'):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                load(self.path)

    def legacy(self):
        start, end = "2026-11-16T10:00:00-06:00", "2026-11-16T12:00:00-06:00"
        return {"format": "academic-scheduler-workspace", "version": 1,
            "request": {"schema_version": "1", "now": start, "horizon_end": end,
                "tasks": [{"task_id": "uuid-a", "title": "合成任务", "estimated_minutes": 90,
                    "remaining_minutes": 90, "importance": 5, "earliest_start": start,
                    "deadline": end, "splittable": True}],
                "availability": [{"start": start, "end": end}], "busy_events": [],
                "locked_blocks": [{"locked_id": "a", "task_id": "uuid-a", "start": start,
                    "end": "2026-11-16T10:30:00-06:00"},
                    {"locked_id": "b", "task_id": None, "start": "2026-11-16T11:00:00-06:00", "end": end}],
                "strategy": "edf", "parameters": {}}, "result": {"stale": "ignored"}}

    def test_import_maps_ids_preserves_instants_null_reservations_and_source(self):
        original = json.dumps(self.legacy()).encode()
        self.path.write_bytes(original)
        data = import_legacy(self.path)
        self.assertEqual(data["tasks"][0]["id"], 1)
        self.assertEqual(data["locks"][0]["task_id"], 1)
        self.assertEqual(data["locks"][0]["end"] - data["locks"][0]["start"], 30)
        self.assertEqual(len(data["busy"]), 1)
        self.assertEqual(data["plan"], [])
        self.assertEqual(self.path.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "different path"):
            save(self.path, data, original)
        self.assertEqual(self.path.read_bytes(), original)
        other = self.path.with_name("course.json")
        save(other, data)
        self.assertEqual(load(other), data)

    def test_import_rejects_duplicate_ids_and_converts_availability_complement(self):
        old = self.legacy()
        old["request"]["locked_blocks"] = []
        old["request"]["availability"][0]["end"] = "2026-11-16T11:00:00-06:00"
        self.path.write_text(json.dumps(old), encoding="utf-8")
        data = import_legacy(self.path)
        self.assertEqual(data["busy"][0]["end"] - data["busy"][0]["start"], 60)
        old["request"]["tasks"].append(old["request"]["tasks"][0].copy())
        self.path.write_text(json.dumps(old), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unique"):
            import_legacy(self.path)


if __name__ == "__main__":
    unittest.main()
