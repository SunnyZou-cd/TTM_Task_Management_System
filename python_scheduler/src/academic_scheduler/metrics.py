"""Plan allocation metrics. These numbers never represent work completion."""

from .models import ScheduleBlock, ScheduleRequest


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
