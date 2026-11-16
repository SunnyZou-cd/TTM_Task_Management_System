"""普通 JSON 存档：旧内容检查、备份、临时文件替换，以及只读旧版导入。"""

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from .scheduler import new_data, validate_data, _subtract


def _read(path):
    """BOM 也可以读取；损坏的 JSON 不会被当成一个新工作区。"""
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid workspace JSON") from exc


def load(path):
    data = _read(path)
    validate_data(data)
    return data


def _check_disk(path, previous_bytes):
    """调用者必须提供上次读到或写入的原始字节，才有资格覆盖现存文件。"""
    current = path.read_bytes() if path.exists() else None
    if current != previous_bytes:
        raise ValueError("Workspace changed on disk; reload or save to a new path")
    return current


def save(path, data, previous_bytes=None):
    """返回新文件字节，供下次保存比较；.bak 保留替换前的完整文件。"""
    validate_data(data)
    content = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    path = Path(path)
    previous = _check_disk(path, previous_bytes)
    # 即使误把旧档字节传进来，也禁止把旧版存档就地替换成课程版。
    if previous is not None:
        try:
            if json.loads(previous.decode("utf-8-sig")).get("format") != "course-demo-1":
                raise ValueError("Save imported workspaces to a different path")
        except (UnicodeError, AttributeError, json.JSONDecodeError) as exc:
            raise ValueError("Cannot overwrite an invalid workspace") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _check_disk(path, previous_bytes)
        if previous is not None:
            Path(str(path) + ".bak").write_bytes(previous)
        _check_disk(path, previous_bytes)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return content


def _legacy_time(value):
    """旧时间含时区偏移，转换后保留同一个真实时刻。"""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.second or parsed.microsecond:
        raise ValueError("Legacy timestamps must have timezone offsets and whole minutes")
    return int(parsed.timestamp() // 60)


def import_legacy(path):
    """只读转换；旧计划可能已过期，因此清空，仅保留任务、忙碌与显式锁。"""
    old = _read(path)
    try:
        if old["format"] != "academic-scheduler-workspace" or type(old["version"]) is not int or old["version"] != 1:
            raise ValueError("Unsupported legacy workspace format")
        request = old["request"]
        if request["schema_version"] != "1":
            raise ValueError("Unsupported legacy request version")
        data = new_data()
        ids = {}
        for index, task in enumerate(request["tasks"], 1):
            old_id = task["task_id"]
            if not isinstance(old_id, str) or not old_id or old_id in ids:
                raise ValueError("Legacy task IDs must be unique strings")
            ids[old_id] = index
            remaining = task["remaining_minutes"]
            if task.get("status", "active") == "completed":
                remaining = 0
            elif task.get("status", "active") != "active":
                raise ValueError("Unsupported legacy task status")
            data["tasks"].append({"id": index, "title": task["title"],
                "total": task["estimated_minutes"], "remaining": remaining,
                "importance": task["importance"], "start": _legacy_time(task["earliest_start"]),
                "deadline": _legacy_time(task["deadline"]), "splittable": task["splittable"]})
        for event in request["busy_events"] + request["locked_blocks"]:
            block = {"start": _legacy_time(event["start"]), "end": _legacy_time(event["end"])}
            if "locked_id" in event and event.get("task_id") is not None:
                block.update(task_id=ids[event["task_id"]], locked=True)
                data["locks"].append(block)
            else:
                data["busy"].append(block)
        start, end = _legacy_time(request["now"]), _legacy_time(request["horizon_end"])
        if end <= start:
            raise ValueError("Invalid legacy planning horizon")
        # 旧版 availability 之外的部分转换成忙碌，保留旧窗口内的限制。
        unavailable = [(start, end)]
        for slot in request["availability"]:
            left, right = _legacy_time(slot["start"]), _legacy_time(slot["end"])
            if left >= right:
                raise ValueError("Invalid legacy availability")
            unavailable = _subtract(unavailable, left, right)
        data["busy"].extend({"start": left, "end": right} for left, right in unavailable)
        parameters = request.get("parameters", {})
        data["settings"] = {"strategy": request["strategy"],
            "min_block": parameters.get("min_block_minutes", 15),
            "max_block": parameters.get("max_block_minutes", 60),
            "days": max(1, (end - start + 1439) // 1440)}
        validate_data(data)
        return data
    except (KeyError, TypeError, AttributeError, OverflowError, OSError) as exc:
        raise ValueError("Invalid legacy workspace fields") from exc
