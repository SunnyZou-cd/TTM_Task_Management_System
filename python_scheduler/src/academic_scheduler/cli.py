"""JSON command line interface for the scheduling API."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile

from . import engine, models, validation


class CLIError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIError(message)


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CLIError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise CLIError(f"invalid JSON constant: {value}")


def _read_json(path: str, *, stdin_allowed: bool = True) -> object:
    if path == "-":
        if not stdin_allowed:
            raise CLIError("result file cannot be stdin")
        data = sys.stdin.read().lstrip("\ufeff")
    else:
        data = Path(path).read_text(encoding="utf-8-sig")
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise CLIError(f"invalid JSON: {exc}") from exc


def _check_output(output: str, inputs: list[str]) -> None:
    target = Path(output)
    for item in inputs:
        if item == "-":
            continue
        source = Path(item)
        if target.resolve() == source.resolve():
            raise CLIError("output path must differ from input path")
        if target.exists() and source.exists() and os.path.samefile(target, source):
            raise CLIError("output path must differ from input path")


def _write_json(value: object, output: str | None, inputs: list[str]) -> None:
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if output is None:
        sys.stdout.write(text)
        return
    _check_output(output, inputs)
    target = Path(output)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, prefix=f".{target.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck just before replacement, including hard links.
        _check_output(output, inputs)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def _parser() -> Parser:
    parser = Parser(prog="academic-scheduler")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    for name in ("schedule", "compare"):
        command = commands.add_parser(name)
        command.add_argument("input")
        command.add_argument("--output")
    command = commands.add_parser("validate")
    command.add_argument("input")
    command.add_argument("result")
    return parser


def _error(code: str, message: str, status: int) -> int:
    sys.stderr.write(json.dumps({"error": {"code": code, "message": message}},
                                ensure_ascii=True) + "\n")
    return status


def main(argv: list[str] | None = None) -> int:
    try:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        args = _parser().parse_args(argv)
        request = models.parse_request(_read_json(args.input))
        if args.command == "validate":
            result = models.parse_result(_read_json(args.result, stdin_allowed=False))
            errors = validation.validate_result(request, result)
            if errors:
                return _error("validation_failed", "; ".join(errors), 3)
            _write_json({"valid": True}, None, [args.input, args.result])
            return 0
        results = []
        strategies = (request.strategy,) if args.command == "schedule" else ("edf", "importance", "risk")
        for strategy in strategies:
            variant = replace(request, strategy=strategy)
            result = engine.schedule(variant)
            errors = validation.validate_result(variant, result)
            if errors:
                return _error("validation_failed", "; ".join(errors), 3)
            results.append(models.result_to_dict(result, variant.timezone))
        value = results[0] if args.command == "schedule" else {
            "request_id": request.request_id, "input_revision": request.input_revision,
            "results": results,
        }
        _write_json(value, args.output, [args.input])
        return 0
    except (CLIError, models.InputError, json.JSONDecodeError, UnicodeError, OSError) as exc:
        return _error("input_error", str(exc), 2)
    except Exception as exc:
        return _error("internal_error", str(exc), 1)
