#!/usr/bin/env python3
"""Demo 1: graphical Python academic scheduling software (Python 3.11+).

Run: python demo1.py
Text menu: python demo1.py --terminal
Separate personal file: python demo1.py --data work/my-tasks.json
Optional synthetic examples: python demo1.py --demo
Machine-readable example results: python demo1.py --demo --json

All source is in this file. Default UTC needs only the Python standard library.
The graphical interface uses tkinter, included with standard Windows Python.
Other IANA timezones need system timezone data or tzdata.
The program writes personal data only when the user chooses to save.
The default file is work/demo1-data/workspace.json under the current directory.

Generated from the tested modules by python_scheduler/scripts/build_single_file.py.
No runtime exec, encoded payload, project import or external example is required.
Regeneration overwrites edits to this file; use a copy for personal experiments.
"""

from __future__ import annotations


# ==================== models.py ====================

"""Strict, immutable models for the standalone scheduler snapshot API."""
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone, tzinfo
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

class InputError(ValueError):
    """A malformed snapshot or saved result, with a JSON field path."""

def resolve_timezone(name: str) -> tzinfo:
    """Keep the default UTC workspace usable without optional IANA data."""
    if name == 'UTC':
        return datetime_timezone.utc
    if not isinstance(name, str) or not name or name.strip() != name:
        raise InputError('timezone: must be a valid IANA timezone name')
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InputError('timezone: 时区无效或缺少时区数据；请核对 IANA 名称，必要时运行 python -m pip install tzdata') from exc

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
    status: str = 'active'

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

def _models_error(path: str, message: str) -> None:
    raise InputError(f'{path}: {message}')

def _models_object(value: Any, path: str, required: set[str], optional: set[str] | None=None) -> dict:
    if not isinstance(value, dict):
        _models_error(path, 'must be an object')
    unknown = value.keys() - required - (optional or set())
    if unknown:
        _models_error(path, f"unknown fields: {', '.join(sorted(map(str, unknown)))}")
    missing = required - value.keys()
    if missing:
        _models_error(path, f"missing fields: {', '.join(sorted(missing))}")
    return value

def _models_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        _models_error(path, 'must be a nonempty string without surrounding whitespace')
    if any((55296 <= ord(character) <= 57343 for character in value)):
        _models_error(path, 'must contain valid Unicode scalar values')
    return value

def _models_integer(value: Any, path: str, minimum: int=0, maximum: int | None=None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        _models_error(path, f'must be an integer >= {minimum}' + (f' and <= {maximum}' if maximum is not None else ''))
    return value

def _models_array(value: Any, path: str) -> list:
    if not isinstance(value, list):
        _models_error(path, 'must be a JSON array')
    return value

def _models_choice(value: Any, path: str, choices: set[str]) -> str:
    value = _models_string(value, path)
    if value not in choices:
        _models_error(path, f"must be one of {', '.join(sorted(choices))}")
    return value
_models_DATETIME = re.compile('\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}(?::00)?(?:Z|[+-]\\d{2}:\\d{2})\\Z')

def parse_datetime(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not _models_DATETIME.fullmatch(value):
        _models_error(path, 'must be ISO 8601 with explicit minute offset and zero seconds/microseconds')
    if value[-1] != 'Z' and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        _models_error(path, 'invalid UTC offset')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(datetime_timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise InputError(f'{path}: invalid timestamp') from exc

def _models_display_time(value: datetime, zone: tzinfo, path: str) -> str:
    try:
        local = value.astimezone(zone)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"{path}: timestamp is outside the display timezone's supported datetime range") from exc
    offset = local.utcoffset()
    if offset is None or offset.total_seconds() % 60 or local.second or local.microsecond:
        _models_error(path, 'display timezone requires a historical seconds offset, unsupported by the minute-precision contract')
    return local.isoformat(timespec='seconds')

def _models_interval(value: Any, path: str) -> Interval:
    value = _models_object(value, path, {'start', 'end'})
    start, end = (parse_datetime(value[k], f'{path}.{k}') for k in ('start', 'end'))
    if start >= end:
        _models_error(path, 'start must be before end')
    return Interval(start, end)

def _models_task(value: Any, path: str) -> Task:
    value = _models_object(value, path, {'task_id', 'title', 'estimated_minutes', 'remaining_minutes', 'importance', 'deadline', 'earliest_start', 'splittable'}, {'status'})
    estimated = _models_integer(value['estimated_minutes'], f'{path}.estimated_minutes')
    remaining = _models_integer(value['remaining_minutes'], f'{path}.remaining_minutes', maximum=estimated)
    deadline = parse_datetime(value['deadline'], f'{path}.deadline')
    earliest = parse_datetime(value['earliest_start'], f'{path}.earliest_start')
    if earliest > deadline:
        _models_error(f'{path}.earliest_start', 'must not be after deadline')
    if type(value['splittable']) is not bool:
        _models_error(f'{path}.splittable', 'must be a boolean')
    status = _models_choice(value.get('status', 'active'), f'{path}.status', {'active', 'completed', 'deleted'})
    if status != 'active' and remaining:
        _models_error(f'{path}.remaining_minutes', 'must be zero for completed/deleted tasks')
    return Task(_models_string(value['task_id'], f'{path}.task_id'), _models_string(value['title'], f'{path}.title'), estimated, remaining, _models_integer(value['importance'], f'{path}.importance', 1, 5), deadline, earliest, value['splittable'], status)

def parse_request(value: dict) -> ScheduleRequest:
    value = _models_object(value, '$', {'schema_version', 'request_id', 'input_revision', 'now', 'timezone', 'horizon_end', 'tasks', 'availability', 'busy_events', 'locked_blocks', 'strategy', 'parameters'})
    _models_choice(value['schema_version'], '$.schema_version', {'1'})
    now = parse_datetime(value['now'], '$.now')
    end = parse_datetime(value['horizon_end'], '$.horizon_end')
    if end <= now:
        _models_error('$.horizon_end', 'must be after now')
    zone = _models_string(value['timezone'], '$.timezone')
    try:
        display_zone = resolve_timezone(zone)
    except InputError as exc:
        raise InputError(f'$.timezone: {exc}') from exc
    tasks = tuple((_models_task(v, f'$.tasks[{i}]') for i, v in enumerate(_models_array(value['tasks'], '$.tasks'))))
    task_map = {task.task_id: task for task in tasks}
    if len(task_map) != len(tasks):
        _models_error('$.tasks', 'task_id values must be unique')
    intervals = {key: tuple((_models_interval(v, f'$.{key}[{i}]') for i, v in enumerate(_models_array(value[key], f'$.{key}')))) for key in ('availability', 'busy_events')}
    params = _models_object(value['parameters'], '$.parameters', set(), {'min_block_minutes', 'max_block_minutes'})
    minimum = _models_integer(params.get('min_block_minutes', 15), '$.parameters.min_block_minutes', 1)
    maximum = _models_integer(params.get('max_block_minutes', 60), '$.parameters.max_block_minutes', 1)
    if minimum > maximum:
        _models_error('$.parameters', 'min_block_minutes must not exceed max_block_minutes')
    locks = []
    lock_ids = set()
    for i, raw in enumerate(_models_array(value['locked_blocks'], '$.locked_blocks')):
        path = f'$.locked_blocks[{i}]'
        raw = _models_object(raw, path, {'locked_id', 'task_id', 'start', 'end'})
        lock_id = _models_string(raw['locked_id'], f'{path}.locked_id')
        if lock_id in lock_ids:
            _models_error(f'{path}.locked_id', 'must be unique')
        lock_ids.add(lock_id)
        task_id = None if raw['task_id'] is None else _models_string(raw['task_id'], f'{path}.task_id')
        interval = _models_interval({'start': raw['start'], 'end': raw['end']}, path)
        if interval.start < now or interval.end > end:
            _models_error(path, 'must lie fully within [now, horizon_end]')
        if task_id is not None:
            task = task_map.get(task_id)
            if task is None or task.status != 'active' or task.remaining_minutes <= 0:
                _models_error(f'{path}.task_id', 'must reference an active task with remaining work')
            if interval.start < task.earliest_start or interval.end > task.deadline:
                _models_error(path, "must lie within the task's earliest_start/deadline")
        locks.append(LockedBlock(lock_id, task_id, interval.start, interval.end))
    merged = merge_intervals(intervals['availability'])
    for i, lock in enumerate(locks):
        path = f'$.locked_blocks[{i}]'
        if not any((slot.start <= lock.start and lock.end <= slot.end for slot in merged)):
            _models_error(path, 'must be covered by merged availability')
        if any((event.start < lock.end and lock.start < event.end for event in intervals['busy_events'])):
            _models_error(path, 'must not overlap busy_events')
        if any((other.start < lock.end and lock.start < other.end for other in locks[:i])):
            _models_error(path, 'must not overlap another locked block')
    for task in tasks:
        task_locks = [lock for lock in locks if lock.task_id == task.task_id]
        minutes = sum((duration_minutes(lock.start, lock.end) for lock in task_locks))
        if minutes > task.remaining_minutes:
            _models_error('$.locked_blocks', f'locked minutes exceed remaining for task {task.task_id}')
        if task_locks and (not task.splittable) and (len(task_locks) != 1 or minutes != task.remaining_minutes):
            _models_error('$.locked_blocks', f'unsplittable task {task.task_id} requires one lock covering all remaining minutes')
    _models_display_time(now, display_zone, '$.now')
    _models_display_time(end, display_zone, '$.horizon_end')
    for i, task in enumerate(tasks):
        _models_display_time(task.earliest_start, display_zone, f'$.tasks[{i}].earliest_start')
        _models_display_time(task.deadline, display_zone, f'$.tasks[{i}].deadline')
    for key, collection in (*intervals.items(), ('locked_blocks', locks)):
        for i, interval in enumerate(collection):
            _models_display_time(interval.start, display_zone, f'$.{key}[{i}].start')
            _models_display_time(interval.end, display_zone, f'$.{key}[{i}].end')
    return ScheduleRequest('1', _models_string(value['request_id'], '$.request_id'), _models_string(value['input_revision'], '$.input_revision'), now, zone, end, tasks, intervals['availability'], intervals['busy_events'], tuple(locks), _models_choice(value['strategy'], '$.strategy', {'edf', 'importance', 'risk'}), Parameters(minimum, maximum))

def parse_result(value: dict) -> ScheduleResult:
    value = _models_object(value, '$', {'request_id', 'input_revision', 'strategy', 'strategy_version', 'blocks', 'unscheduled', 'metrics'})
    blocks = []
    for i, raw in enumerate(_models_array(value['blocks'], '$.blocks')):
        path = f'$.blocks[{i}]'
        raw = _models_object(raw, path, {'task_id', 'start', 'end', 'minutes', 'source', 'locked_id'})
        interval = _models_interval({'start': raw['start'], 'end': raw['end']}, path)
        blocks.append(ScheduleBlock(None if raw['task_id'] is None else _models_string(raw['task_id'], f'{path}.task_id'), interval.start, interval.end, _models_integer(raw['minutes'], f'{path}.minutes', 1), _models_choice(raw['source'], f'{path}.source', {'locked', 'edf', 'importance', 'risk'}), None if raw['locked_id'] is None else _models_string(raw['locked_id'], f'{path}.locked_id')))
    unscheduled = []
    for i, raw in enumerate(_models_array(value['unscheduled'], '$.unscheduled')):
        path = f'$.unscheduled[{i}]'
        raw = _models_object(raw, path, {'task_id', 'minutes', 'reasons'})
        reasons = tuple((_models_string(v, f'{path}.reasons[{j}]') for j, v in enumerate(_models_array(raw['reasons'], f'{path}.reasons'))))
        unscheduled.append(UnscheduledTask(_models_string(raw['task_id'], f'{path}.task_id'), _models_integer(raw['minutes'], f'{path}.minutes', 1), reasons))
    if not isinstance(value['metrics'], dict):
        _models_error('$.metrics', 'must be an object')
    return ScheduleResult(_models_string(value['request_id'], '$.request_id'), _models_string(value['input_revision'], '$.input_revision'), _models_choice(value['strategy'], '$.strategy', {'edf', 'importance', 'risk'}), _models_string(value['strategy_version'], '$.strategy_version'), tuple(blocks), tuple(unscheduled), dict(value['metrics']))

def result_to_dict(result: ScheduleResult, timezone: str) -> dict:
    zone = resolve_timezone(timezone)

    def timestamp(value: datetime) -> str:
        return _models_display_time(value, zone, '$.blocks')
    return {'request_id': result.request_id, 'input_revision': result.input_revision, 'strategy': result.strategy, 'strategy_version': result.strategy_version, 'blocks': [{'task_id': block.task_id, 'start': timestamp(block.start), 'end': timestamp(block.end), 'minutes': block.minutes, 'source': block.source, 'locked_id': block.locked_id} for block in result.blocks], 'unscheduled': [{'task_id': task.task_id, 'minutes': task.minutes, 'reasons': list(task.reasons)} for task in result.unscheduled], 'metrics': dict(result.metrics)}

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
STRATEGY_VERSIONS = {'edf': 'edf-1', 'importance': 'importance-1', 'risk': 'risk-1'}

def task_intervals(request: ScheduleRequest, task: Task, free: Iterable[Interval]) -> tuple[Interval, ...]:
    start = max(request.now, task.earliest_start)
    end = min(request.horizon_end, task.deadline)
    return tuple((Interval(max(slot.start, start), min(slot.end, end)) for slot in free if max(slot.start, start) < min(slot.end, end)))

def risk_score(request: ScheduleRequest, task: Task, remaining: int, capacity: int) -> Fraction:
    hours = max(Fraction(0), Fraction(duration_minutes(request.now, task.deadline), 60))
    return (1 / (1 + hours) + Fraction(task.importance, 5) + min(Fraction(remaining, capacity), Fraction(1))) / 3

def order_tasks(request: ScheduleRequest, tasks: Iterable[Task], remaining: Mapping[str, int], free: tuple[Interval, ...]) -> tuple[Task, ...]:
    candidates = [task for task in tasks if remaining[task.task_id] > 0]
    if request.strategy == 'edf':
        return tuple(sorted(candidates, key=lambda task: (task.deadline, task.task_id)))
    if request.strategy == 'importance':
        return tuple(sorted(candidates, key=lambda task: (-task.importance, task.deadline, task.task_id)))
    scores = {}
    for task in candidates:
        capacity = sum((duration_minutes(slot.start, slot.end) for slot in task_intervals(request, task, free)))
        if capacity:
            scores[task.task_id] = risk_score(request, task, remaining[task.task_id], capacity)
    return tuple(sorted((task for task in candidates if task.task_id in scores), key=lambda task: (-scores[task.task_id], task.deadline, task.task_id)))

# ==================== metrics.py ====================

"""Plan allocation metrics. These numbers never represent work completion."""

def _metrics_available_minutes(request: ScheduleRequest) -> int:
    boundaries = {request.now, request.horizon_end}
    for interval in (*request.availability, *request.busy_events):
        boundaries.add(max(request.now, min(request.horizon_end, interval.start)))
        boundaries.add(max(request.now, min(request.horizon_end, interval.end)))
    points = sorted(boundaries)
    total = 0
    for start, end in zip(points, points[1:]):
        available = any((i.start <= start and end <= i.end for i in request.availability))
        busy = any((i.start < end and start < i.end for i in request.busy_events))
        if available and (not busy):
            total += int((end - start).total_seconds() // 60)
    return total

def compute_metrics(request: ScheduleRequest, blocks: tuple[ScheduleBlock, ...]) -> dict:
    """Compute deterministic ratios from a validated request and planned blocks."""
    tasks = [t for t in request.tasks if t.status == 'active' and t.remaining_minutes > 0]
    totals = {t.task_id: 0 for t in tasks}
    reserved = 0
    for block in blocks:
        if block.task_id in totals:
            totals[block.task_id] += block.minutes
        elif block.task_id is None:
            reserved += block.minutes
    complete = [t for t in tasks if totals[t.task_id] == t.remaining_minutes]
    requested = sum((t.remaining_minutes for t in tasks))
    scheduled = sum(totals.values())
    available = _metrics_available_minutes(request)
    weight = sum((t.importance for t in tasks))
    return {'eligible_tasks': len(tasks), 'fully_scheduled_tasks': len(complete), 'completion_ratio': len(complete) / len(tasks) if tasks else None, 'weighted_completion_ratio': sum((t.importance for t in complete)) / weight if weight else None, 'requested_minutes': requested, 'scheduled_minutes': scheduled, 'unscheduled_minutes': requested - scheduled, 'available_minutes': available, 'reserved_minutes': reserved, 'utilization_ratio': (scheduled + reserved) / available if available else None}

# ==================== engine.py ====================

"""Shared feasible-block allocator for EDF, importance and dynamic risk."""
from datetime import timedelta

def _engine_next_block(request: ScheduleRequest, task: Task, remaining: int, free: tuple[Interval, ...]) -> ScheduleBlock | None:
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

def _engine_reason(request: ScheduleRequest, task: Task, remaining: int, free: tuple[Interval, ...]) -> str:
    if task.deadline <= request.now:
        return 'deadline_passed'
    if task.earliest_start >= min(task.deadline, request.horizon_end):
        return 'outside_window'
    capacities = [duration_minutes(slot.start, slot.end) for slot in task_intervals(request, task, free)]
    if not sum(capacities):
        return 'no_available_capacity'
    if not task.splittable:
        return 'insufficient_contiguous_capacity'
    if remaining >= request.parameters.min_block_minutes and all((capacity < request.parameters.min_block_minutes for capacity in capacities)):
        return 'below_min_block'
    return 'insufficient_capacity'

def schedule(request: ScheduleRequest) -> ScheduleResult:
    tasks = tuple((task for task in request.tasks if task.status == 'active' and task.remaining_minutes > 0))
    remaining = {task.task_id: task.remaining_minutes for task in tasks}
    blocks = [ScheduleBlock(lock.task_id, lock.start, lock.end, duration_minutes(lock.start, lock.end), 'locked', lock.locked_id) for lock in request.locked_blocks]
    for lock in request.locked_blocks:
        if lock.task_id is not None:
            remaining[lock.task_id] -= duration_minutes(lock.start, lock.end)
    free = free_intervals(request)
    while True:
        for task in order_tasks(request, tasks, remaining, free):
            block = _engine_next_block(request, task, remaining[task.task_id], free)
            if block is not None:
                blocks.append(block)
                remaining[task.task_id] -= block.minutes
                free = subtract_intervals(free, (Interval(block.start, block.end),))
                break
        else:
            break
    ordered = tuple(sorted(blocks, key=lambda block: (block.start, block.end, block.task_id or '')))
    unscheduled = tuple((UnscheduledTask(task.task_id, remaining[task.task_id], (_engine_reason(request, task, remaining[task.task_id], free),)) for task in sorted(tasks, key=lambda task: task.task_id) if remaining[task.task_id] > 0))
    return ScheduleResult(request.request_id, request.input_revision, request.strategy, STRATEGY_VERSIONS[request.strategy], ordered, unscheduled, compute_metrics(request, ordered))

# ==================== validation.py ====================

"""Independent output checks; does not import the allocator or interval helpers."""
from collections import Counter, defaultdict
from datetime import datetime
import math
_validation_VERSIONS = {'edf': 'edf-1', 'importance': 'importance-1', 'risk': 'risk-1'}

def _validation_minutes(start, end):
    return int((end - start).total_seconds() // 60)

def _validation_segments(request, blocks=()):
    """Independent sweep of endpoints, returning usable half-open segments."""
    exclusions = [(i.start, i.end) for i in request.busy_events]
    exclusions.extend(((b.start, b.end) for b in blocks))
    points = {request.now, request.horizon_end}
    for start, end in [(i.start, i.end) for i in request.availability] + exclusions:
        points.update((max(request.now, min(request.horizon_end, start)), max(request.now, min(request.horizon_end, end))))
    points = sorted(points)
    usable = []
    for start, end in zip(points, points[1:]):
        if any((i.start <= start and end <= i.end for i in request.availability)) and (not any((a < end and start < b for a, b in exclusions))):
            if usable and usable[-1][1] == start:
                usable[-1] = (usable[-1][0], end)
            else:
                usable.append((start, end))
    return usable

def _validation_valid_time(value):
    return isinstance(value, datetime) and value.tzinfo is not None and (value.utcoffset() is not None) and (value.second == 0) and (value.microsecond == 0) and (value.utcoffset().total_seconds() % 60 == 0)

def validate_result(request: ScheduleRequest, result: ScheduleResult) -> list[str]:
    """Return all detected constraint violations; an empty list means valid.

    Request objects must come from parse_request. Result dataclasses may be
    modified by callers; file structures are checked separately by parse_result.
    """
    errors = []
    for name in ('request_id', 'input_revision', 'strategy'):
        if getattr(result, name) != getattr(request, name):
            errors.append(f'{name}: does not match request (stale or unrelated result)')
    if result.strategy_version != _validation_VERSIONS[request.strategy]:
        errors.append('strategy_version: unsupported version for request strategy')
    tasks = {t.task_id: t for t in request.tasks}
    locks = {b.locked_id: b for b in request.locked_blocks}
    seen_locks = Counter()
    task_blocks = defaultdict(list)
    valid_blocks = []
    totals = Counter()
    reserved = 0
    for index, block in enumerate(result.blocks):
        prefix = f'blocks[{index}]'
        if not _validation_valid_time(block.start) or not _validation_valid_time(block.end) or block.start >= block.end:
            errors.append(f'{prefix}: invalid positive whole-minute interval')
            continue
        valid_blocks.append(block)
        actual = _validation_minutes(block.start, block.end)
        if type(block.minutes) is not int or block.minutes != actual:
            errors.append(f'{prefix}.minutes: does not match elapsed UTC minutes')
        if block.start < request.now or block.end > request.horizon_end:
            errors.append(f'{prefix}: outside planning window')
        cursor = block.start
        for interval in sorted(request.availability, key=lambda i: i.start):
            if interval.start <= cursor < interval.end:
                cursor = max(cursor, interval.end)
            if cursor >= block.end:
                break
        if cursor < block.end:
            errors.append(f'{prefix}: not fully covered by availability')
        if any((b.start < block.end and block.start < b.end for b in request.busy_events)):
            errors.append(f'{prefix}: overlaps busy time')
        if block.source == 'locked':
            lock = locks.get(block.locked_id)
            if lock is None:
                errors.append(f'{prefix}: unknown locked_id')
            else:
                seen_locks[block.locked_id] += 1
                if (block.task_id, block.start, block.end) != (lock.task_id, lock.start, lock.end):
                    errors.append(f'{prefix}: locked block changed')
        elif block.source != request.strategy or block.locked_id is not None:
            errors.append(f'{prefix}: invalid automatic source or locked_id')
        if block.task_id is None:
            if block.source != 'locked':
                errors.append(f'{prefix}: automatic block requires task_id')
            reserved += actual
            continue
        task = tasks.get(block.task_id)
        if task is None:
            errors.append(f'{prefix}: unknown task_id')
            continue
        if task.status != 'active' or task.remaining_minutes == 0:
            errors.append(f'{prefix}: task is not eligible')
        if block.start < task.earliest_start or block.end > task.deadline:
            errors.append(f'{prefix}: violates task release time or deadline')
        task_blocks[block.task_id].append(block)
        totals[block.task_id] += actual
        if block.source != 'locked' and task.splittable and (actual > request.parameters.max_block_minutes):
            errors.append(f'{prefix}: exceeds maximum split block length')
    ordered = sorted(valid_blocks, key=lambda b: (b.start, b.end, b.task_id or ''))
    if list(result.blocks) != ordered:
        errors.append('blocks: not sorted by start/end/task_id')
    furthest = None
    for block in ordered:
        if furthest is not None and block.start < furthest:
            errors.append('blocks: overlapping output intervals')
        furthest = max(furthest, block.end) if furthest is not None else block.end
    for locked_id in locks:
        if seen_locks[locked_id] != 1:
            errors.append(f'locked_blocks[{locked_id}]: must occur exactly once')
    expected_unscheduled = {}
    for task in request.tasks:
        assigned = totals[task.task_id]
        if assigned > task.remaining_minutes:
            errors.append(f'tasks[{task.task_id}]: exceeds remaining_minutes')
        blocks = task_blocks[task.task_id]
        if not task.splittable and assigned and (len(blocks) != 1 or assigned != task.remaining_minutes):
            errors.append(f'tasks[{task.task_id}]: nonsplittable work must be one complete block')
        automatic = sorted((b for b in blocks if b.source != 'locked'), key=lambda b: b.start)
        auto_target = task.remaining_minutes - sum((_validation_minutes(b.start, b.end) for b in blocks if b.source == 'locked'))
        short_blocks = [b for b in automatic if _validation_minutes(b.start, b.end) < request.parameters.min_block_minutes]
        if task.splittable and short_blocks and (len(short_blocks) > 1 or sum((_validation_minutes(b.start, b.end) for b in automatic)) != auto_target):
            errors.append(f'tasks[{task.task_id}]: short block is not a complete final tail')
        if task.status == 'active' and task.remaining_minutes > assigned:
            expected_unscheduled[task.task_id] = task.remaining_minutes - assigned
    final_free = _validation_segments(request, valid_blocks)
    seen_unscheduled = set()
    for index, item in enumerate(result.unscheduled):
        prefix = f'unscheduled[{index}]'
        if item.task_id in seen_unscheduled:
            errors.append(f'{prefix}: duplicate task')
        seen_unscheduled.add(item.task_id)
        remaining = expected_unscheduled.get(item.task_id)
        if remaining is None or type(item.minutes) is not int or item.minutes != remaining:
            errors.append(f'{prefix}: incorrect unallocated minutes or task')
            continue
        task = tasks[item.task_id]
        end = min(task.deadline, request.horizon_end)
        lengths = [_validation_minutes(max(a, task.earliest_start), min(b, end)) for a, b in final_free if max(a, task.earliest_start) < min(b, end)]
        if task.deadline <= request.now:
            reason = 'deadline_passed'
        elif task.earliest_start >= end:
            reason = 'outside_window'
        elif not lengths:
            reason = 'no_available_capacity'
        elif not task.splittable:
            reason = 'insufficient_contiguous_capacity'
            if max(lengths) >= remaining:
                errors.append(f'{prefix}: remaining contiguous work still fits')
        elif remaining >= request.parameters.min_block_minutes and max(lengths) < request.parameters.min_block_minutes:
            reason = 'below_min_block'
        else:
            reason = 'insufficient_capacity'
            if max(lengths) >= min(remaining, request.parameters.min_block_minutes):
                errors.append(f'{prefix}: remaining split work still fits')
        if tuple(item.reasons) != (reason,):
            errors.append(f'{prefix}.reasons: expected {reason}')
    if seen_unscheduled != set(expected_unscheduled):
        errors.append('unscheduled: must list exactly the unfinished eligible tasks')
    eligible = [t for t in request.tasks if t.status == 'active' and t.remaining_minutes > 0]
    complete = [t for t in eligible if totals[t.task_id] == t.remaining_minutes]
    requested = sum((t.remaining_minutes for t in eligible))
    scheduled = sum((totals[t.task_id] for t in eligible))
    available = sum((_validation_minutes(a, b) for a, b in _validation_segments(request)))
    weights = sum((t.importance for t in eligible))
    expected_metrics = {'eligible_tasks': len(eligible), 'fully_scheduled_tasks': len(complete), 'completion_ratio': len(complete) / len(eligible) if eligible else None, 'weighted_completion_ratio': sum((t.importance for t in complete)) / weights if weights else None, 'requested_minutes': requested, 'scheduled_minutes': scheduled, 'unscheduled_minutes': requested - scheduled, 'available_minutes': available, 'reserved_minutes': reserved, 'utilization_ratio': (scheduled + reserved) / available if available else None}
    if not isinstance(result.metrics, dict) or set(result.metrics) != set(expected_metrics):
        errors.append('metrics: incorrect field set')
    else:
        for key, expected in expected_metrics.items():
            actual = result.metrics[key]
            if expected is None:
                matches = actual is None
            elif type(expected) is int:
                matches = type(actual) is int and actual == expected
            else:
                matches = type(actual) in (int, float) and 0 <= actual <= 1 and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
            if not matches:
                errors.append(f'metrics.{key}: expected {expected}')
    return errors

# ==================== workspace.py ====================

"""Transactional personal workspace; planned minutes never mean completed work."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

class WorkspaceError(ValueError):
    """A rejected user operation leaves the workspace unchanged."""

def _workspace_utc_now(value: datetime | None=None) -> datetime:
    value = datetime.now(timezone.utc) if value is None else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise WorkspaceError('当前时间必须是带时区的 datetime。')
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise WorkspaceError('当前时间超出可用日期范围。') from exc

def _workspace_ceil_minute(value: datetime | None=None) -> datetime:
    value = _workspace_utc_now(value)
    try:
        return value.replace(second=0, microsecond=0) + (timedelta(minutes=1) if value.second or value.microsecond else timedelta())
    except OverflowError as exc:
        raise WorkspaceError('当前时间超出可用日期范围。') from exc

def _workspace_stamp(value: datetime) -> str:
    return value.isoformat(timespec='seconds')

def _workspace_validated(request: dict, result: dict | None=None):
    try:
        parsed = parse_request(request)
        if result is not None:
            errors = validate_result(parsed, parse_result(result))
            if errors:
                raise WorkspaceError('计划已过期或不满足约束：' + '; '.join(errors))
        return parsed
    except InputError as exc:
        raise WorkspaceError(str(exc)) from exc

class Workspace:

    def __init__(self, request: dict, result: dict | None=None):
        parsed = _workspace_validated(request, result)
        self._request = deepcopy(request)
        self._request['parameters'] = {'min_block_minutes': parsed.parameters.min_block_minutes, 'max_block_minutes': parsed.parameters.max_block_minutes}
        self._result = deepcopy(result)

    @classmethod
    def new(cls, now: datetime | None=None) -> 'Workspace':
        start = _workspace_ceil_minute(now)
        try:
            end = start + timedelta(days=7)
        except OverflowError as exc:
            raise WorkspaceError('新工作区的七天窗口超出可用日期范围。') from exc
        return cls({'schema_version': '1', 'request_id': str(uuid4()), 'input_revision': str(uuid4()), 'now': _workspace_stamp(start), 'timezone': 'UTC', 'horizon_end': _workspace_stamp(end), 'tasks': [], 'availability': [], 'busy_events': [], 'locked_blocks': [], 'strategy': 'edf', 'parameters': {'min_block_minutes': 15, 'max_block_minutes': 60}})

    @classmethod
    def from_document(cls, document: dict) -> 'Workspace':
        if not isinstance(document, dict) or set(document) != {'format', 'version', 'request', 'result'}:
            raise WorkspaceError('存档必须包含 format、version、request、result 四个字段。')
        if document['format'] != 'academic-scheduler-workspace' or type(document['version']) is not int or document['version'] != 1:
            raise WorkspaceError('不支持的工作区存档格式或版本。')
        if document['result'] is not None and (not isinstance(document['result'], dict)):
            raise WorkspaceError('存档 result 必须是计划对象或 null。')
        return cls(document['request'], document['result'])

    def to_document(self) -> dict:
        _workspace_validated(self._request, self._result)
        return {'format': 'academic-scheduler-workspace', 'version': 1, 'request': self.snapshot, 'result': self.result}

    @property
    def snapshot(self) -> dict:
        return deepcopy(self._request)

    @property
    def result(self) -> dict | None:
        return deepcopy(self._result)

    def _edit(self, operation: Callable[[dict], None]) -> None:
        candidate = self.snapshot
        operation(candidate)
        _workspace_validated(candidate)
        candidate['input_revision'] = str(uuid4())
        self._request, self._result = (candidate, None)

    @staticmethod
    def _find_task(request: dict, task_id: str) -> dict:
        for task in request['tasks']:
            if task['task_id'] == task_id:
                return task
        raise WorkspaceError('未找到该任务；请重新查看任务列表。')

    def add_task(self, *, title, estimated_minutes, remaining_minutes, importance, deadline, earliest_start, splittable) -> str:
        task_id = str(uuid4())
        self._edit(lambda request: request['tasks'].append({'task_id': task_id, 'title': title, 'estimated_minutes': estimated_minutes, 'remaining_minutes': remaining_minutes, 'importance': importance, 'deadline': deadline, 'earliest_start': earliest_start, 'splittable': splittable, 'status': 'active'}))
        return task_id

    def update_task(self, task_id: str, /, **fields) -> None:
        allowed = {'title', 'estimated_minutes', 'remaining_minutes', 'importance', 'deadline', 'earliest_start', 'splittable', 'status'}
        if not fields.keys() <= allowed:
            raise WorkspaceError('任务 ID 不可修改，且不能设置未支持的任务字段。')

        def update(request):
            self._find_task(request, task_id).update(fields)
        self._edit(update)

    def delete_task(self, task_id: str) -> None:

        def delete(request):
            self._find_task(request, task_id)
            request['tasks'] = [task for task in request['tasks'] if task['task_id'] != task_id]
            request['locked_blocks'] = [block for block in request['locked_blocks'] if block['task_id'] != task_id]
        self._edit(delete)

    def complete_task(self, task_id: str) -> None:

        def complete(request):
            self._find_task(request, task_id).update(remaining_minutes=0, status='completed')
            request['locked_blocks'] = [block for block in request['locked_blocks'] if block['task_id'] != task_id]
        self._edit(complete)

    def set_window(self, start: str, end: str, timezone: str) -> None:
        self._edit(lambda request: request.update(now=start, horizon_end=end, timezone=timezone))

    def set_strategy(self, strategy: str) -> None:
        self._edit(lambda request: request.update(strategy=strategy))

    def set_parameters(self, min_block_minutes: int, max_block_minutes: int) -> None:
        self._edit(lambda request: request.update(parameters={'min_block_minutes': min_block_minutes, 'max_block_minutes': max_block_minutes}))

    @staticmethod
    def _interval_kind(kind: str) -> None:
        if kind not in ('availability', 'busy_events'):
            raise WorkspaceError('时段类型必须是 availability 或 busy_events。')

    def add_interval(self, kind: str, start: str, end: str) -> None:
        self._interval_kind(kind)
        self._edit(lambda request: request[kind].append({'start': start, 'end': end}))

    def remove_interval(self, kind: str, index: int) -> None:
        self._interval_kind(kind)

        def remove(request):
            if type(index) is not int or not 0 <= index < len(request[kind]):
                raise WorkspaceError('时段序号无效；请重新查看时段列表。')
            del request[kind][index]
        self._edit(remove)

    def update_interval(self, kind: str, index: int, start: str, end: str) -> None:
        """Edit a calendar event atomically, preserving it on invalid input."""
        self._interval_kind(kind)

        def update(request):
            if type(index) is not int or not 0 <= index < len(request[kind]):
                raise WorkspaceError('时段序号无效；请重新查看时段列表。')
            request[kind][index] = {'start': start, 'end': end}
        self._edit(update)

    def _planning_snapshot(self, now: datetime | None) -> dict:
        candidate = self.snapshot
        current = max(parse_datetime(candidate['now'], 'now'), _workspace_ceil_minute(now))
        if current >= parse_datetime(candidate['horizon_end'], 'horizon_end'):
            raise WorkspaceError('规划窗口已经结束；请重新设置起止时间。')
        if any((parse_datetime(block['start'], 'locked_blocks.start') < current for block in candidate['locked_blocks'])):
            raise WorkspaceError('存在已开始或过去的锁定块；请先解除锁定，并手动核对任务剩余分钟后重排。')
        candidate['now'] = _workspace_stamp(current)
        return candidate

    @staticmethod
    def _run(candidate: dict) -> dict:
        parsed = _workspace_validated(candidate)
        result = schedule(parsed)
        errors = validate_result(parsed, result)
        if errors:
            raise WorkspaceError('计划约束校验失败：' + '; '.join(errors))
        try:
            return result_to_dict(result, parsed.timezone)
        except InputError as exc:
            raise WorkspaceError(str(exc)) from exc

    def generate(self, *, now: datetime | None=None) -> dict:
        candidate = self._planning_snapshot(now)
        candidate['input_revision'] = str(uuid4())
        result = self._run(candidate)
        self._request, self._result = (candidate, result)
        return self.result

    def compare(self, *, now: datetime | None=None) -> list[dict]:
        candidate = self._planning_snapshot(now)
        results = []
        for strategy in ('edf', 'importance', 'risk'):
            candidate['strategy'] = strategy
            results.append(self._run(candidate))
        return results

    def _calendar_snapshot(self, now: datetime | None) -> dict:
        candidate = self._planning_snapshot(now)
        candidate['availability'] = [{'start': candidate['now'], 'end': candidate['horizon_end']}]
        return candidate

    def generate_calendar(self, *, now: datetime | None=None) -> dict:
        """Plan in all free calendar slots; busy events and locks still apply."""
        candidate = self._calendar_snapshot(now)
        candidate['input_revision'] = str(uuid4())
        result = self._run(candidate)
        self._request, self._result = (candidate, result)
        return self.result

    def compare_calendar(self, *, now: datetime | None=None) -> list[dict]:
        candidate = self._calendar_snapshot(now)
        results = []
        for strategy in ('edf', 'importance', 'risk'):
            candidate['strategy'] = strategy
            results.append(self._run(candidate))
        return results

    def lock_block(self, index: int, *, now: datetime | None=None) -> str:
        if self._result is None:
            raise WorkspaceError('当前没有有效计划；请先生成计划。')
        _workspace_validated(self._request, self._result)
        result = self.result
        if type(index) is not int or not 0 <= index < len(result['blocks']):
            raise WorkspaceError('计划块序号无效；请重新查看计划。')
        block = result['blocks'][index]
        if block['source'] == 'locked':
            raise WorkspaceError('这个计划块已经锁定。')
        if parse_datetime(block['start'], 'block.start') <= _workspace_utc_now(now):
            raise WorkspaceError('只能锁定尚未开始的计划块；已开始的工作请手动核对剩余分钟。')
        candidate = self.snapshot
        locked_id = str(uuid4())
        candidate['locked_blocks'].append({'locked_id': locked_id, 'task_id': block['task_id'], 'start': block['start'], 'end': block['end']})
        candidate['input_revision'] = str(uuid4())
        block.update(source='locked', locked_id=locked_id)
        result['input_revision'] = candidate['input_revision']
        parsed = _workspace_validated(candidate)
        result['metrics'] = compute_metrics(parsed, parse_result(result).blocks)
        _workspace_validated(candidate, result)
        self._request, self._result = (candidate, result)
        return locked_id

    def unlock(self, locked_id: str) -> None:

        def remove(request):
            blocks = request['locked_blocks']
            if not any((block['locked_id'] == locked_id for block in blocks)):
                raise WorkspaceError('未找到该锁定块；请重新查看锁定列表。')
            request['locked_blocks'] = [block for block in blocks if block['locked_id'] != locked_id]
        self._edit(remove)

# ==================== storage.py ====================

"""Atomic workspace files with backups and cooperative optimistic concurrency."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

class StorageError(ValueError):
    """A storage operation was rejected without discarding in-memory work."""

def _storage_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StorageError(f'存档 JSON 含重复字段：{key}')
        result[key] = value
    return result

def _storage_constant(value):
    raise StorageError(f'存档 JSON 不允许 {value}。')

def _storage_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def _storage_decode(content: bytes) -> Workspace:
    try:
        document = json.loads(content.decode('utf-8-sig'), object_pairs_hook=_storage_pairs, parse_constant=_storage_constant)
        return Workspace.from_document(document)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StorageError(f'无法读取工作区存档：{exc}') from exc

class WorkspaceStore:

    def __init__(self, path):
        self.path = Path(path).expanduser().absolute()
        self._fingerprint: str | None = None

    def load(self) -> Workspace:
        try:
            content = self.path.read_bytes()
        except OSError as exc:
            raise StorageError(f'无法打开存档 {self.path}：{exc}') from exc
        workspace = _storage_decode(content)
        self._fingerprint = _storage_digest(content)
        return workspace

    def _check_current(self) -> bytes | None:
        try:
            current = self.path.read_bytes()
        except FileNotFoundError:
            if self._fingerprint is not None:
                raise StorageError('存档已被其他程序删除；请先核对磁盘文件。')
            return None
        if self._fingerprint is None:
            raise StorageError('存档已存在但尚未加载；请先加载，不能直接覆盖。')
        if _storage_digest(current) != self._fingerprint:
            raise StorageError('存档已被其他程序修改；请先重新加载或另存到新路径。')
        return current

    @staticmethod
    def _temporary(parent: Path, filename: str, content: bytes) -> Path:
        descriptor, name = tempfile.mkstemp(prefix=f'.{filename}.', suffix='.tmp', dir=parent)
        path = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def save(self, workspace: Workspace) -> None:
        try:
            document = workspace.to_document()
            Workspace.from_document(document)
            content = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')
        except (WorkspaceError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise StorageError(f'工作区验证失败，尚未保存：{exc}') from exc
        lock_path = Path(str(self.path) + '.lock')
        owned_lock = False
        temporary = []
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 384)
            except FileExistsError as exc:
                raise StorageError('存档正在被其他进程保存，或留有锁文件；请核对后重试。') from exc
            owned_lock = True
            with os.fdopen(descriptor, 'w', encoding='ascii') as stream:
                stream.write(str(os.getpid()))
            previous = self._check_current()
            pending = self._temporary(self.path.parent, self.path.name, content)
            temporary.append(pending)
            if previous is not None:
                backup = self._temporary(self.path.parent, self.path.name + '.bak', previous)
                temporary.append(backup)
                self._check_current()
                os.replace(backup, Path(str(self.path) + '.bak'))
            self._check_current()
            os.replace(pending, self.path)
            self._fingerprint = _storage_digest(content)
        except StorageError:
            raise
        except OSError as exc:
            raise StorageError(f'保存失败，内存数据仍保留：{exc}') from exc
        finally:
            for path in temporary:
                path.unlink(missing_ok=True)
            if owned_lock:
                lock_path.unlink(missing_ok=True)

# ==================== terminal.py ====================

"""Interactive, local-only interface for personal scheduling workspaces."""
from datetime import datetime, timezone
from pathlib import Path
import re
_terminal_REASONS = {'deadline_passed': '截止时间已过', 'outside_window': '任务不在规划窗口内', 'no_available_capacity': '没有可用时间', 'insufficient_contiguous_capacity': '没有足够的连续时间', 'below_min_block': '可用时段短于最小块长', 'insufficient_capacity': '可用时间不足'}

def _terminal_time(value, zone):
    """Return an offset-bearing ISO time; reject DST gaps and folds."""
    if re.fullmatch('\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}', value):
        local = datetime.strptime(value, '%Y-%m-%d %H:%M')
        tz = resolve_timezone(zone)
        choices = []
        for fold in (0, 1):
            candidate = local.replace(tzinfo=tz, fold=fold)
            if candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == local:
                if all((candidate.utcoffset() != c.utcoffset() for c in choices)):
                    choices.append(candidate)
        if not choices:
            raise ValueError('这个本地时间因夏令时调整而不存在，请重新输入。')
        if len(choices) > 1:
            raise ValueError('这个本地时间有两个可能的时差，请输入带偏移的 ISO 时间。')
        return choices[0].isoformat(timespec='minutes')
    parse_datetime(value, '时间')
    return value

def _terminal_prompt(label, default=None):
    suffix = f' [{default}]' if default is not None else ''
    answer = input(f'{label}{suffix}: ').strip()
    return str(default) if not answer and default is not None else answer

def _terminal_number(label, default=None):
    value = _terminal_prompt(label, default)
    try:
        return int(value)
    except ValueError:
        raise ValueError('请输入整数。') from None

def _terminal_yes(label):
    return _terminal_prompt(label + '（输入 y 确认）').lower() == 'y'

def _terminal_choose(items, label):
    if not items:
        raise ValueError('没有可选择的项目。')
    index = _terminal_number(label) - 1
    if index < 0 or index >= len(items):
        raise ValueError('序号超出范围。')
    return index

def _terminal_display_time(label, zone, default=None):
    return _terminal_time(_terminal_prompt(label + '（YYYY-MM-DD HH:MM 或带偏移 ISO）', default), zone)

class _terminal_Terminal:

    def __init__(self, store, workspace):
        self.store, self.workspace = (store, workspace)
        self.dirty = False

    def _edit(self, method, *args, **kwargs):
        result = method(*args, **kwargs)
        self.dirty = True
        return result

    def _tasks(self):
        tasks = self.workspace.snapshot['tasks']
        if not tasks:
            print('暂无任务。')
        for index, task in enumerate(tasks, 1):
            print(f"{index}. {task['title']} | 剩余 {task['remaining_minutes']}/{task['estimated_minutes']} 分钟 | 重要性 {task['importance']} | 截止 {task['deadline']} | {task.get('status', 'active')}")
        return tasks

    def _task_fields(self, task=None):
        task = task or {}
        zone = self.workspace.snapshot['timezone']
        title = _terminal_prompt('任务名称', task.get('title'))
        estimated = _terminal_number('总工作量（分钟）', task.get('estimated_minutes'))
        remaining = _terminal_number('剩余工作量（分钟）', task.get('remaining_minutes'))
        importance = _terminal_number('重要性（1-5）', task.get('importance'))
        deadline = _terminal_display_time('截止时间', zone, task.get('deadline'))
        earliest = _terminal_display_time('最早开始', zone, task.get('earliest_start'))
        default = ('y' if task['splittable'] else 'n') if 'splittable' in task else None
        split = _terminal_prompt('允许拆分（y/n）', default).lower()
        if split not in ('y', 'n'):
            raise ValueError('请输入 y 或 n。')
        if estimated < 0 or remaining < 0:
            raise ValueError('总工作量和剩余工作量不能为负数。')
        if remaining > estimated:
            raise ValueError('剩余工作量不能大于总工作量。')
        if not 1 <= importance <= 5:
            raise ValueError('重要性必须在 1 到 5 之间。')
        return dict(title=title, estimated_minutes=estimated, remaining_minutes=remaining, importance=importance, deadline=deadline, earliest_start=earliest, splittable=split == 'y')

    def tasks(self):
        while True:
            print('\n任务管理：1列表 2新增 3编辑 4删除 5记录剩余分钟 6标记完成 0返回')
            try:
                choice = _terminal_prompt('选择')
                if choice == '0':
                    return
                if choice == '1':
                    self._tasks()
                    continue
                if choice == '2':
                    self._edit(self.workspace.add_task, **self._task_fields())
                    print('任务已新增。')
                    continue
                if choice not in ('3', '4', '5', '6'):
                    raise ValueError('请选择菜单中的序号。')
                tasks = self._tasks()
                task = tasks[_terminal_choose(tasks, '任务序号')]
                ident = task['task_id']
                if choice == '3':
                    self._edit(self.workspace.update_task, ident, **self._task_fields(task))
                elif choice == '4':
                    if not _terminal_yes('删除任务及其所有锁定'):
                        continue
                    self._edit(self.workspace.delete_task, ident)
                elif choice == '5':
                    self._edit(self.workspace.update_task, ident, remaining_minutes=_terminal_number('实际剩余分钟', task['remaining_minutes']))
                elif _terminal_yes('标记完成并移除其锁定'):
                    self._edit(self.workspace.complete_task, ident)
                else:
                    continue
                print('任务已更新。')
            except (ValueError, OSError) as exc:
                print(f'操作失败：{exc}')

    def _intervals(self, kind):
        items = self.workspace.snapshot[kind]
        print('可用时段：' if kind == 'availability' else '忙碌时段：')
        if not items:
            print('  暂无。')
        for i, item in enumerate(items, 1):
            print(f"{i}. {item['start']} → {item['end']}")
        return items

    def times(self):
        while True:
            print('\n时间设置：1窗口/时区 2列时段 3新增可用 4删除可用 5新增忙碌 6删除忙碌 0返回')
            try:
                choice = _terminal_prompt('选择')
                if choice == '0':
                    return
                snap = self.workspace.snapshot
                if choice == '1':
                    zone = _terminal_prompt('IANA 时区', snap['timezone'])
                    resolve_timezone(zone)
                    start = _terminal_display_time('规划开始', zone, snap['now'])
                    end = _terminal_display_time('规划结束', zone, snap['horizon_end'])
                    self._edit(self.workspace.set_window, start, end, zone)
                elif choice == '2':
                    self._intervals('availability')
                    self._intervals('busy_events')
                    continue
                elif choice in ('3', '5'):
                    kind = 'availability' if choice == '3' else 'busy_events'
                    start = _terminal_display_time('开始', snap['timezone'])
                    end = _terminal_display_time('结束', snap['timezone'])
                    self._edit(self.workspace.add_interval, kind, start, end)
                elif choice in ('4', '6'):
                    kind = 'availability' if choice == '4' else 'busy_events'
                    index = _terminal_choose(self._intervals(kind), '时段序号')
                    self._edit(self.workspace.remove_interval, kind, index)
                else:
                    raise ValueError('请选择菜单中的序号。')
                print('时间设置已更新。')
            except (ValueError, OSError) as exc:
                print(f'操作失败：{exc}')

    def strategy(self):
        snap = self.workspace.snapshot
        print('策略：1 EDF（截止优先） 2 Importance（重要性优先） 3 Risk（风险优先）')
        choice = _terminal_prompt('选择策略（回车保留）', {'edf': '1', 'importance': '2', 'risk': '3'}[snap['strategy']])
        options = {'1': 'edf', '2': 'importance', '3': 'risk'}
        if choice not in options:
            raise ValueError('请选择 1、2 或 3。')
        minimum = _terminal_number('最短自动块长（分钟）', snap['parameters']['min_block_minutes'])
        maximum = _terminal_number('最长自动块长（分钟）', snap['parameters']['max_block_minutes'])
        if minimum <= 0 or maximum < minimum:
            raise ValueError('块长必须为正整数，且最短不能大于最长。')
        if options[choice] != snap['strategy']:
            self._edit(self.workspace.set_strategy, options[choice])
        if minimum != snap['parameters']['min_block_minutes'] or maximum != snap['parameters']['max_block_minutes']:
            self._edit(self.workspace.set_parameters, minimum, maximum)
        print('策略和块长已设置。')

    def show_result(self, result=None):
        result = result if result is not None else self.workspace.result
        if result is None:
            print('暂无计划，请先生成。')
            return
        names = {t['task_id']: t['title'] for t in self.workspace.snapshot['tasks']}
        print(f"计划（{result['strategy']}）：")
        if not result['blocks']:
            print('  没有安排时间块。')
        for i, block in enumerate(result['blocks'], 1):
            name = names.get(block['task_id'], '固定预留')
            locked = ' [已锁定]' if block['source'] == 'locked' else ''
            print(f"{i}. {name} | {block['start']} → {block['end']} | {block['minutes']} 分钟{locked}")
        if any((parse_datetime(block['start'], '时间块开始') <= datetime.now(timezone.utc) for block in result['blocks'])):
            print('计划包含已开始的时间块，请核对实际进度和剩余分钟，再按需重新排计划。')
        for item in result['unscheduled']:
            reasons = '、'.join((_terminal_REASONS.get(reason, reason) for reason in item['reasons']))
            print(f"未排：{names.get(item['task_id'], item['task_id'])}，{item['minutes']} 分钟（{reasons}）")
        m = result['metrics']
        print(f"已安排 {m['scheduled_minutes']} 分钟；未排 {m['unscheduled_minutes']} 分钟；完整任务 {m['fully_scheduled_tasks']}/{m['eligible_tasks']}。")

    def locks(self):
        while True:
            print('\n锁定管理：1列锁定 2从计划锁定 3解锁 0返回')
            try:
                choice = _terminal_prompt('选择')
                if choice == '0':
                    return
                locks = self.workspace.snapshot['locked_blocks']
                if choice in ('1', '3'):
                    if not locks:
                        print('暂无锁定。')
                    for i, block in enumerate(locks, 1):
                        names = {t['task_id']: t['title'] for t in self.workspace.snapshot['tasks']}
                        print(f"{i}. {names.get(block['task_id'], '固定预留')} | {block['start']} → {block['end']}")
                    if choice == '3':
                        lock = locks[_terminal_choose(locks, '锁定序号')]
                        self._edit(self.workspace.unlock, lock['locked_id'])
                        print('已解锁，旧计划已失效。')
                elif choice == '2':
                    result = self.workspace.result
                    self.show_result(result)
                    blocks = result['blocks'] if result is not None else []
                    index = _terminal_choose(blocks, '计划时间块序号')
                    self._edit(self.workspace.lock_block, index)
                    print('已锁定。')
                else:
                    raise ValueError('请选择菜单中的序号。')
            except (ValueError, OSError) as exc:
                print(f'操作失败：{exc}')

    def save(self):
        self.store.save(self.workspace)
        self.dirty = False
        print(f'已保存到 {self.store.path}。')

    def save_as(self):
        path = _terminal_prompt('新存档路径')
        if not path:
            raise ValueError('请输入新存档路径。')
        store = WorkspaceStore(Path(path))
        store.save(self.workspace)
        self.store, self.dirty = (store, False)
        print(f'已另存到 {self.store.path}。')

    def run(self):
        while True:
            snap = self.workspace.snapshot
            print(f"\n存档：{self.store.path} | {('未保存' if self.dirty else '无未保存更改')} | 时区：{snap['timezone']}")
            print(f"规划窗口：{snap['now']} → {snap['horizon_end']}")
            print('1任务管理 2时间设置 3策略/块长 4生成/重排 5查看计划 6锁定管理 7比较策略 8保存 9重新加载 10另存为 0退出')
            try:
                choice = _terminal_prompt('选择')
                if choice == '1':
                    self.tasks()
                elif choice == '2':
                    self.times()
                elif choice == '3':
                    self.strategy()
                elif choice == '4':
                    self._edit(self.workspace.generate)
                    print('计划已生成。请根据实际进度记录剩余分钟。')
                    self.show_result()
                elif choice == '5':
                    self.show_result()
                elif choice == '6':
                    self.locks()
                elif choice == '7':
                    for result in self.workspace.compare():
                        self.show_result(result)
                    print('比较未更改当前计划。')
                elif choice == '8':
                    self.save()
                elif choice == '10':
                    self.save_as()
                elif choice == '9':
                    if self.dirty and (not _terminal_yes('放弃未保存更改并重新加载')):
                        continue
                    loaded = self.store.load()
                    self.workspace, self.dirty = (loaded, False)
                    print('已重新加载。')
                elif choice == '0':
                    if not self.dirty:
                        return 0
                    action = _terminal_prompt('有未保存更改：保存(s)、放弃(d)、取消(c)').lower()
                    if action == 's':
                        self.save()
                        return 0
                    if action == 'd':
                        print('已放弃未保存更改。')
                        return 0
                    if action != 'c':
                        print('请输入 s、d 或 c。')
                else:
                    print('请选择菜单中的序号。')
            except (ValueError, OSError) as exc:
                print(f'操作失败：{exc}')

def run_terminal(data_path: str | Path | None=None) -> int:
    path = Path(data_path) if data_path is not None else Path.cwd() / 'work' / 'demo1-data' / 'workspace.json'
    store = WorkspaceStore(path)
    try:
        workspace = store.load() if path.exists() else Workspace.new()
    except (ValueError, OSError) as exc:
        print(f'无法加载存档：{exc}')
        return 1
    terminal = _terminal_Terminal(store, workspace)
    try:
        return terminal.run()
    except (EOFError, KeyboardInterrupt):
        print('\n输入已中断。' + ('更改尚未保存。' if terminal.dirty else ''))
        return 1

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

def _cli_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CLIError(f'duplicate JSON key: {key}')
        result[key] = value
    return result

def _cli_constant(value: str) -> None:
    raise CLIError(f'invalid JSON constant: {value}')

def _cli_read_json(path: str, *, stdin_allowed: bool=True) -> object:
    if path == '-':
        if not stdin_allowed:
            raise CLIError('result file cannot be stdin')
        data = sys.stdin.read().lstrip('\ufeff')
    else:
        data = Path(path).read_text(encoding='utf-8-sig')
    try:
        return json.loads(data, object_pairs_hook=_cli_pairs, parse_constant=_cli_constant)
    except (ValueError, RecursionError) as exc:
        raise CLIError(f'invalid JSON: {exc}') from exc

def _cli_check_output(output: str, inputs: list[str]) -> None:
    target = Path(output)
    for item in inputs:
        if item == '-':
            continue
        source = Path(item)
        if target.resolve() == source.resolve():
            raise CLIError('output path must differ from input path')
        if target.exists() and source.exists() and os.path.samefile(target, source):
            raise CLIError('output path must differ from input path')

def _cli_write_json(value: object, output: str | None, inputs: list[str]) -> None:
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
    if output is None:
        sys.stdout.write(text)
        return
    _cli_check_output(output, inputs)
    target = Path(output)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', dir=target.parent, prefix=f'.{target.name}.', suffix='.tmp', delete=False) as stream:
            temporary = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        _cli_check_output(output, inputs)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)

def _cli_parser() -> Parser:
    parser = Parser(prog='academic-scheduler')
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for name in ('schedule', 'compare'):
        command = commands.add_parser(name)
        command.add_argument('input')
        command.add_argument('--output')
    command = commands.add_parser('validate')
    command.add_argument('input')
    command.add_argument('result')
    return parser

def _cli_error(code: str, message: str, status: int) -> int:
    sys.stderr.write(json.dumps({'error': {'code': code, 'message': message}}, ensure_ascii=True) + '\n')
    return status

def _cli_main(argv: list[str] | None=None) -> int:
    try:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        args = _cli_parser().parse_args(argv)
        request = parse_request(_cli_read_json(args.input))
        if args.command == 'validate':
            result = parse_result(_cli_read_json(args.result, stdin_allowed=False))
            errors = validate_result(request, result)
            if errors:
                return _cli_error('validation_failed', '; '.join(errors), 3)
            _cli_write_json({'valid': True}, None, [args.input, args.result])
            return 0
        results = []
        strategies = (request.strategy,) if args.command == 'schedule' else ('edf', 'importance', 'risk')
        for strategy in strategies:
            variant = replace(request, strategy=strategy)
            result = schedule(variant)
            errors = validate_result(variant, result)
            if errors:
                return _cli_error('validation_failed', '; '.join(errors), 3)
            results.append(result_to_dict(result, variant.timezone))
        value = results[0] if args.command == 'schedule' else {'request_id': request.request_id, 'input_revision': request.input_revision, 'results': results}
        _cli_write_json(value, args.output, [args.input])
        return 0
    except (CLIError, InputError, json.JSONDecodeError, UnicodeError, OSError) as exc:
        return _cli_error('input_error', str(exc), 2)
    except Exception as exc:
        return _cli_error('internal_error', str(exc), 1)

# ==================== demo_cases.py ====================

"""Optional fixed synthetic snapshots, displayed in UTC."""
DEMO_EXAMPLES = {'feasible': {'schema_version': '1', 'request_id': 'demo-feasible-2026-11-13', 'input_revision': 'demo-feasible-r1', 'now': '2026-11-13T09:00:00-06:00', 'timezone': 'UTC', 'horizon_end': '2026-11-13T12:00:00-06:00', 'tasks': [{'task_id': 'read-chapter', 'title': '阅读课程章节', 'estimated_minutes': 90, 'remaining_minutes': 90, 'importance': 4, 'deadline': '2026-11-13T11:00:00-06:00', 'earliest_start': '2026-11-13T09:00:00-06:00', 'splittable': True}, {'task_id': 'submit-notes', 'title': '整理并提交课堂笔记', 'estimated_minutes': 60, 'remaining_minutes': 60, 'importance': 3, 'deadline': '2026-11-13T12:00:00-06:00', 'earliest_start': '2026-11-13T09:00:00-06:00', 'splittable': True}], 'availability': [{'start': '2026-11-13T09:00:00-06:00', 'end': '2026-11-13T12:00:00-06:00'}], 'busy_events': [], 'locked_blocks': [], 'strategy': 'edf', 'parameters': {'min_block_minutes': 15, 'max_block_minutes': 60}}, 'overloaded': {'schema_version': '1', 'request_id': 'demo-overloaded-2026-11-13', 'input_revision': 'demo-overloaded-r1', 'now': '2026-11-13T09:00:00-06:00', 'timezone': 'UTC', 'horizon_end': '2026-11-13T11:00:00-06:00', 'tasks': [{'task_id': 'lab-report', 'title': '完成实验报告', 'estimated_minutes': 90, 'remaining_minutes': 90, 'importance': 5, 'deadline': '2026-11-13T10:00:00-06:00', 'earliest_start': '2026-11-13T09:00:00-06:00', 'splittable': True}, {'task_id': 'review-lecture', 'title': '复习讲义', 'estimated_minutes': 90, 'remaining_minutes': 90, 'importance': 3, 'deadline': '2026-11-13T11:00:00-06:00', 'earliest_start': '2026-11-13T09:00:00-06:00', 'splittable': True}], 'availability': [{'start': '2026-11-13T09:00:00-06:00', 'end': '2026-11-13T11:00:00-06:00'}], 'busy_events': [], 'locked_blocks': [], 'strategy': 'edf', 'parameters': {'min_block_minutes': 15, 'max_block_minutes': 60}}, 'replan': {'schema_version': '1', 'request_id': 'demo-replan-2026-11-13', 'input_revision': 'demo-replan-r1', 'now': '2026-11-13T14:00:00-06:00', 'timezone': 'UTC', 'horizon_end': '2026-11-13T18:00:00-06:00', 'tasks': [{'task_id': 'write-draft', 'title': '撰写论文初稿', 'estimated_minutes': 90, 'remaining_minutes': 90, 'importance': 5, 'deadline': '2026-11-13T18:00:00-06:00', 'earliest_start': '2026-11-13T14:00:00-06:00', 'splittable': True}, {'task_id': 'prepare-quiz', 'title': '准备小测', 'estimated_minutes': 60, 'remaining_minutes': 60, 'importance': 3, 'deadline': '2026-11-13T18:00:00-06:00', 'earliest_start': '2026-11-13T14:00:00-06:00', 'splittable': True}], 'availability': [{'start': '2026-11-13T14:00:00-06:00', 'end': '2026-11-13T18:00:00-06:00'}], 'busy_events': [], 'locked_blocks': [{'locked_id': 'keep-draft-session', 'task_id': 'write-draft', 'start': '2026-11-13T15:00:00-06:00', 'end': '2026-11-13T15:30:00-06:00'}, {'locked_id': 'reserved-appointment', 'task_id': None, 'start': '2026-11-13T16:00:00-06:00', 'end': '2026-11-13T16:30:00-06:00'}], 'strategy': 'importance', 'parameters': {'min_block_minutes': 15, 'max_block_minutes': 60}}}

# ==================== demo.py ====================

"""Optional fixed synthetic examples, separate from the interactive product."""
from dataclasses import replace
_demo_CASE_TITLES = {'feasible': '可行案例', 'overloaded': '超载案例', 'replan': '锁定重排案例'}
_demo_REASON_TITLES = {'deadline_passed': '截止时间已到', 'outside_window': '任务窗口为空', 'no_available_capacity': '任务窗口已无空闲容量', 'insufficient_contiguous_capacity': '没有足够连续容量', 'below_min_block': '剩余空档短于最小块长', 'insufficient_capacity': '剩余容量不足'}

class DemoValidationError(RuntimeError):
    pass

def run_demo(example='all', strategy='all'):
    """Run optional synthetic examples without changing the personal workspace."""
    names = tuple(DEMO_EXAMPLES) if example == 'all' else (example,)
    strategies = ('edf', 'importance', 'risk') if strategy == 'all' else (strategy,)
    cases = []
    for name in names:
        request = parse_request(DEMO_EXAMPLES[name])
        results = []
        for selected in strategies:
            variant = replace(request, strategy=selected)
            result = schedule(variant)
            errors = validate_result(variant, result)
            if errors:
                raise DemoValidationError('; '.join(errors))
            results.append(result_to_dict(result, variant.timezone))
        cases.append({'name': name, 'title': _demo_CASE_TITLES[name], 'results': results})
    return {'demo': 'Demo 1', 'timezone': 'UTC', 'cases': cases}

def print_demo(report):
    print('Demo 1 — 合成案例演示（UTC）')
    print('个人任务请运行无参数入口进入工作区；以下指标表示计划安排。')
    for case in report['cases']:
        print(f"\n{case['title']} ({case['name']})")
        for result in case['results']:
            metrics = result['metrics']
            print(f"  {result['strategy']:10} 已排 {metrics['scheduled_minutes']}/{metrics['requested_minutes']} 分钟；未排 {metrics['unscheduled_minutes']} 分钟；完整安排 {metrics['fully_scheduled_tasks']}/{metrics['eligible_tasks']} 项；校验通过")
        selected = case['results'][0]
        for block in selected['blocks']:
            task = block['task_id'] or '固定预留'
            locked = f"，锁定 {block['locked_id']}" if block['source'] == 'locked' else ''
            print(f"    {block['start']} → {block['end']}  {task}  {block['minutes']} 分钟{locked}")
        for item in selected['unscheduled']:
            reasons = '；'.join((_demo_REASON_TITLES[r] for r in item['reasons']))
            print(f"    未排：{item['task_id']}，{item['minutes']} 分钟，{reasons}")
    print('\n演示完成：所有结果通过独立约束校验。')

# ==================== gui.py ====================

def _load_gui_runner():
    """Local desktop interface for the academic scheduler."""
    from datetime import datetime, timedelta, time, timezone
    from pathlib import Path
    from uuid import uuid4
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import filedialog, messagebox, simpledialog, ttk
    _gui_EN = {'学业任务规划': 'Academic Task Planner', '保存': 'Save', '另存为': 'Save as', '打开存档': 'Open workspace', '重新加载': 'Reload', '任务': 'Tasks', '时间': 'Time', '计划': 'Plan', '剩余/总分钟': 'Remaining / total min', '重要性': 'Priority', '截止': 'Deadline', '状态': 'Status', '任务信息': 'Task details', '任务名称': 'Title', '总分钟': 'Total minutes', '剩余分钟': 'Remaining minutes', '重要性 1–5': 'Priority 1–5', '最早开始': 'Earliest start', '截止时间': 'Deadline', '允许拆分': 'Allow splitting', '时间可输入 YYYY-MM-DD HH:MM（当前时区）或带偏移 ISO 时间。': 'Use YYYY-MM-DD HH:MM in the current time zone, or ISO time with an offset.', '清空表单': 'Clear form', '新增任务': 'Add task', '保存选中任务修改': 'Update selected task', '记录剩余分钟': 'Record remaining', '标记完成': 'Mark complete', '删除任务': 'Delete task', '规划窗口与时区': 'Planning window and time zone', 'IANA 时区': 'IANA time zone', '开始': 'Start', '结束': 'End', '应用窗口': 'Apply window', '本地时间格式 YYYY-MM-DD HH:MM；夏令时歧义时请使用带偏移的 ISO 时间。': 'Local time: YYYY-MM-DD HH:MM. For ambiguous daylight-saving times, include an ISO offset.', '类型': 'Type', '添加可用时段': 'Add availability', '添加忙碌时段': 'Add busy time', '删除选中时段': 'Remove selected interval', '调度设置': 'Scheduling settings', '策略': 'Strategy', '最短块（分钟）': 'Minimum block (min)', '最长块（分钟）': 'Maximum block (min)', '应用设置': 'Apply settings', '生成 / 重新规划': 'Generate / replan', '比较三种策略': 'Compare strategies', '锁定选中计划块': 'Lock selected block', '解锁选中锁定块': 'Unlock selected block', '分钟': 'min', '未排任务与指标': 'Unscheduled tasks and metrics', '解锁时在上方计划选择锁定块；若计划已失效，请从下方锁定列表选择。': 'To unlock, select a locked plan block above or select it from the lock list below.', '锁定任务': 'Locked task', '操作失败': 'Action failed', '请先选择一行。': 'Select a row first.', '任务信息有误': 'Invalid task', '请选择任务': 'Select a task', '记录进度': 'Record progress', '实际剩余分钟：': 'Actual remaining minutes:', '确认完成该任务？其锁定时间块也会移除。': 'Mark this task complete? Its locked blocks will also be removed.', '确认删除该任务及其锁定时间块？': 'Delete this task and its locked blocks?', '时间有误': 'Invalid time', '请选择时段': 'Select an interval', '设置有误': 'Invalid settings', '请选择计划块': 'Select a plan block', '请选择锁定块': 'Select a locked block', '请在锁定列表选择一行。': 'Select a row in the lock list.', '所选时间块尚未锁定。': 'The selected block is not locked.', '比较失败': 'Comparison failed', '策略比较（不更改当前计划）': 'Strategy comparison (current plan unchanged)', '保存失败': 'Save failed', '另存失败': 'Save as failed', '加载失败': 'Load failed', '无法加载存档': 'Could not load workspace', '另存为新文件': 'Save as a new file', '工作区': 'Workspace', '所有文件': 'All files', '打开放弃': 'Discard', '放弃更改': 'Discard changes', '有未保存更改，确认放弃并加载其他存档？': 'Discard unsaved changes and load another workspace?', '打开工作区': 'Open workspace', '未保存更改': 'Unsaved changes', '保存更改后退出？选择“否”放弃更改，选择“取消”继续编辑。': 'Save changes before quitting? Choose No to discard or Cancel to keep editing.', '总分钟、剩余分钟和重要性必须是整数。': 'Total, remaining minutes and priority must be integers.', '工作分钟不能为负数。': 'Minutes cannot be negative.', '剩余分钟不能大于总分钟。': 'Remaining minutes cannot exceed total minutes.', '重要性必须在 1 到 5 之间。': 'Priority must be between 1 and 5.', '块长须为正整数，最短不能大于最长。': 'Block lengths must be positive and the minimum cannot exceed the maximum.', '请选择策略。': 'Select a strategy.', '这个本地时间因夏令时调整而不存在，请重新输入。': 'This local time does not exist due to daylight saving time. Enter another time.', '这个本地时间有两个可能的时差，请输入带偏移的 ISO 时间。': 'This local time is ambiguous. Enter an ISO time with an explicit offset.', '暂无计划。请先设置可用时段并生成。': 'No plan yet. Create tasks and generate a plan from free calendar slots.', '固定预留': 'Reserved', '已锁定': 'Locked', '自动': 'Automatic', '可用': 'Available', '忙碌': 'Busy', '未保存': 'Unsaved', '无未保存更改': 'No unsaved changes', '存档：': 'Workspace: ', '时区：': 'Time zone: ', '策略：': 'Strategy: ', '已安排：': 'Scheduled: ', '未排：': 'Unscheduled: ', '完整任务：': 'Fully scheduled: ', '完成比例：': 'Completion ratio: ', '加权完成比例：': 'Weighted completion: ', '可用：': 'Available: ', '预留：': 'Reserved: ', '利用率：': 'Utilization: ', ' 分钟': ' min', '包含已开始的时间块，请核对实际进度与剩余分钟，再按需重新规划。': 'Some blocks have started. Check actual progress and remaining minutes before replanning.', '截止时间已过': 'Deadline passed', '任务不在规划窗口内': 'Outside planning window', '没有可用时间': 'No available time', '没有足够的连续时间': 'Insufficient contiguous time', '可用时段短于最小块长': 'Available intervals are below the minimum block length', '可用时间不足': 'Insufficient available time', '存档 JSON 含重复字段：': 'Duplicate JSON field: ', '存档 JSON 不允许 ': 'Invalid JSON constant: ', '无法读取工作区存档：': 'Cannot read workspace: ', '无法打开存档 ': 'Cannot open workspace ', '存档已被其他程序删除；请先核对磁盘文件。': 'The workspace was deleted externally. Check the file before saving.', '存档已存在但尚未加载；请先加载，不能直接覆盖。': 'The file already exists and was not loaded. Open it first or choose a new path.', '存档已被其他程序修改；请先重新加载或另存到新路径。': 'The workspace changed externally. Reload or save to a new path.', '工作区验证失败，尚未保存：': 'Workspace validation failed; nothing saved: ', '存档正在被其他进程保存，或留有锁文件；请核对后重试。': 'Another process is saving, or a lock file remains. Check and retry.', '保存失败，内存数据仍保留：': 'Save failed; your in-memory changes remain: ', '当前时间必须是带时区的 datetime。': 'The current time must include a time zone.', '当前时间超出可用日期范围。': 'The current time is out of range.', '计划已过期或不满足约束：': 'The plan is stale or violates constraints: ', '新工作区的七天窗口超出可用日期范围。': 'The new seven-day window is out of range.', '存档必须包含 format、version、request、result 四个字段。': 'The workspace must contain format, version, request, and result.', '不支持的工作区存档格式或版本。': 'Unsupported workspace format or version.', '存档 result 必须是计划对象或 null。': 'Workspace result must be a plan or null.', '未找到该任务；请重新查看任务列表。': 'Task not found. Refresh the task list.', '任务 ID 不可修改，且不能设置未支持的任务字段。': 'Task IDs cannot be changed and unsupported fields are not allowed.', '时段类型必须是 availability 或 busy_events。': 'Invalid interval type.', '时段序号无效；请重新查看时段列表。': 'Invalid interval selection.', '规划窗口已经结束；请重新设置起止时间。': 'The planning window has ended. Set a new window.', '存在已开始或过去的锁定块；请先解除锁定，并手动核对任务剩余分钟后重排。': 'A locked block has started or passed. Unlock it and check remaining work before replanning.', '计划约束校验失败：': 'Plan validation failed: ', '当前没有有效计划；请先生成计划。': 'There is no valid plan. Generate one first.', '计划块序号无效；请重新查看计划。': 'Invalid plan block selection.', '这个计划块已经锁定。': 'This block is already locked.', '只能锁定尚未开始的计划块；已开始的工作请手动核对剩余分钟。': 'Only future blocks can be locked. Check remaining work for blocks that have started.', '未找到该锁定块；请重新查看锁定列表。': 'Lock not found. Refresh the lock list.'}
    _gui_EN.update({'表单尚未应用': 'Unapplied form changes', '请先应用或清空表单中的更改，再保存。': 'Apply or clear form changes before saving.', '有尚未应用的表单内容，确认放弃？': 'Discard unapplied form changes?', '任务表单有未应用的更改，确认放弃并选择其他任务？': 'Discard unapplied task changes and select another task?'})
    _gui_EN.update({'文件': 'File', '今天': 'Today', '规划设置': 'Planning settings', '＋ 新建任务': '＋ Create task', '编辑': 'Edit', '日': 'Day', '周': 'Week', '高级选项': 'Advanced options', '取消': 'Cancel', '删除': 'Delete', '忙碌时间': 'Busy time', '计划块': 'Plan block', '解锁': 'Unlock', '锁定时间': 'Lock time', '编辑任务': 'Edit task', '点击空白添加忙碌时间 · 点击色块查看详情': 'Click an empty slot to add busy time · Click a block for details', '按日历空白自动安排；忙碌时间与锁定块会被保留。': 'Schedule in free calendar slots. Busy time and locked blocks are preserved.'})
    _gui_EN.update({'在整个规划范围的空白时间安排': 'Free slots across the planning window'})
    _gui_ZH_ERRORS = {'must be ISO 8601 with explicit minute offset and zero seconds/microseconds': '须为带明确时差且秒数为零的 ISO 时间', 'must be a nonempty string without surrounding whitespace': '不能为空，且首尾不能有空格', 'must contain valid Unicode scalar values': '必须包含有效字符', 'must not be after deadline': '不得晚于截止时间', 'must be after now': '必须晚于规划开始时间', 'start must be before end': '开始时间必须早于结束时间', 'must lie fully within [now, horizon_end]': '必须完全位于规划窗口内', 'must be covered by merged availability': '必须在可用时段内', 'must not overlap busy_events': '不能与忙碌时段重叠', 'must not overlap another locked block': '不能与其他锁定块重叠', 'must reference an active task with remaining work': '必须关联仍有剩余工作的有效任务', "must lie within the task's earliest_start/deadline": '必须在任务最早开始与截止时间之间', 'invalid UTC offset': 'UTC 偏移无效', 'must be zero for completed/deleted tasks': '已完成或已删除任务的剩余分钟必须为零', 'must be an integer >= ': '必须为整数，且不少于 ', ' and <= ': '，且不大于 '}

    def _gui_english(text):
        text = str(text)
        if text in _gui_EN:
            return _gui_EN[text]
        for source in sorted(_gui_EN, key=len, reverse=True):
            text = text.replace(source, _gui_EN[source])
        return text

    class _gui_Dialogs:

        def __init__(self, gui):
            self.gui = gui

        def __getattr__(self, name):
            function = getattr(messagebox, name)

            def translated(title, message, **kwargs):
                if self.gui.language.get() != 'English':
                    for source, replacement in _gui_ZH_ERRORS.items():
                        message = str(message).replace(source, replacement)
                return function(self.gui.tr(title), self.gui.tr(message), **kwargs)
            return translated

    class SchedulerGUI:

        def __init__(self, root, store, workspace):
            self.root, self.store, self.workspace = (root, store, workspace)
            self.dirty = False
            self._suppress_selection = False
            self._task_baseline = None
            self._last_snapshot = None
            self.language = tk.StringVar(value='English')
            self.msg = _gui_Dialogs(self)
            self.view_date = parse_datetime(workspace.snapshot['now'], 'now').astimezone(resolve_timezone(workspace.snapshot['timezone'])).date()
            self.view_mode = tk.StringVar(value='Week')
            self._dialog = None
            root.geometry('1240x800')
            root.minsize(960, 640)
            root.protocol('WM_DELETE_WINDOW', self.close)
            style = ttk.Style(root)
            style.configure('Primary.TButton', padding=(18, 9))
            style.configure('TButton', padding=(8, 5))
            self._build_calendar_ui()
            self._capture_text()
            self.refresh()
            self.change_language()

        def tr(self, text):
            if self.language.get() != 'English':
                return str(text)
            return _gui_english(text)

        def _capture_text(self):
            previous = {str(widget): text for widget, text in getattr(self, '_widget_text', []) if widget.winfo_exists()}
            self._widget_text = []
            previous_headings = {(str(tree), col): text for tree, col, text in getattr(self, '_headings', []) if tree.winfo_exists()}
            self._headings = []
            self._tabs = []

            def visit(widget):
                if isinstance(widget, ttk.Notebook):
                    self._tabs.extend(((widget, tab, widget.tab(tab, 'text')) for tab in widget.tabs()))
                if isinstance(widget, ttk.Treeview):
                    self._headings.extend(((widget, col, previous_headings.get((str(widget), col), widget.heading(col, 'text'))) for col in widget['columns']))
                try:
                    text = widget.cget('text')
                    if text and (not getattr(widget, '_user_content', False)):
                        self._widget_text.append((widget, previous.get(str(widget), text)))
                except tk.TclError:
                    pass
                for child in widget.winfo_children():
                    visit(child)
            visit(self.root)

        def change_language(self, event=None):
            self.root.title(self.tr('学业任务规划'))
            for widget, text in self._widget_text:
                if widget.winfo_exists():
                    widget.configure(text=self.tr(text))
            for tree, col, text in self._headings:
                if tree.winfo_exists():
                    tree.heading(col, text=self.tr(text))
            for index, (label, command) in enumerate(self._file_actions):
                self.file_menu.entryconfigure(index, label=self.tr(label))
            self.menu.entryconfigure(0, label=self.tr('文件'))
            self.refresh()

        def _tree(self, parent, columns, height=7, expand=True):
            frame = ttk.Frame(parent)
            frame.pack(fill='both' if expand else 'x', expand=expand, pady=5)
            tree = ttk.Treeview(frame, columns=[key for key, _, _ in columns], show='headings', height=height, selectmode='browse')
            scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            for key, title, width in columns:
                tree.heading(key, text=title)
                tree.column(key, width=width, minwidth=60, stretch=True)
            tree.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')
            return tree

        def _buttons(self, parent, buttons):
            bar = ttk.Frame(parent)
            bar.pack(fill='x', pady=4)
            for label, command in buttons:
                ttk.Button(bar, text=label, command=command).pack(side='left', padx=(0, 6))

        def _build_calendar_ui(self):
            self._file_actions = (('保存', self.save), ('另存为', self.save_as), ('打开存档', self.open_file), ('重新加载', self.reload))
            self.menu = tk.Menu(self.root, tearoff=False)
            self.file_menu = tk.Menu(self.menu, tearoff=False)
            for label, command in self._file_actions:
                self.file_menu.add_command(label=label, command=command)
            self.menu.add_cascade(label='文件', menu=self.file_menu)
            self.root.configure(menu=self.menu)
            header = ttk.Frame(self.root, padding=(16, 12))
            header.pack(fill='x')
            ttk.Label(header, text='学业任务规划', font=('Segoe UI', 13, 'bold')).pack(side='left', padx=(0, 10))
            ttk.Button(header, text='今天', command=self.today).pack(side='left')
            ttk.Button(header, text='‹', width=3, command=lambda: self.navigate(-1)).pack(side='left', padx=(10, 2))
            ttk.Button(header, text='›', width=3, command=lambda: self.navigate(1)).pack(side='left')
            self.date_title = ttk.Label(header, font=('Segoe UI', 13))
            self.date_title.pack(side='left', padx=8)
            actions = ttk.Frame(self.root, padding=(16, 0, 16, 8))
            actions.pack(fill='x')
            selector = ttk.Combobox(actions, textvariable=self.language, values=('English', '简体中文'), state='readonly', width=11)
            selector.pack(side='right', padx=(12, 0))
            selector.bind('<<ComboboxSelected>>', self.change_language)
            ttk.Button(actions, text='规划设置', command=self.settings_dialog).pack(side='right', padx=6)
            ttk.Button(actions, text='生成 / 重新规划', style='Primary.TButton', command=self.generate).pack(side='right')
            ttk.Label(actions, text='在整个规划范围的空白时间安排').pack(side='left')
            self.status = ttk.Label(self.root, padding=(16, 2), anchor='w')
            self.status.pack(side='bottom', fill='x')
            body = ttk.Panedwindow(self.root, orient='horizontal')
            body.pack(fill='both', expand=True, padx=16, pady=(0, 8))
            sidebar = ttk.Frame(body, width=260, padding=(0, 8, 12, 0))
            body.add(sidebar, weight=0)
            ttk.Button(sidebar, text='＋ 新建任务', style='Primary.TButton', command=self.task_dialog).pack(fill='x', pady=(0, 14))
            ttk.Label(sidebar, text='任务', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
            self.task_tree = self._tree(sidebar, [('title', '任务', 145), ('remaining', '分钟', 65)], height=10)
            self.task_tree.bind('<<TreeviewSelect>>', self._select_task)
            self.task_tree.bind('<Double-1>', lambda event: self.task_dialog(edit=True))
            self._buttons(sidebar, (('编辑', lambda: self.task_dialog(edit=True)), ('标记完成', self.complete_task)))
            self._buttons(sidebar, (('记录进度', self.progress), ('删除任务', self.delete_task)))
            ttk.Label(sidebar, text='未排任务与指标').pack(anchor='w', pady=(12, 4))
            self.summary = tk.Text(sidebar, width=30, height=9, wrap='word', relief='flat', background='#f5f7fb', font=('Segoe UI', 9), state='disabled')
            self.summary.pack(fill='x')
            calendar = ttk.Frame(body, padding=(8, 8, 0, 0))
            body.add(calendar, weight=1)
            bar = ttk.Frame(calendar)
            bar.pack(fill='x', pady=(0, 8))
            ttk.Label(bar, text='点击空白添加忙碌时间 · 点击色块查看详情').pack(side='left')
            for label, value in (('周', 'Week'), ('日', 'Day')):
                ttk.Radiobutton(bar, text=label, variable=self.view_mode, value=value, command=self.draw_calendar).pack(side='right', padx=6)
            legend = ttk.Frame(calendar)
            legend.pack(fill='x', pady=(0, 7))
            for label, color in (('自动', '#d9e7fd'), ('已锁定', '#cbeadc'), ('忙碌', '#e8e9ed')):
                tk.Label(legend, text='  ', background=color).pack(side='left', padx=(0, 4))
                ttk.Label(legend, text=label).pack(side='left', padx=(0, 14))
            self.day_header = tk.Canvas(calendar, height=45, background='white', highlightthickness=0)
            self.day_header.pack(fill='x')
            grid = ttk.Frame(calendar)
            grid.pack(fill='both', expand=True)
            self.canvas = tk.Canvas(grid, background='white', highlightthickness=0)
            scroll = ttk.Scrollbar(grid, orient='vertical', command=self.canvas.yview)
            self.canvas.configure(yscrollcommand=scroll.set)
            self.canvas.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')
            self.canvas.bind('<Configure>', lambda event: self.draw_calendar())
            self.canvas.bind('<Button-1>', self.calendar_click)
            self.canvas.bind('<MouseWheel>', lambda event: self.canvas.yview_scroll(-int(event.delta / 120), 'units'))
            self.root.after_idle(lambda: self.canvas.yview_moveto(7 / 24))
            hidden = ttk.Frame(self.root)
            self.interval_tree = ttk.Treeview(hidden, columns=('kind', 'start', 'end'))
            self.block_tree = ttk.Treeview(hidden, columns=('task', 'start', 'end', 'minutes', 'source'))
            self.lock_tree = ttk.Treeview(hidden, columns=('task', 'start', 'end'))
            self.block_tree.bind('<<TreeviewSelect>>', lambda event: self._exclusive_selection(self.block_tree, self.lock_tree))
            self.lock_tree.bind('<<TreeviewSelect>>', lambda event: self._exclusive_selection(self.lock_tree, self.block_tree))
            self.task_vars = {name: tk.StringVar() for name in ('title', 'estimated_minutes', 'remaining_minutes', 'importance', 'earliest_start', 'deadline')}
            self.splittable = tk.BooleanVar(value=True)
            self.window_vars = {key: tk.StringVar() for key in ('timezone', 'now', 'horizon_end')}
            self.interval_start, self.interval_end = (tk.StringVar(), tk.StringVar())
            self.strategy_var, self.min_var, self.max_var = (tk.StringVar(), tk.StringVar(), tk.StringVar())

        def prepare_planning(self):
            return True

        def today(self):
            self.view_date = datetime.now(resolve_timezone(self.workspace.snapshot['timezone'])).date()
            self.draw_calendar()

        def navigate(self, direction):
            self.view_date += timedelta(days=direction * (7 if self.view_mode.get() == 'Week' else 1))
            self.draw_calendar()

        def _visible_dates(self):
            start = self.view_date - timedelta(days=self.view_date.weekday()) if self.view_mode.get() == 'Week' else self.view_date
            return [start + timedelta(days=i) for i in range(7 if self.view_mode.get() == 'Week' else 1)]

        def draw_calendar(self):
            self.canvas.delete('all')
            self.day_header.delete('all')
            dates = self._visible_dates()
            width = max(400, self.canvas.winfo_width())
            gutter = 54
            col = (width - gutter) / len(dates)
            hour = 58
            self._calendar_geometry = (gutter, col, hour, dates)
            self.canvas.configure(scrollregion=(0, 0, width, hour * 24))
            self.date_title.configure(text=f'{dates[0]:%b %d} – {dates[-1]:%b %d, %Y}' if len(dates) > 1 else f'{dates[0]:%b %d, %Y}')
            weekdays = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun') if self.language.get() == 'English' else ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
            zone = resolve_timezone(self.workspace.snapshot['timezone'])
            today = datetime.now(zone).date()
            for i, day in enumerate(dates):
                x = gutter + i * col
                if day == today:
                    self.canvas.create_rectangle(x, 0, x + col, 24 * hour, fill='#f6f9ff', outline='')
                self.day_header.create_text(x + col / 2, 22, text=f'{weekdays[day.weekday()]} {day.day}', fill='#1967d2' if day == today else '#46516a', font=('Segoe UI', 11, 'bold'))
                self.canvas.create_line(x, 0, x, 24 * hour, fill='#e8ebf0')
            for h in range(24):
                y = h * hour
                self.canvas.create_text(gutter - 8, y + 8, text=f'{h:02}:00', anchor='e', fill='#7a8495', font=('Segoe UI', 9))
                self.canvas.create_line(gutter, y, width, y, fill='#e8ebf0')
            snap = self.workspace.snapshot
            result = self.workspace.result
            names = {t['task_id']: t['title'] for t in snap['tasks']}
            entries = [('busy', i, item) for i, item in enumerate(snap['busy_events'])]
            entries += [('block', i, item) for i, item in enumerate(result['blocks'])] if result else [('lock', i, item) for i, item in enumerate(snap['locked_blocks'])]
            self._calendar_items = {}
            for day_index, day in enumerate(dates):
                midnight = datetime.combine(day, time(), zone)
                next_midnight = datetime.combine(day + timedelta(days=1), time(), zone)
                day_entries = []
                for kind, index, item in entries:
                    start = parse_datetime(item['start'], 'start').astimezone(zone)
                    end = parse_datetime(item['end'], 'end').astimezone(zone)
                    if start < next_midnight and end > midnight:
                        day_entries.append((max(start, midnight), min(end, next_midnight), kind, index, item))
                day_entries.sort(key=lambda entry: entry[0])
                clusters = []
                for entry in day_entries:
                    if not clusters or entry[0] >= max((e[1] for e in clusters[-1])):
                        clusters.append([])
                    clusters[-1].append(entry)
                for cluster in clusters:
                    lanes = []
                    placed = []
                    for entry in cluster:
                        lane = next((i for i, end in enumerate(lanes) if end <= entry[0]), len(lanes))
                        if lane == len(lanes):
                            lanes.append(entry[1])
                        else:
                            lanes[lane] = entry[1]
                        placed.append((lane, entry))
                    for lane, (start, end, kind, index, item) in placed:
                        y1 = (start.hour * 60 + start.minute) / 60 * hour
                        y2 = 24 * hour if end.date() > day else (end.hour * 60 + end.minute) / 60 * hour
                        x1 = gutter + day_index * col + lane * col / len(lanes) + 3
                        x2 = x1 + col / len(lanes) - 6
                        locked = kind == 'lock' or item.get('source') == 'locked'
                        color = '#e8e9ed' if kind == 'busy' else '#cbeadc' if locked else '#d9e7fd'
                        label = self.tr('忙碌') if kind == 'busy' else names.get(item['task_id'], self.tr('固定预留'))
                        tag = f'event_{kind}_{index}_{day_index}'
                        dst = start.utcoffset() != end.utcoffset()
                        bottom = max(y1 + (44 if dst else 23), y2 - 2)
                        self.canvas.create_rectangle(x1, y1 + 2, x2, bottom, fill=color, outline='#b26c18' if dst else 'white', tags=tag)
                        text = f"{start:%H:%M}  {('◆ ' if locked else '')}{label}"
                        if dst:
                            elapsed = int((end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds() / 60)
                            text = f'{start:%H:%M %z} → {end:%H:%M %z} ({elapsed} min) {label}'
                        fitted = self._fit_event_text(text, max(10, x2 - x1 - 10), bottom - y1 - 7)
                        self.canvas.create_text(x1 + 5, y1 + 5, text=fitted, anchor='nw', fill='#253858', font=('Segoe UI', 9), tags=tag)
                        self._calendar_items[tag] = (kind, index)
            if today in dates:
                now = datetime.now(zone)
                y = (now.hour + now.minute / 60) * hour
                x = gutter + dates.index(today) * col
                self.canvas.create_line(x, y, x + col, y, fill='#d93025', width=2)

        def _fit_event_text(self, text, width, height):
            font = tkfont.Font(root=self.root, family='Segoe UI', size=9)
            limit = max(1, int(height / font.metrics('linespace')))
            lines = []
            pending = str(text)
            for line_index in range(limit):
                count = 0
                while count < len(pending) and font.measure(pending[:count + 1]) <= width:
                    count += 1
                if count == len(pending):
                    lines.append(pending)
                    break
                if line_index == limit - 1:
                    while count > 0 and font.measure(pending[:count] + '…') > width:
                        count -= 1
                    lines.append(pending[:count] + '…')
                    break
                lines.append(pending[:count])
                pending = pending[count:].lstrip()
            return '\n'.join(lines)

        def calendar_click(self, event):
            for item in reversed(self.canvas.find_overlapping(event.x, self.canvas.canvasy(event.y), event.x, self.canvas.canvasy(event.y))):
                for tag in self.canvas.gettags(item):
                    if tag in self._calendar_items:
                        self.event_dialog(*self._calendar_items[tag])
                        return
            gutter, col, hour, dates = self._calendar_geometry
            if event.x < gutter:
                return
            day = min(len(dates) - 1, max(0, int((event.x - gutter) / col)))
            minutes = min(23 * 60 + 45, max(0, int(self.canvas.canvasy(event.y) / hour * 4) * 15))
            zone = resolve_timezone(self.workspace.snapshot['timezone'])
            start = datetime.combine(dates[day], time(), zone) + timedelta(minutes=minutes)
            try:
                _terminal_time(start.strftime('%Y-%m-%d %H:%M'), self.workspace.snapshot['timezone'])
            except ValueError as exc:
                self.msg.showerror('时间有误', str(exc), parent=self.root)
                return
            self.busy_dialog(start=start)

        def _new_dialog(self, title):
            if self._dialog is not None and self._dialog.winfo_exists():
                self._dialog.lift()
                return None
            dialog = tk.Toplevel(self.root)
            dialog.title(self.tr(title))
            dialog.transient(self.root)
            dialog.resizable(False, False)
            dialog.grab_set()
            self._dialog = dialog
            return dialog

        def _dialog_labels(self):
            self._capture_text()
            self.change_language()

        def task_dialog(self, edit=False):
            if edit:
                try:
                    task = self._selected_task()
                except ValueError:
                    return
            dialog = self._new_dialog('任务信息')
            if dialog is None:
                return
            if edit:
                for key, var in self.task_vars.items():
                    var.set(str(task[key]))
                self.splittable.set(task['splittable'])
                self._task_baseline = (task['task_id'], self._task_form())
            else:
                self.clear_task()
                snap = self.workspace.snapshot
                for key, value in {'estimated_minutes': '60', 'remaining_minutes': '60', 'importance': '3', 'earliest_start': snap['now'], 'deadline': snap['horizon_end']}.items():
                    self.task_vars[key].set(value)
            form = ttk.Frame(dialog, padding=20)
            form.pack(fill='both')

            def field(parent, row, key, label):
                ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', pady=6)
                entry = ttk.Entry(parent, textvariable=self.task_vars[key], width=36)
                entry.grid(row=row, column=1, sticky='ew', padx=(14, 0), pady=6)
                return entry
            title = field(form, 0, 'title', '任务名称')
            field(form, 1, 'estimated_minutes', '总分钟')
            field(form, 2, 'deadline', '截止时间')
            advanced = ttk.Frame(form)
            opened = tk.BooleanVar(value=False)

            def toggle():
                if opened.get():
                    advanced.grid(row=4, column=0, columnspan=2, sticky='ew')
                else:
                    advanced.grid_remove()
            ttk.Checkbutton(form, text='高级选项', variable=opened, command=toggle).grid(row=3, column=0, columnspan=2, sticky='w', pady=8)
            field(advanced, 0, 'remaining_minutes', '剩余分钟')
            field(advanced, 1, 'importance', '重要性 1–5')
            field(advanced, 2, 'earliest_start', '最早开始')
            ttk.Checkbutton(advanced, text='允许拆分', variable=self.splittable).grid(row=3, column=0, columnspan=2, sticky='w')
            previous_total = [self.task_vars['estimated_minutes'].get()]

            def follow_total(*args):
                value = self.task_vars['estimated_minutes'].get()
                if not edit and self.task_vars['remaining_minutes'].get() == previous_total[0]:
                    self.task_vars['remaining_minutes'].set(value)
                previous_total[0] = value
            trace = self.task_vars['estimated_minutes'].trace_add('write', follow_total)

            def finish():
                self.task_vars['estimated_minutes'].trace_remove('write', trace)
                self.clear_task()
                dialog.destroy()

            def cancel():
                if self._has_drafts() and (not self.msg.askyesno('表单尚未应用', '有尚未应用的表单内容，确认放弃？', parent=dialog)):
                    return
                finish()

            def submit():
                before = self.workspace.snapshot['input_revision']
                self.update_task() if edit else self.add_task()
                if before != self.workspace.snapshot['input_revision']:
                    finish()
            buttons = ttk.Frame(form)
            buttons.grid(row=5, column=0, columnspan=2, sticky='e', pady=(16, 0))
            ttk.Button(buttons, text='取消', command=cancel).pack(side='left', padx=6)
            ttk.Button(buttons, text='保存', style='Primary.TButton', command=submit).pack(side='left')
            dialog.protocol('WM_DELETE_WINDOW', cancel)
            title.focus_set()
            self._dialog_labels()

        def busy_dialog(self, start=None, index=None):
            dialog = self._new_dialog('忙碌时间')
            if dialog is None:
                return
            zone = resolve_timezone(self.workspace.snapshot['timezone'])
            if index is not None:
                interval = self.workspace.snapshot['busy_events'][index]
                a, b = (interval['start'], interval['end'])
            else:
                start = start or datetime.now(zone).replace(second=0, microsecond=0)
                a, b = (start.isoformat(timespec='minutes'), (start + timedelta(hours=1)).isoformat(timespec='minutes'))
            self.interval_start.set(a)
            self.interval_end.set(b)
            form = ttk.Frame(dialog, padding=20)
            form.pack()
            for row, (label, var) in enumerate((('开始', self.interval_start), ('结束', self.interval_end))):
                ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', pady=8)
                ttk.Entry(form, textvariable=var, width=36).grid(row=row, column=1, padx=12)
            ttk.Label(form, text='时间可输入 YYYY-MM-DD HH:MM（当前时区）或带偏移 ISO 时间。', wraplength=360).grid(row=2, column=0, columnspan=2, sticky='w', pady=8)

            def finish():
                self.interval_start.set('')
                self.interval_end.set('')
                dialog.destroy()

            def save_busy():
                try:
                    a = _terminal_time(self.interval_start.get().strip(), self.workspace.snapshot['timezone'])
                    b = _terminal_time(self.interval_end.get().strip(), self.workspace.snapshot['timezone'])
                except ValueError as exc:
                    self.msg.showerror('时间有误', str(exc), parent=dialog)
                    return
                ok = self._perform(self.workspace.add_interval, 'busy_events', a, b) if index is None else self._perform(self.workspace.update_interval, 'busy_events', index, a, b)
                if ok:
                    finish()
            bar = ttk.Frame(form)
            bar.grid(row=3, column=0, columnspan=2, sticky='e')
            if index is not None:
                ttk.Button(bar, text='删除', command=lambda: finish() if self._perform(self.workspace.remove_interval, 'busy_events', index) else None).pack(side='left', padx=6)
            ttk.Button(bar, text='取消', command=finish).pack(side='left', padx=6)
            ttk.Button(bar, text='保存', command=save_busy).pack(side='left')
            dialog.protocol('WM_DELETE_WINDOW', finish)
            self._dialog_labels()

        def event_dialog(self, kind, index):
            if kind == 'busy':
                self.busy_dialog(index=index)
                return
            result = self.workspace.result
            item = result['blocks'][index] if kind == 'block' else self.workspace.snapshot['locked_blocks'][index]
            dialog = self._new_dialog('计划块')
            if dialog is None:
                return
            snap = self.workspace.snapshot
            task = next((t for t in snap['tasks'] if t['task_id'] == item['task_id']), None)
            form = ttk.Frame(dialog, padding=20)
            form.pack()
            title_label = ttk.Label(form, text=task['title'] if task else self.tr('固定预留'), font=('Segoe UI', 13, 'bold'), wraplength=400)
            title_label._user_content = True
            title_label.pack(anchor='w')
            zone = resolve_timezone(snap['timezone'])
            ttk.Label(form, text='\n'.join((parse_datetime(item[key], key).astimezone(zone).strftime('%a %b %d  %H:%M %z') for key in ('start', 'end')))).pack(anchor='w', pady=16)
            locked = kind == 'lock' or item.get('source') == 'locked'

            def act():
                ok = self._perform(self.workspace.unlock, item['locked_id']) if locked else self._perform(self.workspace.lock_block, index)
                if ok:
                    dialog.destroy()
            ttk.Button(form, text='解锁' if locked else '锁定时间', command=act).pack(fill='x')
            if task:

                def edit_task():
                    dialog.destroy()
                    task_index = next((i for i, t in enumerate(snap['tasks']) if t['task_id'] == task['task_id']))
                    self.task_tree.selection_set(str(task_index))
                    self.task_dialog(edit=True)
                ttk.Button(form, text='编辑任务', command=edit_task).pack(fill='x', pady=6)
            self._dialog_labels()

        def settings_dialog(self):
            dialog = self._new_dialog('规划设置')
            if dialog is None:
                return
            form = ttk.Frame(dialog, padding=20)
            form.pack()
            fields = (('timezone', 'IANA 时区'), ('now', '开始'), ('horizon_end', '结束'))
            for row, (key, label) in enumerate(fields):
                ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', pady=6)
                ttk.Entry(form, textvariable=self.window_vars[key], width=34).grid(row=row, column=1, padx=12)
            ttk.Label(form, text='策略').grid(row=3, column=0, sticky='w', pady=6)
            ttk.Combobox(form, textvariable=self.strategy_var, values=('edf', 'importance', 'risk'), state='readonly').grid(row=3, column=1, sticky='ew', padx=12)
            for row, (label, var) in enumerate((('最短块（分钟）', self.min_var), ('最长块（分钟）', self.max_var)), 4):
                ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', pady=6)
                ttk.Entry(form, textvariable=var, width=8).grid(row=row, column=1, sticky='w', padx=12)
            ttk.Label(form, text='按日历空白自动安排；忙碌时间与锁定块会被保留。', wraplength=390).grid(row=6, column=0, columnspan=2, sticky='w', pady=12)

            def cancel():
                snap = self.workspace.snapshot
                for key, var in self.window_vars.items():
                    var.set(snap[key])
                self.strategy_var.set(snap['strategy'])
                self.min_var.set(str(snap['parameters']['min_block_minutes']))
                self.max_var.set(str(snap['parameters']['max_block_minutes']))
                dialog.destroy()

            def apply():
                try:
                    candidate = self.workspace.snapshot
                    zone = self.window_vars['timezone'].get().strip()
                    resolve_timezone(zone)
                    candidate.update(timezone=zone, now=_terminal_time(self.window_vars['now'].get().strip(), zone), horizon_end=_terminal_time(self.window_vars['horizon_end'].get().strip(), zone), strategy=self.strategy_var.get())
                    candidate['parameters'] = {'min_block_minutes': int(self.min_var.get()), 'max_block_minutes': int(self.max_var.get())}
                    changed = candidate != self.workspace.snapshot
                    if changed:
                        candidate['input_revision'] = str(uuid4())
                    validated = Workspace(candidate)
                except ValueError as exc:
                    self.msg.showerror('设置有误', str(exc), parent=dialog)
                    return
                if changed:
                    self.workspace = validated
                    self.dirty = True
                    self._last_snapshot = None
                self.refresh()
                dialog.destroy()
            bar = ttk.Frame(form)
            bar.grid(row=7, column=0, columnspan=2, sticky='e')
            ttk.Button(bar, text='比较三种策略', command=self.compare).pack(side='left', padx=6)
            ttk.Button(bar, text='取消', command=cancel).pack(side='left', padx=6)
            ttk.Button(bar, text='应用设置', command=apply).pack(side='left')
            dialog.protocol('WM_DELETE_WINDOW', cancel)
            self._dialog_labels()

        def _exclusive_selection(self, source, other):
            if source.selection() and other.selection():
                other.selection_remove(other.selection())

        def _perform(self, action, *args, **kwargs):
            try:
                value = action(*args, **kwargs)
            except (ValueError, OSError) as exc:
                self.msg.showerror('操作失败', str(exc), parent=self.root)
                return False
            self.dirty = True
            self.refresh()
            return True

        def _selected(self, tree):
            selected = tree.selection()
            if not selected:
                raise ValueError('请先选择一行。')
            return selected[0]

        def _selected_task(self):
            return self.workspace.snapshot['tasks'][int(self._selected(self.task_tree))]

        def _select_task(self, event=None):
            if self._suppress_selection or not self.task_tree.selection():
                return
            selected = self._selected_task()['task_id']
            previous_id = self._task_baseline[0] if self._task_baseline is not None else None
            baseline = self._task_baseline[1] if self._task_baseline is not None else ('', '', '', '', '', '', True)
            if selected == previous_id and self._task_form() != baseline:
                return
            if selected != previous_id and self._task_form() != baseline:
                if not self.msg.askyesno('表单尚未应用', '任务表单有未应用的更改，确认放弃并选择其他任务？', parent=self.root):
                    previous = next((str(i) for i, task in enumerate(self.workspace.snapshot['tasks']) if task['task_id'] == previous_id), None)
                    self._suppress_selection = True
                    self.task_tree.selection_remove(self.task_tree.selection())
                    if previous is not None:
                        self.task_tree.selection_set(previous)
                    self.root.after_idle(lambda: setattr(self, '_suppress_selection', False))
                    return
            task = self._selected_task()
            for name, var in self.task_vars.items():
                var.set(str(task[name]))
            self.splittable.set(task['splittable'])
            self._task_baseline = (task['task_id'], self._task_form())

        def _task_form(self):
            return tuple((var.get() for var in self.task_vars.values())) + (self.splittable.get(),)

        def _has_drafts(self):
            snap = self.workspace.snapshot
            baseline = self._task_baseline[1] if self._task_baseline is not None else ('', '', '', '', '', '', True)
            task_draft = self._task_form() != baseline
            window_draft = any((var.get() != snap[key] for key, var in self.window_vars.items()))
            settings_draft = (self.strategy_var.get(), self.min_var.get(), self.max_var.get()) != (snap['strategy'], str(snap['parameters']['min_block_minutes']), str(snap['parameters']['max_block_minutes']))
            return task_draft or window_draft or settings_draft or bool(self.interval_start.get().strip() or self.interval_end.get().strip())

        def clear_task(self):
            for var in self.task_vars.values():
                var.set('')
            self.splittable.set(True)
            self._task_baseline = None
            self.task_tree.selection_remove(self.task_tree.selection())

        def _task_fields(self):
            values = {key: var.get().strip() for key, var in self.task_vars.items()}
            try:
                for key in ('estimated_minutes', 'remaining_minutes', 'importance'):
                    values[key] = int(values[key])
            except ValueError:
                raise ValueError('总分钟、剩余分钟和重要性必须是整数。') from None
            if values['estimated_minutes'] < 0 or values['remaining_minutes'] < 0:
                raise ValueError('工作分钟不能为负数。')
            if values['remaining_minutes'] > values['estimated_minutes']:
                raise ValueError('剩余分钟不能大于总分钟。')
            if not 1 <= values['importance'] <= 5:
                raise ValueError('重要性必须在 1 到 5 之间。')
            zone = self.workspace.snapshot['timezone']
            for key in ('deadline', 'earliest_start'):
                values[key] = _terminal_time(values[key], zone)
            values['splittable'] = self.splittable.get()
            return values

        def add_task(self):
            try:
                fields = self._task_fields()
            except ValueError as exc:
                self.msg.showerror('任务信息有误', str(exc), parent=self.root)
                return
            if self._perform(self.workspace.add_task, **fields):
                self.clear_task()

        def update_task(self):
            try:
                task, fields = (self._selected_task(), self._task_fields())
            except ValueError as exc:
                self.msg.showerror('任务信息有误', str(exc), parent=self.root)
                return
            if self._perform(self.workspace.update_task, task['task_id'], **fields):
                self.clear_task()

        def progress(self):
            try:
                task = self._selected_task()
            except ValueError as exc:
                self.msg.showerror('请选择任务', str(exc), parent=self.root)
                return
            value = simpledialog.askinteger(self.tr('记录进度'), self.tr('实际剩余分钟：'), initialvalue=task['remaining_minutes'], minvalue=0, parent=self.root)
            if value is not None:
                self._perform(self.workspace.update_task, task['task_id'], remaining_minutes=value)

        def complete_task(self):
            try:
                task = self._selected_task()
            except ValueError as exc:
                self.msg.showerror('请选择任务', str(exc), parent=self.root)
                return
            if self.msg.askyesno('标记完成', '确认完成该任务？其锁定时间块也会移除。', parent=self.root):
                self._perform(self.workspace.complete_task, task['task_id'])

        def delete_task(self):
            try:
                task = self._selected_task()
            except ValueError as exc:
                self.msg.showerror('请选择任务', str(exc), parent=self.root)
                return
            if self.msg.askyesno('删除任务', '确认删除该任务及其锁定时间块？', parent=self.root):
                self._perform(self.workspace.delete_task, task['task_id'])

        def set_window(self):
            try:
                zone = self.window_vars['timezone'].get().strip()
                resolve_timezone(zone)
                start = _terminal_time(self.window_vars['now'].get().strip(), zone)
                end = _terminal_time(self.window_vars['horizon_end'].get().strip(), zone)
            except ValueError as exc:
                self.msg.showerror('时间有误', str(exc), parent=self.root)
                return
            self._perform(self.workspace.set_window, start, end, zone)

        def add_interval(self, kind):
            try:
                zone = self.workspace.snapshot['timezone']
                start, end = (_terminal_time(self.interval_start.get().strip(), zone), _terminal_time(self.interval_end.get().strip(), zone))
            except ValueError as exc:
                self.msg.showerror('时间有误', str(exc), parent=self.root)
                return
            if self._perform(self.workspace.add_interval, kind, start, end):
                self.interval_start.set('')
                self.interval_end.set('')

        def remove_interval(self):
            try:
                kind, index = self._selected(self.interval_tree).split(':')
                self._perform(self.workspace.remove_interval, kind, int(index))
            except ValueError as exc:
                self.msg.showerror('请选择时段', str(exc), parent=self.root)

        def set_strategy(self):
            try:
                minimum, maximum = (int(self.min_var.get()), int(self.max_var.get()))
                strategy = self.strategy_var.get()
                if minimum <= 0 or maximum < minimum:
                    raise ValueError('块长须为正整数，最短不能大于最长。')
                if strategy not in ('edf', 'importance', 'risk'):
                    raise ValueError('请选择策略。')
            except ValueError as exc:
                self.msg.showerror('设置有误', str(exc), parent=self.root)
                return
            snap = self.workspace.snapshot
            if strategy != snap['strategy'] and (not self._perform(self.workspace.set_strategy, strategy)):
                return
            if (minimum, maximum) != (snap['parameters']['min_block_minutes'], snap['parameters']['max_block_minutes']):
                self._perform(self.workspace.set_parameters, minimum, maximum)

        def generate(self):
            if not self.prepare_planning():
                return
            if self._perform(self.workspace.generate_calendar):
                blocks = self.workspace.result['blocks']
                if blocks:
                    start = parse_datetime(blocks[0]['start'], 'start').astimezone(resolve_timezone(self.workspace.snapshot['timezone']))
                    self.view_date = start.date()
                    self.draw_calendar()
                    self.canvas.yview_moveto(max(0, start.hour - 1) / 24)

        def lock_block(self):
            try:
                index = int(self._selected(self.block_tree))
            except ValueError as exc:
                self.msg.showerror('请选择计划块', str(exc), parent=self.root)
                return
            self._perform(self.workspace.lock_block, index)

        def unlock(self):
            try:
                if self.lock_tree.selection():
                    lock = self.workspace.snapshot['locked_blocks'][int(self._selected(self.lock_tree))]['locked_id']
                else:
                    result = self.workspace.result
                    if result is None:
                        raise ValueError('请在锁定列表选择一行。')
                    block = result['blocks'][int(self._selected(self.block_tree))]
                    lock = block['locked_id']
                    if not lock:
                        raise ValueError('所选时间块尚未锁定。')
            except ValueError as exc:
                self.msg.showerror('请选择锁定块', str(exc), parent=self.root)
                return
            self._perform(self.workspace.unlock, lock)

        def _summary(self, result):
            if result is None:
                return '暂无计划。请先设置可用时段并生成。'
            names = {t['task_id']: t['title'] for t in self.workspace.snapshot['tasks']}
            metrics = result['metrics']
            percent = lambda value: f'{value:.1%}' if value is not None else '—'
            lines = [f"{self.tr('策略：')}{result['strategy']}\u3000{self.tr('已安排：')}{metrics['scheduled_minutes']}{self.tr(' 分钟')}\u3000{self.tr('未排：')}{metrics['unscheduled_minutes']}{self.tr(' 分钟')}\u3000{self.tr('完整任务：')}{metrics['fully_scheduled_tasks']}/{metrics['eligible_tasks']}", f"{self.tr('完成比例：')}{percent(metrics['completion_ratio'])}\u3000{self.tr('加权完成比例：')}{percent(metrics['weighted_completion_ratio'])}\u3000{self.tr('可用：')}{metrics['available_minutes']}{self.tr(' 分钟')}\u3000{self.tr('预留：')}{metrics['reserved_minutes']}{self.tr(' 分钟')}\u3000{self.tr('利用率：')}{percent(metrics['utilization_ratio'])}"]
            for item in result['unscheduled']:
                reasons = ', '.join((self.tr(_terminal_REASONS.get(reason, reason)) for reason in item['reasons']))
                lines.append(f"{self.tr('未排：')}{names.get(item['task_id'], item['task_id'])}: {item['minutes']}{self.tr(' 分钟')} ({reasons})")
            if any((parse_datetime(block['start'], '时间') <= datetime.now(timezone.utc) for block in result['blocks'])):
                lines.append(self.tr('包含已开始的时间块，请核对实际进度与剩余分钟，再按需重新规划。'))
            return '\n'.join(lines)

        def compare(self):
            try:
                results = self.workspace.compare_calendar()
            except (ValueError, OSError) as exc:
                self.msg.showerror('比较失败', str(exc), parent=self.root)
                return
            window = tk.Toplevel(self.root)
            window.title(self.tr('策略比较（不更改当前计划）'))
            text = tk.Text(window, width=100, height=24, wrap='word')
            text.pack(fill='both', expand=True, padx=10, pady=10)
            text.insert('1.0', '\n\n'.join((self._summary(result) for result in results)))
            text.configure(state='disabled')

        def refresh(self):
            snap, result = (self.workspace.snapshot, self.workspace.result)
            self.status.configure(text=f"{self.tr('存档：')}{self.store.path}  |  {self.tr('未保存' if self.dirty else '无未保存更改')}  |  {self.tr('时区：')}{snap['timezone']}")
            selections = {tree: tree.selection() for tree in (self.task_tree, self.interval_tree, self.block_tree, self.lock_tree)}
            for tree in selections:
                tree.delete(*tree.get_children())
            names = {t['task_id']: t['title'] for t in snap['tasks']}
            for i, task in enumerate(snap['tasks']):
                statuses = {'active': 'Active', 'completed': 'Completed', 'deleted': 'Deleted'} if self.language.get() == 'English' else {'active': '进行中', 'completed': '已完成', 'deleted': '已删除'}
                self.task_tree.insert('', 'end', iid=str(i), values=(task['title'], f"{task['remaining_minutes']}/{task['estimated_minutes']}"))
            for kind, label in (('availability', '可用'), ('busy_events', '忙碌')):
                for i, interval in enumerate(snap[kind]):
                    self.interval_tree.insert('', 'end', iid=f'{kind}:{i}', values=(self.tr(label), interval['start'], interval['end']))
            for i, lock in enumerate(snap['locked_blocks']):
                self.lock_tree.insert('', 'end', iid=str(i), values=(names.get(lock['task_id'], self.tr('固定预留')), lock['start'], lock['end']))
            if result:
                for i, block in enumerate(result['blocks']):
                    self.block_tree.insert('', 'end', iid=str(i), values=(names.get(block['task_id'], self.tr('固定预留')), block['start'], block['end'], block['minutes'], self.tr('已锁定' if block['source'] == 'locked' else '自动')))
            for tree, items in selections.items():
                for item in items:
                    if tree.exists(item):
                        tree.selection_add(item)
            old = self._last_snapshot
            for key, var in self.window_vars.items():
                if old is None or old[key] != snap[key]:
                    var.set(snap[key])
            if old is None or old['strategy'] != snap['strategy']:
                self.strategy_var.set(snap['strategy'])
            if old is None or old['parameters'] != snap['parameters']:
                self.min_var.set(str(snap['parameters']['min_block_minutes']))
                self.max_var.set(str(snap['parameters']['max_block_minutes']))
            self._last_snapshot = snap
            self.summary.configure(state='normal')
            self.summary.delete('1.0', 'end')
            self.summary.insert('1.0', self.tr('暂无计划。请先设置可用时段并生成。') if result is None else self._summary(result))
            self.summary.configure(state='disabled')
            self.draw_calendar()

        def save(self):
            if self._has_drafts():
                self.msg.showerror('表单尚未应用', '请先应用或清空表单中的更改，再保存。', parent=self.root)
                return False
            try:
                self.store.save(self.workspace)
            except (ValueError, OSError) as exc:
                self.msg.showerror('保存失败', str(exc), parent=self.root)
                return False
            self.dirty = False
            self.refresh()
            return True

        def save_as(self):
            if self._has_drafts():
                self.msg.showerror('表单尚未应用', '请先应用或清空表单中的更改，再保存。', parent=self.root)
                return False
            path = filedialog.asksaveasfilename(parent=self.root, title=self.tr('另存为新文件'), defaultextension='.json', filetypes=[(self.tr('工作区'), '*.json'), (self.tr('所有文件'), '*')])
            if not path:
                return False
            candidate = WorkspaceStore(path)
            try:
                candidate.save(self.workspace)
            except (ValueError, OSError) as exc:
                self.msg.showerror('另存失败', str(exc), parent=self.root)
                return False
            self.store = candidate
            self.dirty = False
            self.refresh()
            return True

        def _discard(self):
            if self._has_drafts() and (not self.msg.askyesno('表单尚未应用', '有尚未应用的表单内容，确认放弃？', parent=self.root)):
                return False
            return not self.dirty or self.msg.askyesno('放弃更改', '有未保存更改，确认放弃并加载其他存档？', parent=self.root)

        def _load(self, candidate):
            try:
                workspace = candidate.load()
            except (ValueError, OSError) as exc:
                self.msg.showerror('加载失败', str(exc), parent=self.root)
                return False
            self.store, self.workspace, self.dirty = (candidate, workspace, False)
            self.clear_task()
            self.interval_start.set('')
            self.interval_end.set('')
            self._last_snapshot = None
            self.refresh()
            return True

        def reload(self):
            if self._discard():
                self._load(WorkspaceStore(self.store.path))

        def open_file(self):
            if not self._discard():
                return
            path = filedialog.askopenfilename(parent=self.root, title=self.tr('打开工作区'), filetypes=[(self.tr('工作区'), '*.json'), (self.tr('所有文件'), '*')])
            if path:
                self._load(WorkspaceStore(path))

        def close(self):
            if self._has_drafts() and (not self.msg.askyesno('表单尚未应用', '有尚未应用的表单内容，确认放弃？', parent=self.root)):
                return
            if self.dirty:
                decision = self.msg.askyesnocancel('未保存更改', '保存更改后退出？选择“否”放弃更改，选择“取消”继续编辑。', parent=self.root)
                if decision is None:
                    return
                if decision:
                    self.clear_task()
                    self.interval_start.set('')
                    self.interval_end.set('')
                    self._last_snapshot = None
                    self.refresh()
                    if not self.save():
                        return
            self.root.destroy()

    def run_gui(data_path: str | Path | None=None) -> int:
        path = Path(data_path) if data_path is not None else Path.cwd() / 'work' / 'demo1-data' / 'workspace.json'
        root = tk.Tk()
        root.withdraw()
        store = WorkspaceStore(path)
        try:
            workspace = store.load() if path.exists() else Workspace.new()
        except (ValueError, OSError) as exc:
            messagebox.showerror('Could not load workspace', _gui_english(exc), parent=root)
            root.destroy()
            return 1
        SchedulerGUI(root, store, workspace)
        root.deiconify()
        root.mainloop()
        return 0
    return run_gui

def run_gui(*args, **kwargs):
    return _load_gui_runner()(*args, **kwargs)

# ==================== application.py ====================

"""User-facing entry point: graphical workspace by default."""
import sys

def main(argv=None):
    try:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        args = list(sys.argv[1:] if argv is None else argv)
        if args and args[0] in ('schedule', 'compare', 'validate'):
            return _cli_main(args)
        parser = Parser(description='Academic Scheduler: open the graphical workspace; --terminal uses the text menu.')
        parser.add_argument('--data', metavar='PATH', help='交互工作区存档路径')
        interface = parser.add_mutually_exclusive_group()
        interface.add_argument('--gui', action='store_true', help='open the graphical workspace (default)')
        interface.add_argument('--terminal', action='store_true', help='open the terminal workspace')
        parser.add_argument('--demo', action='store_true', help='运行合成案例，不进入个人工作区')
        parser.add_argument('--example', choices=('all', *DEMO_EXAMPLES), default=None)
        parser.add_argument('--strategy', choices=('all', 'edf', 'importance', 'risk'), default=None)
        parser.add_argument('--json', action='store_true', help='输出合成案例的JSON结果')
        options = parser.parse_args(args)
        demonstration = options.demo or options.json or options.example is not None or (options.strategy is not None)
        if demonstration:
            if options.data is not None:
                raise CLIError('--data用于个人工作区，不能与合成案例选项混用')
            if options.gui or options.terminal:
                raise CLIError('--gui/--terminal不能与合成案例选项混用')
            report = run_demo(options.example or 'all', options.strategy or 'all')
            if options.json:
                _cli_write_json(report, None, [])
            else:
                print_demo(report)
            return 0
        if options.terminal:
            return run_terminal(options.data)
        return run_gui(options.data)
    except DemoValidationError as exc:
        return _cli_error('validation_failed', str(exc), 3)
    except (CLIError, InputError, UnicodeError, OSError) as exc:
        return _cli_error('input_error', str(exc), 2)
    except Exception as exc:
        return _cli_error('internal_error', str(exc), 1)

if __name__ == "__main__":
    raise SystemExit(main())
