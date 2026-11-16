"""User-facing entry point: graphical workspace by default."""

import sys

from .cli import CLIError, Parser, _error as cli_error, _write_json, main as cli_main
from .demo import DemoValidationError, print_demo, run_demo
from .demo_cases import DEMO_EXAMPLES
from .models import InputError
from .terminal import run_terminal


def main(argv=None):
    try:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        args = list(sys.argv[1:] if argv is None else argv)
        if args and args[0] in ("schedule", "compare", "validate"):
            return cli_main(args)
        parser = Parser(description="Academic Scheduler: open the graphical workspace; --terminal uses the text menu.")
        parser.add_argument("--data", metavar="PATH", help="交互工作区存档路径")
        interface = parser.add_mutually_exclusive_group()
        interface.add_argument("--gui", action="store_true", help="open the graphical workspace (default)")
        interface.add_argument("--terminal", action="store_true", help="open the terminal workspace")
        parser.add_argument("--demo", action="store_true", help="运行合成案例，不进入个人工作区")
        parser.add_argument("--example", choices=("all", *DEMO_EXAMPLES), default=None)
        parser.add_argument("--strategy", choices=("all", "edf", "importance", "risk"), default=None)
        parser.add_argument("--json", action="store_true", help="输出合成案例的JSON结果")
        options = parser.parse_args(args)
        demonstration = options.demo or options.json or options.example is not None or options.strategy is not None
        if demonstration:
            if options.data is not None:
                raise CLIError("--data用于个人工作区，不能与合成案例选项混用")
            if options.gui or options.terminal:
                raise CLIError("--gui/--terminal不能与合成案例选项混用")
            report = run_demo(options.example or "all", options.strategy or "all")
            if options.json:
                _write_json(report, None, [])
            else:
                print_demo(report)
            return 0
        if options.terminal:
            return run_terminal(options.data)
        # JSON/help/terminal remain usable on installations without Tk.
        from .gui import run_gui
        return run_gui(options.data)
    except DemoValidationError as exc:
        return cli_error("validation_failed", str(exc), 3)
    except (CLIError, InputError, UnicodeError, OSError) as exc:
        return cli_error("input_error", str(exc), 2)
    except Exception as exc:
        return cli_error("internal_error", str(exc), 1)
