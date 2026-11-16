"""Local desktop interface for the academic scheduler."""

from datetime import datetime, timedelta, time, timezone
from pathlib import Path
from uuid import uuid4
import tkinter as tk
from tkinter import font as tkfont
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
    "暂无计划。请先设置可用时段并生成。": "No plan yet. Create tasks and generate a plan from free calendar slots.", "固定预留": "Reserved", "已锁定": "Locked", "自动": "Automatic", "可用": "Available", "忙碌": "Busy", "未保存": "Unsaved", "无未保存更改": "No unsaved changes", "存档：": "Workspace: ", "时区：": "Time zone: ",
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
_EN.update({"文件":"File", "今天":"Today", "规划设置":"Planning settings", "＋ 新建任务":"＋ Create task", "编辑":"Edit", "日":"Day", "周":"Week", "高级选项":"Advanced options", "取消":"Cancel", "删除":"Delete", "忙碌时间":"Busy time", "计划块":"Plan block", "解锁":"Unlock", "锁定时间":"Lock time", "编辑任务":"Edit task", "点击空白添加忙碌时间 · 点击色块查看详情":"Click an empty slot to add busy time · Click a block for details", "按日历空白自动安排；忙碌时间与锁定块会被保留。":"Schedule in free calendar slots. Busy time and locked blocks are preserved."})
_EN.update({"在整个规划范围的空白时间安排":"Free slots across the planning window", "本机时间 YYYY-MM-DD HH:MM":"Computer time: YYYY-MM-DD HH:MM"})
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


def _local_text(value):
    return parse_datetime(value, "时间").astimezone(resolve_timezone("local")).strftime("%Y-%m-%d %H:%M")


def _local_input(value, original=None):
    # Keeping an unchanged field preserves its exact instant, including fold.
    if original is not None and value == _local_text(original):
        return original
    return _time(value, "local")


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
        workspace = Workspace.from_document(workspace.to_document(), local_time=True)
        self.root, self.store, self.workspace = root, store, workspace
        self.dirty = False
        self._suppress_selection = False
        self._task_baseline = None
        self._last_snapshot = None
        self.language = tk.StringVar(value="English")
        self.msg = _Dialogs(self)
        self.view_date = parse_datetime(workspace.snapshot["now"], "now").astimezone(resolve_timezone("local")).date()
        self.view_mode = tk.StringVar(value="Week")
        self._dialog = None
        root.geometry("1240x800")
        root.minsize(960, 640)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.configure("Primary.TButton", padding=(18, 9))
        style.configure("TButton", padding=(8, 5))
        self._build_calendar_ui()
        self._capture_text()
        self.refresh()
        self.change_language()

    def tr(self, text):
        if self.language.get() != "English": return str(text)
        return _english(text)

    def _capture_text(self):
        previous = {str(widget): text for widget, text in getattr(self, "_widget_text", []) if widget.winfo_exists()}
        self._widget_text = []
        previous_headings = {(str(tree), col): text for tree, col, text in getattr(self, "_headings", []) if tree.winfo_exists()}
        self._headings = []
        self._tabs = []
        def visit(widget):
            if isinstance(widget, ttk.Notebook):
                self._tabs.extend((widget, tab, widget.tab(tab, "text")) for tab in widget.tabs())
            if isinstance(widget, ttk.Treeview):
                self._headings.extend((widget, col, previous_headings.get((str(widget), col), widget.heading(col, "text"))) for col in widget["columns"])
            try:
                text = widget.cget("text")
                if text and not getattr(widget, "_user_content", False): self._widget_text.append((widget, previous.get(str(widget), text)))
            except tk.TclError: pass
            for child in widget.winfo_children(): visit(child)
        visit(self.root)

    def change_language(self, event=None):
        self.root.title(self.tr("学业任务规划"))
        for widget, text in self._widget_text:
            if widget.winfo_exists(): widget.configure(text=self.tr(text))
        for tree, col, text in self._headings:
            if tree.winfo_exists(): tree.heading(col, text=self.tr(text))
        for index, (label, command) in enumerate(self._file_actions):
            self.file_menu.entryconfigure(index, label=self.tr(label))
        self.menu.entryconfigure(0, label=self.tr("文件"))
        self.refresh()

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

    def _build_calendar_ui(self):
        self._file_actions = (("保存", self.save), ("另存为", self.save_as), ("打开存档", self.open_file), ("重新加载", self.reload))
        self.menu = tk.Menu(self.root, tearoff=False)
        self.file_menu = tk.Menu(self.menu, tearoff=False)
        for label, command in self._file_actions: self.file_menu.add_command(label=label, command=command)
        self.menu.add_cascade(label="文件", menu=self.file_menu)
        self.root.configure(menu=self.menu)
        header = ttk.Frame(self.root, padding=(16, 12))
        header.pack(fill="x")
        ttk.Label(header, text="学业任务规划", font=("Segoe UI", 13, "bold")).pack(side="left", padx=(0, 10))
        ttk.Button(header, text="今天", command=self.today).pack(side="left")
        ttk.Button(header, text="‹", width=3, command=lambda: self.navigate(-1)).pack(side="left", padx=(10, 2))
        ttk.Button(header, text="›", width=3, command=lambda: self.navigate(1)).pack(side="left")
        self.date_title = ttk.Label(header, font=("Segoe UI", 13))
        self.date_title.pack(side="left", padx=8)
        actions = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        actions.pack(fill="x")
        selector = ttk.Combobox(actions, textvariable=self.language, values=("English", "简体中文"), state="readonly", width=11)
        selector.pack(side="right", padx=(12, 0)); selector.bind("<<ComboboxSelected>>", self.change_language)
        ttk.Button(actions, text="规划设置", command=self.settings_dialog).pack(side="right", padx=6)
        ttk.Button(actions, text="生成 / 重新规划", style="Primary.TButton", command=self.generate).pack(side="right")
        ttk.Label(actions, text="在整个规划范围的空白时间安排").pack(side="left")
        self.status = ttk.Label(self.root, padding=(16, 2), anchor="w")
        self.status.pack(side="bottom", fill="x")
        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        sidebar = ttk.Frame(body, width=260, padding=(0, 8, 12, 0))
        body.add(sidebar, weight=0)
        ttk.Button(sidebar, text="＋ 新建任务", style="Primary.TButton", command=self.task_dialog).pack(fill="x", pady=(0, 14))
        ttk.Label(sidebar, text="任务", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.task_tree = self._tree(sidebar, [("title", "任务", 145), ("remaining", "分钟", 65)], height=10)
        self.task_tree.bind("<<TreeviewSelect>>", self._select_task)
        self.task_tree.bind("<Double-1>", lambda event: self.task_dialog(edit=True))
        self._buttons(sidebar, (("编辑", lambda: self.task_dialog(edit=True)), ("标记完成", self.complete_task)))
        self._buttons(sidebar, (("记录进度", self.progress), ("删除任务", self.delete_task)))
        ttk.Label(sidebar, text="未排任务与指标").pack(anchor="w", pady=(12, 4))
        self.summary = tk.Text(sidebar, width=30, height=9, wrap="word", relief="flat", background="#f5f7fb", font=("Segoe UI", 9), state="disabled")
        self.summary.pack(fill="x")
        calendar = ttk.Frame(body, padding=(8, 8, 0, 0)); body.add(calendar, weight=1)
        bar = ttk.Frame(calendar); bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="点击空白添加忙碌时间 · 点击色块查看详情").pack(side="left")
        for label, value in (("周", "Week"), ("日", "Day")):
            ttk.Radiobutton(bar, text=label, variable=self.view_mode, value=value, command=self.draw_calendar).pack(side="right", padx=6)
        legend = ttk.Frame(calendar); legend.pack(fill="x", pady=(0, 7))
        for label, color in (("自动", "#d9e7fd"), ("已锁定", "#cbeadc"), ("忙碌", "#e8e9ed")):
            tk.Label(legend, text="  ", background=color).pack(side="left", padx=(0, 4))
            ttk.Label(legend, text=label).pack(side="left", padx=(0, 14))
        self.day_header = tk.Canvas(calendar, height=45, background="white", highlightthickness=0)
        self.day_header.pack(fill="x")
        grid = ttk.Frame(calendar); grid.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(grid, background="white", highlightthickness=0)
        scroll = ttk.Scrollbar(grid, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", lambda event: self.draw_calendar())
        self.canvas.bind("<Button-1>", self.calendar_click)
        self.canvas.bind("<MouseWheel>", lambda event: self.canvas.yview_scroll(-int(event.delta/120), "units"))
        self.root.after_idle(lambda: self.canvas.yview_moveto(7/24))
        # Selection adapters retain the same validated workspace actions without visible tabs.
        hidden = ttk.Frame(self.root)
        self.interval_tree = ttk.Treeview(hidden, columns=("kind", "start", "end"))
        self.block_tree = ttk.Treeview(hidden, columns=("task", "start", "end", "minutes", "source"))
        self.lock_tree = ttk.Treeview(hidden, columns=("task", "start", "end"))
        self.block_tree.bind("<<TreeviewSelect>>", lambda event: self._exclusive_selection(self.block_tree, self.lock_tree))
        self.lock_tree.bind("<<TreeviewSelect>>", lambda event: self._exclusive_selection(self.lock_tree, self.block_tree))
        self.task_vars = {name: tk.StringVar() for name in ("title", "estimated_minutes", "remaining_minutes", "importance", "earliest_start", "deadline")}
        self.splittable = tk.BooleanVar(value=True)
        self.window_vars = {key: tk.StringVar() for key in ("now", "horizon_end")}
        self.interval_start, self.interval_end = tk.StringVar(), tk.StringVar()
        self.strategy_var, self.min_var, self.max_var = tk.StringVar(), tk.StringVar(), tk.StringVar()

    def prepare_planning(self):
        return True

    def today(self):
        self.view_date = datetime.now(resolve_timezone("local")).date()
        self.draw_calendar()

    def navigate(self, direction):
        self.view_date += timedelta(days=direction * (7 if self.view_mode.get() == "Week" else 1))
        self.draw_calendar()

    def _visible_dates(self):
        start = self.view_date - timedelta(days=self.view_date.weekday()) if self.view_mode.get() == "Week" else self.view_date
        return [start + timedelta(days=i) for i in range(7 if self.view_mode.get() == "Week" else 1)]

    def draw_calendar(self):
        self.canvas.delete("all"); self.day_header.delete("all")
        dates = self._visible_dates()
        width = max(400, self.canvas.winfo_width()); gutter = 54; col = (width-gutter)/len(dates); hour = 58
        self._calendar_geometry = (gutter, col, hour, dates)
        self.canvas.configure(scrollregion=(0, 0, width, hour*24))
        self.date_title.configure(text=f"{dates[0]:%b %d} – {dates[-1]:%b %d, %Y}" if len(dates)>1 else f"{dates[0]:%b %d, %Y}")
        weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun") if self.language.get()=="English" else ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        zone = resolve_timezone("local")
        today = datetime.now(zone).date()
        for i, day in enumerate(dates):
            x = gutter+i*col
            if day==today: self.canvas.create_rectangle(x,0,x+col,24*hour,fill="#f6f9ff",outline="")
            self.day_header.create_text(x+col/2,22,text=f"{weekdays[day.weekday()]} {day.day}",fill="#1967d2" if day==today else "#46516a",font=("Segoe UI",11,"bold"))
            self.canvas.create_line(x,0,x,24*hour,fill="#e8ebf0")
        for h in range(24):
            y=h*hour
            self.canvas.create_text(gutter-8,y+8,text=f"{h:02}:00",anchor="e",fill="#7a8495",font=("Segoe UI",9))
            self.canvas.create_line(gutter,y,width,y,fill="#e8ebf0")
        snap=self.workspace.snapshot; result=self.workspace.result
        names={t["task_id"]:t["title"] for t in snap["tasks"]}
        entries=[("busy",i,item) for i,item in enumerate(snap["busy_events"])]
        entries += [("block",i,item) for i,item in enumerate(result["blocks"])] if result else [("lock",i,item) for i,item in enumerate(snap["locked_blocks"])]
        self._calendar_items={}
        for day_index,day in enumerate(dates):
            midnight=datetime.combine(day,time(),zone); next_midnight=datetime.combine(day+timedelta(days=1),time(),zone)
            day_entries=[]
            for kind,index,item in entries:
                start=parse_datetime(item["start"],"start").astimezone(zone); end=parse_datetime(item["end"],"end").astimezone(zone)
                if start<next_midnight and end>midnight: day_entries.append((max(start,midnight),min(end,next_midnight),kind,index,item))
            day_entries.sort(key=lambda entry:entry[0])
            # Divide overlapping clusters into lanes so every event remains clickable.
            clusters=[]
            for entry in day_entries:
                if not clusters or entry[0]>=max(e[1] for e in clusters[-1]): clusters.append([])
                clusters[-1].append(entry)
            for cluster in clusters:
                lanes=[]; placed=[]
                for entry in cluster:
                    lane=next((i for i,end in enumerate(lanes) if end<=entry[0]),len(lanes))
                    if lane==len(lanes): lanes.append(entry[1])
                    else: lanes[lane]=entry[1]
                    placed.append((lane,entry))
                for lane,(start,end,kind,index,item) in placed:
                    y1=(start.hour*60+start.minute)/60*hour
                    y2=24*hour if end.date()>day else (end.hour*60+end.minute)/60*hour
                    x1=gutter+day_index*col+lane*col/len(lanes)+3; x2=x1+col/len(lanes)-6
                    locked=kind=="lock" or item.get("source")=="locked"
                    color="#e8e9ed" if kind=="busy" else "#cbeadc" if locked else "#d9e7fd"
                    label=self.tr("忙碌") if kind=="busy" else names.get(item["task_id"],self.tr("固定预留"))
                    tag=f"event_{kind}_{index}_{day_index}"
                    dst = start.utcoffset() != end.utcoffset()
                    bottom=max(y1+(44 if dst else 23),y2-2)
                    self.canvas.create_rectangle(x1,y1+2,x2,bottom,fill=color,outline="#b26c18" if dst else "white",tags=tag)
                    text=f"{start:%H:%M}  {'◆ ' if locked else ''}{label}"
                    if dst:
                        elapsed=int((end.astimezone(timezone.utc)-start.astimezone(timezone.utc)).total_seconds()/60)
                        text=f"{start:%H:%M} → {end:%H:%M} ({elapsed} min) {label}"
                    fitted=self._fit_event_text(text,max(10,x2-x1-10),bottom-y1-7)
                    self.canvas.create_text(x1+5,y1+5,text=fitted,anchor="nw",fill="#253858",font=("Segoe UI",9),tags=tag)
                    self._calendar_items[tag]=(kind,index)
        if today in dates:
            now=datetime.now(zone); y=(now.hour+now.minute/60)*hour; x=gutter+dates.index(today)*col
            self.canvas.create_line(x,y,x+col,y,fill="#d93025",width=2)

    def _fit_event_text(self, text, width, height):
        font=tkfont.Font(root=self.root,family="Segoe UI",size=9)
        limit=max(1,int(height/font.metrics("linespace")))
        lines=[]; pending=str(text)
        for line_index in range(limit):
            count=0
            while count<len(pending) and font.measure(pending[:count+1])<=width: count+=1
            if count==len(pending): lines.append(pending); break
            if line_index==limit-1:
                while count>0 and font.measure(pending[:count]+"…")>width: count-=1
                lines.append(pending[:count]+"…"); break
            lines.append(pending[:count]); pending=pending[count:].lstrip()
        return "\n".join(lines)

    def calendar_click(self, event):
        for item in reversed(self.canvas.find_overlapping(event.x,self.canvas.canvasy(event.y),event.x,self.canvas.canvasy(event.y))):
            for tag in self.canvas.gettags(item):
                if tag in self._calendar_items:
                    self.event_dialog(*self._calendar_items[tag]); return
        gutter,col,hour,dates=self._calendar_geometry
        if event.x<gutter: return
        day=min(len(dates)-1,max(0,int((event.x-gutter)/col)))
        minutes=min(23*60+45,max(0,int(self.canvas.canvasy(event.y)/hour*4)*15))
        zone=resolve_timezone("local")
        start=datetime.combine(dates[day],time(),zone)+timedelta(minutes=minutes)
        try:
            _time(start.strftime("%Y-%m-%d %H:%M"), "local")
        except ValueError as exc:
            self.msg.showerror("时间有误",str(exc),parent=self.root); return
        self.busy_dialog(start=start)

    def _new_dialog(self, title):
        if self._dialog is not None and self._dialog.winfo_exists():
            self._dialog.lift(); return None
        dialog=tk.Toplevel(self.root); dialog.title(self.tr(title)); dialog.transient(self.root)
        dialog.resizable(False,False); dialog.grab_set(); self._dialog=dialog
        return dialog

    def _dialog_labels(self):
        self._capture_text()
        self.change_language()

    def task_dialog(self, edit=False):
        if edit:
            try: task=self._selected_task()
            except ValueError: return
        dialog=self._new_dialog("任务信息")
        if dialog is None: return
        if edit:
            for key,var in self.task_vars.items(): var.set(_local_text(task[key]) if key in ("earliest_start", "deadline") else str(task[key]))
            self.splittable.set(task["splittable"])
            self._task_baseline=(task["task_id"],self._task_form())
        else:
            self.clear_task(); snap=self.workspace.snapshot
            for key,value in {"estimated_minutes":"60","remaining_minutes":"60","importance":"3","earliest_start":_local_text(snap["now"]),"deadline":_local_text(snap["horizon_end"])}.items(): self.task_vars[key].set(value)
        form=ttk.Frame(dialog,padding=20); form.pack(fill="both")
        def field(parent,row,key,label):
            ttk.Label(parent,text=label).grid(row=row,column=0,sticky="w",pady=6)
            entry=ttk.Entry(parent,textvariable=self.task_vars[key],width=36); entry.grid(row=row,column=1,sticky="ew",padx=(14,0),pady=6)
            return entry
        title=field(form,0,"title","任务名称"); field(form,1,"estimated_minutes","总分钟"); field(form,2,"deadline","截止时间")
        advanced=ttk.Frame(form); opened=tk.BooleanVar(value=False)
        def toggle():
            if opened.get(): advanced.grid(row=4,column=0,columnspan=2,sticky="ew")
            else: advanced.grid_remove()
        ttk.Checkbutton(form,text="高级选项",variable=opened,command=toggle).grid(row=3,column=0,columnspan=2,sticky="w",pady=8)
        field(advanced,0,"remaining_minutes","剩余分钟"); field(advanced,1,"importance","重要性 1–5"); field(advanced,2,"earliest_start","最早开始")
        ttk.Checkbutton(advanced,text="允许拆分",variable=self.splittable).grid(row=3,column=0,columnspan=2,sticky="w")
        previous_total=[self.task_vars["estimated_minutes"].get()]
        def follow_total(*args):
            value=self.task_vars["estimated_minutes"].get()
            if not edit and self.task_vars["remaining_minutes"].get()==previous_total[0]: self.task_vars["remaining_minutes"].set(value)
            previous_total[0]=value
        trace=self.task_vars["estimated_minutes"].trace_add("write",follow_total)
        def finish():
            self.task_vars["estimated_minutes"].trace_remove("write",trace)
            self.clear_task(); dialog.destroy()
        def cancel():
            if self._has_drafts() and not self.msg.askyesno("表单尚未应用","有尚未应用的表单内容，确认放弃？",parent=dialog): return
            finish()
        def submit():
            before=self.workspace.snapshot["input_revision"]
            self.update_task() if edit else self.add_task()
            if before!=self.workspace.snapshot["input_revision"]: finish()
        buttons=ttk.Frame(form); buttons.grid(row=5,column=0,columnspan=2,sticky="e",pady=(16,0))
        ttk.Button(buttons,text="取消",command=cancel).pack(side="left",padx=6)
        ttk.Button(buttons,text="保存",style="Primary.TButton",command=submit).pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW",cancel); title.focus_set(); self._dialog_labels()

    def busy_dialog(self, start=None, index=None):
        dialog=self._new_dialog("忙碌时间")
        if dialog is None: return
        zone=resolve_timezone("local")
        if index is not None:
            interval=self.workspace.snapshot["busy_events"][index]
            a,b=interval["start"],interval["end"]
        else:
            start=start or datetime.now(zone).replace(second=0,microsecond=0)
            a,b=start.isoformat(timespec="minutes"),(start+timedelta(hours=1)).isoformat(timespec="minutes")
        self.interval_start.set(_local_text(a)); self.interval_end.set(_local_text(b))
        form=ttk.Frame(dialog,padding=20); form.pack()
        for row,(label,var) in enumerate((("开始",self.interval_start),("结束",self.interval_end))):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky="w",pady=8)
            ttk.Entry(form,textvariable=var,width=36).grid(row=row,column=1,padx=12)
        ttk.Label(form,text="本机时间 YYYY-MM-DD HH:MM",wraplength=360).grid(row=2,column=0,columnspan=2,sticky="w",pady=8)
        def finish(): self.interval_start.set(""); self.interval_end.set(""); dialog.destroy()
        def save_busy():
            try:
                start_value=_local_input(self.interval_start.get().strip(), a)
                end_value=_local_input(self.interval_end.get().strip(), b)
            except ValueError as exc: self.msg.showerror("时间有误",str(exc),parent=dialog); return
            ok=self._perform(self.workspace.add_interval,"busy_events",start_value,end_value) if index is None else self._perform(self.workspace.update_interval,"busy_events",index,start_value,end_value)
            if ok: finish()
        bar=ttk.Frame(form); bar.grid(row=3,column=0,columnspan=2,sticky="e")
        if index is not None:
            ttk.Button(bar,text="删除",command=lambda: finish() if self._perform(self.workspace.remove_interval,"busy_events",index) else None).pack(side="left",padx=6)
        ttk.Button(bar,text="取消",command=finish).pack(side="left",padx=6)
        ttk.Button(bar,text="保存",command=save_busy).pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW",finish); self._dialog_labels()

    def event_dialog(self, kind, index):
        if kind=="busy": self.busy_dialog(index=index); return
        result=self.workspace.result
        item=result["blocks"][index] if kind=="block" else self.workspace.snapshot["locked_blocks"][index]
        dialog=self._new_dialog("计划块")
        if dialog is None: return
        snap=self.workspace.snapshot; task=next((t for t in snap["tasks"] if t["task_id"]==item["task_id"]),None)
        form=ttk.Frame(dialog,padding=20); form.pack()
        title_label=ttk.Label(form,text=task["title"] if task else self.tr("固定预留"),font=("Segoe UI",13,"bold"),wraplength=400)
        title_label._user_content=True; title_label.pack(anchor="w")
        zone=resolve_timezone("local")
        ttk.Label(form,text="\n".join(parse_datetime(item[key],key).astimezone(zone).strftime("%a %b %d  %H:%M") for key in ("start","end"))).pack(anchor="w",pady=16)
        locked=kind=="lock" or item.get("source")=="locked"
        def act():
            ok=self._perform(self.workspace.unlock,item["locked_id"]) if locked else self._perform(self.workspace.lock_block,index)
            if ok: dialog.destroy()
        ttk.Button(form,text="解锁" if locked else "锁定时间",command=act).pack(fill="x")
        if task:
            def edit_task():
                dialog.destroy()
                task_index=next(i for i,t in enumerate(snap["tasks"]) if t["task_id"]==task["task_id"])
                self.task_tree.selection_set(str(task_index)); self.task_dialog(edit=True)
            ttk.Button(form,text="编辑任务",command=edit_task).pack(fill="x",pady=6)
        self._dialog_labels()

    def settings_dialog(self):
        dialog=self._new_dialog("规划设置")
        if dialog is None: return
        form=ttk.Frame(dialog,padding=20); form.pack()
        fields=(("now","开始"),("horizon_end","结束"))
        for row,(key,label) in enumerate(fields):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky="w",pady=6)
            ttk.Entry(form,textvariable=self.window_vars[key],width=34).grid(row=row,column=1,padx=12)
        ttk.Label(form,text="策略").grid(row=3,column=0,sticky="w",pady=6)
        ttk.Combobox(form,textvariable=self.strategy_var,values=("edf","importance","risk"),state="readonly").grid(row=3,column=1,sticky="ew",padx=12)
        for row,(label,var) in enumerate((("最短块（分钟）",self.min_var),("最长块（分钟）",self.max_var)),4):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky="w",pady=6)
            ttk.Entry(form,textvariable=var,width=8).grid(row=row,column=1,sticky="w",padx=12)
        ttk.Label(form,text="按日历空白自动安排；忙碌时间与锁定块会被保留。",wraplength=390).grid(row=6,column=0,columnspan=2,sticky="w",pady=12)
        def cancel():
            snap=self.workspace.snapshot
            for key,var in self.window_vars.items(): var.set(_local_text(snap[key]))
            self.strategy_var.set(snap["strategy"]); self.min_var.set(str(snap["parameters"]["min_block_minutes"])); self.max_var.set(str(snap["parameters"]["max_block_minutes"]))
            dialog.destroy()
        def apply():
            try:
                candidate = self.workspace.snapshot
                candidate.update(timezone="local", now=_local_input(self.window_vars["now"].get().strip(),candidate["now"]), horizon_end=_local_input(self.window_vars["horizon_end"].get().strip(),candidate["horizon_end"]), strategy=self.strategy_var.get())
                candidate["parameters"] = {"min_block_minutes":int(self.min_var.get()), "max_block_minutes":int(self.max_var.get())}
                changed = candidate != self.workspace.snapshot
                if changed: candidate["input_revision"] = str(uuid4())
                validated = Workspace(candidate)
            except ValueError as exc:
                self.msg.showerror("设置有误",str(exc),parent=dialog); return
            # Validate the whole dialog before committing any of its settings.
            if changed:
                self.workspace = validated; self.dirty=True; self._last_snapshot=None
            self.refresh(); dialog.destroy()
        bar=ttk.Frame(form); bar.grid(row=7,column=0,columnspan=2,sticky="e")
        ttk.Button(bar,text="比较三种策略",command=self.compare).pack(side="left",padx=6)
        ttk.Button(bar,text="取消",command=cancel).pack(side="left",padx=6)
        ttk.Button(bar,text="应用设置",command=apply).pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW",cancel); self._dialog_labels()

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
        for name, var in self.task_vars.items(): var.set(_local_text(task[name]) if name in ("earliest_start", "deadline") else str(task[name]))
        self.splittable.set(task["splittable"])
        self._task_baseline = (task["task_id"], self._task_form())

    def _task_form(self):
        return tuple(var.get() for var in self.task_vars.values()) + (self.splittable.get(),)

    def _has_drafts(self):
        snap = self.workspace.snapshot
        baseline = self._task_baseline[1] if self._task_baseline is not None else ("", "", "", "", "", "", True)
        task_draft = self._task_form() != baseline
        window_draft = any(var.get() != _local_text(snap[key]) for key, var in self.window_vars.items())
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
        snap = self.workspace.snapshot
        original = self._selected_task() if self.task_tree.selection() else {"earliest_start":snap["now"], "deadline":snap["horizon_end"]}
        for key in ("deadline", "earliest_start"): values[key] = _local_input(values[key], original[key])
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
            zone = "local"
            start = _local_input(self.window_vars["now"].get().strip(), self.workspace.snapshot["now"])
            end = _local_input(self.window_vars["horizon_end"].get().strip(), self.workspace.snapshot["horizon_end"])
        except ValueError as exc: self.msg.showerror("时间有误", str(exc), parent=self.root); return
        self._perform(self.workspace.set_window, start, end, zone)

    def add_interval(self, kind):
        try:
            zone = "local"
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
        if not self.prepare_planning(): return
        if self._perform(self.workspace.generate_calendar):
            blocks = self.workspace.result["blocks"]
            if blocks:
                start = parse_datetime(blocks[0]["start"],"start").astimezone(resolve_timezone("local"))
                self.view_date = start.date(); self.draw_calendar()
                self.canvas.yview_moveto(max(0, start.hour-1)/24)

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
        try: results = self.workspace.compare_calendar()
        except (ValueError, OSError) as exc: self.msg.showerror("比较失败", str(exc), parent=self.root); return
        window = tk.Toplevel(self.root)
        window.title(self.tr("策略比较（不更改当前计划）"))
        text = tk.Text(window, width=100, height=24, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", "\n\n".join(self._summary(result) for result in results))
        text.configure(state="disabled")

    def refresh(self):
        snap, result = self.workspace.snapshot, self.workspace.result
        self.status.configure(text=f"{self.tr('存档：')}{self.store.path}  |  {self.tr('未保存' if self.dirty else '无未保存更改')}")
        selections = {tree: tree.selection() for tree in (self.task_tree, self.interval_tree, self.block_tree, self.lock_tree)}
        for tree in selections: tree.delete(*tree.get_children())
        names = {t["task_id"]: t["title"] for t in snap["tasks"]}
        for i, task in enumerate(snap["tasks"]):
            statuses = {"active": "Active", "completed": "Completed", "deleted": "Deleted"} if self.language.get() == "English" else {"active": "进行中", "completed": "已完成", "deleted": "已删除"}
            self.task_tree.insert("", "end", iid=str(i), values=(task["title"], f"{task['remaining_minutes']}/{task['estimated_minutes']}"))
        for kind, label in (("availability", "可用"), ("busy_events", "忙碌")):
            for i, interval in enumerate(snap[kind]): self.interval_tree.insert("", "end", iid=f"{kind}:{i}", values=(self.tr(label), _local_text(interval["start"]), _local_text(interval["end"])))
        for i, lock in enumerate(snap["locked_blocks"]): self.lock_tree.insert("", "end", iid=str(i), values=(names.get(lock["task_id"], self.tr("固定预留")), _local_text(lock["start"]), _local_text(lock["end"])))
        if result:
            for i, block in enumerate(result["blocks"]): self.block_tree.insert("", "end", iid=str(i), values=(names.get(block["task_id"], self.tr("固定预留")), _local_text(block["start"]), _local_text(block["end"]), block["minutes"], self.tr("已锁定" if block["source"] == "locked" else "自动")))
        for tree, items in selections.items():
            for item in items:
                if tree.exists(item): tree.selection_add(item)
        old = self._last_snapshot
        for key, var in self.window_vars.items():
            if old is None or old[key] != snap[key]: var.set(_local_text(snap[key]))
        if old is None or old["strategy"] != snap["strategy"]: self.strategy_var.set(snap["strategy"])
        if old is None or old["parameters"] != snap["parameters"]:
            self.min_var.set(str(snap["parameters"]["min_block_minutes"]))
            self.max_var.set(str(snap["parameters"]["max_block_minutes"]))
        self._last_snapshot = snap
        self.summary.configure(state="normal"); self.summary.delete("1.0", "end"); self.summary.insert("1.0", self.tr("暂无计划。请先设置可用时段并生成。") if result is None else self._summary(result)); self.summary.configure(state="disabled")

        self.draw_calendar()

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
        try: workspace = candidate.load(local_time=True)
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
    try: workspace = store.load(local_time=True) if path.exists() else Workspace.new()
    except (ValueError, OSError) as exc:
        messagebox.showerror("Could not load workspace", _english(exc), parent=root)
        root.destroy()
        return 1
    SchedulerGUI(root, store, workspace)
    root.deiconify()
    root.mainloop()
    return 0
