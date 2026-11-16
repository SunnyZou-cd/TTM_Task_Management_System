"""Local desktop interface for the academic scheduler."""

from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .models import parse_datetime, resolve_timezone
from .storage import WorkspaceStore
from .terminal import _REASONS, _time
from .workspace import Workspace


_EN = {
    "学业任务规划": "Academic Task Planner", "保存": "Save", "另存为": "Save as", "打开存档": "Open workspace", "重新加载": "Reload",
    "任务": "Tasks", "时间": "Time", "计划": "Plan", "剩余/总分钟": "Remaining / total min", "重要性": "Priority", "截止": "Deadline", "状态": "Status",
    "任务信息": "Task details", "任务名称": "Title", "总分钟": "Total minutes", "剩余分钟": "Remaining minutes", "重要性 1–5": "Priority 1–5", "最早开始": "Earliest start", "截止时间": "Deadline", "允许拆分": "Allow splitting",
    "时间可输入 YYYY-MM-DD HH:MM（当前时区）或带偏移 ISO 时间。": "Use YYYY-MM-DD HH:MM in the current time zone, or ISO time with an offset.",
    "清空表单": "Clear form", "新增任务": "Add task", "保存选中任务修改": "Update selected task", "记录剩余分钟": "Record remaining", "标记完成": "Mark complete", "删除任务": "Delete task",
    "规划窗口与时区": "Planning window and time zone", "IANA 时区": "IANA time zone", "开始": "Start", "结束": "End", "应用窗口": "Apply window",
    "本地时间格式 YYYY-MM-DD HH:MM；夏令时歧义时请使用带偏移的 ISO 时间。": "Local time: YYYY-MM-DD HH:MM. For ambiguous daylight-saving times, include an ISO offset.",
    "类型": "Type", "添加可用时段": "Add availability", "添加忙碌时段": "Add busy time", "删除选中时段": "Remove selected interval",
    "调度设置": "Scheduling settings", "策略": "Strategy", "最短块（分钟）": "Minimum block (min)", "最长块（分钟）": "Maximum block (min)", "应用设置": "Apply settings",
    "生成 / 重新规划": "Generate / replan", "比较三种策略": "Compare strategies", "锁定选中计划块": "Lock selected block", "解锁选中锁定块": "Unlock selected block",
    "分钟": "min", "未排任务与指标": "Unscheduled tasks and metrics", "解锁时在上方计划选择锁定块；若计划已失效，请从下方锁定列表选择。": "To unlock, select a locked plan block above or select it from the lock list below.", "锁定任务": "Locked task",
    "操作失败": "Action failed", "请先选择一行。": "Select a row first.", "任务信息有误": "Invalid task", "请选择任务": "Select a task", "记录进度": "Record progress", "实际剩余分钟：": "Actual remaining minutes:",
    "确认完成该任务？其锁定时间块也会移除。": "Mark this task complete? Its locked blocks will also be removed.", "确认删除该任务及其锁定时间块？": "Delete this task and its locked blocks?",
    "时间有误": "Invalid time", "请选择时段": "Select an interval", "设置有误": "Invalid settings", "请选择计划块": "Select a plan block", "请选择锁定块": "Select a locked block", "请在锁定列表选择一行。": "Select a row in the lock list.", "所选时间块尚未锁定。": "The selected block is not locked.",
    "比较失败": "Comparison failed", "策略比较（不更改当前计划）": "Strategy comparison (current plan unchanged)", "保存失败": "Save failed", "另存失败": "Save as failed", "加载失败": "Load failed", "无法加载存档": "Could not load workspace",
    "另存为新文件": "Save as a new file", "工作区": "Workspace", "所有文件": "All files", "打开放弃": "Discard", "放弃更改": "Discard changes", "有未保存更改，确认放弃并加载其他存档？": "Discard unsaved changes and load another workspace?",
    "打开工作区": "Open workspace", "未保存更改": "Unsaved changes", "保存更改后退出？选择“否”放弃更改，选择“取消”继续编辑。": "Save changes before quitting? Choose No to discard or Cancel to keep editing.",
    "总分钟、剩余分钟和重要性必须是整数。": "Total, remaining minutes and priority must be integers.", "工作分钟不能为负数。": "Minutes cannot be negative.", "剩余分钟不能大于总分钟。": "Remaining minutes cannot exceed total minutes.", "重要性必须在 1 到 5 之间。": "Priority must be between 1 and 5.", "块长须为正整数，最短不能大于最长。": "Block lengths must be positive and the minimum cannot exceed the maximum.", "请选择策略。": "Select a strategy.",
    "这个本地时间因夏令时调整而不存在，请重新输入。": "This local time does not exist due to daylight saving time. Enter another time.", "这个本地时间有两个可能的时差，请输入带偏移的 ISO 时间。": "This local time is ambiguous. Enter an ISO time with an explicit offset.",
    "暂无计划。请先设置可用时段并生成。": "No plan yet. Add availability and generate a plan.", "固定预留": "Reserved", "已锁定": "Locked", "自动": "Automatic", "可用": "Available", "忙碌": "Busy", "未保存": "Unsaved", "无未保存更改": "No unsaved changes", "存档：": "Workspace: ", "时区：": "Time zone: ",
    "策略：": "Strategy: ", "已安排：": "Scheduled: ", "未排：": "Unscheduled: ", "完整任务：": "Fully scheduled: ", "完成比例：": "Completion ratio: ", "加权完成比例：": "Weighted completion: ", "可用：": "Available: ", "预留：": "Reserved: ", "利用率：": "Utilization: ", " 分钟": " min", "包含已开始的时间块，请核对实际进度与剩余分钟，再按需重新规划。": "Some blocks have started. Check actual progress and remaining minutes before replanning.",
    "截止时间已过": "Deadline passed", "任务不在规划窗口内": "Outside planning window", "没有可用时间": "No available time", "没有足够的连续时间": "Insufficient contiguous time", "可用时段短于最小块长": "Available intervals are below the minimum block length", "可用时间不足": "Insufficient available time",
    "存档 JSON 含重复字段：": "Duplicate JSON field: ", "存档 JSON 不允许 ": "Invalid JSON constant: ", "无法读取工作区存档：": "Cannot read workspace: ", "无法打开存档 ": "Cannot open workspace ",
    "存档已被其他程序删除；请先核对磁盘文件。": "The workspace was deleted externally. Check the file before saving.", "存档已存在但尚未加载；请先加载，不能直接覆盖。": "The file already exists and was not loaded. Open it first or choose a new path.", "存档已被其他程序修改；请先重新加载或另存到新路径。": "The workspace changed externally. Reload or save to a new path.",
    "工作区验证失败，尚未保存：": "Workspace validation failed; nothing saved: ", "存档正在被其他进程保存，或留有锁文件；请核对后重试。": "Another process is saving, or a lock file remains. Check and retry.", "保存失败，内存数据仍保留：": "Save failed; your in-memory changes remain: ",
    "当前时间必须是带时区的 datetime。": "The current time must include a time zone.", "当前时间超出可用日期范围。": "The current time is out of range.", "计划已过期或不满足约束：": "The plan is stale or violates constraints: ", "新工作区的七天窗口超出可用日期范围。": "The new seven-day window is out of range.",
    "存档必须包含 format、version、request、result 四个字段。": "The workspace must contain format, version, request, and result.", "不支持的工作区存档格式或版本。": "Unsupported workspace format or version.", "存档 result 必须是计划对象或 null。": "Workspace result must be a plan or null.",
    "未找到该任务；请重新查看任务列表。": "Task not found. Refresh the task list.", "任务 ID 不可修改，且不能设置未支持的任务字段。": "Task IDs cannot be changed and unsupported fields are not allowed.", "时段类型必须是 availability 或 busy_events。": "Invalid interval type.", "时段序号无效；请重新查看时段列表。": "Invalid interval selection.",
    "规划窗口已经结束；请重新设置起止时间。": "The planning window has ended. Set a new window.", "存在已开始或过去的锁定块；请先解除锁定，并手动核对任务剩余分钟后重排。": "A locked block has started or passed. Unlock it and check remaining work before replanning.", "计划约束校验失败：": "Plan validation failed: ",
    "当前没有有效计划；请先生成计划。": "There is no valid plan. Generate one first.", "计划块序号无效；请重新查看计划。": "Invalid plan block selection.", "这个计划块已经锁定。": "This block is already locked.", "只能锁定尚未开始的计划块；已开始的工作请手动核对剩余分钟。": "Only future blocks can be locked. Check remaining work for blocks that have started.", "未找到该锁定块；请重新查看锁定列表。": "Lock not found. Refresh the lock list.",
}


_EN.update({"表单尚未应用": "Unapplied form changes", "请先应用或清空表单中的更改，再保存。": "Apply or clear form changes before saving.", "有尚未应用的表单内容，确认放弃？": "Discard unapplied form changes?", "任务表单有未应用的更改，确认放弃并选择其他任务？": "Discard unapplied task changes and select another task?"})
_ZH_ERRORS = {
    "must be ISO 8601 with explicit minute offset and zero seconds/microseconds": "须为带明确时差且秒数为零的 ISO 时间",
    "must be a nonempty string without surrounding whitespace": "不能为空，且首尾不能有空格", "must contain valid Unicode scalar values": "必须包含有效字符",
    "must not be after deadline": "不得晚于截止时间", "must be after now": "必须晚于规划开始时间", "start must be before end": "开始时间必须早于结束时间",
    "must lie fully within [now, horizon_end]": "必须完全位于规划窗口内", "must be covered by merged availability": "必须在可用时段内", "must not overlap busy_events": "不能与忙碌时段重叠", "must not overlap another locked block": "不能与其他锁定块重叠",
    "must reference an active task with remaining work": "必须关联仍有剩余工作的有效任务", "must lie within the task's earliest_start/deadline": "必须在任务最早开始与截止时间之间", "invalid UTC offset": "UTC 偏移无效",
    "must be zero for completed/deleted tasks": "已完成或已删除任务的剩余分钟必须为零", "must be an integer >= ": "必须为整数，且不少于 ", " and <= ": "，且不大于 ",
}


def _english(text):
    text = str(text)
    if text in _EN: return _EN[text]
    for source in sorted(_EN, key=len, reverse=True): text = text.replace(source, _EN[source])
    return text


class _Dialogs:
    def __init__(self, gui): self.gui = gui
    def __getattr__(self, name):
        function = getattr(messagebox, name)
        def translated(title, message, **kwargs):
            if self.gui.language.get() != "English":
                for source, replacement in _ZH_ERRORS.items(): message = str(message).replace(source, replacement)
            return function(self.gui.tr(title), self.gui.tr(message), **kwargs)
        return translated


class SchedulerGUI:
    def __init__(self, root, store, workspace):
        self.root, self.store, self.workspace = root, store, workspace
        self.dirty = False
        self._suppress_selection = False
        self._task_baseline = None
        self._last_snapshot = None
        self.language = tk.StringVar(value="English")
        self.msg = _Dialogs(self)
        root.title("学业任务规划")
        width = min(1100, max(820, root.winfo_screenwidth() - 60))
        height = min(760, max(600, root.winfo_screenheight() - 100))
        root.geometry(f"{width}x{height}")
        root.minsize(820, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Language / 语言").pack(side="right", padx=4)
        selector = ttk.Combobox(toolbar, textvariable=self.language, values=("English", "简体中文"), state="readonly", width=12)
        selector.pack(side="right", padx=4)
        selector.bind("<<ComboboxSelected>>", self.change_language)
        for label, command in (("保存", self.save), ("另存为", self.save_as), ("打开存档", self.open_file), ("重新加载", self.reload)):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 6))
        self.status = ttk.Label(root, anchor="w", padding=(10, 4))
        self.status.pack(fill="x")
        tabs = ttk.Notebook(root)
        tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.task_tab, self.time_tab, self.plan_tab = (ttk.Frame(tabs, padding=10) for _ in range(3))
        for frame, name in ((self.task_tab, "任务"), (self.time_tab, "时间"), (self.plan_tab, "计划")):
            tabs.add(frame, text=name)
        self._task_ui()
        self._time_ui()
        self._plan_ui()
        self._capture_text()
        self.refresh()
        self.change_language()

    def tr(self, text):
        if self.language.get() != "English": return str(text)
        return _english(text)

    def _capture_text(self):
        self._widget_text = []
        self._headings = []
        self._tabs = []
        def visit(widget):
            if isinstance(widget, ttk.Notebook):
                self._tabs.extend((widget, tab, widget.tab(tab, "text")) for tab in widget.tabs())
            if isinstance(widget, ttk.Treeview):
                self._headings.extend((widget, col, widget.heading(col, "text")) for col in widget["columns"])
            try:
                text = widget.cget("text")
                if text: self._widget_text.append((widget, text))
            except tk.TclError: pass
            for child in widget.winfo_children(): visit(child)
        visit(self.root)

    def change_language(self, event=None):
        window_values = {key: var.get() for key, var in self.window_vars.items()}
        settings = (self.strategy_var.get(), self.min_var.get(), self.max_var.get())
        selections = {tree: tree.selection() for tree in (self.task_tree, self.interval_tree, self.block_tree, self.lock_tree)}
        self.root.title(self.tr("学业任务规划"))
        for widget, text in self._widget_text: widget.configure(text=self.tr(text))
        for tree, col, text in self._headings: tree.heading(col, text=self.tr(text))
        for notebook, tab, text in self._tabs: notebook.tab(tab, text=self.tr(text))
        self._suppress_selection = True
        self.refresh()
        for key, value in window_values.items(): self.window_vars[key].set(value)
        for var, value in zip((self.strategy_var, self.min_var, self.max_var), settings): var.set(value)
        for tree, items in selections.items():
            for item in items:
                if tree.exists(item): tree.selection_add(item)
        self.root.after_idle(lambda: setattr(self, "_suppress_selection", False))

    def _tree(self, parent, columns, height=7, expand=True):
        frame = ttk.Frame(parent)
        frame.pack(fill="both" if expand else "x", expand=expand, pady=5)
        tree = ttk.Treeview(frame, columns=[key for key, _, _ in columns], show="headings", height=height, selectmode="browse")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=60, stretch=True)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    def _buttons(self, parent, buttons):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=4)
        for label, command in buttons:
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=(0, 6))

    def _task_ui(self):
        self.task_tree = self._tree(self.task_tab, [("title", "任务", 200), ("remaining", "剩余/总分钟", 110), ("importance", "重要性", 70), ("deadline", "截止", 180), ("status", "状态", 80)])
        self.task_tree.bind("<<TreeviewSelect>>", self._select_task)
        form = ttk.LabelFrame(self.task_tab, text="任务信息", padding=8)
        form.pack(fill="x")
        self.task_vars = {name: tk.StringVar() for name in ("title", "estimated_minutes", "remaining_minutes", "importance", "earliest_start", "deadline")}
        labels = (("title", "任务名称"), ("estimated_minutes", "总分钟"), ("remaining_minutes", "剩余分钟"), ("importance", "重要性 1–5"), ("earliest_start", "最早开始"), ("deadline", "截止时间"))
        for index, (key, label) in enumerate(labels):
            row, col = divmod(index, 3)
            ttk.Label(form, text=label).grid(row=row*2, column=col, sticky="w", padx=4)
            ttk.Entry(form, textvariable=self.task_vars[key]).grid(row=row*2+1, column=col, sticky="ew", padx=4, pady=(0, 6))
            form.columnconfigure(col, weight=1)
        self.splittable = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="允许拆分", variable=self.splittable).grid(row=4, column=0, sticky="w", padx=4)
        ttk.Label(form, text="时间可输入 YYYY-MM-DD HH:MM（当前时区）或带偏移 ISO 时间。").grid(row=5, column=0, columnspan=3, sticky="w", padx=4)
        self._buttons(self.task_tab, (("清空表单", self.clear_task), ("新增任务", self.add_task), ("保存选中任务修改", self.update_task), ("记录剩余分钟", self.progress), ("标记完成", self.complete_task), ("删除任务", self.delete_task)))

    def _time_ui(self):
        window = ttk.LabelFrame(self.time_tab, text="规划窗口与时区", padding=8)
        window.pack(fill="x")
        self.window_vars = {key: tk.StringVar() for key in ("timezone", "now", "horizon_end")}
        for col, (key, title) in enumerate((("timezone", "IANA 时区"), ("now", "开始"), ("horizon_end", "结束"))):
            ttk.Label(window, text=title).grid(row=0, column=col, sticky="w", padx=4)
            ttk.Entry(window, textvariable=self.window_vars[key]).grid(row=1, column=col, sticky="ew", padx=4)
            window.columnconfigure(col, weight=1)
        ttk.Button(window, text="应用窗口", command=self.set_window).grid(row=1, column=3, padx=6)
        ttk.Label(window, text="本地时间格式 YYYY-MM-DD HH:MM；夏令时歧义时请使用带偏移的 ISO 时间。").grid(row=2, column=0, columnspan=4, sticky="w", padx=4, pady=5)
        self.interval_tree = self._tree(self.time_tab, [("kind", "类型", 90), ("start", "开始", 210), ("end", "结束", 210)], height=9)
        entry = ttk.Frame(self.time_tab)
        entry.pack(fill="x")
        self.interval_start, self.interval_end = tk.StringVar(), tk.StringVar()
        for label, var in (("开始", self.interval_start), ("结束", self.interval_end)):
            ttk.Label(entry, text=label).pack(side="left", padx=4)
            ttk.Entry(entry, textvariable=var).pack(side="left", fill="x", expand=True, padx=4)
        self._buttons(self.time_tab, (("添加可用时段", lambda: self.add_interval("availability")), ("添加忙碌时段", lambda: self.add_interval("busy_events")), ("删除选中时段", self.remove_interval)))

    def _plan_ui(self):
        settings = ttk.LabelFrame(self.plan_tab, text="调度设置", padding=8)
        settings.pack(fill="x")
        self.strategy_var, self.min_var, self.max_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(settings, text="策略").pack(side="left")
        ttk.Combobox(settings, textvariable=self.strategy_var, values=("edf", "importance", "risk"), state="readonly", width=15).pack(side="left", padx=5)
        for title, var in (("最短块（分钟）", self.min_var), ("最长块（分钟）", self.max_var)):
            ttk.Label(settings, text=title).pack(side="left", padx=4)
            ttk.Entry(settings, textvariable=var, width=7).pack(side="left", padx=4)
        ttk.Button(settings, text="应用设置", command=self.set_strategy).pack(side="left", padx=5)
        self._buttons(self.plan_tab, (("生成 / 重新规划", self.generate), ("比较三种策略", self.compare), ("锁定选中计划块", self.lock_block), ("解锁选中锁定块", self.unlock)))
        self.block_tree = self._tree(self.plan_tab, [("task", "任务", 170), ("start", "开始", 180), ("end", "结束", 180), ("minutes", "分钟", 65), ("source", "状态", 80)], height=7)
        ttk.Label(self.plan_tab, text="未排任务与指标").pack(anchor="w")
        self.summary = tk.Text(self.plan_tab, height=4, wrap="word", state="disabled")
        self.summary.pack(fill="both", expand=True)
        ttk.Label(self.plan_tab, text="解锁时在上方计划选择锁定块；若计划已失效，请从下方锁定列表选择。").pack(anchor="w", pady=(5, 0))
        self.lock_tree = self._tree(self.plan_tab, [("task", "锁定任务", 170), ("start", "开始", 180), ("end", "结束", 180)], height=2, expand=False)
        self.block_tree.bind("<<TreeviewSelect>>", lambda event: self._exclusive_selection(self.block_tree, self.lock_tree))
        self.lock_tree.bind("<<TreeviewSelect>>", lambda event: self._exclusive_selection(self.lock_tree, self.block_tree))

    def _exclusive_selection(self, source, other):
        if source.selection() and other.selection(): other.selection_remove(other.selection())

    def _perform(self, action, *args, **kwargs):
        try:
            value = action(*args, **kwargs)
        except (ValueError, OSError) as exc:
            self.msg.showerror("操作失败", str(exc), parent=self.root)
            return False
        self.dirty = True
        self.refresh()
        return True

    def _selected(self, tree):
        selected = tree.selection()
        if not selected:
            raise ValueError("请先选择一行。")
        return selected[0]

    def _selected_task(self):
        return self.workspace.snapshot["tasks"][int(self._selected(self.task_tree))]

    def _select_task(self, event=None):
        if self._suppress_selection or not self.task_tree.selection(): return
        selected = self._selected_task()["task_id"]
        previous_id = self._task_baseline[0] if self._task_baseline is not None else None
        baseline = self._task_baseline[1] if self._task_baseline is not None else ("", "", "", "", "", "", True)
        if selected == previous_id and self._task_form() != baseline:
            return
        if selected != previous_id and self._task_form() != baseline:
            if not self.msg.askyesno("表单尚未应用", "任务表单有未应用的更改，确认放弃并选择其他任务？", parent=self.root):
                previous = next((str(i) for i, task in enumerate(self.workspace.snapshot["tasks"]) if task["task_id"] == previous_id), None)
                self._suppress_selection = True
                self.task_tree.selection_remove(self.task_tree.selection())
                if previous is not None: self.task_tree.selection_set(previous)
                self.root.after_idle(lambda: setattr(self, "_suppress_selection", False))
                return
        task = self._selected_task()
        for name, var in self.task_vars.items(): var.set(str(task[name]))
        self.splittable.set(task["splittable"])
        self._task_baseline = (task["task_id"], self._task_form())

    def _task_form(self):
        return tuple(var.get() for var in self.task_vars.values()) + (self.splittable.get(),)

    def _has_drafts(self):
        snap = self.workspace.snapshot
        baseline = self._task_baseline[1] if self._task_baseline is not None else ("", "", "", "", "", "", True)
        task_draft = self._task_form() != baseline
        window_draft = any(var.get() != snap[key] for key, var in self.window_vars.items())
        settings_draft = (self.strategy_var.get(), self.min_var.get(), self.max_var.get()) != (snap["strategy"], str(snap["parameters"]["min_block_minutes"]), str(snap["parameters"]["max_block_minutes"]))
        return task_draft or window_draft or settings_draft or bool(self.interval_start.get().strip() or self.interval_end.get().strip())

    def clear_task(self):
        for var in self.task_vars.values(): var.set("")
        self.splittable.set(True)
        self._task_baseline = None
        self.task_tree.selection_remove(self.task_tree.selection())

    def _task_fields(self):
        values = {key: var.get().strip() for key, var in self.task_vars.items()}
        try:
            for key in ("estimated_minutes", "remaining_minutes", "importance"): values[key] = int(values[key])
        except ValueError: raise ValueError("总分钟、剩余分钟和重要性必须是整数。") from None
        if values["estimated_minutes"] < 0 or values["remaining_minutes"] < 0: raise ValueError("工作分钟不能为负数。")
        if values["remaining_minutes"] > values["estimated_minutes"]: raise ValueError("剩余分钟不能大于总分钟。")
        if not 1 <= values["importance"] <= 5: raise ValueError("重要性必须在 1 到 5 之间。")
        zone = self.workspace.snapshot["timezone"]
        for key in ("deadline", "earliest_start"): values[key] = _time(values[key], zone)
        values["splittable"] = self.splittable.get()
        return values

    def add_task(self):
        try: fields = self._task_fields()
        except ValueError as exc: self.msg.showerror("任务信息有误", str(exc), parent=self.root); return
        if self._perform(self.workspace.add_task, **fields): self.clear_task()

    def update_task(self):
        try: task, fields = self._selected_task(), self._task_fields()
        except ValueError as exc: self.msg.showerror("任务信息有误", str(exc), parent=self.root); return
        if self._perform(self.workspace.update_task, task["task_id"], **fields): self.clear_task()

    def progress(self):
        try: task = self._selected_task()
        except ValueError as exc: self.msg.showerror("请选择任务", str(exc), parent=self.root); return
        value = simpledialog.askinteger(self.tr("记录进度"), self.tr("实际剩余分钟："), initialvalue=task["remaining_minutes"], minvalue=0, parent=self.root)
        if value is not None: self._perform(self.workspace.update_task, task["task_id"], remaining_minutes=value)

    def complete_task(self):
        try: task = self._selected_task()
        except ValueError as exc: self.msg.showerror("请选择任务", str(exc), parent=self.root); return
        if self.msg.askyesno("标记完成", "确认完成该任务？其锁定时间块也会移除。", parent=self.root): self._perform(self.workspace.complete_task, task["task_id"])

    def delete_task(self):
        try: task = self._selected_task()
        except ValueError as exc: self.msg.showerror("请选择任务", str(exc), parent=self.root); return
        if self.msg.askyesno("删除任务", "确认删除该任务及其锁定时间块？", parent=self.root): self._perform(self.workspace.delete_task, task["task_id"])

    def set_window(self):
        try:
            zone = self.window_vars["timezone"].get().strip()
            resolve_timezone(zone)
            start = _time(self.window_vars["now"].get().strip(), zone)
            end = _time(self.window_vars["horizon_end"].get().strip(), zone)
        except ValueError as exc: self.msg.showerror("时间有误", str(exc), parent=self.root); return
        self._perform(self.workspace.set_window, start, end, zone)

    def add_interval(self, kind):
        try:
            zone = self.workspace.snapshot["timezone"]
            start, end = _time(self.interval_start.get().strip(), zone), _time(self.interval_end.get().strip(), zone)
        except ValueError as exc: self.msg.showerror("时间有误", str(exc), parent=self.root); return
        if self._perform(self.workspace.add_interval, kind, start, end): self.interval_start.set(""); self.interval_end.set("")

    def remove_interval(self):
        try:
            kind, index = self._selected(self.interval_tree).split(":")
            self._perform(self.workspace.remove_interval, kind, int(index))
        except ValueError as exc: self.msg.showerror("请选择时段", str(exc), parent=self.root)

    def set_strategy(self):
        try:
            minimum, maximum = int(self.min_var.get()), int(self.max_var.get())
            strategy = self.strategy_var.get()
            if minimum <= 0 or maximum < minimum: raise ValueError("块长须为正整数，最短不能大于最长。")
            if strategy not in ("edf", "importance", "risk"): raise ValueError("请选择策略。")
        except ValueError as exc: self.msg.showerror("设置有误", str(exc), parent=self.root); return
        snap = self.workspace.snapshot
        if strategy != snap["strategy"] and not self._perform(self.workspace.set_strategy, strategy): return
        if (minimum, maximum) != (snap["parameters"]["min_block_minutes"], snap["parameters"]["max_block_minutes"]): self._perform(self.workspace.set_parameters, minimum, maximum)

    def generate(self):
        self._perform(self.workspace.generate)

    def lock_block(self):
        try: index = int(self._selected(self.block_tree))
        except ValueError as exc: self.msg.showerror("请选择计划块", str(exc), parent=self.root); return
        self._perform(self.workspace.lock_block, index)

    def unlock(self):
        try:
            if self.lock_tree.selection():
                lock = self.workspace.snapshot["locked_blocks"][int(self._selected(self.lock_tree))]["locked_id"]
            else:
                result = self.workspace.result
                if result is None: raise ValueError("请在锁定列表选择一行。")
                block = result["blocks"][int(self._selected(self.block_tree))]
                lock = block["locked_id"]
                if not lock: raise ValueError("所选时间块尚未锁定。")
        except ValueError as exc: self.msg.showerror("请选择锁定块", str(exc), parent=self.root); return
        self._perform(self.workspace.unlock, lock)

    def _summary(self, result):
        if result is None: return "暂无计划。请先设置可用时段并生成。"
        names = {t["task_id"]: t["title"] for t in self.workspace.snapshot["tasks"]}
        metrics = result["metrics"]
        percent = lambda value: f"{value:.1%}" if value is not None else "—"
        lines = [f"{self.tr('策略：')}{result['strategy']}　{self.tr('已安排：')}{metrics['scheduled_minutes']}{self.tr(' 分钟')}　{self.tr('未排：')}{metrics['unscheduled_minutes']}{self.tr(' 分钟')}　{self.tr('完整任务：')}{metrics['fully_scheduled_tasks']}/{metrics['eligible_tasks']}",
                 f"{self.tr('完成比例：')}{percent(metrics['completion_ratio'])}　{self.tr('加权完成比例：')}{percent(metrics['weighted_completion_ratio'])}　{self.tr('可用：')}{metrics['available_minutes']}{self.tr(' 分钟')}　{self.tr('预留：')}{metrics['reserved_minutes']}{self.tr(' 分钟')}　{self.tr('利用率：')}{percent(metrics['utilization_ratio'])}"]
        for item in result["unscheduled"]:
            reasons = ", ".join(self.tr(_REASONS.get(reason, reason)) for reason in item["reasons"])
            lines.append(f"{self.tr('未排：')}{names.get(item['task_id'], item['task_id'])}: {item['minutes']}{self.tr(' 分钟')} ({reasons})")
        if any(parse_datetime(block["start"], "时间") <= datetime.now(timezone.utc) for block in result["blocks"]): lines.append(self.tr("包含已开始的时间块，请核对实际进度与剩余分钟，再按需重新规划。"))
        return "\n".join(lines)

    def compare(self):
        try: results = self.workspace.compare()
        except (ValueError, OSError) as exc: self.msg.showerror("比较失败", str(exc), parent=self.root); return
        window = tk.Toplevel(self.root)
        window.title(self.tr("策略比较（不更改当前计划）"))
        text = tk.Text(window, width=100, height=24, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", "\n\n".join(self._summary(result) for result in results))
        text.configure(state="disabled")

    def refresh(self):
        snap, result = self.workspace.snapshot, self.workspace.result
        self.status.configure(text=f"{self.tr('存档：')}{self.store.path}  |  {self.tr('未保存' if self.dirty else '无未保存更改')}  |  {self.tr('时区：')}{snap['timezone']}")
        for tree in (self.task_tree, self.interval_tree, self.block_tree, self.lock_tree): tree.delete(*tree.get_children())
        names = {t["task_id"]: t["title"] for t in snap["tasks"]}
        for i, task in enumerate(snap["tasks"]):
            statuses = {"active": "Active", "completed": "Completed", "deleted": "Deleted"} if self.language.get() == "English" else {"active": "进行中", "completed": "已完成", "deleted": "已删除"}
            self.task_tree.insert("", "end", iid=str(i), values=(task["title"], f"{task['remaining_minutes']}/{task['estimated_minutes']}", task["importance"], task["deadline"], statuses.get(task.get("status", "active"))))
        for kind, label in (("availability", "可用"), ("busy_events", "忙碌")):
            for i, interval in enumerate(snap[kind]): self.interval_tree.insert("", "end", iid=f"{kind}:{i}", values=(self.tr(label), interval["start"], interval["end"]))
        for i, lock in enumerate(snap["locked_blocks"]): self.lock_tree.insert("", "end", iid=str(i), values=(names.get(lock["task_id"], self.tr("固定预留")), lock["start"], lock["end"]))
        if result:
            for i, block in enumerate(result["blocks"]): self.block_tree.insert("", "end", iid=str(i), values=(names.get(block["task_id"], self.tr("固定预留")), block["start"], block["end"], block["minutes"], self.tr("已锁定" if block["source"] == "locked" else "自动")))
        old = self._last_snapshot
        for key, var in self.window_vars.items():
            if old is None or old[key] != snap[key]: var.set(snap[key])
        if old is None or old["strategy"] != snap["strategy"]: self.strategy_var.set(snap["strategy"])
        if old is None or old["parameters"] != snap["parameters"]:
            self.min_var.set(str(snap["parameters"]["min_block_minutes"]))
            self.max_var.set(str(snap["parameters"]["max_block_minutes"]))
        self._last_snapshot = snap
        self.summary.configure(state="normal"); self.summary.delete("1.0", "end"); self.summary.insert("1.0", self.tr("暂无计划。请先设置可用时段并生成。") if result is None else self._summary(result)); self.summary.configure(state="disabled")

    def save(self):
        if self._has_drafts():
            self.msg.showerror("表单尚未应用", "请先应用或清空表单中的更改，再保存。", parent=self.root)
            return False
        try: self.store.save(self.workspace)
        except (ValueError, OSError) as exc: self.msg.showerror("保存失败", str(exc), parent=self.root); return False
        self.dirty = False; self.refresh(); return True

    def save_as(self):
        if self._has_drafts():
            self.msg.showerror("表单尚未应用", "请先应用或清空表单中的更改，再保存。", parent=self.root)
            return False
        path = filedialog.asksaveasfilename(parent=self.root, title=self.tr("另存为新文件"), defaultextension=".json", filetypes=[(self.tr("工作区"), "*.json"), (self.tr("所有文件"), "*")])
        if not path: return False
        candidate = WorkspaceStore(path)
        try: candidate.save(self.workspace)
        except (ValueError, OSError) as exc: self.msg.showerror("另存失败", str(exc), parent=self.root); return False
        self.store = candidate; self.dirty = False; self.refresh(); return True

    def _discard(self):
        if self._has_drafts() and not self.msg.askyesno("表单尚未应用", "有尚未应用的表单内容，确认放弃？", parent=self.root): return False
        return not self.dirty or self.msg.askyesno("放弃更改", "有未保存更改，确认放弃并加载其他存档？", parent=self.root)

    def _load(self, candidate):
        try: workspace = candidate.load()
        except (ValueError, OSError) as exc: self.msg.showerror("加载失败", str(exc), parent=self.root); return False
        self.store, self.workspace, self.dirty = candidate, workspace, False
        self.clear_task(); self.interval_start.set(""); self.interval_end.set(""); self._last_snapshot = None; self.refresh(); return True

    def reload(self):
        if self._discard(): self._load(WorkspaceStore(self.store.path))

    def open_file(self):
        if not self._discard(): return
        path = filedialog.askopenfilename(parent=self.root, title=self.tr("打开工作区"), filetypes=[(self.tr("工作区"), "*.json"), (self.tr("所有文件"), "*")])
        if path: self._load(WorkspaceStore(path))

    def close(self):
        if self._has_drafts() and not self.msg.askyesno("表单尚未应用", "有尚未应用的表单内容，确认放弃？", parent=self.root): return
        if self.dirty:
            decision = self.msg.askyesnocancel("未保存更改", "保存更改后退出？选择“否”放弃更改，选择“取消”继续编辑。", parent=self.root)
            if decision is None: return
            if decision:
                self.clear_task(); self.interval_start.set(""); self.interval_end.set(""); self._last_snapshot = None; self.refresh()
                if not self.save(): return
        self.root.destroy()


def run_gui(data_path: str | Path | None = None) -> int:
    path = Path(data_path) if data_path is not None else Path.cwd() / "work" / "demo1-data" / "workspace.json"
    root = tk.Tk()
    root.withdraw()
    store = WorkspaceStore(path)
    try: workspace = store.load() if path.exists() else Workspace.new()
    except (ValueError, OSError) as exc:
        messagebox.showerror("Could not load workspace", _english(exc), parent=root)
        root.destroy()
        return 1
    SchedulerGUI(root, store, workspace)
    root.deiconify()
    root.mainloop()
    return 0
