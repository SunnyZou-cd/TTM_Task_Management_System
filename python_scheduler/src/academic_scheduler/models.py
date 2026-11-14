"""Strict, immutable models for the standalone scheduler snapshot API."""

from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InputError(ValueError):
    """A malformed snapshot or saved result, with a JSON field path."""


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    estimated_minutes: int
    remaining_minutes: int
    importance: int
    deadline: datetime
    earliest_start: datetime
    splittable: bool
    status: str = "active"


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class LockedBlock:
    locked_id: str
    task_id: str | None
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Parameters:
    min_block_minutes: int = 15
    max_block_minutes: int = 60


@dataclass(frozen=True)
class ScheduleRequest:
    schema_version: str
    request_id: str
    input_revision: str
    now: datetime
    timezone: str
    horizon_end: datetime
    tasks: tuple[Task, ...]
    availability: tuple[Interval, ...]
    busy_events: tuple[Interval, ...]
    locked_blocks: tuple[LockedBlock, ...]
    strategy: str
    parameters: Parameters


@dataclass(frozen=True)
class ScheduleBlock:
    task_id: str | None
    start: datetime
    end: datetime
    minutes: int
    source: str
    locked_id: str | None = None


@dataclass(frozen=True)
class UnscheduledTask:
    task_id: str
    minutes: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScheduleResult:
    request_id: str
    input_revision: str
    strategy: str
    strategy_version: str
    blocks: tuple[ScheduleBlock, ...]
    unscheduled: tuple[UnscheduledTask, ...]
    metrics: dict


def _error(path: str, message: str) -> None:
    raise InputError(f"{path}: {message}")


def _object(value: Any, path: str, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        _error(path, "must be an object")
    unknown = value.keys() - required - (optional or set())
    if unknown:
        _error(path, f"unknown fields: {', '.join(sorted(map(str, unknown)))}")
    missing = required - value.keys()
    if missing:
        _error(path, f"missing fields: {', '.join(sorted(missing))}")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        _error(path, "must be a nonempty string without surrounding whitespace")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        _error(path, "must contain valid Unicode scalar values")
    return value


def _integer(value: Any, path: str, minimum: int = 0, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        _error(path, f"must be an integer >= {minimum}" + (f" and <= {maximum}" if maximum is not None else ""))
    return value


def _array(value: Any, path: str) -> list:
    if not isinstance(value, list):
        _error(path, "must be a JSON array")
    return value


def _choice(value: Any, path: str, choices: set[str]) -> str:
    value = _string(value, path)
    if value not in choices:
        _error(path, f"must be one of {', '.join(sorted(choices))}")
    return value


_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::00)?(?:Z|[+-]\d{2}:\d{2})\Z")


def parse_datetime(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not _DATETIME.fullmatch(value):
        _error(path, "must be ISO 8601 with explicit minute offset and zero seconds/microseconds")
    if value[-1] != "Z" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        _error(path, "invalid UTC offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(datetime_timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"{path}: invalid timestamp") from exc


def _display_time(value: datetime, zone: ZoneInfo, path: str) -> str:
    try:
        local = value.astimezone(zone)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"{path}: timestamp is outside the display timezone's supported datetime range") from exc
    offset = local.utcoffset()
    if offset is None or offset.total_seconds() % 60 or local.second or local.microsecond:
        _error(path, "display timezone requires a historical seconds offset, unsupported by the minute-precision contract")
    return local.isoformat(timespec="seconds")


def _interval(value: Any, path: str) -> Interval:
    value = _object(value, path, {"start", "end"})
    start, end = (parse_datetime(value[k], f"{path}.{k}") for k in ("start", "end"))
    if start >= end:
        _error(path, "start must be before end")
    return Interval(start, end)


def _task(value: Any, path: str) -> Task:
    value = _object(value, path, {"task_id", "title", "estimated_minutes", "remaining_minutes", "importance", "deadline", "earliest_start", "splittable"}, {"status"})
    estimated = _integer(value["estimated_minutes"], f"{path}.estimated_minutes")
    remaining = _integer(value["remaining_minutes"], f"{path}.remaining_minutes", maximum=estimated)
    deadline = parse_datetime(value["deadline"], f"{path}.deadline")
    earliest = parse_datetime(value["earliest_start"], f"{path}.earliest_start")
    if earliest > deadline:
        _error(f"{path}.earliest_start", "must not be after deadline")
    if type(value["splittable"]) is not bool:
        _error(f"{path}.splittable", "must be a boolean")
    status = _choice(value.get("status", "active"), f"{path}.status", {"active", "completed", "deleted"})
    if status != "active" and remaining:
        _error(f"{path}.remaining_minutes", "must be zero for completed/deleted tasks")
    return Task(_string(value["task_id"], f"{path}.task_id"), _string(value["title"], f"{path}.title"), estimated, remaining, _integer(value["importance"], f"{path}.importance", 1, 5), deadline, earliest, value["splittable"], status)


def parse_request(value: dict) -> ScheduleRequest:
    value = _object(value, "$", {"schema_version", "request_id", "input_revision", "now", "timezone", "horizon_end", "tasks", "availability", "busy_events", "locked_blocks", "strategy", "parameters"})
    _choice(value["schema_version"], "$.schema_version", {"1"})
    now = parse_datetime(value["now"], "$.now")
    end = parse_datetime(value["horizon_end"], "$.horizon_end")
    if end <= now:
        _error("$.horizon_end", "must be after now")
    zone = _string(value["timezone"], "$.timezone")
    try:
        display_zone = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InputError("$.timezone: must be a valid IANA timezone") from exc
    tasks = tuple(_task(v, f"$.tasks[{i}]") for i, v in enumerate(_array(value["tasks"], "$.tasks")))
    task_map = {task.task_id: task for task in tasks}
    if len(task_map) != len(tasks):
        _error("$.tasks", "task_id values must be unique")
    intervals = {key: tuple(_interval(v, f"$.{key}[{i}]") for i, v in enumerate(_array(value[key], f"$.{key}"))) for key in ("availability", "busy_events")}
    params = _object(value["parameters"], "$.parameters", set(), {"min_block_minutes", "max_block_minutes"})
    minimum = _integer(params.get("min_block_minutes", 15), "$.parameters.min_block_minutes", 1)
    maximum = _integer(params.get("max_block_minutes", 60), "$.parameters.max_block_minutes", 1)
    if minimum > maximum:
        _error("$.parameters", "min_block_minutes must not exceed max_block_minutes")
    locks = []
    lock_ids = set()
    for i, raw in enumerate(_array(value["locked_blocks"], "$.locked_blocks")):
        path = f"$.locked_blocks[{i}]"
        raw = _object(raw, path, {"locked_id", "task_id", "start", "end"})
        lock_id = _string(raw["locked_id"], f"{path}.locked_id")
        if lock_id in lock_ids:
            _error(f"{path}.locked_id", "must be unique")
        lock_ids.add(lock_id)
        task_id = None if raw["task_id"] is None else _string(raw["task_id"], f"{path}.task_id")
        interval = _interval({"start": raw["start"], "end": raw["end"]}, path)
        if interval.start < now or interval.end > end:
            _error(path, "must lie fully within [now, horizon_end]")
        if task_id is not None:
            task = task_map.get(task_id)
            if task is None or task.status != "active" or task.remaining_minutes <= 0:
                _error(f"{path}.task_id", "must reference an active task with remaining work")
            if interval.start < task.earliest_start or interval.end > task.deadline:
                _error(path, "must lie within the task's earliest_start/deadline")
        locks.append(LockedBlock(lock_id, task_id, interval.start, interval.end))
    # Import at call time to keep the model definitions independent of import order.
    from .availability import duration_minutes, merge_intervals

    merged = merge_intervals(intervals["availability"])
    for i, lock in enumerate(locks):
        path = f"$.locked_blocks[{i}]"
        if not any(slot.start <= lock.start and lock.end <= slot.end for slot in merged):
            _error(path, "must be covered by merged availability")
        if any(event.start < lock.end and lock.start < event.end for event in intervals["busy_events"]):
            _error(path, "must not overlap busy_events")
        if any(other.start < lock.end and lock.start < other.end for other in locks[:i]):
            _error(path, "must not overlap another locked block")
    for task in tasks:
        task_locks = [lock for lock in locks if lock.task_id == task.task_id]
        minutes = sum(duration_minutes(lock.start, lock.end) for lock in task_locks)
        if minutes > task.remaining_minutes:
            _error("$.locked_blocks", f"locked minutes exceed remaining for task {task.task_id}")
        if task_locks and not task.splittable and (len(task_locks) != 1 or minutes != task.remaining_minutes):
            _error("$.locked_blocks", f"unsplittable task {task.task_id} requires one lock covering all remaining minutes")
    # Every supplied endpoint must be safely representable in the requested display
    # timezone. Serialization repeats this check for generated block endpoints.
    _display_time(now, display_zone, "$.now")
    _display_time(end, display_zone, "$.horizon_end")
    for i, task in enumerate(tasks):
        _display_time(task.earliest_start, display_zone, f"$.tasks[{i}].earliest_start")
        _display_time(task.deadline, display_zone, f"$.tasks[{i}].deadline")
    for key, collection in (*intervals.items(), ("locked_blocks", locks)):
        for i, interval in enumerate(collection):
            _display_time(interval.start, display_zone, f"$.{key}[{i}].start")
            _display_time(interval.end, display_zone, f"$.{key}[{i}].end")
    return ScheduleRequest("1", _string(value["request_id"], "$.request_id"), _string(value["input_revision"], "$.input_revision"), now, zone, end, tasks, intervals["availability"], intervals["busy_events"], tuple(locks), _choice(value["strategy"], "$.strategy", {"edf", "importance", "risk"}), Parameters(minimum, maximum))


def parse_result(value: dict) -> ScheduleResult:
    value = _object(value, "$", {"request_id", "input_revision", "strategy", "strategy_version", "blocks", "unscheduled", "metrics"})
    blocks = []
    for i, raw in enumerate(_array(value["blocks"], "$.blocks")):
        path = f"$.blocks[{i}]"
        raw = _object(raw, path, {"task_id", "start", "end", "minutes", "source", "locked_id"})
        interval = _interval({"start": raw["start"], "end": raw["end"]}, path)
        blocks.append(ScheduleBlock(None if raw["task_id"] is None else _string(raw["task_id"], f"{path}.task_id"), interval.start, interval.end, _integer(raw["minutes"], f"{path}.minutes", 1), _choice(raw["source"], f"{path}.source", {"locked", "edf", "importance", "risk"}), None if raw["locked_id"] is None else _string(raw["locked_id"], f"{path}.locked_id")))
    unscheduled = []
    for i, raw in enumerate(_array(value["unscheduled"], "$.unscheduled")):
        path = f"$.unscheduled[{i}]"
        raw = _object(raw, path, {"task_id", "minutes", "reasons"})
        reasons = tuple(_string(v, f"{path}.reasons[{j}]") for j, v in enumerate(_array(raw["reasons"], f"{path}.reasons")))
        unscheduled.append(UnscheduledTask(_string(raw["task_id"], f"{path}.task_id"), _integer(raw["minutes"], f"{path}.minutes", 1), reasons))
    if not isinstance(value["metrics"], dict):
        _error("$.metrics", "must be an object")
    return ScheduleResult(_string(value["request_id"], "$.request_id"), _string(value["input_revision"], "$.input_revision"), _choice(value["strategy"], "$.strategy", {"edf", "importance", "risk"}), _string(value["strategy_version"], "$.strategy_version"), tuple(blocks), tuple(unscheduled), dict(value["metrics"]))


def result_to_dict(result: ScheduleResult, timezone: str) -> dict:
    zone = ZoneInfo(timezone)
    def timestamp(value: datetime) -> str:
        return _display_time(value, zone, "$.blocks")
    return {
        "request_id": result.request_id,
        "input_revision": result.input_revision,
        "strategy": result.strategy,
        "strategy_version": result.strategy_version,
        "blocks": [{"task_id": block.task_id, "start": timestamp(block.start), "end": timestamp(block.end), "minutes": block.minutes, "source": block.source, "locked_id": block.locked_id} for block in result.blocks],
        "unscheduled": [{"task_id": task.task_id, "minutes": task.minutes, "reasons": list(task.reasons)} for task in result.unscheduled],
        "metrics": dict(result.metrics),
    }
