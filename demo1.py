#!/usr/bin/env python3
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


# ==================== models.py ====================

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
        display_zone = _display_zone(zone)
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
    zone = _display_zone(timezone)
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


def _display_zone(name):
    """UTC remains available on Windows without third-party timezone data."""
    return datetime_timezone.utc if name == "UTC" else ZoneInfo(name)

# ==================== availability.py ====================

"""Half-open interval operations; all internal timestamps are UTC."""

from datetime import datetime, timedelta
from collections.abc import Iterable


def duration_minutes(start: datetime, end: datetime) -> int:
    return (end - start) // timedelta(minutes=1)


def merge_intervals(intervals: Iterable[Interval]) -> tuple[Interval, ...]:
    merged: list[Interval] = []
    for interval in sorted(intervals, key=lambda item: (item.start, item.end)):
        if interval.start >= interval.end:
            continue
        if merged and interval.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, interval.end))
        else:
            merged.append(interval)
    return tuple(merged)


def subtract_intervals(intervals: Iterable[Interval], exclusions: Iterable[Interval]) -> tuple[Interval, ...]:
    exclusions = merge_intervals(exclusions)
    result: list[Interval] = []
    exclusion_index = 0
    for interval in merge_intervals(intervals):
        cursor = interval.start
        while exclusion_index < len(exclusions) and exclusions[exclusion_index].end <= cursor:
            exclusion_index += 1
        index = exclusion_index
        while index < len(exclusions) and exclusions[index].start < interval.end:
            exclusion = exclusions[index]
            if exclusion.start > cursor:
                result.append(Interval(cursor, min(exclusion.start, interval.end)))
            cursor = max(cursor, exclusion.end)
            if cursor >= interval.end:
                break
            index += 1
        if cursor < interval.end:
            result.append(Interval(cursor, interval.end))
    return tuple(result)


def free_intervals(request: ScheduleRequest) -> tuple[Interval, ...]:
    clipped = (Interval(max(slot.start, request.now), min(slot.end, request.horizon_end)) for slot in request.availability)
    exclusions = (*request.busy_events, *(Interval(lock.start, lock.end) for lock in request.locked_blocks))
    return subtract_intervals(clipped, exclusions)

# ==================== strategies.py ====================

"""Deterministic candidate ordering; allocation constraints belong to the engine."""

from collections.abc import Iterable, Mapping
from fractions import Fraction


STRATEGY_VERSIONS = {"edf": "edf-1", "importance": "importance-1", "risk": "risk-1"}


def task_intervals(request: ScheduleRequest, task: Task, free: Iterable[Interval]) -> tuple[Interval, ...]:
    start = max(request.now, task.earliest_start)
    end = min(request.horizon_end, task.deadline)
    return tuple(Interval(max(slot.start, start), min(slot.end, end)) for slot in free if max(slot.start, start) < min(slot.end, end))


def risk_score(request: ScheduleRequest, task: Task, remaining: int, capacity: int) -> Fraction:
    # Exact arithmetic keeps ties and repeated runs stable across platforms.
    hours = max(Fraction(0), Fraction(duration_minutes(request.now, task.deadline), 60))
    return (1 / (1 + hours) + Fraction(task.importance, 5) + min(Fraction(remaining, capacity), Fraction(1))) / 3


def order_tasks(request: ScheduleRequest, tasks: Iterable[Task], remaining: Mapping[str, int], free: tuple[Interval, ...]) -> tuple[Task, ...]:
    candidates = [task for task in tasks if remaining[task.task_id] > 0]
    if request.strategy == "edf":
        return tuple(sorted(candidates, key=lambda task: (task.deadline, task.task_id)))
    if request.strategy == "importance":
        return tuple(sorted(candidates, key=lambda task: (-task.importance, task.deadline, task.task_id)))
    scores = {}
    for task in candidates:
        capacity = sum(duration_minutes(slot.start, slot.end) for slot in task_intervals(request, task, free))
        if capacity:
            scores[task.task_id] = risk_score(request, task, remaining[task.task_id], capacity)
    return tuple(sorted((task for task in candidates if task.task_id in scores), key=lambda task: (-scores[task.task_id], task.deadline, task.task_id)))

# ==================== metrics.py ====================

"""Plan allocation metrics. These numbers never represent work completion."""


def _available_minutes(request: ScheduleRequest) -> int:
    # Use boundary segments so overlapping availability and busy are counted once.
    boundaries = {request.now, request.horizon_end}
    for interval in (*request.availability, *request.busy_events):
        boundaries.add(max(request.now, min(request.horizon_end, interval.start)))
        boundaries.add(max(request.now, min(request.horizon_end, interval.end)))
    points = sorted(boundaries)
    total = 0
    for start, end in zip(points, points[1:]):
        available = any(i.start <= start and end <= i.end for i in request.availability)
        busy = any(i.start < end and start < i.end for i in request.busy_events)
        if available and not busy:
            total += int((end - start).total_seconds() // 60)
    return total


def compute_metrics(request: ScheduleRequest, blocks: tuple[ScheduleBlock, ...]) -> dict:
    """Compute deterministic ratios from a validated request and planned blocks."""
    tasks = [t for t in request.tasks if t.status == "active" and t.remaining_minutes > 0]
    totals = {t.task_id: 0 for t in tasks}
    reserved = 0
    for block in blocks:
        if block.task_id in totals:
            totals[block.task_id] += block.minutes
        elif block.task_id is None:
            reserved += block.minutes
    complete = [t for t in tasks if totals[t.task_id] == t.remaining_minutes]
    requested = sum(t.remaining_minutes for t in tasks)
    scheduled = sum(totals.values())
    available = _available_minutes(request)
    weight = sum(t.importance for t in tasks)
    return {
        "eligible_tasks": len(tasks),
        "fully_scheduled_tasks": len(complete),
        "completion_ratio": len(complete) / len(tasks) if tasks else None,
        "weighted_completion_ratio": sum(t.importance for t in complete) / weight if weight else None,
        "requested_minutes": requested,
        "scheduled_minutes": scheduled,
        "unscheduled_minutes": requested - scheduled,
        "available_minutes": available,
        "reserved_minutes": reserved,
        "utilization_ratio": (scheduled + reserved) / available if available else None,
    }

# ==================== engine.py ====================

"""Shared feasible-block allocator for EDF, importance and dynamic risk."""

from datetime import timedelta


def _next_block(request: ScheduleRequest, task: Task, remaining: int, free: tuple[Interval, ...]) -> ScheduleBlock | None:
    for slot in task_intervals(request, task, free):
        capacity = duration_minutes(slot.start, slot.end)
        if task.splittable:
            minutes = min(capacity, remaining, request.parameters.max_block_minutes)
            if minutes < request.parameters.min_block_minutes and minutes != remaining:
                continue
        else:
            if capacity < remaining:
                continue
            minutes = remaining
        return ScheduleBlock(task.task_id, slot.start, slot.start + timedelta(minutes=minutes), minutes, request.strategy)
    return None


def _reason(request: ScheduleRequest, task: Task, remaining: int, free: tuple[Interval, ...]) -> str:
    if task.deadline <= request.now:
        return "deadline_passed"
    if task.earliest_start >= min(task.deadline, request.horizon_end):
        return "outside_window"
    capacities = [duration_minutes(slot.start, slot.end) for slot in task_intervals(request, task, free)]
    if not sum(capacities):
        return "no_available_capacity"
    if not task.splittable:
        return "insufficient_contiguous_capacity"
    if remaining >= request.parameters.min_block_minutes and all(capacity < request.parameters.min_block_minutes for capacity in capacities):
        return "below_min_block"
    return "insufficient_capacity"


def schedule(request: ScheduleRequest) -> ScheduleResult:
    tasks = tuple(task for task in request.tasks if task.status == "active" and task.remaining_minutes > 0)
    remaining = {task.task_id: task.remaining_minutes for task in tasks}
    blocks = [ScheduleBlock(lock.task_id, lock.start, lock.end, duration_minutes(lock.start, lock.end), "locked", lock.locked_id) for lock in request.locked_blocks]
    for lock in request.locked_blocks:
        if lock.task_id is not None:
            remaining[lock.task_id] -= duration_minutes(lock.start, lock.end)
    free = free_intervals(request)
    while True:
        for task in order_tasks(request, tasks, remaining, free):
            block = _next_block(request, task, remaining[task.task_id], free)
            if block is not None:
                blocks.append(block)
                remaining[task.task_id] -= block.minutes
                free = subtract_intervals(free, (Interval(block.start, block.end),))
                break
        else:
            break
    ordered = tuple(sorted(blocks, key=lambda block: (block.start, block.end, block.task_id or "")))
    unscheduled = tuple(UnscheduledTask(task.task_id, remaining[task.task_id], (_reason(request, task, remaining[task.task_id], free),)) for task in sorted(tasks, key=lambda task: task.task_id) if remaining[task.task_id] > 0)
    return ScheduleResult(request.request_id, request.input_revision, request.strategy, STRATEGY_VERSIONS[request.strategy], ordered, unscheduled, compute_metrics(request, ordered))

# ==================== validation.py ====================

"""Independent output checks; does not import the allocator or interval helpers."""

from collections import Counter, defaultdict
from datetime import datetime
import math


_VERSIONS = {"edf": "edf-1", "importance": "importance-1", "risk": "risk-1"}


def _minutes(start, end):
    return int((end - start).total_seconds() // 60)


def _segments(request, blocks=()):
    """Independent sweep of endpoints, returning usable half-open segments."""
    exclusions = [(i.start, i.end) for i in request.busy_events]
    exclusions.extend((b.start, b.end) for b in blocks)
    points = {request.now, request.horizon_end}
    for start, end in [(i.start, i.end) for i in request.availability] + exclusions:
        points.update((max(request.now, min(request.horizon_end, start)),
                       max(request.now, min(request.horizon_end, end))))
    points = sorted(points)
    usable = []
    for start, end in zip(points, points[1:]):
        if (any(i.start <= start and end <= i.end for i in request.availability)
                and not any(a < end and start < b for a, b in exclusions)):
            if usable and usable[-1][1] == start:
                usable[-1] = (usable[-1][0], end)
            else:
                usable.append((start, end))
    return usable


def _valid_time(value):
    return (isinstance(value, datetime) and value.tzinfo is not None
            and value.utcoffset() is not None and value.second == 0
            and value.microsecond == 0 and value.utcoffset().total_seconds() % 60 == 0)


def validate_result(request: ScheduleRequest, result: ScheduleResult) -> list[str]:
    """Return all detected constraint violations; an empty list means valid.

    Request objects must come from parse_request. Result dataclasses may be
    modified by callers; file structures are checked separately by parse_result.
    """
    errors = []
    for name in ("request_id", "input_revision", "strategy"):
        if getattr(result, name) != getattr(request, name):
            errors.append(f"{name}: does not match request (stale or unrelated result)")
    if result.strategy_version != _VERSIONS[request.strategy]:
        errors.append("strategy_version: unsupported version for request strategy")

    tasks = {t.task_id: t for t in request.tasks}
    locks = {b.locked_id: b for b in request.locked_blocks}
    seen_locks = Counter()
    task_blocks = defaultdict(list)
    valid_blocks = []
    totals = Counter()
    reserved = 0
    for index, block in enumerate(result.blocks):
        prefix = f"blocks[{index}]"
        if not _valid_time(block.start) or not _valid_time(block.end) or block.start >= block.end:
            errors.append(f"{prefix}: invalid positive whole-minute interval")
            continue
        valid_blocks.append(block)
        actual = _minutes(block.start, block.end)
        if type(block.minutes) is not int or block.minutes != actual:
            errors.append(f"{prefix}.minutes: does not match elapsed UTC minutes")
        if block.start < request.now or block.end > request.horizon_end:
            errors.append(f"{prefix}: outside planning window")
        # Check coverage by independently sweeping availability boundaries.
        cursor = block.start
        for interval in sorted(request.availability, key=lambda i: i.start):
            if interval.start <= cursor < interval.end:
                cursor = max(cursor, interval.end)
            if cursor >= block.end:
                break
        if cursor < block.end:
            errors.append(f"{prefix}: not fully covered by availability")
        if any(b.start < block.end and block.start < b.end for b in request.busy_events):
            errors.append(f"{prefix}: overlaps busy time")

        if block.source == "locked":
            lock = locks.get(block.locked_id)
            if lock is None:
                errors.append(f"{prefix}: unknown locked_id")
            else:
                seen_locks[block.locked_id] += 1
                if (block.task_id, block.start, block.end) != (lock.task_id, lock.start, lock.end):
                    errors.append(f"{prefix}: locked block changed")
        elif block.source != request.strategy or block.locked_id is not None:
            errors.append(f"{prefix}: invalid automatic source or locked_id")

        if block.task_id is None:
            if block.source != "locked":
                errors.append(f"{prefix}: automatic block requires task_id")
            reserved += actual
            continue
        task = tasks.get(block.task_id)
        if task is None:
            errors.append(f"{prefix}: unknown task_id")
            continue
        if task.status != "active" or task.remaining_minutes == 0:
            errors.append(f"{prefix}: task is not eligible")
        if block.start < task.earliest_start or block.end > task.deadline:
            errors.append(f"{prefix}: violates task release time or deadline")
        task_blocks[block.task_id].append(block)
        totals[block.task_id] += actual
        if block.source != "locked" and task.splittable and actual > request.parameters.max_block_minutes:
            errors.append(f"{prefix}: exceeds maximum split block length")

    ordered = sorted(valid_blocks, key=lambda b: (b.start, b.end, b.task_id or ""))
    if list(result.blocks) != ordered:
        errors.append("blocks: not sorted by start/end/task_id")
    furthest = None
    for block in ordered:
        if furthest is not None and block.start < furthest:
            errors.append("blocks: overlapping output intervals")
        furthest = max(furthest, block.end) if furthest is not None else block.end
    for locked_id in locks:
        if seen_locks[locked_id] != 1:
            errors.append(f"locked_blocks[{locked_id}]: must occur exactly once")

    expected_unscheduled = {}
    for task in request.tasks:
        assigned = totals[task.task_id]
        if assigned > task.remaining_minutes:
            errors.append(f"tasks[{task.task_id}]: exceeds remaining_minutes")
        blocks = task_blocks[task.task_id]
        if not task.splittable and assigned and (len(blocks) != 1 or assigned != task.remaining_minutes):
            errors.append(f"tasks[{task.task_id}]: nonsplittable work must be one complete block")
        automatic = sorted((b for b in blocks if b.source != "locked"), key=lambda b: b.start)
        auto_target = task.remaining_minutes - sum(_minutes(b.start, b.end) for b in blocks if b.source == "locked")
        short_blocks = [b for b in automatic if _minutes(b.start, b.end) < request.parameters.min_block_minutes]
        # The last allocation can backfill an earlier small gap. The result has
        # chronological order, not allocation order, so a complete single short
        # block is the independently checkable tail invariant.
        if (task.splittable and short_blocks
                and (len(short_blocks) > 1 or sum(_minutes(b.start, b.end) for b in automatic) != auto_target)):
            errors.append(f"tasks[{task.task_id}]: short block is not a complete final tail")
        if task.status == "active" and task.remaining_minutes > assigned:
            expected_unscheduled[task.task_id] = task.remaining_minutes - assigned

    final_free = _segments(request, valid_blocks)
    seen_unscheduled = set()
    for index, item in enumerate(result.unscheduled):
        prefix = f"unscheduled[{index}]"
        if item.task_id in seen_unscheduled:
            errors.append(f"{prefix}: duplicate task")
        seen_unscheduled.add(item.task_id)
        remaining = expected_unscheduled.get(item.task_id)
        if remaining is None or type(item.minutes) is not int or item.minutes != remaining:
            errors.append(f"{prefix}: incorrect unallocated minutes or task")
            continue
        task = tasks[item.task_id]
        end = min(task.deadline, request.horizon_end)
        lengths = [_minutes(max(a, task.earliest_start), min(b, end))
                   for a, b in final_free if max(a, task.earliest_start) < min(b, end)]
        if task.deadline <= request.now:
            reason = "deadline_passed"
        elif task.earliest_start >= end:
            reason = "outside_window"
        elif not lengths:
            reason = "no_available_capacity"
        elif not task.splittable:
            reason = "insufficient_contiguous_capacity"
            if max(lengths) >= remaining:
                errors.append(f"{prefix}: remaining contiguous work still fits")
        elif remaining >= request.parameters.min_block_minutes and max(lengths) < request.parameters.min_block_minutes:
            reason = "below_min_block"
        else:
            reason = "insufficient_capacity"
            if max(lengths) >= min(remaining, request.parameters.min_block_minutes):
                errors.append(f"{prefix}: remaining split work still fits")
        if tuple(item.reasons) != (reason,):
            errors.append(f"{prefix}.reasons: expected {reason}")
    if seen_unscheduled != set(expected_unscheduled):
        errors.append("unscheduled: must list exactly the unfinished eligible tasks")

    eligible = [t for t in request.tasks if t.status == "active" and t.remaining_minutes > 0]
    complete = [t for t in eligible if totals[t.task_id] == t.remaining_minutes]
    requested = sum(t.remaining_minutes for t in eligible)
    scheduled = sum(totals[t.task_id] for t in eligible)
    available = sum(_minutes(a, b) for a, b in _segments(request))
    weights = sum(t.importance for t in eligible)
    expected_metrics = {
        "eligible_tasks": len(eligible), "fully_scheduled_tasks": len(complete),
        "completion_ratio": len(complete) / len(eligible) if eligible else None,
        "weighted_completion_ratio": sum(t.importance for t in complete) / weights if weights else None,
        "requested_minutes": requested, "scheduled_minutes": scheduled,
        "unscheduled_minutes": requested - scheduled, "available_minutes": available,
        "reserved_minutes": reserved,
        "utilization_ratio": (scheduled + reserved) / available if available else None,
    }
    if not isinstance(result.metrics, dict) or set(result.metrics) != set(expected_metrics):
        errors.append("metrics: incorrect field set")
    else:
        for key, expected in expected_metrics.items():
            actual = result.metrics[key]
            if expected is None:
                matches = actual is None
            elif type(expected) is int:
                matches = type(actual) is int and actual == expected
            else:
                matches = (type(actual) in (int, float) and 0 <= actual <= 1 and math.isfinite(actual)
                           and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12))
            if not matches:
                errors.append(f"metrics.{key}: expected {expected}")
    return errors

# ==================== cli.py ====================

"""JSON command line interface for the scheduling API."""


import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile


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


def _cli_error(code: str, message: str, status: int) -> int:
    sys.stderr.write(json.dumps({"error": {"code": code, "message": message}},
                                ensure_ascii=True) + "\n")
    return status


def cli_main(argv: list[str] | None = None) -> int:
    try:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        args = _parser().parse_args(argv)
        request = parse_request(_read_json(args.input))
        if args.command == "validate":
            result = parse_result(_read_json(args.result, stdin_allowed=False))
            errors = validate_result(request, result)
            if errors:
                return _cli_error("validation_failed", "; ".join(errors), 3)
            _write_json({"valid": True}, None, [args.input, args.result])
            return 0
        results = []
        strategies = (request.strategy,) if args.command == "schedule" else ("edf", "importance", "risk")
        for strategy in strategies:
            variant = replace(request, strategy=strategy)
            result = schedule(variant)
            errors = validate_result(variant, result)
            if errors:
                return _cli_error("validation_failed", "; ".join(errors), 3)
            results.append(result_to_dict(result, variant.timezone))
        value = results[0] if args.command == "schedule" else {
            "request_id": request.request_id, "input_revision": request.input_revision,
            "results": results,
        }
        _write_json(value, args.output, [args.input])
        return 0
    except (CLIError, InputError, json.JSONDecodeError, UnicodeError, OSError) as exc:
        return _cli_error("input_error", str(exc), 2)
    except Exception as exc:
        return _cli_error("internal_error", str(exc), 1)

# Synthetic snapshots; edit these in a standalone copy to try your own data.
DEMO_EXAMPLES = {'feasible': {'schema_version': '1',
              'request_id': 'demo-feasible-2026-11-13',
              'input_revision': 'demo-feasible-r1',
              'now': '2026-11-13T09:00:00-06:00',
              'timezone': 'UTC',
              'horizon_end': '2026-11-13T12:00:00-06:00',
              'tasks': [{'task_id': 'read-chapter',
                         'title': '阅读课程章节',
                         'estimated_minutes': 90,
                         'remaining_minutes': 90,
                         'importance': 4,
                         'deadline': '2026-11-13T11:00:00-06:00',
                         'earliest_start': '2026-11-13T09:00:00-06:00',
                         'splittable': True},
                        {'task_id': 'submit-notes',
                         'title': '整理并提交课堂笔记',
                         'estimated_minutes': 60,
                         'remaining_minutes': 60,
                         'importance': 3,
                         'deadline': '2026-11-13T12:00:00-06:00',
                         'earliest_start': '2026-11-13T09:00:00-06:00',
                         'splittable': True}],
              'availability': [{'start': '2026-11-13T09:00:00-06:00',
                                'end': '2026-11-13T12:00:00-06:00'}],
              'busy_events': [],
              'locked_blocks': [],
              'strategy': 'edf',
              'parameters': {'min_block_minutes': 15, 'max_block_minutes': 60}},
 'overloaded': {'schema_version': '1',
                'request_id': 'demo-overloaded-2026-11-13',
                'input_revision': 'demo-overloaded-r1',
                'now': '2026-11-13T09:00:00-06:00',
                'timezone': 'UTC',
                'horizon_end': '2026-11-13T11:00:00-06:00',
                'tasks': [{'task_id': 'lab-report',
                           'title': '完成实验报告',
                           'estimated_minutes': 90,
                           'remaining_minutes': 90,
                           'importance': 5,
                           'deadline': '2026-11-13T10:00:00-06:00',
                           'earliest_start': '2026-11-13T09:00:00-06:00',
                           'splittable': True},
                          {'task_id': 'review-lecture',
                           'title': '复习讲义',
                           'estimated_minutes': 90,
                           'remaining_minutes': 90,
                           'importance': 3,
                           'deadline': '2026-11-13T11:00:00-06:00',
                           'earliest_start': '2026-11-13T09:00:00-06:00',
                           'splittable': True}],
                'availability': [{'start': '2026-11-13T09:00:00-06:00',
                                  'end': '2026-11-13T11:00:00-06:00'}],
                'busy_events': [],
                'locked_blocks': [],
                'strategy': 'edf',
                'parameters': {'min_block_minutes': 15, 'max_block_minutes': 60}},
 'replan': {'schema_version': '1',
            'request_id': 'demo-replan-2026-11-13',
            'input_revision': 'demo-replan-r1',
            'now': '2026-11-13T14:00:00-06:00',
            'timezone': 'UTC',
            'horizon_end': '2026-11-13T18:00:00-06:00',
            'tasks': [{'task_id': 'write-draft',
                       'title': '撰写论文初稿',
                       'estimated_minutes': 90,
                       'remaining_minutes': 90,
                       'importance': 5,
                       'deadline': '2026-11-13T18:00:00-06:00',
                       'earliest_start': '2026-11-13T14:00:00-06:00',
                       'splittable': True},
                      {'task_id': 'prepare-quiz',
                       'title': '准备小测',
                       'estimated_minutes': 60,
                       'remaining_minutes': 60,
                       'importance': 3,
                       'deadline': '2026-11-13T18:00:00-06:00',
                       'earliest_start': '2026-11-13T14:00:00-06:00',
                       'splittable': True}],
            'availability': [{'start': '2026-11-13T14:00:00-06:00',
                              'end': '2026-11-13T18:00:00-06:00'}],
            'busy_events': [],
            'locked_blocks': [{'locked_id': 'keep-draft-session',
                               'task_id': 'write-draft',
                               'start': '2026-11-13T15:00:00-06:00',
                               'end': '2026-11-13T15:30:00-06:00'},
                              {'locked_id': 'reserved-appointment',
                               'task_id': None,
                               'start': '2026-11-13T16:00:00-06:00',
                               'end': '2026-11-13T16:30:00-06:00'}],
            'strategy': 'importance',
            'parameters': {'min_block_minutes': 15, 'max_block_minutes': 60}}}


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
