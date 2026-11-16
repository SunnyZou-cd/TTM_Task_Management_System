"""Check the actual copied single-file program, outside the source tree."""

from dataclasses import replace
import json
import os
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from academic_scheduler.engine import schedule
from academic_scheduler.models import parse_request, result_to_dict


ROOT = Path(__file__).resolve().parents[2]


class SingleFileTests(unittest.TestCase):
    def setUp(self):
        work = ROOT / "work"
        work.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.script = self.directory / "demo1.py"
        shutil.copyfile(ROOT / "demo1.py", self.script)

    def invoke(self, *args, data=None):
        # -I ignores project paths and user configuration; -S disables all
        # site-packages, including an installed academic_scheduler and tzdata.
        return subprocess.run([sys.executable, "-I", "-S", "-B", str(self.script), *map(str, args)],
                              input=data, capture_output=True, encoding="utf-8",
                              cwd=self.directory, timeout=30)

    def assertSuccess(self, process):
        self.assertEqual((process.returncode, process.stderr), (0, ""), process.stdout)

    def snapshot(self, name):
        raw = json.loads((ROOT / "python_scheduler" / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        raw["timezone"] = "UTC"
        return raw

    def test_copied_file_runs_without_package_assets_or_site_packages(self):
        process = self.invoke("--demo")
        self.assertSuccess(process)
        self.assertIn("演示完成", process.stdout)
        self.assertEqual(process.stdout.count("校验通过"), 9)
        self.assertIn("未排 60 分钟", process.stdout)
        self.assertIn("锁定 keep-draft-session", process.stdout)
        self.assertEqual([path.name for path in self.directory.iterdir()], ["demo1.py"])

    def test_terminal_is_empty_interactive_software_and_does_not_auto_save(self):
        process = self.invoke("--terminal", data="1\n1\n0\n0\n")
        self.assertSuccess(process)
        self.assertIn("1任务管理", process.stdout)
        self.assertIn("暂无任务", process.stdout)
        self.assertNotIn("合成案例演示", process.stdout)
        self.assertEqual([path.name for path in self.directory.iterdir()], ["demo1.py"])

    def run_wrapper(self, source):
        return subprocess.run([sys.executable, "-I", "-S", "-B", "-c", source, str(self.script)],
                              capture_output=True, encoding="utf-8", cwd=self.directory, timeout=30)

    def test_default_and_explicit_gui_open_real_tk_then_close_without_saving(self):
        source = '''
import json, runpy, sys, tkinter as tk
from tkinter import ttk
real_tk = tk.Tk
opened = []
languages = []
def automatic_root(*args, **kwargs):
    root = real_tk(*args, **kwargs)
    opened.append(root)
    def inspect_and_close():
        try:
            def widgets(parent):
                for child in parent.winfo_children():
                    yield child
                    yield from widgets(child)
            notebook = next(w for w in widgets(root) if isinstance(w, ttk.Notebook))
            assert [notebook.tab(tab, "text") for tab in notebook.tabs()] == ["Tasks", "Time", "Plan"]
            selector = next(w for w in widgets(root) if isinstance(w, ttk.Combobox) and tuple(w["values"]) == ("English", "简体中文"))
            selector.set("简体中文")
            selector.event_generate("<<ComboboxSelected>>")
            root.update_idletasks()
            assert [notebook.tab(tab, "text") for tab in notebook.tabs()] == ["任务", "时间", "计划"]
            languages.append(True)
        finally:
            root.destroy()
    root.after(150, inspect_and_close)
    return root
tk.Tk = automatic_root
namespace = runpy.run_path(sys.argv[1], run_name="smoke_target")
codes = [namespace["main"]([]), namespace["main"](["--gui"])]
print(json.dumps({"codes": codes, "windows": len(opened), "languages": languages}))
'''
        process = self.run_wrapper(source)
        self.assertSuccess(process)
        self.assertEqual(json.loads(process.stdout), {"codes": [0, 0], "windows": 2, "languages": [True, True]})
        self.assertEqual([path.name for path in self.directory.iterdir()], ["demo1.py"])

    def test_cli_and_terminal_do_not_import_tkinter(self):
        source = '''
import builtins, io, runpy, sys
original_import = builtins.__import__
def without_tk(name, *args, **kwargs):
    if name.split(".")[0] == "tkinter":
        raise ModuleNotFoundError("Tk intentionally unavailable")
    return original_import(name, *args, **kwargs)
builtins.__import__ = without_tk
namespace = runpy.run_path(sys.argv[1], run_name="headless_target")
assert namespace["main"](["--json"]) == 0
sys.stdin = io.StringIO("0\\n")
assert namespace["main"](["--terminal"]) == 0
'''
        process = self.run_wrapper(source)
        self.assertSuccess(process)
        self.assertIn('"timezone": "UTC"', process.stdout)
        self.assertIn("1任务管理", process.stdout)

    def test_real_personal_workflow_save_restart_progress_and_completion(self):
        archive = self.directory / "personal.json"
        saved_as = self.directory / "saved-as.json"
        answers = [
            "2", "1", "UTC", "2030-01-01 09:00", "2030-01-01 12:00",
            "3", "2030-01-01 09:00", "2030-01-01 12:00",
            "5", "2030-01-01 10:00", "2030-01-01 10:30", "0",
            "1", "2", "用户录入的阅读任务", "90", "90", "5", "2030-01-01 12:00", "2030-01-01 09:00", "y",
            "2", "不可拆任务", "30", "30", "3", "2030-01-01 12:00", "2030-01-01 09:00", "n", "0",
            "3", "2", "15", "60", "4",
            "6", "2", "1", "2", "2", "0",
            "1", "3", "1", "用户修改后的阅读任务", "", "", "", "", "", "", "0",
            "4", "7", "8",
            "1", "5", "2", "15", "0", "4", "8", "10", str(saved_as), "0",
        ]
        process = self.invoke("--terminal", "--data", archive, data="\n".join(answers) + "\n")
        self.assertSuccess(process)
        self.assertNotIn("操作失败", process.stdout)
        document = json.loads(archive.read_text(encoding="utf-8"))
        snapshot, result = document["request"], document["result"]
        self.assertEqual(json.loads(saved_as.read_text(encoding="utf-8")), document)
        self.assertEqual([t["remaining_minutes"] for t in snapshot["tasks"]], [90, 15])
        self.assertEqual(snapshot["tasks"][0]["title"], "用户修改后的阅读任务")
        self.assertEqual(snapshot["strategy"], "importance")
        locks = snapshot["locked_blocks"]
        self.assertEqual(len(locks), 2)
        self.assertEqual({b["locked_id"] for b in result["blocks"] if b["source"] == "locked"}, {b["locked_id"] for b in locks})
        self.assertEqual(result["metrics"]["scheduled_minutes"], 105)
        self.assertTrue(all(datetime.fromisoformat(b["start"]) >= datetime.fromisoformat(snapshot["now"]) for b in result["blocks"]))
        backup = json.loads(Path(str(archive) + ".bak").read_text(encoding="utf-8"))
        self.assertEqual(backup["request"]["tasks"][1]["remaining_minutes"], 30)
        restarted = self.invoke("--terminal", "--data", archive, data="5\n0\n")
        self.assertSuccess(restarted)
        self.assertIn("用户修改后的阅读任务", restarted.stdout)
        self.assertIn("已锁定", restarted.stdout)
        # Completion/deletion are explicit user operations, never inferred
        # from having generated or saved a plan.
        final = self.invoke("--terminal", "--data", archive, data="1\n6\n1\ny\n4\n2\ny\n0\n4\n8\n0\n")
        self.assertSuccess(final)
        self.assertNotIn("操作失败", final.stdout)
        document = json.loads(archive.read_text(encoding="utf-8"))
        self.assertEqual(len(document["request"]["tasks"]), 1)
        self.assertEqual(document["request"]["tasks"][0]["status"], "completed")
        self.assertEqual(document["request"]["locked_blocks"], [])
        self.assertEqual(document["result"]["metrics"]["eligible_tasks"], 0)

    def test_interactive_unsaved_eof_and_corrupt_archive_are_protected(self):
        archive = self.directory / "personal.json"
        answers = ["1", "2", "尚未保存的任务", "30", "30", "3", "2030-01-01 12:00", "2030-01-01 09:00", "y", "0"]
        process = self.invoke("--terminal", "--data", archive, data="\n".join(answers) + "\n")
        self.assertEqual(process.returncode, 1)
        self.assertIn("更改尚未保存", process.stdout)
        self.assertFalse(archive.exists())
        archive.write_bytes(b"broken personal file")
        process = self.invoke("--terminal", "--data", archive, data="0\n")
        self.assertEqual(process.returncode, 1)
        self.assertIn("无法加载存档", process.stdout)
        self.assertEqual(archive.read_bytes(), b"broken personal file")

    def test_json_all_cases_and_strategies_match_modular_implementation(self):
        process = self.invoke("--json")
        self.assertSuccess(process)
        report = json.loads(process.stdout)
        self.assertEqual(report["timezone"], "UTC")
        self.assertEqual([c["name"] for c in report["cases"]], ["feasible", "overloaded", "replan"])
        for case in report["cases"]:
            request = parse_request(self.snapshot(case["name"]))
            self.assertEqual([r["strategy"] for r in case["results"]], ["edf", "importance", "risk"])
            for result in case["results"]:
                expected = schedule(replace(request, strategy=result["strategy"]))
                self.assertEqual(result, result_to_dict(expected, "UTC"))

    def test_filter_and_deterministic_output(self):
        first = self.invoke("--example", "overloaded", "--strategy", "risk", "--json")
        self.assertSuccess(first)
        second = self.invoke("--example", "overloaded", "--strategy", "risk", "--json")
        self.assertSuccess(second)
        self.assertEqual(first.stdout, second.stdout)
        cases = json.loads(first.stdout)["cases"]
        self.assertEqual(len(cases), 1)
        self.assertEqual(len(cases[0]["results"]), 1)
        self.assertEqual(cases[0]["results"][0]["strategy"], "risk")

    def test_custom_json_subcommands_roundtrip_and_tamper_detection(self):
        source = self.directory / "input.json"
        target = self.directory / "result.json"
        source.write_text(json.dumps(self.snapshot("replan")), encoding="utf-8")
        process = self.invoke("schedule", source, "--output", target)
        self.assertSuccess(process)
        self.assertEqual(process.stdout, "")
        checked = self.invoke("validate", source, target)
        self.assertSuccess(checked)
        self.assertEqual(json.loads(checked.stdout), {"valid": True})
        compared = self.invoke("compare", "-", data=source.read_text(encoding="utf-8"))
        self.assertSuccess(compared)
        self.assertEqual(len(json.loads(compared.stdout)["results"]), 3)
        result = json.loads(target.read_text(encoding="utf-8"))
        result["input_revision"] = "stale"
        target.write_text(json.dumps(result), encoding="utf-8")
        checked = self.invoke("validate", source, target)
        self.assertEqual((checked.returncode, checked.stdout), (3, ""))
        self.assertEqual(json.loads(checked.stderr)["error"]["code"], "validation_failed")

    def test_invalid_options_and_input_emit_error_json(self):
        for args, data in ((("--example", "missing"), None),
                           (("--strategy", "missing"), None),
                           (("--gui", "--terminal"), None),
                           (("--gui", "--demo"), None),
                           (("--terminal", "--json"), None),
                           (("schedule", "-"), '{"\\ud800":1}'),
                           (("schedule", "-"), '{"x":1,"x":2}')):
            with self.subTest(args=args, data=data):
                process = self.invoke(*args, data=data)
                self.assertEqual((process.returncode, process.stdout), (2, ""))
                self.assertEqual(json.loads(process.stderr)["error"]["code"], "input_error")

    def test_help_does_not_run_the_demo(self):
        process = self.invoke("--help")
        self.assertSuccess(process)
        self.assertIn("--example", process.stdout)
        self.assertNotIn("演示完成", process.stdout)

    def test_generated_source_is_in_sync(self):
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.run([sys.executable, str(ROOT / "python_scheduler" / "scripts" / "build_single_file.py"), "--check"],
                                 cwd=self.directory, capture_output=True, encoding="utf-8", timeout=30, env=env)
        self.assertSuccess(process)
        self.assertIn("synchronized", process.stdout)


if __name__ == "__main__":
    unittest.main()
