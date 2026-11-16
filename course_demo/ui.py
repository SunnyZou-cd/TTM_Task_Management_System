"""A small Tkinter calendar. All persistent state lives in one ordinary dictionary."""

import copy
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import scheduler, storage


WORDS = {
    "Tasks": "任务", "New": "新建", "Edit": "编辑", "Delete": "删除",
    "Progress": "进度", "Complete": "完成", "Generate": "生成计划",
    "Compare": "比较策略", "Settings": "设置", "Week": "周", "Day": "日",
    "Today": "今天", "Lock / unlock": "锁定 / 解锁", "File": "文件",
    "Open": "打开", "Save": "保存", "Save as": "另存为",
    "Import legacy": "导入旧工作区", "Title": "标题", "Total minutes": "总分钟",
    "Remaining minutes": "剩余分钟", "Deadline": "截止时间", "Start": "开始时间",
    "Importance (1–5)": "重要性（1–5）", "Splittable": "允许拆分",
    "Advanced": "高级选项", "Cancel": "取消", "End": "结束时间",
    "Busy time": "忙碌时间", "Task": "任务", "Strategy": "策略", "Due": "截止日期",
    "Minimum block": "最短任务块", "Maximum block": "最长任务块",
    "Planning days": "规划天数", "Apply": "应用", "Error": "错误",
    "English": "English", "中文": "中文", "No task selected": "请先选择任务",
    "Saved": "已保存", "Unsaved changes": "有未保存的修改",
    "Save changes before continuing?": "继续前保存修改？",
    "Delete selected task?": "删除所选任务？", "Delete busy time?": "删除该忙碌时间？",
    "Click a cell to add busy time; click a busy block to edit.": "点击空白格添加忙碌时间；点击忙碌块可编辑。",
    "Select a plan block first": "请先点击计划块",
    "Scheduled": "已安排", "Unscheduled": "未安排", "minutes": "分钟",
    "Imported; save to a new file": "已导入；请另存到新文件",
    "Legacy source cannot be overwritten": "不能覆盖导入来源的旧工作区",
    "Task changes clear its generated plan and preserve locks.": "修改任务会清除该任务生成的计划，保留锁定。",
    "Complete task and remove its plan and locks?": "完成任务并移除该任务的计划和锁定？",
    "Local time": "本机时间", "Untitled": "未命名",
}


class PlannerApp:
    def __init__(self, root, path=None):
        self.root = root
        self.path = Path(path) if path else Path(__file__).resolve().parents[1] / "work/course-demo/workspace.json"
        self.previous_bytes = None
        self.import_source = None
        self.data = scheduler.new_data()
        self.dirty = False
        self.language = "English"
        self.view = "Week"
        self.date = datetime.now().date()
        self.selected_block = None
        self.hit_boxes = []
        self.status = ""
        self.root.geometry("1180x800")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Destroy>", self.destroyed, add="+")
        if self.path.exists():
            try:
                # Read bytes before loading: a concurrent disk change must never be overwritten.
                self.previous_bytes = self.path.read_bytes()
                self.data = storage.load(self.path)
                if self.path.read_bytes() != self.previous_bytes:
                    raise ValueError("Workspace changed while opening; open it again")
            except (ValueError, OSError) as exc:
                self.error(exc)
                self.previous_bytes = None
        self.build()
        self.root.after_idle(lambda: self.canvas.yview_moveto(8 / 24))

    def t(self, text):
        return WORDS.get(text, text) if self.language == "中文" else text

    def error(self, exc):
        messagebox.showerror(self.t("Error"), str(exc), parent=self.root)

    def build(self):
        for child in self.root.winfo_children():
            if not isinstance(child, tk.Toplevel):
                child.destroy()
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        for label, command in [("Open", self.open), ("Save", self.save),
                               ("Save as", self.save_as), ("Import legacy", self.import_legacy)]:
            file_menu.add_command(label=self.t(label), command=command)
        menu.add_cascade(label=self.t("File"), menu=file_menu)
        self.root.config(menu=menu)
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        for label, command in [("Generate", self.generate), ("Compare", self.compare), ("Settings", self.settings)]:
            ttk.Button(toolbar, text=self.t(label), command=command).pack(side="left", padx=3)
        language = ttk.Combobox(toolbar, values=["English", "中文"], state="readonly", width=10)
        language.set(self.language)
        language.pack(side="right")
        language.bind("<<ComboboxSelected>>", lambda event: self.set_language(language.get()))
        self.clock_label = ttk.Label(toolbar)
        self.clock_label.pack(side="right", padx=12)
        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8)
        sidebar = ttk.Frame(body, width=290)
        body.add(sidebar, weight=0)
        ttk.Label(sidebar, text=self.t("Tasks")).pack(anchor="w")
        self.task_list = ttk.Treeview(sidebar, columns=("remaining",), show="tree headings", selectmode="browse", height=20)
        self.task_list.heading("#0", text=self.t("Title"))
        self.task_list.heading("remaining", text=self.t("minutes"))
        self.task_list.column("#0", width=150)
        self.task_list.column("remaining", width=110)
        self.task_list.pack(fill="both", expand=True)
        self.task_list.bind("<Double-1>", lambda event: self.edit_task())
        actions = ttk.Frame(sidebar)
        actions.pack(fill="x", pady=5)
        for index, (label, command) in enumerate([("New", self.task_form), ("Edit", self.edit_task),
                                                ("Delete", self.delete_task), ("Progress", self.progress_form),
                                                ("Complete", self.complete_task)]):
            ttk.Button(actions, text=self.t(label), command=command).grid(row=index // 3, column=index % 3, sticky="ew")
        calendar = ttk.Frame(body)
        body.add(calendar, weight=1)
        navigation = ttk.Frame(calendar)
        navigation.pack(fill="x")
        for label, command in [("‹", lambda: self.move(-1)), ("Today", self.today), ("›", lambda: self.move(1)),
                               ("Week", lambda: self.set_view("Week")), ("Day", lambda: self.set_view("Day")),
                               ("Lock / unlock", self.toggle_lock)]:
            ttk.Button(navigation, text=self.t(label), command=command).pack(side="left", padx=2)
        self.date_label = ttk.Label(navigation)
        self.date_label.pack(side="right", padx=4)
        self.header = tk.Canvas(calendar, height=28, background="#f0f0f0", highlightthickness=0)
        self.header.pack(fill="x")
        frame = ttk.Frame(calendar)
        frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(frame, background="#fafafa", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>", lambda event: self.draw_calendar())
        self.canvas.bind("<Button-1>", self.calendar_click)
        self.canvas.bind("<MouseWheel>", lambda event: self.canvas.yview_scroll(-int(event.delta / 120), "units"))
        ttk.Label(calendar, text=self.t("Click a cell to add busy time; click a busy block to edit.")).pack(anchor="w")
        self.status_label = ttk.Label(self.root, padding=8, wraplength=1100)
        self.status_label.pack(fill="x")
        self.refresh()
        self.tick()

    def tick(self):
        self.clock_label.config(text=self.t("Local time") + " " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if hasattr(self, "clock_timer"):
            self.root.after_cancel(self.clock_timer)
        self.clock_timer = self.root.after(1000, self.tick)

    def destroyed(self, event):
        if event.widget is self.root and hasattr(self, "clock_timer"):
            self.root.after_cancel(self.clock_timer)

    def set_language(self, language):
        self.language = language
        self.build()

    def changed(self):
        self.dirty = True
        self.selected_block = None
        self.refresh()

    def refresh(self):
        selected = self.task_list.selection()
        self.task_list.delete(*self.task_list.get_children())
        for task in self.data["tasks"]:
            title = ("✓ " if task["remaining"] == 0 else "") + task["title"]
            self.task_list.insert("", "end", iid=str(task["id"]), text=title, values=(task["remaining"],))
        if selected and self.task_list.exists(selected[0]):
            self.task_list.selection_set(selected[0])
        self.root.title(("* " if self.dirty else "") + "Course Planner — " + str(self.path))
        self.status_label.config(text=self.status)
        self.draw_calendar()

    def selected_task(self):
        selected = self.task_list.selection()
        if not selected:
            self.error(self.t("No task selected"))
            return None
        return next(task for task in self.data["tasks"] if task["id"] == int(selected[0]))

    def dialog(self, title):
        window = tk.Toplevel(self.root)
        window.title(self.t(title))
        window.transient(self.root)
        window.grab_set()
        window.resizable(False, False)
        window.bind("<Escape>", lambda event: window.destroy())
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        return window, frame

    def field(self, frame, label, value):
        row = frame.grid_size()[1]
        ttk.Label(frame, text=self.t(label)).grid(row=row, column=0, sticky="w", padx=4, pady=5)
        entry = ttk.Entry(frame, width=28)
        entry.insert(0, str(value))
        entry.grid(row=row, column=1, sticky="ew", padx=4, pady=5)
        return entry

    def buttons(self, frame, window, save):
        row = frame.grid_size()[1]
        ttk.Button(frame, text=self.t("Save"), command=save).grid(row=row, column=1, sticky="e", pady=10)
        ttk.Button(frame, text=self.t("Cancel"), command=window.destroy).grid(row=row, column=0, sticky="w")

    def task_form(self, task=None):
        window, frame = self.dialog("Task")
        now = scheduler.now_minutes()
        title = self.field(frame, "Title", task["title"] if task else "")
        total = self.field(frame, "Total minutes", task["total"] if task else 60)
        deadline = self.field(frame, "Deadline", scheduler.format_time(task["deadline"] if task else now + 1440))
        advanced = ttk.Frame(frame)
        expanded = tk.BooleanVar(value=False)
        toggle = ttk.Checkbutton(frame, text=self.t("Advanced"), variable=expanded,
                                 command=lambda: advanced.grid() if expanded.get() else advanced.grid_remove())
        toggle.grid(row=3, column=0, columnspan=2, sticky="w")
        advanced.grid(row=4, column=0, columnspan=2)
        remaining = self.field(advanced, "Remaining minutes", task["remaining"] if task else "")
        start = self.field(advanced, "Start", scheduler.format_time(task["start"] if task else now))
        importance = self.field(advanced, "Importance (1–5)", task["importance"] if task else 3)
        split = tk.BooleanVar(value=task["splittable"] if task else True)
        ttk.Checkbutton(advanced, text=self.t("Splittable"), variable=split).grid(row=3, columnspan=2, sticky="w")
        advanced.grid_remove()
        if task:
            ttk.Label(frame, text=self.t("Task changes clear its generated plan and preserve locks.")).grid(row=5, columnspan=2)

        def submit():
            try:
                task_id = task["id"] if task else max([item["id"] for item in self.data["tasks"]], default=0) + 1
                minutes = int(total.get())
                item = {"id": task_id, "title": title.get().strip(), "total": minutes,
                        "remaining": int(remaining.get()) if remaining.get().strip() else minutes,
                        "importance": int(importance.get()), "start": scheduler.parse_time(start.get()),
                        "deadline": scheduler.parse_time(deadline.get()), "splittable": split.get()}
                candidate = copy.deepcopy(self.data)
                candidate["tasks"] = [old for old in candidate["tasks"] if old["id"] != task_id] + [item]
                candidate["plan"] = copy.deepcopy(candidate["locks"])
                scheduler.validate_data(candidate)
                self.data = candidate
                self.status = ""
                self.changed()
                window.destroy()
            except (ValueError, TypeError) as exc:
                self.error(exc)

        self.buttons(frame, window, submit)
        title.focus_set()
        return window

    def edit_task(self):
        task = self.selected_task()
        if task:
            return self.task_form(task)

    def delete_task(self):
        task = self.selected_task()
        if task and messagebox.askyesno(self.t("Delete"), self.t("Delete selected task?"), parent=self.root):
            self.data["tasks"].remove(task)
            self.clear_task_plan(task["id"])
            self.changed()

    def clear_task_plan(self, task_id):
        for key in ("plan", "locks"):
            self.data[key] = [block for block in self.data[key] if block["task_id"] != task_id]

    def update_progress(self, task, remaining):
        if not 0 <= remaining <= task["total"]:
            raise ValueError("Remaining minutes must be between 0 and total")
        candidate = copy.deepcopy(self.data)
        next(item for item in candidate["tasks"] if item["id"] == task["id"])["remaining"] = remaining
        candidate["plan"] = copy.deepcopy(candidate["locks"])
        scheduler.validate_data(candidate)
        task["remaining"] = remaining
        self.data["plan"] = candidate["plan"]
        self.status = ""
        self.changed()

    def progress_form(self):
        task = self.selected_task()
        if not task:
            return None
        window, frame = self.dialog("Progress")
        remaining = self.field(frame, "Remaining minutes", task["remaining"])

        def submit():
            try:
                self.update_progress(task, int(remaining.get()))
                window.destroy()
            except ValueError as exc:
                self.error(exc)

        self.buttons(frame, window, submit)
        remaining.focus_set()
        return window

    def complete_task(self):
        task = self.selected_task()
        if task and messagebox.askyesno(self.t("Complete"), self.t("Complete task and remove its plan and locks?"), parent=self.root):
            task["remaining"] = 0
            self.clear_task_plan(task["id"])
            self.changed()

    def days(self):
        start = self.date if self.view == "Day" else self.date - timedelta(days=self.date.weekday())
        return [start + timedelta(days=index) for index in range(1 if self.view == "Day" else 7)]

    def set_view(self, view):
        self.view = view
        self.draw_calendar()

    def move(self, direction):
        self.date += timedelta(days=direction * (1 if self.view == "Day" else 7))
        self.draw_calendar()

    def today(self):
        self.date = datetime.now().date()
        self.draw_calendar()

    def draw_calendar(self):
        self.canvas.delete("all")
        self.header.delete("all")
        self.hit_boxes = []
        dates = self.days()
        width = max(self.canvas.winfo_width(), 350)
        column = (width - 55) / len(dates)
        self.canvas.configure(scrollregion=(0, 0, width, 1490))
        self.date_label.config(text=str(dates[0]) + (" — " + str(dates[-1]) if len(dates) > 1 else ""))
        for hour in range(25):
            y = 40 + hour * 60
            self.canvas.create_line(50, y, width, y, fill="#dedede")
            if hour < 24:
                self.canvas.create_text(25, y + 8, text=f"{hour:02}:00", fill="#666666")
        tasks = {task["id"]: task for task in self.data["tasks"]}
        for index, day in enumerate(dates):
            x = 55 + index * column
            self.canvas.create_line(x, 0, x, 1480, fill="#dedede")
            self.header.create_text(x + column / 2, 14, text=day.strftime("%a %m-%d"))
            planned = self.data["plan"] or self.data["locks"]
            for kind, blocks in (("busy", self.data["busy"]), ("plan", planned)):
                for block in blocks:
                    start = datetime.fromtimestamp(block["start"] * 60)
                    end = datetime.fromtimestamp(block["end"] * 60)
                    midnight = datetime.combine(day, datetime.min.time())
                    if start >= midnight + timedelta(days=1) or end <= midnight:
                        continue
                    first = max(start, midnight)
                    last = min(end, midnight + timedelta(days=1))
                    y1 = 40 + (first - midnight).total_seconds() / 60
                    y2 = 40 + (last - midnight).total_seconds() / 60
                    color = "#d1d5db" if kind == "busy" else ("#f4bf68" if block["locked"] else "#a9d4ed")
                    outline = "#245a78" if block is self.selected_block else "#ffffff"
                    self.canvas.create_rectangle(x + 2, y1, x + column - 2, y2, fill=color, outline=outline, width=2)
                    label = self.t("Busy time") if kind == "busy" else tasks[block["task_id"]]["title"]
                    if kind == "plan" and block["locked"]:
                        label = "🔒 " + label
                    self.canvas.create_text(x + 6, y1 + 3, text=label, anchor="nw", width=max(20, column - 14))
                    self.hit_boxes.append((x + 2, y1, x + column - 2, y2, kind, block))

    def calendar_click(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for x1, y1, x2, y2, kind, block in reversed(self.hit_boxes):
            if x1 <= x <= x2 and y1 <= y <= y2:
                if kind == "busy":
                    self.busy_form(block)
                else:
                    self.selected_block = block
                    self.draw_calendar()
                return
        dates = self.days()
        column = (max(self.canvas.winfo_width(), 350) - 55) / len(dates)
        index = int((x - 55) // column)
        if x >= 55 and 0 <= index < len(dates) and 40 <= y < 1480:
            minute = int((y - 40) // 30) * 30
            value = scheduler.parse_time(f"{dates[index]} {minute // 60:02}:{minute % 60:02}")
            self.busy_form(start=value)

    def busy_form(self, busy=None, start=None):
        window, frame = self.dialog("Busy time")
        value = busy["start"] if busy else (start if start is not None else scheduler.now_minutes())
        first = self.field(frame, "Start", scheduler.format_time(value))
        last = self.field(frame, "End", scheduler.format_time(busy["end"] if busy else value + 60))

        def submit():
            try:
                candidate = copy.deepcopy(self.data)
                if busy:
                    candidate["busy"].remove(busy)
                candidate["busy"].append({"start": scheduler.parse_time(first.get()), "end": scheduler.parse_time(last.get())})
                candidate["plan"] = copy.deepcopy(candidate["locks"])
                scheduler.validate_data(candidate)
                self.data = candidate
                self.changed()
                window.destroy()
            except ValueError as exc:
                self.error(exc)

        if busy:
            def remove():
                if messagebox.askyesno(self.t("Delete"), self.t("Delete busy time?"), parent=window):
                    self.data["busy"].remove(busy)
                    self.data["plan"] = copy.deepcopy(self.data["locks"])
                    self.changed()
                    window.destroy()
            ttk.Button(frame, text=self.t("Delete"), command=remove).grid(row=2, columnspan=2)
        self.buttons(frame, window, submit)
        first.focus_set()
        return window

    def toggle_lock(self):
        if self.selected_block is None:
            self.error(self.t("Select a plan block first"))
            return
        block = self.selected_block
        if not block["locked"] and block["start"] < scheduler.now_minutes():
            self.error("Only blocks that have not started can be locked")
            return
        if not self.data["plan"]:
            self.data["plan"] = self.data["locks"][:]
        block["locked"] = not block["locked"]
        self.data["locks"] = [copy.deepcopy(item) for item in self.data["plan"] if item["locked"]]
        self.changed()

    def apply_plan(self, result, strategy):
        self.data["settings"]["strategy"] = strategy
        self.data["plan"] = result["blocks"]
        metrics = result["metrics"]
        self.status = f'{self.t("Scheduled")}: {metrics["scheduled"]}; {self.t("Unscheduled")}: {metrics["unscheduled"]} {self.t("minutes")}'
        tasks = {task["id"]: task["title"] for task in self.data["tasks"]}
        for item in result["unscheduled"]:
            self.status += f'\n{tasks[item["task_id"]]}: {item["minutes"]} {self.t("minutes")} — {item["reason"]}'
        if result["blocks"]:
            first = datetime.fromtimestamp(min(block["start"] for block in result["blocks"]) * 60)
            self.date = first.date()
            self.canvas.yview_moveto(max(0, (first.hour - 1) / 24))
        self.changed()

    def generate(self):
        try:
            self.apply_plan(scheduler.make_plan(self.data), self.data["settings"]["strategy"])
        except ValueError as exc:
            self.error(exc)

    def compare(self):
        results = []
        try:
            now = scheduler.now_minutes()
            for strategy in ("edf", "importance", "risk"):
                candidate = copy.deepcopy(self.data)
                candidate["settings"]["strategy"] = strategy
                results.append((strategy, scheduler.make_plan(candidate, now=now)))
        except ValueError as exc:
            self.error(exc)
            return None
        window, frame = self.dialog("Compare")
        for index, (strategy, result) in enumerate(results):
            metrics = result["metrics"]
            ratio = "—" if metrics["weighted_ratio"] is None else f'{metrics["weighted_ratio"]:.2f}'
            label = self.t("Due") if strategy == "edf" else strategy
            text = f'{label}: {self.t("Scheduled")} {metrics["scheduled"]}; {self.t("Unscheduled")} {metrics["unscheduled"]}; weighted {ratio}'
            ttk.Label(frame, text=text).grid(row=index, column=0, sticky="w", pady=8)
            def apply(chosen=result, name=strategy):
                self.apply_plan(chosen, name)
                window.destroy()
            ttk.Button(frame, text=self.t("Apply"), command=apply).grid(row=index, column=1, padx=8)
        return window

    def settings(self):
        window, frame = self.dialog("Settings")
        ttk.Label(frame, text=self.t("Strategy")).grid(row=0, column=0)
        strategy = ttk.Combobox(frame, values=[self.t("Due"), "importance", "risk"], state="readonly", width=26)
        current = self.data["settings"]["strategy"]
        strategy.set(self.t("Due") if current == "edf" else current)
        strategy.grid(row=0, column=1)
        minimum = self.field(frame, "Minimum block", self.data["settings"]["min_block"])
        maximum = self.field(frame, "Maximum block", self.data["settings"]["max_block"])
        days = self.field(frame, "Planning days", self.data["settings"]["days"])

        def submit():
            try:
                candidate = copy.deepcopy(self.data)
                selected = "edf" if strategy.get() == self.t("Due") else strategy.get()
                candidate["settings"] = {"strategy": selected, "min_block": int(minimum.get()),
                                         "max_block": int(maximum.get()), "days": int(days.get())}
                if candidate["settings"] == self.data["settings"]:
                    window.destroy()
                    return
                candidate["plan"] = copy.deepcopy(candidate["locks"])
                scheduler.validate_data(candidate)
                self.data = candidate
                self.changed()
                window.destroy()
            except ValueError as exc:
                self.error(exc)

        self.buttons(frame, window, submit)
        return window

    def may_discard(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(self.t("Unsaved changes"), self.t("Save changes before continuing?"), parent=self.root)
        return self.save() if answer else answer is False

    def save(self):
        if self.import_source is not None:
            return self.save_as()
        try:
            self.previous_bytes = storage.save(self.path, self.data, previous_bytes=self.previous_bytes)
            self.dirty = False
            self.status = self.t("Saved")
            self.refresh()
            return True
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False

    def save_as(self):
        filename = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not filename:
            return False
        path = Path(filename)
        if self.import_source and path.resolve() == self.import_source.resolve():
            self.error(self.t("Legacy source cannot be overwritten"))
            return False
        try:
            # A chosen existing destination is explicitly approved by the Save As dialog.
            previous = self.previous_bytes if path.resolve() == self.path.resolve() else (
                path.read_bytes() if path.exists() else None)
            saved = storage.save(path, self.data, previous_bytes=previous)
            self.path, self.previous_bytes = path, saved
            self.import_source = None
            self.dirty = False
            self.status = self.t("Saved")
            self.refresh()
            return True
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False

    def open(self):
        if not self.may_discard():
            return
        filename = filedialog.askopenfilename(parent=self.root, filetypes=[("JSON", "*.json")])
        if not filename:
            return
        try:
            path = Path(filename)
            previous = path.read_bytes()
            data = storage.load(path)
            if path.read_bytes() != previous:
                raise ValueError("Workspace changed while opening; open it again")
            self.data, self.path, self.previous_bytes = data, path, previous
            self.import_source = None
            self.dirty = False
            self.status = ""
            self.selected_block = None
            self.refresh()
        except (ValueError, OSError) as exc:
            self.error(exc)

    def import_legacy(self):
        if not self.may_discard():
            return
        filename = filedialog.askopenfilename(parent=self.root, filetypes=[("JSON", "*.json")])
        if not filename:
            return
        try:
            self.data = storage.import_legacy(filename)
            self.import_source = Path(filename)
            self.previous_bytes = None
            self.status = self.t("Imported; save to a new file")
            self.changed()
        except (ValueError, OSError) as exc:
            self.error(exc)

    def close(self):
        if self.may_discard():
            self.root.destroy()


def run(path=None):
    root = tk.Tk()
    PlannerApp(root, path)
    root.mainloop()
    return 0
