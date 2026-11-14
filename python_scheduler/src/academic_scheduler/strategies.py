"""Deterministic candidate ordering; allocation constraints belong to the engine."""

from collections.abc import Iterable, Mapping
from fractions import Fraction

from .availability import duration_minutes
from .models import Interval, ScheduleRequest, Task


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
