# Python CLI Demo 1

## 实际操作：单文件 Demo 1

在项目根目录 `C:\codex\TTM_Task_Management_System` 使用 Python 3.11 或更新版本。这个终端程序用菜单录入和管理自己的任务、时间和计划，不需要手改 JSON，也不需要安装本项目包。默认工作区是空白的；程序不会自动把内置演示案例当作你的任务。默认存档在 `work\demo1-data\workspace.json`，启动时会加载该存档（如果文件已存在），否则创建尚未保存的空白工作区。

### 启动与菜单

1. **确认 Python 版本。**

   ```powershell
   python --version
   ```

   **成功标志：** 显示 Python 3.11 或更高版本。

2. **启动交互工作区。**

   ```powershell
   python .\demo1.py
   ```

   **成功标志：** 显示主菜单、当前时区/规划窗口、存档路径和未保存状态。新存档应显示任务列表为空；已有存档则显示加载后的任务。默认只在本机读写该存档，不访问数据库或外部账号。

主菜单为：`1`任务管理、`2`时间设置、`3`策略/块长、`4`生成/重排、`5`查看计划、`6`锁定管理、`7`比较策略、`8`保存、`9`重新加载、`10`另存为、`0`退出。按屏幕提示输入菜单序号，成功后程序返回菜单。

### 建立并运行一份实际计划

1. **录入任务。** 主菜单选择 `1` 进入任务管理，再按菜单提示选择新增。填写标题、总分钟、剩余分钟、重要性、截止时间、最早开始时间和是否可拆分；日期时间可输入 `YYYY-MM-DD HH:MM`，按当前工作区时区解释。

   **成功标志：** 新任务出现在任务列表中，显示的剩余分钟和日期与输入一致。普通编辑可在提示处直接回车保留原值。菜单还可查看、编辑、删除、记录剩余分钟或明确标记完成；删除和标记完成会先要求确认。

2. **设置规划时间与可用时段。** 主菜单选择 `2`。先设置规划起止日期和展示时区，再按需列出、新增或删除可用时段及忙碌时段。新工作区默认 UTC；日期输入仍按提示格式填写。

   **成功标志：** 时间设置页显示所选时区、规划窗口，以及已录入的可用/忙碌区间。夏令时不存在的本地时间会被拒绝；重复的本地时间必须输入带明确偏移的时间。

3. **选择策略和计划块长度。** 主菜单选择 `3`，选择 EDF、Importance First 或 Risk-Aware，并设置自动计划块的最小/最大分钟数。

   **成功标志：** 菜单显示当前策略与块长设置。Risk-Aware 是启发式策略，不保证数学最优。

4. **生成计划并检查结果。** 主菜单选择 `4` 生成或重排；生成后选择 `5` 查看计划。

   **成功标志：** 结果列出任务标题、计划时间块、未排分钟和原因。容量不足会显示缺口，但计划生成本身仍可成功。计划表示建议安排，不代表任务已完成；如要标记实际完成，请在任务管理中明确记录进度或完成状态。

5. **可选：比较三种策略。** 主菜单选择 `7`，程序对同一工作区输入分别运行三种策略。

   **成功标志：** 显示 EDF、Importance First、Risk-Aware 三份结果；比较不会替换当前选择的策略或当前计划。

6. **可选：锁定确定要保留的计划块。** 主菜单选择 `6`，列出当前锁定或从当前计划选择块锁定。只锁定当前有效计划中尚未开始的块；修改任务或时间会使旧计划失效，应重新生成后再锁定。

   **成功标志：** 锁定列表显示该计划块，下一次重排会保留它并重新安排未锁定部分。若锁定块已经开始或已过去，先解除锁定，再核对并更新任务剩余分钟；程序不会把已开始的锁定块自动算作已完成。

7. **保存并确认可恢复。** 主菜单选择 `8` 保存。默认位置为 `work\demo1-data\workspace.json`；要使用其他存档，可从 PowerShell 指定路径启动：

   ```powershell
   python .\demo1.py --data .\work\my-demo\workspace.json
   ```

   **成功标志：** 菜单显示保存成功且未保存状态清除。覆盖已有存档前会保留 `.bak` 备份；并发修改或损坏文件不会被静默覆盖。冲突后可选择`10`另存为，将内存修改保存到新路径；已存在的目标不会被覆盖，成功后切换到新路径。

8. **退出后重新打开。** 选择 `0` 退出，再运行 `python .\demo1.py`（或再次传入同一 `--data` 路径）。若退出时仍有未保存更改，按提示选择保存、放弃或取消；重新加载有未保存更改时也会先要求确认。

   **成功标志：** 重新启动后，任务、时间设置和保存的计划从相同存档恢复。若存档路径与默认值不同，必须再次使用相同 `--data` 参数。

### 显式运行内置演示

内置可行、超载和锁定重排案例仅用于观察策略行为，不是用户的实际任务，也不代表任何完成进度。需显式启动：

```powershell
python .\demo1.py --demo
python .\demo1.py --demo --json
python .\demo1.py --demo --example overloaded --strategy edf
```

默认展示时区为 UTC，不依赖 `tzdata`。若选择其他 IANA 时区，Windows 上需为当前 Python 安装 `tzdata`；下面命令会联网并给当前环境添加时区数据：

```powershell
python -m pip install tzdata
```

**成功标志：** pip 退出码为 `0`，随后程序可使用所选时区。包版 `schedule`、`compare`、`validate` 自定义 JSON 命令仍保留，见下节。

维护者可运行 `python python_scheduler/scripts/build_single_file.py --check` 检查单文件是否与模块源码同步。去掉 `--check` 会重新生成并覆盖根目录的 `demo1.py`。

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
