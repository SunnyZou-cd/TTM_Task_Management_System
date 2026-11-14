"""Half-open interval operations; all internal timestamps are UTC."""

from datetime import datetime, timedelta
from collections.abc import Iterable

from .models import Interval, ScheduleRequest


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
