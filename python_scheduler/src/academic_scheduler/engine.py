"""Shared feasible-block allocator for EDF, importance and dynamic risk."""

from datetime import timedelta

from .availability import duration_minutes, free_intervals, subtract_intervals
from .metrics import compute_metrics
from .models import Interval, ScheduleBlock, ScheduleRequest, ScheduleResult, Task, UnscheduledTask
from .strategies import STRATEGY_VERSIONS, order_tasks, task_intervals


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
