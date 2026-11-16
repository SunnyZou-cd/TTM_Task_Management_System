"""课程调度器：整数分钟、排序和区间贪心，不改变传入的数据。"""

from copy import deepcopy
from datetime import datetime
import time


def new_data():
    """每次返回独立的空工作区。"""
    return {"format": "course-demo-1", "tasks": [], "busy": [], "locks": [],
            "plan": [], "settings": {"strategy": "edf", "min_block": 15,
                                     "max_block": 60, "days": 7}}


def now_minutes():
    """向上取整，避免把当前已经开始的一分钟排进去。"""
    return int(-(-time.time() // 60))


def parse_time(value):
    """本机时间输入转换为 Unix 分钟；拒绝格式错误和不存在的本地时间。"""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
        candidates = set()
        # 回拨时同一个钟面可能对应两个时刻；向前跳时可能一个都没有。
        for fold in (0, 1):
            minute = int(parsed.replace(fold=fold).timestamp() // 60)
            if format_time(minute) == value:
                candidates.add(minute)
        if len(candidates) != 1:
            raise ValueError("Local time is nonexistent or ambiguous")
        return candidates.pop()
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise ValueError("Use a valid local time: YYYY-MM-DD HH:MM") from exc


def format_time(minute):
    """显示时再转回本机日期，不自行实现时区。"""
    return datetime.fromtimestamp(minute * 60).strftime("%Y-%m-%d %H:%M")


def _integer(value, name, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError(name + " must be an integer in range")


def _interval(item):
    if not isinstance(item, dict):
        raise ValueError("Interval must be an object")
    _integer(item.get("start"), "start")
    _integer(item.get("end"), "end")
    if item["start"] >= item["end"]:
        raise ValueError("Interval start must precede end")


def _overlap(first, second):
    return first["start"] < second["end"] and second["start"] < first["end"]


def _validate_blocks(blocks, tasks, busy, is_lock, settings):
    """检查同一份块列表的冲突和工作量；锁会在另一列表里出现，不能重复相加。"""
    totals = {task_id: 0 for task_id in tasks}
    counts = {task_id: 0 for task_id in tasks}
    for index, block in enumerate(blocks):
        _interval(block)
        task_id = block.get("task_id")
        _integer(task_id, "task_id", 1)
        if task_id not in tasks or type(block.get("locked")) is not bool:
            raise ValueError("Block must reference a task and have a boolean locked flag")
        if is_lock and not block["locked"]:
            raise ValueError("All locks must have locked=true")
        task = tasks[task_id]
        if block["start"] < task["start"] or block["end"] > task["deadline"]:
            raise ValueError("Block is outside its task window")
        if any(_overlap(block, other) for other in busy + blocks[:index]):
            raise ValueError("Blocks overlap each other or busy time")
        minutes = block["end"] - block["start"]
        if task["splittable"] and not block["locked"] and minutes > settings["max_block"]:
            raise ValueError("Split block exceeds max_block")
        totals[task_id] += minutes
        counts[task_id] += 1
    for task_id, task in tasks.items():
        if totals[task_id] > task["remaining"]:
            raise ValueError("Blocks exceed remaining task minutes")
        if not task["splittable"] and counts[task_id] and (
                counts[task_id] != 1 or totals[task_id] != task["remaining"]):
            raise ValueError("Non-splittable task needs one complete block")


def validate_data(data):
    """存档和表单共用的基础校验；过去的锁可以加载，但必须解除后才能重排。"""
    if not isinstance(data, dict) or data.get("format") != "course-demo-1":
        raise ValueError("Unsupported workspace format")
    for name in ("tasks", "busy", "locks", "plan"):
        if not isinstance(data.get(name), list):
            raise ValueError(name + " must be a list")
    settings = data.get("settings")
    if not isinstance(settings, dict) or settings.get("strategy") not in ("edf", "importance", "risk"):
        raise ValueError("Unknown strategy")
    for name in ("min_block", "max_block", "days"):
        _integer(settings.get(name), name, 1)
    if settings["min_block"] > settings["max_block"]:
        raise ValueError("min_block must not exceed max_block")
    tasks = {}
    for task in data["tasks"]:
        if not isinstance(task, dict):
            raise ValueError("Task must be an object")
        for name in ("id", "total", "remaining", "importance", "start", "deadline"):
            _integer(task.get(name), name)
        if task["id"] < 1 or task["id"] in tasks:
            raise ValueError("Task IDs must be unique positive integers")
        if not isinstance(task.get("title"), str) or not task["title"].strip():
            raise ValueError("Task title must not be empty")
        if not 0 <= task["remaining"] <= task["total"] or task["total"] < 1:
            raise ValueError("Require 0 <= remaining <= total and total > 0")
        if not 1 <= task["importance"] <= 5 or task["start"] >= task["deadline"]:
            raise ValueError("Importance must be 1..5 and start must precede deadline")
        if type(task.get("splittable")) is not bool:
            raise ValueError("splittable must be boolean")
        tasks[task["id"]] = task
    for busy in data["busy"]:
        _interval(busy)
    for name in ("locks", "plan"):
        _validate_blocks(data[name], tasks, data["busy"], name == "locks", settings)
    if data["plan"]:
        locked = [block for block in data["plan"] if block["locked"]]
        key = lambda block: (block["task_id"], block["start"], block["end"])
        if sorted(map(key, locked)) != sorted(map(key, data["locks"])):
            raise ValueError("Plan locked blocks must match locks")


def _subtract(free, start, end):
    """从空闲区间中剪去一段；允许 busy 相互重叠，结果仍不会重复计时。"""
    result = []
    for left, right in free:
        if end <= left or right <= start:
            result.append((left, right))
        else:
            if left < start:
                result.append((left, start))
            if end < right:
                result.append((end, right))
    return result


def _slots(task, free):
    """任务只能使用自己开始时间到截止时间之间的空闲部分。"""
    return [(max(left, task["start"]), min(right, task["deadline"]))
            for left, right in free
            if max(left, task["start"]) < min(right, task["deadline"])]


def _next_block(task, remaining, free, settings):
    for left, right in _slots(task, free):
        if task["splittable"]:
            minutes = min(right - left, remaining, settings["max_block"])
            # 唯一例外是任务最后一小段，例如 65 分钟可以排成 60 + 5。
            if minutes < settings["min_block"] and minutes != remaining:
                continue
        else:
            if right - left < remaining:
                continue
            minutes = remaining
        return {"task_id": task["id"], "start": left, "end": left + minutes, "locked": False}
    return None


def make_plan(data, now=None):
    """每次取排名最高且能放入的块，扣除空闲时间，再排序，直到无法继续。"""
    validate_data(data)
    now = now_minutes() if now is None else now
    _integer(now, "now")
    end = now + data["settings"]["days"] * 1440
    blocks = deepcopy(data["locks"])
    if any(block["start"] < now or block["end"] > end for block in blocks):
        raise ValueError("Unlock past or outside-horizon blocks before replanning")
    tasks = [task for task in data["tasks"] if task["remaining"] > 0]
    remaining = {task["id"]: task["remaining"] for task in tasks}
    free = [(now, end)]
    for block in data["busy"] + blocks:
        free = _subtract(free, block["start"], block["end"])
    for block in blocks:
        remaining[block["task_id"]] -= block["end"] - block["start"]
    settings = data["settings"]
    while True:
        candidates = [task for task in tasks if remaining[task["id"]] > 0]
        def order(task):
            if settings["strategy"] == "edf":
                return (task["deadline"], task["id"])
            if settings["strategy"] == "importance":
                return (-task["importance"], task["deadline"], task["id"])
            capacity = sum(right - left for left, right in _slots(task, free))
            urgency = 1 / (1 + max(0, task["deadline"] - now) / 60)
            pressure = min(1, remaining[task["id"]] / capacity) if capacity else 1
            risk = (urgency + task["importance"] / 5 + pressure) / 3
            return (-risk, task["deadline"], task["id"])
        for task in sorted(candidates, key=order):
            block = _next_block(task, remaining[task["id"]], free, settings)
            if block:
                blocks.append(block)
                remaining[task["id"]] -= block["end"] - block["start"]
                free = _subtract(free, block["start"], block["end"])
                break
        else:
            break
    unscheduled = []
    for task in sorted(tasks, key=lambda item: item["id"]):
        if remaining[task["id"]] == 0:
            continue
        if task["deadline"] <= now:
            reason = "deadline_passed"
        elif task["start"] >= end:
            reason = "outside_window"
        elif not _slots(task, free):
            reason = "no_available_capacity"
        elif not task["splittable"]:
            reason = "insufficient_contiguous_capacity"
        else:
            reason = "insufficient_capacity"
        unscheduled.append({"task_id": task["id"], "minutes": remaining[task["id"]], "reason": reason})
    complete = [task for task in tasks if remaining[task["id"]] == 0]
    requested = sum(task["remaining"] for task in tasks)
    missing = sum(item["minutes"] for item in unscheduled)
    weight = sum(task["importance"] for task in tasks)
    metrics = {"requested": requested, "scheduled": requested - missing,
               "unscheduled": missing, "complete": len(complete), "tasks": len(tasks),
               "weighted_ratio": sum(task["importance"] for task in complete) / weight if weight else None}
    blocks.sort(key=lambda block: (block["start"], block["end"], block["task_id"]))
    return {"blocks": blocks, "unscheduled": unscheduled, "metrics": metrics}
