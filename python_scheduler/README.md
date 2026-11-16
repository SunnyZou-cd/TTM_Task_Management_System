# Demo 1 · 日历工作区

使用Python 3.11+，在项目根目录执行 `python demo1.py` 打开窗口；选择Save时才写入本地存档。默认English，顶部可切换简体中文，选择仅作用于本次会话。日期和时间跟随本机设置，无需选择时区。

## 常用操作

1. **新建任务：** 点击左侧Create task，填写名称、总分钟和截止时间，再保存。剩余分钟默认等于总分钟，其他字段在Advanced options里。

   **成功标志：** 左侧任务列表出现新任务。双击任务可编辑，也可记录进度、完成或删除。

2. **直接管理日历：** 顶部Today回到今天，左右箭头切换日期，Week/Day切换周与日。点击网格空白建立忙碌时段，点击已有忙碌块可编辑或删除。

   **成功标志：** 忙碌时段显示在日历中。浏览日期不会修改任务或规划范围。

3. **生成计划：** 点击Generate / replan。无需填写可用时间，也没有独立Time页面。程序使用规划范围内的空白，扣除忙碌和锁定时段。

   **成功标志：** 自动安排显示为日历色块，左侧摘要显示未排分钟与原因。全部空白包含夜间；不希望排程的时间请标为忙碌。安排不等于学习完成。

4. **查看与锁定：** 点击计划块查看详情并锁定或解锁。修改任务后可重新生成，锁定块保留；已开始的锁定块需先解锁并核对真实进度。

   **成功标志：** 锁定块用不同颜色和文字标识，重排后仍在原时段。

5. **低频设置：** Planning settings内调整规划范围、策略与块长，并比较三策略。日期时间直接按本机设置输入YYYY-MM-DD HH:MM。

   **成功标志：** 设置成功后旧计划失效，再生成使用新设置。本机夏令时规则由操作系统提供；不存在或歧义的本地时间会明确提示。

6. **保存和恢复：** File菜单提供Save、Save as、Open workspace与Reload。默认路径work/demo1-data/workspace.json。已存在存档覆盖前生成.bak；冲突时可另存为新文件。

   **成功标志：** 保存后未保存标记清除，重新打开同一路径恢复数据。未提交表单和未保存更改在关闭时有提示。

本轮保留原JSON存档格式。旧存档加载时不自动改写；使用新日历规则重新生成并保存后，可用时间字段更新为当前规划范围，旧版本由.bak保留。终端和JSON工具仍沿用原输入契约。

## 其他入口

- `python demo1.py --terminal`：原终端菜单。
- `python demo1.py --demo`：合成算法案例。
- `python demo1.py --data PATH`：指定个人存档。

改版计划见[CALENDAR_REDESIGN_PLAN.md](../docs/scheduler/CALENDAR_REDESIGN_PLAN.md)，课程对应见[COURSE_ALIGNMENT.md](../docs/scheduler/COURSE_ALIGNMENT.md)。

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

## JSON工具的时间契约（兼容接口）

输入时间必须带 `Z` 或明确的 `±HH:MM` 偏移，内部按 UTC 比较，输出再转换为 `timezone` 指定的 IANA 时区。时区只控制展示，不会重新解释输入的墙上时间。夏令时回拨时，重复出现的本地 `01:30` 必须分别提供正确偏移，例如 `-05:00` 和 `-06:00`；跨跳时区间按真实经过分钟计算。固定案例使用 `America/Chicago` 和明确偏移，结果可重复。

历史秒级时区偏移和展示日期溢出会明确拒绝。完整字段与短尾规则见 [CONTRACT.md](../docs/scheduler/CONTRACT.md)，实际安装与测试证据见 [DEMO1_VERIFICATION.md](../docs/scheduler/DEMO1_VERIFICATION.md)。
