"""Check the actual copied single-file program, outside the source tree."""

from dataclasses import replace
import json
import os
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
        process = self.invoke()
        self.assertSuccess(process)
        self.assertIn("演示完成", process.stdout)
        self.assertEqual(process.stdout.count("校验通过"), 9)
        self.assertIn("未排 60 分钟", process.stdout)
        self.assertIn("锁定 keep-draft-session", process.stdout)
        self.assertEqual([path.name for path in self.directory.iterdir()], ["demo1.py"])

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
