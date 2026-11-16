from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from academic_scheduler.gui import SchedulerGUI
from academic_scheduler.storage import WorkspaceStore
from academic_scheduler.workspace import Workspace


class GUITests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[2] / "work"
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "gui-workspace.json"
        self.root = tk.Tk(); self.root.withdraw()
        self.addCleanup(self._destroy)
        self.app = SchedulerGUI(self.root, WorkspaceStore(self.path), Workspace.new())
        self.root.update()

    def _destroy(self):
        if self.root.winfo_exists(): self.root.destroy()

    def test_real_controls_workflow_and_language(self):
        start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=4)
        fmt = lambda value: value.strftime("%Y-%m-%d %H:%M")
        for key, value in {"title": "我的任务", "estimated_minutes": "60", "remaining_minutes": "60", "importance": "4", "earliest_start": fmt(start), "deadline": fmt(end)}.items(): self.app.task_vars[key].set(value)
        self.app.add_task(); self.root.update()
        self.assertEqual(self.app.task_tree.item("0", "values")[0], "我的任务")
        self.assertIn("Unsaved", self.app.status.cget("text"))
        self.app.task_tree.selection_set("0"); self.root.update()
        self.app.task_vars["title"].set("未提交草稿")
        self.app.window_vars["now"].set(fmt(start)); self.app.window_vars["horizon_end"].set(fmt(end))
        self.app.language.set("简体中文"); self.app.change_language(); self.root.update()
        self.assertEqual(self.app.task_vars["title"].get(), "未提交草稿")
        self.assertEqual(self.app.window_vars["now"].get(), fmt(start))
        self.assertEqual(self.app.task_tree.selection(), ("0",))
        self.assertIn("未保存", self.app.status.cget("text"))
        self.app.language.set("English"); self.app.change_language(); self.root.update()
        self.assertEqual(self.app.task_tree.heading("title", "text"), "Tasks")
        self.assertEqual(self.app.task_tree.item("0", "values")[0], "我的任务")
        self.app.clear_task()
        self.app.set_window()
        self.app.interval_start.set(fmt(start)); self.app.interval_end.set(fmt(end)); self.app.add_interval("availability")
        self.app.generate()
        self.assertEqual(len(self.app.block_tree.get_children()), 1)
        self.app.block_tree.selection_set("0"); self.app.lock_block()
        self.assertEqual(len(self.app.workspace.snapshot["locked_blocks"]), 1)
        self.assertTrue(self.app.save())
        self.assertFalse(self.app.dirty)
        loaded = WorkspaceStore(self.path).load()
        self.assertEqual(loaded.snapshot["tasks"][0]["title"], "我的任务")
        self.assertEqual(len(loaded.snapshot["locked_blocks"]), 1)

    def test_save_conflict_and_close_cancel_preserve_changes(self):
        self.assertTrue(self.app.save())
        self.app._perform(self.app.workspace.set_strategy, "risk")
        with self.path.open("a", encoding="utf-8") as stream: stream.write(" ")
        with patch("academic_scheduler.gui.messagebox.showerror") as error:
            self.assertFalse(self.app.save())
        self.assertIn("changed externally", error.call_args.args[1])
        self.assertTrue(self.app.dirty)
        with patch("academic_scheduler.gui.messagebox.askyesnocancel", return_value=None): self.app.close()
        self.assertTrue(self.root.winfo_exists())
        self.assertEqual(self.app.workspace.snapshot["strategy"], "risk")

    def test_unapplied_form_prevents_silent_close_and_save(self):
        self.app.task_vars["title"].set("Unapplied draft")
        with patch("academic_scheduler.gui.messagebox.askyesno", return_value=False) as confirm:
            self.app.close()
        self.assertTrue(self.root.winfo_exists())
        self.assertTrue(confirm.called)
        with patch("academic_scheduler.gui.messagebox.showerror"):
            self.assertFalse(self.app.save())
        self.assertFalse(self.path.exists())
        self.assertEqual(self.app.task_vars["title"].get(), "Unapplied draft")

    def test_reselect_after_other_edit_keeps_task_draft(self):
        start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(second=0, microsecond=0)
        end = start + timedelta(hours=2)
        self.app._perform(self.app.workspace.add_task, title="Task", estimated_minutes=30, remaining_minutes=30, importance=3, earliest_start=start.isoformat(timespec="minutes"), deadline=end.isoformat(timespec="minutes"), splittable=True)
        self.app.task_tree.selection_set("0"); self.root.update()
        self.app.task_vars["title"].set("Edited draft")
        self.app._perform(self.app.workspace.set_strategy, "risk")
        self.app.task_tree.selection_set("0"); self.root.update()
        self.assertEqual(self.app.task_vars["title"].get(), "Edited draft")

    def test_unlock_uses_last_selected_tree(self):
        start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=3)
        a, b = start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes")
        self.app._perform(self.app.workspace.set_window, a, b, "UTC")
        self.app._perform(self.app.workspace.add_interval, "availability", a, b)
        for name in ("A", "B"):
            self.app._perform(self.app.workspace.add_task, title=name, estimated_minutes=30, remaining_minutes=30, importance=3, earliest_start=a, deadline=b, splittable=True)
        self.app.generate()
        self.app._perform(self.app.workspace.lock_block, 0)
        self.app._perform(self.app.workspace.lock_block, 1)
        locks = self.app.workspace.snapshot["locked_blocks"]
        self.app.lock_tree.selection_set("0"); self.root.update()
        self.app.block_tree.selection_set("1"); self.root.update()
        self.app.unlock()
        self.assertEqual([x["locked_id"] for x in self.app.workspace.snapshot["locked_blocks"]], [locks[0]["locked_id"]])


if __name__ == "__main__": unittest.main()
