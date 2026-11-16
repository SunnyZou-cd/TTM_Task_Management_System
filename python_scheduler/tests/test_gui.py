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


    def _button(self, parent, text):
        for child in parent.winfo_children():
            try:
                if child.cget("text") == text: return child
            except tk.TclError: pass
            found = self._button(child, text)
            if found is not None: return found
        return None

    def test_calendar_navigation_is_view_only_and_no_notebook(self):
        from tkinter import ttk
        before = self.app.workspace.to_document()
        self.assertFalse(any(isinstance(child, ttk.Notebook) for child in self.root.winfo_children()))
        self.assertEqual(len(self.app._visible_dates()), 7)
        date = self.app.view_date
        self.app.navigate(1)
        self.assertEqual(self.app.view_date, date + timedelta(days=7))
        self.app.view_mode.set("Day"); self.app.draw_calendar()
        self.assertEqual(len(self.app._visible_dates()), 1)
        self.app.navigate(-1)
        self.assertEqual(self.app.workspace.to_document(), before)
        self.assertFalse(self.app.dirty)

    def test_focused_task_dialog_defaults_and_language_survive(self):
        self.app.task_dialog(); self.root.update()
        dialog = self.app._dialog
        self.assertEqual(self.app.task_vars["importance"].get(), "3")
        self.assertTrue(self.app.splittable.get())
        self.app.task_vars["estimated_minutes"].set("75")
        self.assertEqual(self.app.task_vars["remaining_minutes"].get(), "75")
        self.app.task_vars["title"].set("任务原文 / Original")
        self.app.language.set("简体中文"); self.app.change_language()
        self.app.language.set("English"); self.app.change_language()
        self.assertEqual(self.app.task_vars["title"].get(), "任务原文 / Original")
        self.assertIsNotNone(self._button(dialog, "Advanced options"))
        self._button(dialog, "Save").invoke(); self.root.update()
        self.assertFalse(dialog.winfo_exists())
        task = self.app.workspace.snapshot["tasks"][0]
        self.assertEqual(task["remaining_minutes"], 75)
        self.assertEqual(task["title"], "任务原文 / Original")
        self.assertEqual(self.app.task_tree.heading("title", "text"), "Tasks")

    def test_calendar_busy_create_edit_and_invalid_edit_is_atomic(self):
        start = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(days=2)
        self.app.busy_dialog(start=start); self.root.update()
        self.assertIsNotNone(self._button(self.app._dialog,"Computer time: YYYY-MM-DD HH:MM"))
        self._button(self.app._dialog, "Save").invoke(); self.root.update()
        self.assertEqual(len(self.app.workspace.snapshot["busy_events"]), 1)
        self.app.event_dialog("busy", 0); self.root.update()
        before = self.app.workspace.to_document()
        self.app.interval_end.set((start-timedelta(hours=1)).isoformat(timespec="minutes"))
        with patch("academic_scheduler.gui.messagebox.showerror"):
            self._button(self.app._dialog, "Save").invoke()
        self.assertEqual(self.app.workspace.to_document(), before)
        self.app.interval_end.set((start+timedelta(hours=2)).isoformat(timespec="minutes"))
        self._button(self.app._dialog, "Save").invoke(); self.root.update()
        self.assertEqual(len(self.app.workspace.snapshot["busy_events"]), 1)
        self.assertTrue(any(kind == "busy" for kind,index in self.app._calendar_items.values()))
        self.app.event_dialog("busy",0); self.root.update()
        self._button(self.app._dialog,"Delete").invoke()
        self.assertEqual(self.app.workspace.snapshot["busy_events"], [])

    def test_generate_uses_free_slots_and_focuses_first_block(self):
        start = (datetime.now(timezone.utc)+timedelta(days=8)).replace(hour=10,minute=0,second=0,microsecond=0)
        end = start + timedelta(hours=3)
        a,b = start.isoformat(timespec="minutes"),end.isoformat(timespec="minutes")
        self.app._perform(self.app.workspace.set_window,a,b,"UTC")
        self.app._perform(self.app.workspace.add_task,title="Read",estimated_minutes=60,remaining_minutes=60,importance=3,earliest_start=a,deadline=b,splittable=True)
        self.assertEqual(self.app.workspace.snapshot["availability"], [])
        self.app.generate(); self.root.update()
        self.assertEqual(self.app.workspace.result["metrics"]["scheduled_minutes"],60)
        self.assertEqual(self.app.view_date,start.astimezone().date())
        self.assertTrue(any(kind=="block" for kind,index in self.app._calendar_items.values()))
        self.app.event_dialog("block",0); self.root.update()
        self._button(self.app._dialog,"Lock time").invoke(); self.root.update()
        self.assertEqual(len(self.app.workspace.snapshot["locked_blocks"]),1)
        self.app.event_dialog("block",0); self.root.update()
        self._button(self.app._dialog,"Unlock").invoke()
        self.assertEqual(self.app.workspace.snapshot["locked_blocks"],[])

    def test_settings_invalid_values_leave_workspace_unchanged(self):
        self.app.settings_dialog(); self.root.update()
        before = self.app.workspace.to_document()
        self.app.strategy_var.set("risk"); self.app.min_var.set("-1")
        with patch("academic_scheduler.gui.messagebox.showerror"):
            self._button(self.app._dialog,"Apply settings").invoke()
        self.assertEqual(self.app.workspace.to_document(),before)
        self._button(self.app._dialog,"Cancel").invoke()
        self.assertFalse(self.app._has_drafts())


    def test_settings_unchanged_apply_preserves_plan_and_dirty(self):
        self.app.generate(); self.app.dirty=False
        before=self.app.workspace.to_document()
        self.app.settings_dialog(); self.root.update()
        self._button(self.app._dialog,"Apply settings").invoke()
        self.assertEqual(self.app.workspace.to_document(),before)
        self.assertFalse(self.app.dirty)

    def test_legacy_local_forms_show_wall_time_and_noop_settings_keep_plan(self):
        from test_local_time import chicago_system
        with chicago_system():
            start=datetime(2030,1,1,9,tzinfo=timezone.utc)
            end=start+timedelta(hours=4)
            a,b=start.isoformat(),end.isoformat()
            workspace=Workspace.new(start)
            workspace.set_window(a,b,"UTC")
            workspace.add_task(title="Legacy",estimated_minutes=60,remaining_minutes=60,importance=3,earliest_start=a,deadline=b,splittable=True)
            workspace.add_interval("busy_events",a,(start+timedelta(minutes=30)).isoformat())
            workspace.generate_calendar(now=start)
            self.app.workspace=Workspace.from_document(workspace.to_document(),local_time=True)
            self.app._last_snapshot=None; self.app.refresh(); self.app.dirty=False
            self.assertEqual(set(self.app.window_vars), {"now","horizon_end"})
            self.assertEqual(self.app.window_vars["now"].get(), "2030-01-01 03:00")
            self.assertNotIn("Time zone", self.app.status.cget("text"))
            before=self.app.workspace.to_document()
            self.app.settings_dialog(); self.root.update()
            self.assertIsNone(self._button(self.app._dialog,"IANA time zone"))
            self._button(self.app._dialog,"Apply settings").invoke()
            self.assertEqual(self.app.workspace.to_document(),before)
            self.assertFalse(self.app.dirty)
            self.app.task_tree.selection_set("0"); self.root.update()
            self.app.task_dialog(edit=True); self.root.update()
            self.assertEqual(self.app.task_vars["earliest_start"].get(),"2030-01-01 03:00")
            self.assertEqual(self.app.task_vars["deadline"].get(),"2030-01-01 07:00")
            self._button(self.app._dialog,"Save").invoke(); self.root.update()
            self.assertEqual(self.app.workspace.snapshot["tasks"][0]["earliest_start"], a)
            self.assertEqual(self.app.workspace.snapshot["tasks"][0]["deadline"], b)
            self.app.busy_dialog(index=0); self.root.update()
            self.assertEqual(self.app.interval_start.get(),"2030-01-01 03:00")
            self.assertEqual(self.app.interval_end.get(),"2030-01-01 03:30")
            self._button(self.app._dialog,"Save").invoke(); self.root.update()
            self.assertEqual(self.app.workspace.snapshot["busy_events"],before["request"]["busy_events"])

    def test_calendar_click_rejects_dst_gap_and_fold(self):
        from datetime import date
        from types import SimpleNamespace
        from zoneinfo import ZoneInfo
        chicago=ZoneInfo("America/Chicago")
        gui_zone=patch("academic_scheduler.gui.resolve_timezone", return_value=chicago)
        terminal_zone=patch("academic_scheduler.terminal.resolve_timezone", return_value=chicago)
        gui_zone.start(); terminal_zone.start()
        self.addCleanup(gui_zone.stop); self.addCleanup(terminal_zone.stop)
        self.app._perform(self.app.workspace.set_window,"2027-01-01T00:00-06:00","2028-01-01T00:00-06:00","local")
        self.app.view_mode.set("Day")
        for day,hour in ((date(2027,3,14),2.5),(date(2027,11,7),1.5)):
            self.app.view_date=day; self.app.draw_calendar(); self.root.update()
            gutter,col,pixels,dates=self.app._calendar_geometry
            self.app.canvas.yview_moveto(0)
            event=SimpleNamespace(x=gutter+20,y=hour*pixels-self.app.canvas.canvasy(0))
            with patch("academic_scheduler.gui.messagebox.showerror") as error, patch.object(self.app,"busy_dialog") as busy:
                self.app.calendar_click(event)
            self.assertTrue(error.called)
            self.assertFalse(busy.called)


if __name__ == "__main__": unittest.main()
