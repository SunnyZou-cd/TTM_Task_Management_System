# Python CLI Demo 1

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

   **成功标志：** 3 项测试均显示 `ok`，最终显示 `OK`。

   要运行全部44项测试（含480组三策略合成场景），把 `-p test_examples.py` 删除即可；测试临时文件只放在项目 `work/`。

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
