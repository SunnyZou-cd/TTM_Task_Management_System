#!/usr/bin/env python3
"""Demo 1: interactive Python academic scheduling software (Python 3.11+).

Run: python demo1.py
Separate personal file: python demo1.py --data work/my-tasks.json
Optional synthetic examples: python demo1.py --demo
Machine-readable example results: python demo1.py --demo --json

All source is in this file. Default UTC needs only the Python standard library.
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

# ==================== application.py ====================

"""User-facing entry point: interactive workspace by default."""
import sys

def main(argv=None):
    try:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        args = list(sys.argv[1:] if argv is None else argv)
        if args and args[0] in ('schedule', 'compare', 'validate'):
            return _cli_main(args)
        parser = Parser(description='Python学业调度软件：默认进入交互工作区；--demo查看合成案例。')
        parser.add_argument('--data', metavar='PATH', help='交互工作区存档路径')
        parser.add_argument('--demo', action='store_true', help='运行合成案例，不进入个人工作区')
        parser.add_argument('--example', choices=('all', *DEMO_EXAMPLES), default=None)
        parser.add_argument('--strategy', choices=('all', 'edf', 'importance', 'risk'), default=None)
        parser.add_argument('--json', action='store_true', help='输出合成案例的JSON结果')
        options = parser.parse_args(args)
        demonstration = options.demo or options.json or options.example is not None or (options.strategy is not None)
        if demonstration:
            if options.data is not None:
                raise CLIError('--data用于个人工作区，不能与合成案例选项混用')
            report = run_demo(options.example or 'all', options.strategy or 'all')
            if options.json:
                _cli_write_json(report, None, [])
            else:
                print_demo(report)
            return 0
        return run_terminal(options.data)
    except DemoValidationError as exc:
        return _cli_error('validation_failed', str(exc), 3)
    except (CLIError, InputError, UnicodeError, OSError) as exc:
        return _cli_error('input_error', str(exc), 2)
    except Exception as exc:
        return _cli_error('internal_error', str(exc), 1)

if __name__ == "__main__":
    raise SystemExit(main())
