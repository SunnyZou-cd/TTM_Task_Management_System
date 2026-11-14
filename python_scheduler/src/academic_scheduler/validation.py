"""Independent output checks; does not import the allocator or interval helpers."""

from collections import Counter, defaultdict
from datetime import datetime
import math

from .models import ScheduleRequest, ScheduleResult


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
