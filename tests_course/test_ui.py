"""Real Tk widget flows, with all workspace files isolated beneath work/."""

import copy
import json
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from course_demo import scheduler, storage
from course_demo.ui import PlannerApp


def descendants(widget):
    children = widget.winfo_children()
    return children + [item for child in children for item in descendants(child)]


def entries(window):
    return [widget for widget in descendants(window) if widget.winfo_class() == "TEntry"]


def replace(entry, value):
    entry.delete(0, "end")
    entry.insert(0, str(value))


def press(window, label):
    button = next(widget for widget in descendants(window)
                  if widget.winfo_class() == "TButton" and widget.cget("text") == label)
    button.invoke()


class CalendarFlows(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).resolve().parents[1] / "work/course-ui-tests"
        directory.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=directory)
        self.path = Path(self.temporary.name) / "workspace.json"
        self.root = tk.Tk()
        self.errors = patch("course_demo.ui.messagebox.showerror").start()
        self.addCleanup(patch.stopall)
        self.app = PlannerApp(self.root, self.path)
        self.root.update()

    def tearDown(self):
        if self.root.winfo_exists():
            self.root.destroy()
        self.temporary.cleanup()

    def new_task(self, title="Calculus"):
        window = self.app.task_form()
        self.root.update()
        replace(entries(window)[0], title)
        press(window, "Save")
        self.root.update()
        self.assertFalse(window.winfo_exists())
        self.app.task_list.selection_set(str(self.app.data["tasks"][-1]["id"]))
        return self.app.data["tasks"][-1]

    def test_task_crud_progress_and_completion(self):
        task = self.new_task()
        self.assertEqual((task["total"], task["remaining"], task["importance"]), (60, 60, 3))
        window = self.app.edit_task()
        replace(entries(window)[0], "Calculus review")
        press(window, "Save")
        task = self.app.data["tasks"][0]
        self.assertEqual(task["title"], "Calculus review")
        window = self.app.progress_form()
        replace(entries(window)[0], 25)
        press(window, "Save")
        self.assertEqual(task["remaining"], 25)
        with patch("course_demo.ui.messagebox.askyesno", return_value=True):
            self.app.complete_task()
        self.assertEqual(task["remaining"], 0)
        self.assertTrue(self.app.task_list.item("1", "text").startswith("✓"))
        with patch("course_demo.ui.messagebox.askyesno", return_value=True):
            self.app.delete_task()
        self.assertEqual(self.app.data["tasks"], [])
        self.assertTrue(self.app.dirty)
        self.errors.assert_not_called()

    def test_invalid_form_keeps_data_and_dialog(self):
        window = self.app.task_form()
        replace(entries(window)[0], "Bad input")
        replace(entries(window)[1], -1)
        press(window, "Save")
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.app.data["tasks"], [])
        self.errors.assert_called_once()
        window.destroy()

    def test_generation_compare_locks_and_calendar_views(self):
        self.new_task()
        self.app.generate()
        block = self.app.data["plan"][0]
        self.app.selected_block = block
        self.app.toggle_lock()
        self.assertTrue(self.app.data["locks"][0]["locked"])
        locked = copy.deepcopy(self.app.data["locks"])
        self.app.generate()
        self.assertEqual(self.app.data["locks"], locked)
        self.assertIn(locked[0], self.app.data["plan"])
        window = self.app.compare()
        apply_buttons = [widget for widget in descendants(window)
                         if widget.winfo_class() == "TButton" and widget.cget("text") == "Apply"]
        self.assertEqual(len(apply_buttons), 3)
        apply_buttons[2].invoke()
        self.assertEqual(self.app.data["settings"]["strategy"], "risk")
        self.app.selected_block = next(item for item in self.app.data["plan"] if item["locked"])
        self.app.toggle_lock()
        self.assertEqual(self.app.data["locks"], [])
        self.app.set_view("Day")
        self.assertEqual(len(self.app.days()), 1)
        original = self.app.date
        self.app.move(1)
        self.assertEqual((self.app.date - original).days, 1)
        self.app.set_view("Week")
        self.assertEqual(len(self.app.days()), 7)
        self.errors.assert_not_called()

    def test_empty_compare_and_imported_locks_can_unlock(self):
        window = self.app.compare()
        self.assertIsNotNone(window)
        window.destroy()
        self.new_task()
        self.app.generate()
        self.app.selected_block = self.app.data["plan"][0]
        self.app.toggle_lock()
        self.app.data["plan"] = []
        self.app.draw_calendar()
        self.app.selected_block = self.app.data["locks"][0]
        self.app.toggle_lock()
        self.assertFalse(self.app.data["plan"][0]["locked"])
        self.assertEqual(self.app.data["locks"], [])
        self.errors.assert_not_called()

    def test_task_edit_and_progress_preserve_locks(self):
        self.new_task()
        self.app.generate()
        self.app.selected_block = self.app.data["plan"][0]
        self.app.toggle_lock()
        locked = copy.deepcopy(self.app.data["locks"])
        window = self.app.edit_task()
        replace(entries(window)[0], "Renamed while locked")
        press(window, "Save")
        self.assertEqual(self.app.data["locks"], locked)
        self.app.generate()
        self.assertIn(locked[0], self.app.data["plan"])
        task = self.app.data["tasks"][0]
        with self.assertRaisesRegex(ValueError, "remaining"):
            self.app.update_progress(task, 0)
        self.assertEqual(task["remaining"], 60)
        self.assertEqual(self.app.data["locks"], locked)
        window = self.app.edit_task()
        replace(entries(window)[2], scheduler.format_time(locked[0]["start"]))
        press(window, "Save")
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.app.data["locks"], locked)
        window.destroy()
        with patch("course_demo.ui.messagebox.askyesno", return_value=True):
            self.app.complete_task()
        self.assertEqual(self.app.data["locks"], [])
        self.assertEqual(self.app.data["tasks"][0]["remaining"], 0)

    def test_past_blocks_cannot_be_locked_and_unscheduled_details_visible(self):
        task = self.new_task("Outside horizon")
        self.app.generate()
        block = self.app.data["plan"][0]
        with patch("course_demo.ui.scheduler.now_minutes", return_value=block["start"] + 1):
            self.app.selected_block = block
            self.app.toggle_lock()
        self.assertFalse(block["locked"])
        self.assertEqual(self.app.data["locks"], [])
        self.app.data["plan"] = []
        task["start"] = scheduler.now_minutes() + 20 * 1440
        task["deadline"] = task["start"] + 60
        self.app.generate()
        self.assertIn("Outside horizon", self.app.status)
        self.assertIn("60", self.app.status)
        self.assertGreater(len(self.app.status.splitlines()), 1)

    def test_calendar_cell_busy_create_edit_delete(self):
        self.app.canvas.yview_moveto(0)
        self.root.update()
        self.app.calendar_click(SimpleNamespace(x=80, y=100))
        window = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        press(window, "Save")
        self.assertEqual(len(self.app.data["busy"]), 1)
        busy = self.app.data["busy"][0]
        self.assertEqual(busy["end"] - busy["start"], 60)
        box = next(box for box in self.app.hit_boxes if box[4] == "busy")
        self.app.calendar_click(SimpleNamespace(x=int(box[0] + 5), y=int(box[1] + 5)))
        window = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        replace(entries(window)[1], scheduler.format_time(busy["end"] + 30))
        press(window, "Save")
        self.assertEqual(self.app.data["busy"][0]["end"] - busy["start"], 90)
        window = self.app.busy_form(self.app.data["busy"][0])
        with patch("course_demo.ui.messagebox.askyesno", return_value=True):
            press(window, "Delete")
        self.assertEqual(self.app.data["busy"], [])
        self.errors.assert_not_called()

    def test_settings_language_and_save_reload_conflict(self):
        self.new_task()
        window = self.app.settings()
        replace(entries(window)[0], 10)
        replace(entries(window)[1], 30)
        replace(entries(window)[2], 3)
        press(window, "Save")
        self.assertEqual(self.app.data["settings"]["max_block"], 30)
        self.app.set_language("中文")
        self.root.update()
        self.assertEqual(self.app.t("Generate"), "生成计划")
        self.assertTrue(self.app.save())
        self.assertFalse(self.app.dirty)
        original_bytes = self.path.read_bytes()
        self.path.write_bytes(original_bytes + b" ")
        self.app.data["tasks"][0]["title"] = "Changed"
        self.app.changed()
        self.assertFalse(self.app.save())
        self.assertTrue(self.app.dirty)
        self.assertEqual(self.path.read_bytes(), original_bytes + b" ")
        with patch("course_demo.ui.messagebox.askyesnocancel", return_value=False), patch(
                "course_demo.ui.filedialog.askopenfilename", return_value=str(self.path)):
            self.app.open()
        self.assertEqual(self.app.data["tasks"][0]["title"], "Calculus")
        self.assertEqual(self.app.previous_bytes, self.path.read_bytes())
        self.assertFalse(self.app.dirty)

    def test_dirty_close_cancellation_and_save_as_cancel(self):
        self.new_task()
        with patch("course_demo.ui.messagebox.askyesnocancel", return_value=None):
            self.app.close()
        self.assertTrue(self.root.winfo_exists())
        with patch("course_demo.ui.filedialog.asksaveasfilename", return_value=""):
            self.assertFalse(self.app.save_as())
        self.assertTrue(self.app.dirty)
        with patch("course_demo.ui.messagebox.askyesnocancel", return_value=True):
            self.assertTrue(self.app.may_discard())
        self.assertTrue(self.path.exists())
        self.assertFalse(self.app.dirty)

    def test_open_rejects_disk_change_during_load(self):
        self.new_task()
        self.assertTrue(self.app.save())
        before = copy.deepcopy(self.app.data)
        real_load = storage.load

        def changed_load(path):
            data = real_load(path)
            path.write_bytes(path.read_bytes() + b" ")
            return data

        with patch("course_demo.ui.filedialog.askopenfilename", return_value=str(self.path)), patch(
                "course_demo.ui.storage.load", side_effect=changed_load):
            self.app.open()
        self.errors.assert_called_once()
        self.assertEqual(self.app.data, before)
        self.assertNotEqual(self.app.previous_bytes, self.path.read_bytes())

    def test_legacy_import_must_save_new_format_elsewhere(self):
        source = Path(self.temporary.name) / "legacy.json"
        old = {"format": "academic-scheduler-workspace", "version": 1, "request": {
            "schema_version": "1", "tasks": [], "busy_events": [], "locked_blocks": [],
            "availability": [], "now": "2030-01-01T08:00:00+00:00",
            "horizon_end": "2030-01-02T08:00:00+00:00", "strategy": "edf"}}
        source.write_text(json.dumps(old), encoding="utf-8")
        original = source.read_bytes()
        with patch("course_demo.ui.filedialog.askopenfilename", return_value=str(source)):
            self.app.import_legacy()
        self.assertTrue(self.app.dirty)
        self.assertEqual(self.app.import_source, source)
        with patch("course_demo.ui.filedialog.asksaveasfilename", return_value=str(source)):
            self.assertFalse(self.app.save())
        self.assertEqual(source.read_bytes(), original)
        destination = source.with_name("converted.json")
        with patch("course_demo.ui.filedialog.asksaveasfilename", return_value=str(destination)):
            self.assertTrue(self.app.save())
        self.assertEqual(storage.load(destination)["format"], "course-demo-1")
        self.assertEqual(source.read_bytes(), original)
        self.assertIsNone(self.app.import_source)


if __name__ == "__main__":
    unittest.main()
