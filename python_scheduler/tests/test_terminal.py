import contextlib
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from academic_scheduler.terminal import _time, run_terminal
from academic_scheduler.storage import WorkspaceStore
from academic_scheduler.workspace import Workspace


class TerminalTests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[2] / "work"
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "workspace.json"

    def run_session(self, answers):
        stream = io.StringIO("\n".join(answers) + "\n")
        out = io.StringIO()
        with patch("sys.stdin", stream), contextlib.redirect_stdout(out):
            status = run_terminal(self.path)
        return status, out.getvalue()

    def test_full_workflow_and_restart(self):
        start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=4)
        fmt = lambda value: value.strftime("%Y-%m-%d %H:%M")
        answers = [
            "1", "2", "阅读教材", "60", "60", "4", fmt(end), fmt(start), "y", "0",
            "2", "1", "UTC", fmt(start), fmt(end), "3", fmt(start), fmt(end), "0",
            "7", "4", "6", "2", "1", "0",
            "1", "3", "1", "阅读教材第一章", "", "", "", "", "", "", "0",
            "4", "8", "0",
        ]
        status, output = self.run_session(answers)
        self.assertEqual(status, 0, output)
        self.assertNotIn("操作失败", output)
        self.assertIn("比较未更改当前计划", output)
        self.assertTrue(self.path.exists())
        workspace = WorkspaceStore(self.path).load()
        self.assertEqual(workspace.snapshot["tasks"][0]["title"], "阅读教材第一章")
        self.assertEqual(len(workspace.snapshot["locked_blocks"]), 1)
        self.assertIsNotNone(workspace.result)
        status, output = self.run_session(["5", "0"])
        self.assertEqual(status, 0, output)
        self.assertIn("阅读教材第一章", output)
        self.assertIn("已锁定", output)

    def test_dirty_eof_and_corrupt_file_never_overwrite(self):
        status, output = self.run_session(["1", "2", "任务", "30", "30", "3", "2035-01-02 12:00", "2035-01-01 12:00", "y", "0"])
        self.assertEqual(status, 1)
        self.assertIn("更改尚未保存", output)
        self.assertFalse(self.path.exists())
        self.path.write_text("broken", encoding="utf-8")
        status, output = self.run_session([])
        self.assertEqual(status, 1)
        self.assertIn("无法加载存档", output)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken")

    def test_progress_complete_and_save_failure_keeps_dirty(self):
        answers = ["1", "2", "任务", "30", "30", "3", "2035-01-02 12:00", "2035-01-01 12:00", "y",
                   "5", "1", "10", "6", "1", "y", "0", "8", "0", "c", "0", "d"]
        with patch.object(WorkspaceStore, "save", side_effect=ValueError("模拟保存失败")):
            status, output = self.run_session(answers)
        self.assertEqual(status, 0, output)
        self.assertIn("模拟保存失败", output)
        self.assertIn("有未保存更改", output)
        self.assertFalse(self.path.exists())

    def test_conflict_then_save_as_preserves_work_and_does_not_overwrite(self):
        WorkspaceStore(self.path).save(Workspace.new())
        existing = self.path.parent / "existing.json"
        existing.write_text("已有文件", encoding="utf-8")
        destination = self.path.parent / "new.json"
        answers = iter(["1", "2", "冲突后保留", "30", "30", "3", "2035-01-02 12:00", "2035-01-01 12:00", "y", "0",
                        "8", "10", str(existing), "10", str(destination), "0"])
        def answer(prompt):
            value = next(answers)
            if value == "8":
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(" ")
            return value
        out = io.StringIO()
        with patch("builtins.input", side_effect=answer), contextlib.redirect_stdout(out):
            status = run_terminal(self.path)
        self.assertEqual(status, 0, out.getvalue())
        self.assertIn("操作失败", out.getvalue())
        self.assertIn("已另存到", out.getvalue())
        self.assertEqual(existing.read_text(encoding="utf-8"), "已有文件")
        self.assertEqual(WorkspaceStore(destination).load().snapshot["tasks"][0]["title"], "冲突后保留")
        self.assertEqual(WorkspaceStore(self.path).load().snapshot["tasks"], [])

    def test_invalid_task_numbers_report_chinese(self):
        status, output = self.run_session(["1", "2", "任务", "-1", "0", "3", "2035-01-02 12:00", "2035-01-01 12:00", "y",
                                           "2", "任务", "10", "11", "3", "2035-01-02 12:00", "2035-01-01 12:00", "y",
                                           "2", "任务", "10", "10", "6", "2035-01-02 12:00", "2035-01-01 12:00", "y", "0", "0"])
        self.assertEqual(status, 0, output)
        for message in ("不能为负数", "不能大于总工作量", "重要性必须在 1 到 5 之间"):
            self.assertIn(message, output)

    def test_dst_gap_and_fold(self):
        self.assertEqual(_time("2026-01-01 12:30", "UTC"), "2026-01-01T12:30+00:00")
        self.assertEqual(_time("2026-11-01T01:30-05:00", "America/Chicago"), "2026-11-01T01:30-05:00")
        with self.assertRaisesRegex(ValueError, "不存在"):
            _time("2026-03-08 02:30", "America/Chicago")
        with self.assertRaisesRegex(ValueError, "两个"):
            _time("2026-11-01 01:30", "America/Chicago")


if __name__ == "__main__":
    unittest.main()
