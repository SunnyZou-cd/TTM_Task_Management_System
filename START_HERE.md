# 项目接续入口

Demo 1 已改为以日历为中心的工作区，移除独立Time页面。默认英文，可切换简体中文。日期与时间默认使用本机设置，界面不提供时区选择。按用户确认使用日历空白安排，并直接管理忙碌事件。98项测试与可见窗口检查通过，证据见[日历验收](docs/scheduler/CALENDAR_REDESIGN_VERIFICATION.md)。

启动目的：打开本地窗口；只有选择保存才写入个人存档。在项目根目录执行：

```powershell
python .\demo1.py
```

成功标志：窗口显示日期导航、左侧任务栏、中央周/日日历。点击Create task新增任务，点击日历空白添加忙碌时段，点击Generate生成安排。File菜单保存/加载；Planning settings收纳低频设置。完整步骤见[操作指南](python_scheduler/README.md)。

默认存档work/demo1-data/workspace.json，既有数据加载时不自动改写；重新生成和保存采用新的空白排程规则并保留.bak。测试数据仅放work/。

改版范围见[CALENDAR_REDESIGN_PLAN.md](docs/scheduler/CALENDAR_REDESIGN_PLAN.md)，课程对应见[COURSE_ALIGNMENT.md](docs/scheduler/COURSE_ALIGNMENT.md)。

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
