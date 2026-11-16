# Demo 1 · Tkinter 图形界面

Demo 1 默认入口现为 Tkinter 图形界面：从项目根目录运行 `python .\demo1.py` 打开窗口；`--terminal` 保留原终端菜单，`--demo` 显式查看合成演示。GUI集成验收已完成，88项测试通过；实际范围及证据见 [GUI 验收记录](../docs/scheduler/DEMO1_GUI_VERIFICATION.md)。

## 启动与语言

1. **确认 Python 版本。** GUI 需要 Python 3.11 或更新版本及可用的 Tk 桌面组件。

   ```powershell
   python --version
   ```

   **成功标志：** 显示 Python 3.11 或更新版本。

2. **打开工作区。** 在项目根目录运行：

   ```powershell
   python .\demo1.py
   ```

   **预期成功标志：** 出现 Demo 1 主窗口，而不是自动输出案例。首次使用为空白工作区；如默认存档已存在，则读取该存档。默认只读写本地 `work\demo1-data\workspace.json`，不访问数据库或外部账户。

界面默认语言为 English（英文），可通过 `Language / 语言` 选择 `English` 或 `简体中文`。本文按钮使用英文显示名称并附中文解释。语言选择按当前窗口会话描述，不假定它会保存到下次启动。

## 建立并运行计划

1. **新增任务。** 打开 `Tasks`（任务）页，在 `Task details`（任务信息）填写 `Title`（名称）、`Total minutes`（总分钟）、`Remaining minutes`（剩余分钟）、`Priority 1–5`（重要性）、`Earliest start`（最早开始）、`Deadline`（截止时间）和 `Allow splitting`（允许拆分），点击 `Add task`（新增任务）。选中任务后可用 `Update selected task`（保存选中任务修改）、`Record remaining`（记录剩余分钟）、`Mark complete`（标记完成）或 `Delete task`（删除任务）；完成和删除会先要求确认。

   **成功标志：** 任务列表显示刚新增的任务和对应字段。计划生成不会自动减少剩余分钟或标记完成。

2. **设置时间。** 打开 `Time`（时间）页，在 `Planning window and time zone`（规划窗口与时区）填写 `IANA time zone`（IANA 时区）、`Start`（开始）和 `End`（结束），点击 `Apply window`（应用窗口）。添加时段后，点击 `Add availability`（添加可用时段）或 `Add busy time`（添加忙碌时段）；选中时段后点击 `Remove selected interval`（删除选中时段）。默认时区为 UTC；本地时间格式为 `YYYY-MM-DD HH:MM`。

   **成功标志：** 窗口和时段列表显示已保存的值。夏令时不存在的时间会被拒绝；回拨时重复的本地时间需要明确偏移。Windows 使用非 UTC 的 IANA 时区时，可能需要安装 `tzdata`：`python -m pip install tzdata`（会联网并修改当前 Python 环境）。

3. **设置策略并生成计划。** 打开 `Plan`（计划）页，在 `Scheduling settings`（调度设置）选择策略 `edf`、`importance` 或 `risk`，填写 `Minimum block (min)`（最短块）和 `Maximum block (min)`（最长块），点击 `Apply settings`（应用设置）；再点击 `Generate / replan`（生成/重新规划）。

   **成功标志：** 计划视图列出任务、时间块、未排分钟和原因。容量缺口会显示在结果中；计划是安排建议，不表示实际完成。

4. **查看或比较。** 在 `Plan`（计划）页查看当前计划；点击 `Compare strategies`（比较三种策略）在相同工作区输入下查看三个结果。

   **成功标志：** 计划视图呈现块时间和任务标题；比较视图提供 EDF、Importance First、Risk-Aware 的并列结果，且不会改变当前策略或计划。

5. **锁定与重排。** 在 `Plan`（计划）页选中尚未开始的计划块，点击 `Lock selected block`（锁定选中计划块）；在锁定列表选中已锁定块后点击 `Unlock selected locked block`（解锁选中锁定块）。任务或时间编辑会使旧计划失效，应重新生成后再锁定。已开始的锁定块需先解除，再根据实际进度更新剩余分钟；不能将锁定或安排当成已完成。

   **成功标志：** 后续重排仍保留锁定块，并重新安排其余工作。

6. **保存、打开、另存、重新加载。** 顶部的 `Save`（保存）写入默认存档 `work\demo1-data\workspace.json`；`Save as`（另存为）使用新路径；`Open workspace`（打开存档）选择已有文件；`Reload`（重新加载）从当前路径读取。关闭窗口或加载时遇到未保存更改，应选择保存、放弃或取消。

   **成功标志：** 保存后未保存状态清除；重启后任务、设置和计划可从同一存档恢复。覆盖存档会保留 `.bak` 备份；检测到并发冲突或损坏存档时，不应静默覆盖。

### 保留入口

```powershell
python .\demo1.py --terminal
python .\demo1.py --demo
```

`--terminal` 打开原终端菜单；`--demo` 只运行可行、超载和锁定重排合成案例，案例结果不是个人任务或完成记录。自定义 JSON 的包版 `schedule`、`compare`、`validate` 命令仍保留，见下节。

GUI整体计划见 [DEMO1_GUI_PLAN.md](../docs/scheduler/DEMO1_GUI_PLAN.md)，验收记录见 [DEMO1_GUI_VERIFICATION.md](../docs/scheduler/DEMO1_GUI_VERIFICATION.md)。

## 包版 CLI 与自定义输入

下方说明的是基于本地包的CLI，用于读取自定义JSON输入并调用`schedule`、`compare`、`validate`子命令；它与上面的个人工作区并行保留。

这个命令行工具根据一份任务和可用时间快照生成计划。它不会连接数据库、改写任务完成状态或保存日历；输出是建议计划，不能当作任务已完成的证据。每次重排都从当前完整输入重新计算。保存结果前，调用方应先确认 `input_revision` 仍与当前输入一致。

## Windows PowerShell：从项目根目录开始

以下命令在仓库根目录 `C:\codex\TTM_Task_Management_System` 执行。Python 需要 3.11 或更新版本；本轮案例验收使用 Python 3.14.3。

1. **检查 Python 版本并建立项目内的虚拟环境。** 版本检查不满足时会停止；环境只会创建在 `work\python-scheduler-venv`。

   ```powershell
   python -c "import sys; print(sys.version); sys.exit(0 if sys.version_info >= (3, 11) else 'Python 3.11+ is required')"
   if ($LASTEXITCODE -ne 0) { throw '请先安装 Python 3.11 或更新版本' }
   python -m venv work\python-scheduler-venv
   ```

   **成功标志：** 版本检查显示 `3.11` 或更高版本，且 `work\python-scheduler-venv\Scripts\python.exe` 存在。

2. **安装本地源码及依赖。** 这一步会联网下载构建依赖；Windows 上还会安装 `tzdata`，以提供 IANA 时区数据。本地包构建可能生成已被 Git 忽略的构建元数据。

   ```powershell
   .\work\python-scheduler-venv\Scripts\python.exe -m pip install .\python_scheduler
   ```

   **成功标志：** 命令以退出码 `0` 结束，并显示 `Successfully installed` 或 `academic-scheduler` 已满足。

3. **运行标准库定向测试。** 测试只读取三份合成案例，不需要安装 pytest。

   ```powershell
   $env:PYTHONDONTWRITEBYTECODE = '1'
   .\work\python-scheduler-venv\Scripts\python.exe -m unittest discover -s .\python_scheduler\tests -p test_examples.py -v
   ```

   **成功标志：** 测试命令结束时unittest显示`OK`。2026-11-15全套81项通过，包括真实单文件菜单输入、保存和重启；详细证据见[软件验收](../docs/scheduler/DEMO1_PRODUCT_VERIFICATION.md)。

   需要发现该目录下的全部标准库测试时，把 `-p test_examples.py` 删除即可；测试临时文件只放在项目 `work/`。

4. **运行一个完整案例。** 这条命令从仓库根目录读取可行案例，生成 JSON 计划并保存到 `work\feasible-result.json`。

   ```powershell
   .\work\python-scheduler-venv\Scripts\python.exe -m academic_scheduler schedule .\python_scheduler\examples\feasible.json --output .\work\feasible-result.json
   ```

   **成功标志：** 退出码为 `0`，终端没有计划 JSON（使用 `--output` 时 stdout 为空），且 `work\feasible-result.json` 存在。该案例应将两项任务都排满。

5. **从标准输入比较三种策略。** 管道不会修改案例文件；比较结果写到终端。

   ```powershell
   Get-Content -Raw .\python_scheduler\examples\feasible.json | .\work\python-scheduler-venv\Scripts\python.exe -m academic_scheduler compare -
   ```

   **成功标志：** 退出码为 `0`，输出 JSON 的 `results` 含 EDF、importance 和 risk 三份结果，且它们引用同一个 `request_id` 和 `input_revision`。

6. **校验刚才保存的结果。** 输入可从标准输入读取；结果文件必须是普通文件路径。

   ```powershell
   Get-Content -Raw .\python_scheduler\examples\feasible.json | .\work\python-scheduler-venv\Scripts\python.exe -m academic_scheduler validate - .\work\feasible-result.json
   ```

   **成功标志：** 退出码为 `0`，输出 `{"valid": true}`。

## 案例和原因码

- `examples\feasible.json`：固定时间 `2026-11-13 09:00`，任务需求不超过可用容量，预期没有未排分钟。
- `examples\overloaded.json`：可用容量为 120 分钟，任务需求为 180 分钟；预期明确保留未排任务/分钟。容量不足仍是一次成功的计划生成，所以退出码为 `0`。
- `examples\replan.json`：包含 `write-draft` 的 30 分钟带任务锁定，以及 30 分钟 `task_id: null` 固定预留。任务的 `remaining_minutes` 包含锁定工作；调度器会保留锁定块，只安排其余分钟，并从其他任务共用的容量中扣除空白预留。`now` 固定在 14:00，因此生成块不得落在该时刻之前。

未排原因码按规则择一：`deadline_passed`（截止时间已到）、`outside_window`（任务窗口为空）、`no_available_capacity`（最终窗口无空闲）、`insufficient_contiguous_capacity`（不可拆任务无足够连续容量）、`below_min_block`（可拆任务仅有短于最小块的容量）或 `insufficient_capacity`（其他容量不足）。原因描述本次策略结束时的容量情况，不是全局最优不可行证明。

计划指标统计已排/未排分钟和计划覆盖情况，不统计实际完成情况或墙钟耗时。`scheduled_minutes` 包含带任务锁定时间；`reserved_minutes` 统计 `task_id: null` 的预留时间。退出码为 `0` 成功（即使有缺口）、`2` 输入/参数/文件结构错误、`3` 输出结果约束校验失败、`1` 意外内部错误；错误以 JSON 写入 stderr，stdout 为空。

## 时间与夏令时

输入时间必须带 `Z` 或明确的 `±HH:MM` 偏移，内部按 UTC 比较，输出再转换为 `timezone` 指定的 IANA 时区。时区只控制展示，不会重新解释输入的墙上时间。夏令时回拨时，重复出现的本地 `01:30` 必须分别提供正确偏移，例如 `-05:00` 和 `-06:00`；跨跳时区间按真实经过分钟计算。固定案例使用 `America/Chicago` 和明确偏移，结果可重复。

历史秒级时区偏移和展示日期溢出会明确拒绝。完整字段与短尾规则见 [CONTRACT.md](../docs/scheduler/CONTRACT.md)，实际安装与测试证据见 [DEMO1_VERIFICATION.md](../docs/scheduler/DEMO1_VERIFICATION.md)。
