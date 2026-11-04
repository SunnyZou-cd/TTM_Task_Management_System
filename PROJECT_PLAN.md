# Intelligent Academic Workload Scheduler — 项目规划

规划日期：2026-11-04。状态：规划完成，调度模块尚未实现。

## 目标与依据

开发可独立运行的 Python 学业任务调度引擎，比较截止时间优先、重要性优先和风险感知三种策略，并逐步接入 Pinboard。

依据：参考对话《申请科研时间协调》最后两轮中，用户确认改做 Python project，并最终选择 Intelligent Academic Workload Scheduler。算法比较和技术框架来自对话中的建议，本文件将其细化为实施方案。具体选题获批、评分标准和演示要求仍待课程方确认。

核心问题：在相同任务和可用时间下，不同策略如何影响截止前计划完成比例、加权计划完成比例和未安排工作量？

## 当前基础与新增范围

现有 Electron / React / TypeScript / Vite 界面继续负责任务、便笺和日历；本地 JSON 与可选 Supabase 继续管理原有记录。现有 Item 有日期、时间、标签和循环规则，尚无工作量、重要性、可用时段和排程结果模型。

新增 Python 模块负责输入校验、空闲时段计算、任务拆分、策略排序、排程、独立结果校验和实验评估。第一阶段使用 JSON 文件和 CLI，课程演示可在没有 Electron 的环境中独立运行。SQLite 延后到确有历史查询需求时，避免同一任务出现两个数据主库。

本轮范围不含机器学习、LLM 自动规划、多用户协作、外部日历同步、主题重设计和第三方插件。Windows 桌面模式及云端验收按既有产品路线单独推进。

## 数据契约

| 对象 | 必需字段及约束 |
| --- | --- |
| Task | 字符串 task_id（沿用 UUID）、title、estimated_minutes、remaining_minutes、importance（1–5）、deadline、earliest_start、splittable；分钟数为非负整数，remaining 不超过 estimated |
| Availability | start、end，采用半开区间；重叠时段先合并 |
| BusyEvent / LockedBlock | start、end、可选 task_id；从可用时间中扣除，锁定块在重排时保留 |
| ScheduleRequest | schema_version、request_id、now、timezone、horizon_end、tasks、availability、busy_events、locked_blocks、strategy、parameters |
| ScheduleResult | request_id、input_revision、blocks、每项未排分钟与原因、metrics、strategy_version |
| ScheduleBlock | task_id、start、end、minutes、来源策略 |

输入时间必须含时区偏移，内部统一 UTC；展示使用请求指定的 IANA 时区。只有日期的旧任务需用户明确截止时间后才能进入调度。缺少工作量或重要性的旧任务标为“待补充”，不推测耗时。

## 调度规则与算法

1. 规划窗口从 now 开始；合并 availability，扣除 busy 和 locked 区间。
2. 每个时间块在可用区间内、截止时间前，且互不重叠；总安排分钟不超过剩余工作量。
3. 默认最大块长 60 分钟，最小块长 15 分钟；任务最后不足 15 分钟的尾段允许安排。不可拆分任务需连续容纳全部剩余工作量。
4. 已完成、已删除任务不进入候选。循环任务只使用已生成的具体实例，未来实例展开为后续扩展。
5. 重排只替换未来未锁定块；生成计划不改变任务完成状态。提交前比较输入版本，过期结果要求重新生成。
6. 统一分配器负责约束，策略仅提供下一候选的排序；同分以 deadline、task_id 稳定决胜，确保结果可复现。

策略 A：EDF，按 deadline 升序。策略 B：Importance First，按 importance 降序，再按 deadline。

策略 C：Risk-Aware，为待验证启发式。每次分配后重新计算任务截止前尚未占用容量 A_i、剩余工作量 R_i；A_i=0 时输出不可安排原因。初始候选评分为 urgency、importance/5、min(R_i/A_i, 1) 的等权平均；urgency = 1/(1+距离截止的小时数)。权重只在开发种子上调节，评估前冻结并记录版本。单任务比例仅用于排序；共享容量冲突由分配器与结果校验器判断。

## 模块与集成

建议目录：

```text
python_scheduler/
  pyproject.toml
  src/academic_scheduler/
    models.py          # dataclasses 与输入校验
    availability.py    # 合并、扣除与时间处理
    strategies.py      # Strategy Protocol 与三种策略
    engine.py          # 共享分配器
    validation.py      # 独立输出约束检查
    metrics.py
    cli.py
  tests/
  examples/            # 合成演示数据
  experiments/         # 固定种子生成器、benchmark
docs/scheduler/         # 契约、实验协议、演示说明
```

Python 核心优先用标准库 dataclasses、datetime、zoneinfo、json、unittest；Windows 时区数据通过 tzdata 依赖提供。绘图依赖放实验可选组。

Electron 接入阶段通过主进程 spawn Python CLI，使用 stdin/stdout JSON、stderr 日志和退出码；禁用 shell 拼接，设置超时、输出大小上限及取消机制。renderer 只通过有限 IPC 请求排程。主进程保存经校验和用户确认的计划，Python 不直接读写应用数据库。Python 可执行文件配置与 Windows 分发包装单列验收，CLI Demo 不依赖它完成。

## 里程碑与验收

以下为内部目标日期（America/Chicago）；11 月 9 日和 12 月 3 日来自参考对话，原 syllabus 未在本轮核验。

| 时间 | 交付 | 成功标志 |
| --- | --- | --- |
| 11/4–11/5 | 契约、模型、空闲区间运算、EDF | 一份 JSON 输入生成合法时间块；独立校验器通过 |
| 11/6–11/8 | CLI、错误处理、合成演示、单元测试 | 可行、容量不足、重排三个案例可重复运行；干净环境安装说明可用 |
| 11/9 | Demo 1 最小版本 | 从输入到时间块及未排原因完整演示，能解释 EDF 和关键测试 |
| 11/10–11/16 | Importance、Risk-Aware、实验生成器 | 三策略复用分配器；相同种子输入可复现；所有输出先经约束校验 |
| 11/17–11/23 | 冻结参数、运行实验、结果分析 | 原始数据、配置、版本、图表互相可追溯 |
| 11/24–11/29 | Pinboard 最小集成 | 补充任务参数→选择可用时段→预览→确认→日历显示；过期结果拒绝保存 |
| 11/30–12/2 | 缺陷收敛、报告、独立安装与演示演练 | README、测试、结果和演示脚本齐备；没有未经测量的性能结论 |
| 12/3 | 暂定最终交付 | 代码、可运行 Python 入口、三策略比较、测试、报告和演示材料归档 |

若时间不足，优先保住 Python CLI、三策略、公平实验和单元测试；Electron 联动与安装包集成后移。可用开发工时尚未提供，以上是里程碑顺序，不是已确认的工时承诺。

## 实验协议

- 任务数 20/50/100 与负载比（总工作量/总可用分钟）0.6/1.0/1.4 交叉设计，避免用任务数直接代表拥挤程度。
- 增加集中截止和分散截止两种分布、连续和碎片化可用时段两种分布；记录数据生成规则。
- 开发种子 0–9，正式评估种子 100–129；每组输入在三策略之间保持完全一致，固定 now 和时区。
- 指标：截止前完整安排的任务数/有效任务数；完整安排任务的重要性总和/全部重要性总和；未排分钟；排程核心耗时。空任务集的比例记 N/A。
- 计时排除文件 I/O 和绘图，记录 Python、系统、硬件与提交；预热后重复测量，汇报中位数和分位数。计划指标跨种子报告均值与离散程度及配对差值。
- 所有结果必须通过独立约束检查；违规结果单独标记算法失败。Risk-Aware 是否优于基线由结果决定。指标衡量计划分配，不把它记作实际学习完成。

## 必测边界

无任务、零剩余工作量、负分钟、重复 ID、非法时区、截止早于 now、零容量、重叠可用时段、busy 全覆盖、跨午夜/DST、不可拆任务、尾段、同分排序、容量不足、锁定块冲突、过期结果、两次相同输入一致。小规模手算案例用于核对指标，独立检查器不复用分配器的正确性判断。

## 后续第一项任务

实现 models、availability、EDF、CLI 与对应测试，并提供一个可行案例和一个超载案例。开始实现前需核对课程对 Python 版本、AI 辅助使用、演示形式及具体选题批准的要求；未获得的信息保留为待确认项。

文档、定向测试可交给轻量 subagent；调度规则和时间边界交给独立审查者。每次按文件分工，合并后统一验收，完成后按项目约定同步 GitHub。
