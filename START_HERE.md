# 项目接续入口

Python Demo 1 已加入Tkinter图形界面，88项测试通过。 `python .\demo1.py` 默认打开图形界面，`--terminal` 保留原终端菜单，`--demo` 显式运行案例。界面默认 English，并可切换简体中文。既有终端工作区验收不代表 GUI 验收；GUI 实测状态见[GUI验收记录](docs/scheduler/DEMO1_GUI_VERIFICATION.md)。

## Python Demo 1：图形界面使用流程

以下指南适用于 Tkinter 窗口。控件名称按 English 显示，并附中文解释。使用 Python 3.11 或更新版本，无需编辑 JSON 或安装项目包。

1. **检查版本并启动窗口。**

   ```powershell
   python --version
   python .\demo1.py
   ```

   **成功标志：** Python 版本为 3.11+，且出现 Demo 1 窗口。首次运行为空白工作区；已有默认存档时加载本机数据。程序只读写本地工作区文件，不连接数据库。

界面默认语言为 English。通过 `Language / 语言` 切换 `English` 或 `简体中文`；不假定选择会保存到下次启动。

2. **录入任务。** 在 `Tasks`（任务）页的 `Task details`（任务信息）填写 `Title`（名称）、`Total minutes`（总分钟）、`Remaining minutes`（剩余分钟）、`Priority 1–5`（重要性）、`Earliest start`（最早开始）、`Deadline`（截止时间）和 `Allow splitting`（允许拆分），点击 `Add task`（新增任务）。选中任务后可用 `Update selected task`（保存修改）、`Record remaining`（记录进度）、`Mark complete`（标记完成）或 `Delete task`（删除任务）。

   **成功标志：** 列表显示新任务及字段。完成和删除操作需确认；计划不会自动减少剩余分钟或标记完成。

3. **设置规划时间和可用时段。** 打开 `Time`（时间）页，在 `Planning window and time zone`（规划窗口与时区）填写 `IANA time zone`（时区）、`Start`（开始）和 `End`（结束），点击 `Apply window`（应用窗口）。按需添加可用和忙碌区间，或选中区间后移除。

   **成功标志：** 页面显示规划窗口、时区和各区间。默认 UTC；时间格式为 `YYYY-MM-DD HH:MM`。夏令时不存在的时间会被拒绝；重复时间需带偏移 ISO 格式。Windows 使用其他 IANA 时区可能需要 `python -m pip install tzdata`。

4. **设置策略并生成计划。** 打开 `Plan`（计划）页，设置策略及 `Minimum block (min)`（最短块）和 `Maximum block (min)`（最长块），点击 `Apply settings`（应用设置），再点击 `Generate / replan`（生成/重新规划）。

   **成功标志：** 计划显示任务、时间块、未排分钟和原因。计划只表示安排建议，不代表实际完成。

5. **查看、比较或锁定。** 在计划列表查看结果。点击 `Compare strategies`（比较三种策略）可查看 EDF、importance 和 risk 结果。选中尚未开始的块后点 `Lock selected block`（锁定选中块）；在锁定列表选中块，再点 `Unlock selected locked block`（解锁）。

   **成功标志：** 三策略结果可见；重排保留锁定块并重新安排其他任务。若任务或时间已修改，应重新生成有效计划后再锁定。已经开始的锁定块先解锁，再核对进度并更新剩余分钟。

6. **保存和恢复工作区。** 窗口顶部的 `Save`（保存）写入默认路径 `work\demo1-data\workspace.json`；`Save as`（另存为）选择新位置，`Open workspace`（打开存档）选择现有文件，`Reload`（重新加载）读取当前路径。

   **成功标志：** 保存后未保存状态清除，重启后同一路径恢复任务、设置和计划。已有存档会保留 `.bak`；并发修改或损坏存档不会被静默覆盖。关闭或加载时若有未保存更改，应选择保存、放弃或取消。

可使用 `python .\demo1.py --data .\work\my-demo\workspace.json` 指定存档位置。用 `python .\demo1.py --terminal` 打开原终端菜单；用 `python .\demo1.py --demo` 运行合成案例。案例不是实际任务，也不代表完成。完整 GUI 操作和验收草稿见 [python_scheduler/README.md](python_scheduler/README.md) 与 [docs/scheduler/DEMO1_GUI_VERIFICATION.md](docs/scheduler/DEMO1_GUI_VERIFICATION.md)。

本项目作为中期项目继续开发。应用名 Pinboard，仓库名 TTM_Task_Management_System。

## 工作目录

- 后续开发目录：`C:\codex\TTM_Task_Management_System`。
- 原目录 `C:\codex\Pinboard` 保留作历史工作副本；后续修改集中在新目录。
- Git 历史已完整复制，origin 指向既有 GitHub 仓库。
- 新目录未复制 node_modules、安装包、临时测试数据或用户应用数据。

## 导入 Codex Desktop

1. 在 Codex Desktop 添加项目并选择本文件所在目录。成功标志：项目工作目录为 `C:\codex\TTM_Task_Management_System`。
2. 新建项目内聊天，让 Codex 先阅读 `AGENTS.md`、本文件、`PROJECT_STATE.md` 和 `docs/MODULARITY.md`。成功标志：后续操作使用新目录，并区分历史测试结果和本次验证。

## 开发基线

复制时本地提交为 `6d9a7fa`，版本为 0.3.0 预览版。历史实现和验证见 `PROJECT_STATE.md`；本次目录整理没有重新执行应用功能测试。

当前使用 Electron + React + TypeScript + Vite，可选 Supabase 云同步。正式发布前待确认技术方向，桌面模式 Win+D 与真实云端登录、跨设备同步仍需验收。

## 包版 JSON CLI（可选）

以下命令用于包版 JSON CLI 自定义输入；交互式个人任务管理请使用上面的单文件菜单。命令在本目录执行：建立虚拟环境并安装本地 Python 模块，随后比较相同输入的三种策略。安装会联网下载构建依赖和 Windows 时区数据；环境只写入项目 `work/`，调度不访问真实任务数据库。

```powershell
python -m venv work\python-scheduler-venv
.\work\python-scheduler-venv\Scripts\python.exe -m pip install .\python_scheduler
.\work\python-scheduler-venv\Scripts\python.exe -m academic_scheduler compare .\python_scheduler\examples\feasible.json
```

成功标志：退出码为 `0`，JSON 的 `results` 有三个策略结果。Python 需 3.11+；逐步操作和各步成功标志见模块 README。

## Electron 开发启动

在本目录执行 `npm ci` 安装依赖，再执行 `npm run dev`。安装会联网下载依赖并写入本目录的 node_modules。成功标志：Pinboard 开发窗口打开。

功能调整前先确定具体目标；测试使用项目内独立数据目录。已授权在完成工作并验证后自动提交和推送 GitHub，推送前排除凭据、个人数据和构建临时文件。
