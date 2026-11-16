"""Transactional personal workspace; planned minutes never mean completed work."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from .engine import schedule
from .metrics import compute_metrics
from .models import InputError, parse_datetime, parse_request, parse_result, result_to_dict
from .validation import validate_result


class WorkspaceError(ValueError):
    """A rejected user operation leaves the workspace unchanged."""


def _utc_now(value: datetime | None = None) -> datetime:
    value = datetime.now(timezone.utc) if value is None else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise WorkspaceError("当前时间必须是带时区的 datetime。")
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise WorkspaceError("当前时间超出可用日期范围。") from exc


def _ceil_minute(value: datetime | None = None) -> datetime:
    value = _utc_now(value)
    try:
        return value.replace(second=0, microsecond=0) + (timedelta(minutes=1) if value.second or value.microsecond else timedelta())
    except OverflowError as exc:
        raise WorkspaceError("当前时间超出可用日期范围。") from exc


def _stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _validated(request: dict, result: dict | None = None):
    try:
        parsed = parse_request(request)
        if result is not None:
            errors = validate_result(parsed, parse_result(result))
            if errors:
                raise WorkspaceError("计划已过期或不满足约束：" + "; ".join(errors))
        return parsed
    except InputError as exc:
        raise WorkspaceError(str(exc)) from exc


class Workspace:
    def __init__(self, request: dict, result: dict | None = None):
        parsed = _validated(request, result)
        self._request = deepcopy(request)
        self._request["parameters"] = {"min_block_minutes": parsed.parameters.min_block_minutes, "max_block_minutes": parsed.parameters.max_block_minutes}
        self._result = deepcopy(result)

    @classmethod
    def new(cls, now: datetime | None = None) -> "Workspace":
        start = _ceil_minute(now)
        try:
            end = start + timedelta(days=7)
        except OverflowError as exc:
            raise WorkspaceError("新工作区的七天窗口超出可用日期范围。") from exc
        return cls({"schema_version": "1", "request_id": str(uuid4()), "input_revision": str(uuid4()), "now": _stamp(start), "timezone": "local", "horizon_end": _stamp(end), "tasks": [], "availability": [], "busy_events": [], "locked_blocks": [], "strategy": "edf", "parameters": {"min_block_minutes": 15, "max_block_minutes": 60}})

    @classmethod
    def from_document(cls, document: dict, *, local_time: bool = False) -> "Workspace":
        if not isinstance(document, dict) or set(document) != {"format", "version", "request", "result"}:
            raise WorkspaceError("存档必须包含 format、version、request、result 四个字段。")
        if document["format"] != "academic-scheduler-workspace" or type(document["version"]) is not int or document["version"] != 1:
            raise WorkspaceError("不支持的工作区存档格式或版本。")
        if document["result"] is not None and not isinstance(document["result"], dict):
            raise WorkspaceError("存档 result 必须是计划对象或 null。")
        if not local_time:
            return cls(document["request"], document["result"])
        # Only the in-memory display preference changes. Endpoints, revisions,
        # locks and the existing plan retain their original absolute instants.
        request = deepcopy(document["request"])
        if isinstance(request, dict) and "timezone" in request:
            if not isinstance(request["timezone"], str) or not request["timezone"] or request["timezone"].strip() != request["timezone"]:
                raise WorkspaceError("timezone: must be a nonempty string without surrounding whitespace")
            request["timezone"] = "local"
        workspace = cls(request, document["result"])
        if workspace._result is not None:
            workspace._result = result_to_dict(parse_result(workspace._result), "local")
        return workspace

    def to_document(self) -> dict:
        _validated(self._request, self._result)
        return {"format": "academic-scheduler-workspace", "version": 1, "request": self.snapshot, "result": self.result}

    @property
    def snapshot(self) -> dict:
        return deepcopy(self._request)

    @property
    def result(self) -> dict | None:
        return deepcopy(self._result)

    def _edit(self, operation: Callable[[dict], None]) -> None:
        candidate = self.snapshot
        operation(candidate)
        _validated(candidate)
        candidate["input_revision"] = str(uuid4())
        self._request, self._result = candidate, None

    @staticmethod
    def _find_task(request: dict, task_id: str) -> dict:
        for task in request["tasks"]:
            if task["task_id"] == task_id:
                return task
        raise WorkspaceError("未找到该任务；请重新查看任务列表。")

    def add_task(self, *, title, estimated_minutes, remaining_minutes, importance, deadline, earliest_start, splittable) -> str:
        task_id = str(uuid4())
        self._edit(lambda request: request["tasks"].append({"task_id": task_id, "title": title, "estimated_minutes": estimated_minutes, "remaining_minutes": remaining_minutes, "importance": importance, "deadline": deadline, "earliest_start": earliest_start, "splittable": splittable, "status": "active"}))
        return task_id

    def update_task(self, task_id: str, /, **fields) -> None:
        allowed = {"title", "estimated_minutes", "remaining_minutes", "importance", "deadline", "earliest_start", "splittable", "status"}
        if not fields.keys() <= allowed:
            raise WorkspaceError("任务 ID 不可修改，且不能设置未支持的任务字段。")
        def update(request):
            self._find_task(request, task_id).update(fields)
        self._edit(update)

    def delete_task(self, task_id: str) -> None:
        def delete(request):
            self._find_task(request, task_id)
            request["tasks"] = [task for task in request["tasks"] if task["task_id"] != task_id]
            request["locked_blocks"] = [block for block in request["locked_blocks"] if block["task_id"] != task_id]
        self._edit(delete)

    def complete_task(self, task_id: str) -> None:
        def complete(request):
            self._find_task(request, task_id).update(remaining_minutes=0, status="completed")
            request["locked_blocks"] = [block for block in request["locked_blocks"] if block["task_id"] != task_id]
        self._edit(complete)

    def set_window(self, start: str, end: str, timezone: str) -> None:
        self._edit(lambda request: request.update(now=start, horizon_end=end, timezone=timezone))

    def set_strategy(self, strategy: str) -> None:
        self._edit(lambda request: request.update(strategy=strategy))

    def set_parameters(self, min_block_minutes: int, max_block_minutes: int) -> None:
        self._edit(lambda request: request.update(parameters={"min_block_minutes": min_block_minutes, "max_block_minutes": max_block_minutes}))

    @staticmethod
    def _interval_kind(kind: str) -> None:
        if kind not in ("availability", "busy_events"):
            raise WorkspaceError("时段类型必须是 availability 或 busy_events。")

    def add_interval(self, kind: str, start: str, end: str) -> None:
        self._interval_kind(kind)
        self._edit(lambda request: request[kind].append({"start": start, "end": end}))

    def remove_interval(self, kind: str, index: int) -> None:
        self._interval_kind(kind)
        def remove(request):
            if type(index) is not int or not 0 <= index < len(request[kind]):
                raise WorkspaceError("时段序号无效；请重新查看时段列表。")
            del request[kind][index]
        self._edit(remove)

    def update_interval(self, kind: str, index: int, start: str, end: str) -> None:
        """Edit a calendar event atomically, preserving it on invalid input."""
        self._interval_kind(kind)
        def update(request):
            if type(index) is not int or not 0 <= index < len(request[kind]):
                raise WorkspaceError("时段序号无效；请重新查看时段列表。")
            request[kind][index] = {"start": start, "end": end}
        self._edit(update)

    def _planning_snapshot(self, now: datetime | None) -> dict:
        candidate = self.snapshot
        current = max(parse_datetime(candidate["now"], "now"), _ceil_minute(now))
        if current >= parse_datetime(candidate["horizon_end"], "horizon_end"):
            raise WorkspaceError("规划窗口已经结束；请重新设置起止时间。")
        if any(parse_datetime(block["start"], "locked_blocks.start") < current for block in candidate["locked_blocks"]):
            raise WorkspaceError("存在已开始或过去的锁定块；请先解除锁定，并手动核对任务剩余分钟后重排。")
        candidate["now"] = _stamp(current)
        return candidate

    @staticmethod
    def _run(candidate: dict) -> dict:
        parsed = _validated(candidate)
        result = schedule(parsed)
        errors = validate_result(parsed, result)
        if errors:
            raise WorkspaceError("计划约束校验失败：" + "; ".join(errors))
        try:
            return result_to_dict(result, parsed.timezone)
        except InputError as exc:
            raise WorkspaceError(str(exc)) from exc

    def generate(self, *, now: datetime | None = None) -> dict:
        candidate = self._planning_snapshot(now)
        candidate["input_revision"] = str(uuid4())
        result = self._run(candidate)
        self._request, self._result = candidate, result
        return self.result

    def compare(self, *, now: datetime | None = None) -> list[dict]:
        candidate = self._planning_snapshot(now)
        results = []
        for strategy in ("edf", "importance", "risk"):
            candidate["strategy"] = strategy
            results.append(self._run(candidate))
        return results

    def _calendar_snapshot(self, now: datetime | None) -> dict:
        candidate = self._planning_snapshot(now)
        candidate["availability"] = [{"start": candidate["now"], "end": candidate["horizon_end"]}]
        return candidate

    def generate_calendar(self, *, now: datetime | None = None) -> dict:
        """Plan in all free calendar slots; busy events and locks still apply."""
        candidate = self._calendar_snapshot(now)
        candidate["input_revision"] = str(uuid4())
        result = self._run(candidate)
        self._request, self._result = candidate, result
        return self.result

    def compare_calendar(self, *, now: datetime | None = None) -> list[dict]:
        candidate = self._calendar_snapshot(now)
        results = []
        for strategy in ("edf", "importance", "risk"):
            candidate["strategy"] = strategy
            results.append(self._run(candidate))
        return results

    def lock_block(self, index: int, *, now: datetime | None = None) -> str:
        if self._result is None:
            raise WorkspaceError("当前没有有效计划；请先生成计划。")
        _validated(self._request, self._result)
        result = self.result
        if type(index) is not int or not 0 <= index < len(result["blocks"]):
            raise WorkspaceError("计划块序号无效；请重新查看计划。")
        block = result["blocks"][index]
        if block["source"] == "locked":
            raise WorkspaceError("这个计划块已经锁定。")
        if parse_datetime(block["start"], "block.start") <= _utc_now(now):
            raise WorkspaceError("只能锁定尚未开始的计划块；已开始的工作请手动核对剩余分钟。")
        candidate = self.snapshot
        locked_id = str(uuid4())
        candidate["locked_blocks"].append({"locked_id": locked_id, "task_id": block["task_id"], "start": block["start"], "end": block["end"]})
        candidate["input_revision"] = str(uuid4())
        block.update(source="locked", locked_id=locked_id)
        result["input_revision"] = candidate["input_revision"]
        parsed = _validated(candidate)
        result["metrics"] = compute_metrics(parsed, parse_result(result).blocks)
        _validated(candidate, result)
        self._request, self._result = candidate, result
        return locked_id

    def unlock(self, locked_id: str) -> None:
        def remove(request):
            blocks = request["locked_blocks"]
            if not any(block["locked_id"] == locked_id for block in blocks):
                raise WorkspaceError("未找到该锁定块；请重新查看锁定列表。")
            request["locked_blocks"] = [block for block in blocks if block["locked_id"] != locked_id]
        self._edit(remove)
