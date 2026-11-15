"""Persistent-state safety tests operate exclusively below the project's work/."""

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from academic_scheduler.storage import StorageError, WorkspaceStore
from academic_scheduler.workspace import Workspace


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2030, 1, 1, 9, tzinfo=timezone.utc)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="scheduler-storage-", dir=ROOT / "work")
        self.root = Path(self.directory.name)
        self.path = self.root / "nested" / "workspace.json"
        self.workspace = Workspace.new(NOW)
        self.store = WorkspaceStore(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_create_save_reload_and_backup_exact_previous_bytes(self):
        self.store.save(self.workspace)
        self.assertIsInstance(self.store.path, Path)
        original = self.path.read_bytes()
        self.assertFalse(Path(str(self.path) + ".bak").exists())
        self.workspace.set_strategy("risk")
        self.store.save(self.workspace)
        self.assertEqual(Path(str(self.path) + ".bak").read_bytes(), original)
        loaded = WorkspaceStore(self.path).load()
        self.assertEqual(loaded.to_document(), self.workspace.to_document())
        self.assertFalse(Path(str(self.path) + ".lock").exists())
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_unloaded_store_never_overwrites_existing_file(self):
        self.store.save(self.workspace)
        original = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "尚未加载"):
            WorkspaceStore(self.path).save(self.workspace)
        self.assertEqual(self.path.read_bytes(), original)

    def test_stale_writer_and_external_deletion_rejected(self):
        self.store.save(self.workspace)
        second = WorkspaceStore(self.path)
        second_workspace = second.load()
        self.workspace.set_strategy("risk")
        self.store.save(self.workspace)
        saved = self.path.read_bytes()
        second_workspace.set_strategy("importance")
        before = second_workspace.to_document()
        with self.assertRaisesRegex(StorageError, "其他程序修改"):
            second.save(second_workspace)
        self.assertEqual(second_workspace.to_document(), before)
        self.assertEqual(self.path.read_bytes(), saved)
        self.path.unlink()
        with self.assertRaisesRegex(StorageError, "删除"):
            self.store.save(self.workspace)

    def test_existing_lock_is_never_removed_by_rejected_writer(self):
        self.path.parent.mkdir(parents=True)
        lock = Path(str(self.path) + ".lock")
        lock.write_text("other-owner", encoding="utf-8")
        with self.assertRaisesRegex(StorageError, "锁文件"):
            self.store.save(self.workspace)
        self.assertEqual(lock.read_text(encoding="utf-8"), "other-owner")
        self.assertFalse(self.path.exists())

    def test_corrupt_foreign_or_stale_document_is_not_loaded_or_overwritten(self):
        self.path.parent.mkdir(parents=True)
        good = self.workspace.to_document()
        corrupt = [b"not json", b"\xff", b'{"format":"x","format":"y"}', b'{"number":NaN}', b'{"number":Infinity}', json.dumps(self.workspace.snapshot).encode(), json.dumps({**good, "version": True}).encode()]
        for content in corrupt:
            with self.subTest(content=content):
                self.path.write_bytes(content)
                with self.assertRaises(StorageError):
                    self.store.load()
                with self.assertRaises(StorageError):
                    self.store.save(self.workspace)
                self.assertEqual(self.path.read_bytes(), content)

    def test_utf8_bom_loads_and_invalid_saved_plan_is_rejected(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(self.workspace.to_document()), encoding="utf-8-sig")
        self.assertEqual(self.store.load().to_document(), self.workspace.to_document())
        document = self.workspace.to_document()
        document["result"] = {"request_id": "bad"}
        content = json.dumps(document).encode()
        self.path.write_bytes(content)
        with self.assertRaises(StorageError):
            self.store.load()
        with self.assertRaises(StorageError):
            self.store.save(self.workspace)
        self.assertEqual(self.path.read_bytes(), content)

    def test_replace_failure_cleans_files_preserving_disk_and_memory(self):
        self.store.save(self.workspace)
        original = self.path.read_bytes()
        self.workspace.set_strategy("risk")
        before = self.workspace.to_document()
        from academic_scheduler import storage
        real_replace = storage.os.replace
        def fail_target(source, target):
            if Path(target) == self.path:
                raise OSError("simulated disk failure")
            return real_replace(source, target)
        with patch("academic_scheduler.storage.os.replace", side_effect=fail_target):
            with self.assertRaisesRegex(StorageError, "内存数据仍保留"):
                self.store.save(self.workspace)
        self.assertEqual(self.workspace.to_document(), before)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(Path(str(self.path) + ".lock").exists())
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
        self.store.save(self.workspace)

    def test_conflict_during_staging_is_detected(self):
        self.store.save(self.workspace)
        original_temporary = self.store._temporary
        external = b"external modification"
        def changed(parent, filename, content):
            pending = original_temporary(parent, filename, content)
            self.path.write_bytes(external)
            return pending
        with patch.object(self.store, "_temporary", side_effect=changed):
            with self.assertRaisesRegex(StorageError, "其他程序修改"):
                self.store.save(self.workspace)
        self.assertEqual(self.path.read_bytes(), external)
        self.assertFalse(Path(str(self.path) + ".lock").exists())
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
