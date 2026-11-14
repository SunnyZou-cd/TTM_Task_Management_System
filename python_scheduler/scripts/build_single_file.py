"""Build the readable standalone demo from the tested Python modules.

Run from any directory: python python_scheduler/scripts/build_single_file.py
Use --check to detect drift without changing demo1.py.
"""

import argparse
import json
from pathlib import Path
import pprint
import re


ROOT = Path(__file__).resolve().parents[2]
MODULES = ROOT / "python_scheduler" / "src" / "academic_scheduler"
ORDER = ("models", "availability", "strategies", "metrics", "engine", "validation", "cli")
HEADER = '''#!/usr/bin/env python3
"""Demo 1: standalone academic scheduler (Python 3.11+).

Run: python demo1.py
JSON demo: python demo1.py --json
Custom input: python demo1.py schedule input.json

All algorithms, validation and synthetic examples are in this file.
The built-in demo displays UTC and needs only the Python standard library.
Other IANA display timezones need system timezone data or the tzdata package.
No database or network access is performed by this program.

Generated from the modular implementation by
python_scheduler/scripts/build_single_file.py. No exec, encoded payload,
local package import or external example file is used at runtime.
Regeneration overwrites edits to this file; edit a separate copy if needed.
"""

from __future__ import annotations

'''
RUNNER = r'''

# ==================== Built-in demonstration ====================

_CASE_TITLES = {
    "feasible": "可行案例",
    "overloaded": "超载案例",
    "replan": "锁定重排案例",
}
_REASON_TITLES = {
    "deadline_passed": "截止时间已到",
    "outside_window": "任务窗口为空",
    "no_available_capacity": "任务窗口已无空闲容量",
    "insufficient_contiguous_capacity": "没有足够连续容量",
    "below_min_block": "剩余空档短于最小块长",
    "insufficient_capacity": "剩余容量不足",
}


class DemoValidationError(RuntimeError):
    pass


def run_demo(example="all", strategy="all"):
    """Return validated results for fixed synthetic snapshots, without I/O."""
    names = tuple(DEMO_EXAMPLES) if example == "all" else (example,)
    strategies = ("edf", "importance", "risk") if strategy == "all" else (strategy,)
    cases = []
    for name in names:
        # Parsing does not mutate the embedded input; each strategy sees the
        # same request snapshot and only its strategy field changes.
        request = parse_request(DEMO_EXAMPLES[name])
        results = []
        for selected in strategies:
            variant = replace(request, strategy=selected)
            result = schedule(variant)
            errors = validate_result(variant, result)
            if errors:
                raise DemoValidationError("; ".join(errors))
            results.append(result_to_dict(result, variant.timezone))
        cases.append({"name": name, "title": _CASE_TITLES[name], "results": results})
    return {"demo": "Demo 1", "timezone": "UTC", "cases": cases}


def _print_demo(report):
    print("Demo 1 — Python 学业任务调度（固定合成数据，显示时区 UTC）")
    print("指标表示计划安排，不表示实际学习完成。")
    for case in report["cases"]:
        print(f"\n{case['title']} ({case['name']})")
        for result in case["results"]:
            metrics = result["metrics"]
            print(f"  {result['strategy']:10} 已排 {metrics['scheduled_minutes']}/{metrics['requested_minutes']} 分钟；"
                  f"未排 {metrics['unscheduled_minutes']} 分钟；"
                  f"完整安排 {metrics['fully_scheduled_tasks']}/{metrics['eligible_tasks']} 项；校验通过")
        # Show one detailed plan per case; all strategy outputs are in --json.
        selected = case["results"][0]
        print(f"  时间块（{selected['strategy']}）：")
        for block in selected["blocks"]:
            task = block["task_id"] or "固定预留"
            lock = f"，锁定 {block['locked_id']}" if block["source"] == "locked" else ""
            print(f"    {block['start']} → {block['end']}  {task}  {block['minutes']} 分钟{lock}")
        for item in selected["unscheduled"]:
            reasons = "；".join(_REASON_TITLES[reason] for reason in item["reasons"])
            print(f"    未排：{item['task_id']}，{item['minutes']} 分钟，{reasons}")
    print("\n演示完成：所有结果通过独立约束校验。")


def main(argv=None):
    """No arguments runs the demo; existing JSON subcommands remain usable."""
    try:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        args = list(sys.argv[1:] if argv is None else argv)
        if args and args[0] in ("schedule", "compare", "validate"):
            return cli_main(args)
        parser = Parser(description="运行内置学业调度演示；JSON 文件操作可用 schedule/compare/validate 子命令。")
        parser.add_argument("--example", choices=("all", *DEMO_EXAMPLES), default="all")
        parser.add_argument("--strategy", choices=("all", "edf", "importance", "risk"), default="all")
        parser.add_argument("--json", action="store_true", help="只输出 JSON，便于程序读取")
        options = parser.parse_args(args)
        report = run_demo(options.example, options.strategy)
        if options.json:
            _write_json(report, None, [])
        else:
            _print_demo(report)
        return 0
    except DemoValidationError as exc:
        return _cli_error("validation_failed", str(exc), 3)
    except (CLIError, InputError, UnicodeError, OSError) as exc:
        return _cli_error("input_error", str(exc), 2)
    except Exception as exc:
        return _cli_error("internal_error", str(exc), 1)


if __name__ == "__main__":
    raise SystemExit(main())
'''


def build() -> str:
    sections = [HEADER]
    for name in ORDER:
        source = (MODULES / f"{name}.py").read_text(encoding="utf-8")
        # Every intra-package import in the current modules is one line. Fail
        # visibly on a future multiline import instead of emitting broken code.
        for line in source.splitlines():
            if re.match(r"\s*from \.[\w.]* import", line) and "(" in line:
                raise ValueError(f"Multiline relative import in {name}; update builder")
        source = re.sub(r"^\s*from \.[\w.]* import[^\n]*\n", "", source, flags=re.MULTILINE)
        source = source.replace("from __future__ import annotations\n", "")
        if name == "models":
            source = source.replace("ZoneInfo(zone)", "_display_zone(zone)")
            source = source.replace("ZoneInfo(timezone)", "_display_zone(timezone)")
            source += '\n\ndef _display_zone(name):\n    """UTC remains available on Windows without third-party timezone data."""\n    return datetime_timezone.utc if name == "UTC" else ZoneInfo(name)\n'
        if name == "cli":
            source = re.sub(r"\b(?:models|engine|validation)\.", "", source)
            source = re.sub(r"\b_error\b", "_cli_error", source)
            source = source.replace("def main(", "def cli_main(")
        sections.append(f"\n# ==================== {name}.py ====================\n\n{source.rstrip()}\n")
    examples = {}
    for name in ("feasible", "overloaded", "replan"):
        raw = json.loads((ROOT / "python_scheduler" / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        # Preserve the same instants/workload/locks. Only display timezone changes.
        raw["timezone"] = "UTC"
        examples[name] = raw
    sections.append("\n# Synthetic snapshots; edit these in a standalone copy to try your own data.\nDEMO_EXAMPLES = " + pprint.pformat(examples, width=100, sort_dicts=False) + "\n")
    sections.append(RUNNER)
    result = "".join(sections)
    compile(result, "demo1.py", "exec")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "demo1.py"
    expected = build()
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            parser.exit(1, "demo1.py differs from the modular sources; regenerate it\n")
        print("demo1.py is synchronized")
    else:
        target.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Generated {target}")


if __name__ == "__main__":
    main()
