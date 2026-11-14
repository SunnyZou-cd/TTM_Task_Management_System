# 项目接续入口

独立 Python CLI Demo 1 已实现并在 2026-11-13 完成自动验收，包含 EDF、Importance First、Risk-Aware、锁定重排与独立结果校验。运行步骤见 [python_scheduler/README.md](python_scheduler/README.md)，证据见 [DEMO1_VERIFICATION.md](docs/scheduler/DEMO1_VERIFICATION.md)。三策略正式实验及 Pinboard 集成按 [PROJECT_PLAN.md](PROJECT_PLAN.md) 后续推进。

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

## Python Demo 1 启动

以下命令在本目录执行：建立虚拟环境并安装本地 Python 模块，随后比较相同输入的三种策略。安装会联网下载构建依赖和 Windows 时区数据；环境只写入项目 `work/`，调度不访问真实任务数据库。

```powershell
python -m venv work\python-scheduler-venv
.\work\python-scheduler-venv\Scripts\python.exe -m pip install .\python_scheduler
.\work\python-scheduler-venv\Scripts\python.exe -m academic_scheduler compare .\python_scheduler\examples\feasible.json
```

成功标志：退出码为 `0`，JSON 的 `results` 有三个结果，每个结果的 `unscheduled_minutes` 都为 `0`。Python 需 3.11+；本轮实测版本是 3.14.3。逐步操作和各步成功标志见模块 README。

## Electron 开发启动

在本目录执行 `npm ci` 安装依赖，再执行 `npm run dev`。安装会联网下载依赖并写入本目录的 node_modules。成功标志：Pinboard 开发窗口打开。

功能调整前先确定具体目标；测试使用项目内独立数据目录。已授权在完成工作并验证后自动提交和推送 GitHub，推送前排除凭据、个人数据和构建临时文件。
