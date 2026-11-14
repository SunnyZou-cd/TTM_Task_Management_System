import contextlib
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from academic_scheduler import cli


@dataclass(frozen=True)
class Request:
    request_id: str = "request"
    input_revision: str = "revision"
    strategy: str = "edf"
    timezone: str = "UTC"


class CLITests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[2] / "work"
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.input = self.directory / "input.json"
        self.input.write_text('{}', encoding='utf-8')

    def run_cli(self, *args, stdin=""):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = cli.main(list(args))
        return status, stdout.getvalue(), stderr.getvalue()

    def test_compare_validates_each_strategy(self):
        seen = []
        with patch.object(cli.models, "parse_request", return_value=Request()), \
             patch.object(cli.engine, "schedule", side_effect=lambda req: req.strategy), \
             patch.object(cli.validation, "validate_result", side_effect=lambda req, result: seen.append((req.strategy, result)) or []), \
             patch.object(cli.models, "result_to_dict", side_effect=lambda result, tz: {"strategy": result}):
            status, out, err = self.run_cli("compare", str(self.input))
        self.assertEqual((status, err), (0, ""))
        self.assertEqual(seen, [(x, x) for x in ("edf", "importance", "risk")])
        self.assertEqual(len(json.loads(out)["results"]), 3)

    def test_validation_failure_emits_no_output(self):
        with patch.object(cli.models, "parse_request", return_value=Request()), \
             patch.object(cli.engine, "schedule", return_value=object()), \
             patch.object(cli.validation, "validate_result", return_value=["invalid block"]):
            status, out, err = self.run_cli("schedule", str(self.input))
        self.assertEqual((status, out), (3, ""))
        self.assertEqual(json.loads(err)["error"]["code"], "validation_failed")

    def test_strict_json_and_argument_errors(self):
        for data in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{'):
            status, out, err = self.run_cli("schedule", "-", stdin=data)
            self.assertEqual((status, out), (2, ""))
            self.assertEqual(json.loads(err)["error"]["code"], "input_error")
        status, out, err = self.run_cli("unknown")
        self.assertEqual((status, out), (2, ""))
        self.assertEqual(json.loads(err)["error"]["code"], "input_error")

    def test_atomic_output_and_input_protection(self):
        output = self.directory / "output.json"
        with patch.object(cli.models, "parse_request", return_value=Request()), \
             patch.object(cli.engine, "schedule", return_value=object()), \
             patch.object(cli.validation, "validate_result", return_value=[]), \
             patch.object(cli.models, "result_to_dict", return_value={"ok": True}):
            status, out, err = self.run_cli("schedule", str(self.input), "--output", str(output))
            self.assertEqual((status, out, err), (0, "", ""))
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"ok": True})
            status, out, err = self.run_cli("schedule", str(self.input), "--output", str(self.input))
        self.assertEqual((status, out), (2, ""))
        self.assertEqual(self.input.read_text(encoding="utf-8"), "{}")
        self.assertEqual(json.loads(err)["error"]["code"], "input_error")
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ["input.json", "output.json"])

    def test_validate_uses_result_parser_and_rejects_stdin_result(self):
        result = self.directory / "result.json"
        result.write_text('{}', encoding="utf-8-sig")
        with patch.object(cli.models, "parse_request", return_value=Request()), \
             patch.object(cli.models, "parse_result", return_value="parsed") as parse, \
             patch.object(cli.validation, "validate_result", return_value=[]):
            status, out, err = self.run_cli("validate", str(self.input), str(result))
            self.assertEqual((status, json.loads(out), err), (0, {"valid": True}, ""))
            parse.assert_called_once_with({})
            status, out, err = self.run_cli("validate", str(self.input), "-")
        self.assertEqual((status, out), (2, ""))
        self.assertEqual(json.loads(err)["error"]["code"], "input_error")


class CLIProcessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        work = self.root / "work"
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.example = self.root / "python_scheduler" / "examples" / "feasible.json"

    def invoke(self, *args, stdin=None):
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(self.root / "python_scheduler" / "src"), env.get("PYTHONPATH", "")]))
        return subprocess.run([sys.executable, "-m", "academic_scheduler", *map(str, args)],
                              input=stdin, capture_output=True, encoding="utf-8", env=env)

    def test_end_to_end(self):
        result_file = self.directory / "result.json"
        request = json.loads(self.example.read_text(encoding="utf-8"))
        request["request_id"] = "中文请求"
        data = json.dumps(request, ensure_ascii=False)
        source = self.directory / "bom-input.json"
        source.write_text(data, encoding="utf-8-sig")
        scheduled = self.invoke("schedule", "-", "--output", result_file, stdin="\ufeff" + data)
        self.assertEqual((scheduled.returncode, scheduled.stdout, scheduled.stderr), (0, "", ""))
        result = json.loads(result_file.read_text(encoding="utf-8"))
        self.assertEqual(result["request_id"], "中文请求")
        checked = self.invoke("validate", source, result_file)
        self.assertEqual((checked.returncode, json.loads(checked.stdout), checked.stderr), (0, {"valid": True}, ""))
        compared = self.invoke("compare", source)
        self.assertEqual((compared.returncode, compared.stderr), (0, ""))
        self.assertEqual([r["strategy"] for r in json.loads(compared.stdout)["results"]], ["edf", "importance", "risk"])
        result["metrics"]["scheduled_minutes"] += 1
        result_file.write_text(json.dumps(result), encoding="utf-8")
        checked = self.invoke("validate", source, result_file)
        self.assertEqual((checked.returncode, checked.stdout), (3, ""))
        self.assertEqual(json.loads(checked.stderr)["error"]["code"], "validation_failed")
        # Huge, syntactically valid JSON integers are a validation failure,
        # never an internal float-conversion exception.
        result["metrics"]["scheduled_minutes"] -= 1
        result["metrics"]["completion_ratio"] = 10**400
        result_file.write_text(json.dumps(result), encoding="utf-8")
        checked = self.invoke("validate", source, result_file)
        self.assertEqual((checked.returncode, checked.stdout), (3, ""))
        self.assertEqual(json.loads(checked.stderr)["error"]["code"], "validation_failed")

    def test_invalid_json_and_same_path(self):
        for data in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}',
                     '{"\\ud800":1}', '{"request_id":"\\ud800"}',
                     '{"x":' + '9' * 5000 + '}', '[' * 1100 + ']' * 1100):
            process = self.invoke("schedule", "-", stdin=data)
            self.assertEqual((process.returncode, process.stdout), (2, ""))
            self.assertEqual(json.loads(process.stderr)["error"]["code"], "input_error")
        bad_args = self.invoke("schedule")
        self.assertEqual((bad_args.returncode, bad_args.stdout), (2, ""))
        self.assertEqual(json.loads(bad_args.stderr)["error"]["code"], "input_error")
        source = self.directory / "source.json"
        original = self.example.read_bytes()
        source.write_bytes(original)
        process = self.invoke("schedule", source, "--output", source)
        self.assertEqual((process.returncode, process.stdout), (2, ""))
        self.assertEqual(source.read_bytes(), original)
        link = self.directory / "hardlink.json"
        os.link(source, link)
        process = self.invoke("schedule", source, "--output", link)
        self.assertEqual((process.returncode, process.stdout), (2, ""))
        self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
