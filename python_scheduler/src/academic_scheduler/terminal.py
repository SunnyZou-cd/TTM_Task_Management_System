"""Interactive, local-only interface for personal scheduling workspaces."""

from datetime import datetime, timezone
from pathlib import Path
import re

from .models import parse_datetime, resolve_timezone
from .storage import WorkspaceStore
from .workspace import Workspace


_REASONS = {
    "deadline_passed": "截止时间已过", "outside_window": "任务不在规划窗口内",
    "no_available_capacity": "没有可用时间", "insufficient_contiguous_capacity": "没有足够的连续时间",
    "below_min_block": "可用时段短于最小块长", "insufficient_capacity": "可用时间不足",
}


def _time(value, zone):
    """Return an offset-bearing ISO time; reject DST gaps and folds."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", value):
        local = datetime.strptime(value, "%Y-%m-%d %H:%M")
        tz = resolve_timezone(zone)
        choices = []
        for fold in (0, 1):
            candidate = local.replace(tzinfo=tz, fold=fold)
            if candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == local:
                if all(candidate.utcoffset() != c.utcoffset() for c in choices):
                    choices.append(candidate)
        if not choices:
            raise ValueError("这个本地时间因夏令时调整而不存在，请重新输入。")
        if len(choices) > 1:
            raise ValueError("这个本地时间有两个可能的时差，请输入带偏移的 ISO 时间。")
        return choices[0].isoformat(timespec="minutes")
    parse_datetime(value, "时间")
    return value


def _prompt(label, default=None):
    suffix = f" [{default}]" if default is not None else ""
    answer = input(f"{label}{suffix}: ").strip()
    return str(default) if not answer and default is not None else answer


def _number(label, default=None):
    value = _prompt(label, default)
    try:
        return int(value)
    except ValueError:
        raise ValueError("请输入整数。") from None


def _yes(label):
    return _prompt(label + "（输入 y 确认）").lower() == "y"


def _choose(items, label):
    if not items:
        raise ValueError("没有可选择的项目。")
    index = _number(label) - 1
    if index < 0 or index >= len(items):
        raise ValueError("序号超出范围。")
    return index


def _display_time(label, zone, default=None):
    return _time(_prompt(label + "（YYYY-MM-DD HH:MM 或带偏移 ISO）", default), zone)


class _Terminal:
    def __init__(self, store, workspace):
        self.store, self.workspace = store, workspace
        self.dirty = False

    def _edit(self, method, *args, **kwargs):
        result = method(*args, **kwargs)
        self.dirty = True
        return result

    def _tasks(self):
        tasks = self.workspace.snapshot["tasks"]
        if not tasks:
            print("暂无任务。")
        for index, task in enumerate(tasks, 1):
            print(f"{index}. {task['title']} | 剩余 {task['remaining_minutes']}/{task['estimated_minutes']} 分钟 | 重要性 {task['importance']} | 截止 {task['deadline']} | {task.get('status', 'active')}")
        return tasks

    def _task_fields(self, task=None):
        task = task or {}
        zone = self.workspace.snapshot["timezone"]
        title = _prompt("任务名称", task.get("title"))
        estimated = _number("总工作量（分钟）", task.get("estimated_minutes"))
        remaining = _number("剩余工作量（分钟）", task.get("remaining_minutes"))
        importance = _number("重要性（1-5）", task.get("importance"))
        deadline = _display_time("截止时间", zone, task.get("deadline"))
        earliest = _display_time("最早开始", zone, task.get("earliest_start"))
        default = ("y" if task["splittable"] else "n") if "splittable" in task else None
        split = _prompt("允许拆分（y/n）", default).lower()
        if split not in ("y", "n"):
            raise ValueError("请输入 y 或 n。")
        if estimated < 0 or remaining < 0:
            raise ValueError("总工作量和剩余工作量不能为负数。")
        if remaining > estimated:
            raise ValueError("剩余工作量不能大于总工作量。")
        if not 1 <= importance <= 5:
            raise ValueError("重要性必须在 1 到 5 之间。")
        return dict(title=title, estimated_minutes=estimated, remaining_minutes=remaining,
                    importance=importance, deadline=deadline, earliest_start=earliest, splittable=split == "y")

    def tasks(self):
        while True:
            print("\n任务管理：1列表 2新增 3编辑 4删除 5记录剩余分钟 6标记完成 0返回")
            try:
                choice = _prompt("选择")
                if choice == "0": return
                if choice == "1": self._tasks(); continue
                if choice == "2":
                    self._edit(self.workspace.add_task, **self._task_fields()); print("任务已新增。"); continue
                if choice not in ("3", "4", "5", "6"): raise ValueError("请选择菜单中的序号。")
                tasks = self._tasks()
                task = tasks[_choose(tasks, "任务序号")]
                ident = task["task_id"]
                if choice == "3": self._edit(self.workspace.update_task, ident, **self._task_fields(task))
                elif choice == "4":
                    if not _yes("删除任务及其所有锁定"): continue
                    self._edit(self.workspace.delete_task, ident)
                elif choice == "5": self._edit(self.workspace.update_task, ident, remaining_minutes=_number("实际剩余分钟", task["remaining_minutes"]))
                elif _yes("标记完成并移除其锁定"):
                    self._edit(self.workspace.complete_task, ident)
                else: continue
                print("任务已更新。")
            except (ValueError, OSError) as exc: print(f"操作失败：{exc}")

    def _intervals(self, kind):
        items = self.workspace.snapshot[kind]
        print("可用时段：" if kind == "availability" else "忙碌时段：")
        if not items: print("  暂无。")
        for i, item in enumerate(items, 1): print(f"{i}. {item['start']} → {item['end']}")
        return items

    def times(self):
        while True:
            print("\n时间设置：1窗口/时区 2列时段 3新增可用 4删除可用 5新增忙碌 6删除忙碌 0返回")
            try:
                choice = _prompt("选择")
                if choice == "0": return
                snap = self.workspace.snapshot
                if choice == "1":
                    zone = _prompt("IANA 时区", snap["timezone"])
                    resolve_timezone(zone)
                    start = _display_time("规划开始", zone, snap["now"])
                    end = _display_time("规划结束", zone, snap["horizon_end"])
                    self._edit(self.workspace.set_window, start, end, zone)
                elif choice == "2": self._intervals("availability"); self._intervals("busy_events"); continue
                elif choice in ("3", "5"):
                    kind = "availability" if choice == "3" else "busy_events"
                    start = _display_time("开始", snap["timezone"])
                    end = _display_time("结束", snap["timezone"])
                    self._edit(self.workspace.add_interval, kind, start, end)
                elif choice in ("4", "6"):
                    kind = "availability" if choice == "4" else "busy_events"
                    index = _choose(self._intervals(kind), "时段序号")
                    self._edit(self.workspace.remove_interval, kind, index)
                else: raise ValueError("请选择菜单中的序号。")
                print("时间设置已更新。")
            except (ValueError, OSError) as exc: print(f"操作失败：{exc}")

    def strategy(self):
        snap = self.workspace.snapshot
        print("策略：1 EDF（截止优先） 2 Importance（重要性优先） 3 Risk（风险优先）")
        choice = _prompt("选择策略（回车保留）", {"edf": "1", "importance": "2", "risk": "3"}[snap["strategy"]])
        options = {"1": "edf", "2": "importance", "3": "risk"}
        if choice not in options: raise ValueError("请选择 1、2 或 3。")
        minimum = _number("最短自动块长（分钟）", snap["parameters"]["min_block_minutes"])
        maximum = _number("最长自动块长（分钟）", snap["parameters"]["max_block_minutes"])
        # Each workspace edit is transactional; validate both inputs before the first edit.
        if minimum <= 0 or maximum < minimum: raise ValueError("块长必须为正整数，且最短不能大于最长。")
        if options[choice] != snap["strategy"]: self._edit(self.workspace.set_strategy, options[choice])
        if minimum != snap["parameters"]["min_block_minutes"] or maximum != snap["parameters"]["max_block_minutes"]:
            self._edit(self.workspace.set_parameters, minimum, maximum)
        print("策略和块长已设置。")

    def show_result(self, result=None):
        result = result if result is not None else self.workspace.result
        if result is None:
            print("暂无计划，请先生成。")
            return
        names = {t["task_id"]: t["title"] for t in self.workspace.snapshot["tasks"]}
        print(f"计划（{result['strategy']}）：")
        if not result["blocks"]: print("  没有安排时间块。")
        for i, block in enumerate(result["blocks"], 1):
            name = names.get(block["task_id"], "固定预留")
            locked = " [已锁定]" if block["source"] == "locked" else ""
            print(f"{i}. {name} | {block['start']} → {block['end']} | {block['minutes']} 分钟{locked}")
        if any(parse_datetime(block["start"], "时间块开始") <= datetime.now(timezone.utc) for block in result["blocks"]):
            print("计划包含已开始的时间块，请核对实际进度和剩余分钟，再按需重新排计划。")
        for item in result["unscheduled"]:
            reasons = "、".join(_REASONS.get(reason, reason) for reason in item["reasons"])
            print(f"未排：{names.get(item['task_id'], item['task_id'])}，{item['minutes']} 分钟（{reasons}）")
        m = result["metrics"]
        print(f"已安排 {m['scheduled_minutes']} 分钟；未排 {m['unscheduled_minutes']} 分钟；完整任务 {m['fully_scheduled_tasks']}/{m['eligible_tasks']}。")

    def locks(self):
        while True:
            print("\n锁定管理：1列锁定 2从计划锁定 3解锁 0返回")
            try:
                choice = _prompt("选择")
                if choice == "0": return
                locks = self.workspace.snapshot["locked_blocks"]
                if choice in ("1", "3"):
                    if not locks: print("暂无锁定。")
                    for i, block in enumerate(locks, 1):
                        names = {t['task_id']: t['title'] for t in self.workspace.snapshot['tasks']}
                        print(f"{i}. {names.get(block['task_id'], '固定预留')} | {block['start']} → {block['end']}")
                    if choice == "3":
                        lock = locks[_choose(locks, "锁定序号")]
                        self._edit(self.workspace.unlock, lock["locked_id"]); print("已解锁，旧计划已失效。")
                elif choice == "2":
                    result = self.workspace.result
                    self.show_result(result)
                    blocks = result["blocks"] if result is not None else []
                    index = _choose(blocks, "计划时间块序号")
                    self._edit(self.workspace.lock_block, index); print("已锁定。")
                else: raise ValueError("请选择菜单中的序号。")
            except (ValueError, OSError) as exc: print(f"操作失败：{exc}")

    def save(self):
        self.store.save(self.workspace)
        self.dirty = False
        print(f"已保存到 {self.store.path}。")

    def save_as(self):
        path = _prompt("新存档路径")
        if not path:
            raise ValueError("请输入新存档路径。")
        store = WorkspaceStore(Path(path))
        store.save(self.workspace)
        self.store, self.dirty = store, False
        print(f"已另存到 {self.store.path}。")

    def run(self):
        while True:
            snap = self.workspace.snapshot
            print(f"\n存档：{self.store.path} | {'未保存' if self.dirty else '无未保存更改'} | 时区：{snap['timezone']}")
            print(f"规划窗口：{snap['now']} → {snap['horizon_end']}")
            print("1任务管理 2时间设置 3策略/块长 4生成/重排 5查看计划 6锁定管理 7比较策略 8保存 9重新加载 10另存为 0退出")
            try:
                choice = _prompt("选择")
                if choice == "1": self.tasks()
                elif choice == "2": self.times()
                elif choice == "3": self.strategy()
                elif choice == "4":
                    self._edit(self.workspace.generate); print("计划已生成。请根据实际进度记录剩余分钟。")
                    self.show_result()
                elif choice == "5": self.show_result()
                elif choice == "6": self.locks()
                elif choice == "7":
                    for result in self.workspace.compare(): self.show_result(result)
                    print("比较未更改当前计划。")
                elif choice == "8": self.save()
                elif choice == "10": self.save_as()
                elif choice == "9":
                    if self.dirty and not _yes("放弃未保存更改并重新加载"): continue
                    loaded = self.store.load()
                    self.workspace, self.dirty = loaded, False
                    print("已重新加载。")
                elif choice == "0":
                    if not self.dirty: return 0
                    action = _prompt("有未保存更改：保存(s)、放弃(d)、取消(c)").lower()
                    if action == "s": self.save(); return 0
                    if action == "d": print("已放弃未保存更改。"); return 0
                    if action != "c": print("请输入 s、d 或 c。")
                else: print("请选择菜单中的序号。")
            except (ValueError, OSError) as exc: print(f"操作失败：{exc}")


def run_terminal(data_path: str | Path | None = None) -> int:
    path = Path(data_path) if data_path is not None else Path.cwd() / "work" / "demo1-data" / "workspace.json"
    store = WorkspaceStore(path)
    try:
        workspace = store.load() if path.exists() else Workspace.new()
    except (ValueError, OSError) as exc:
        print(f"无法加载存档：{exc}")
        return 1
    terminal = _Terminal(store, workspace)
    try:
        return terminal.run()
    except (EOFError, KeyboardInterrupt):
        print("\n输入已中断。" + ("更改尚未保存。" if terminal.dirty else ""))
        return 1
