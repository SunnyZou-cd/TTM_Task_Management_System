# Demo 1 输入输出契约（schema_version = "1"）

Python >=3.11，标准库加 Windows IANA 数据依赖 tzdata。所有公开模型为 frozen dataclasses。未知字段拒绝；整数不接受 bool；字符串非空、无首尾空白且不含孤立 Unicode 代理字符；列表必须是 JSON 数组。输入错误抛 InputError(ValueError)，具有可读字段路径。原规划中的 task_id 可沿用 UUID；合成案例允许其他非空字符串。

## 输入

ScheduleRequest 必需字段：schema_version（固定 "1"）、request_id、input_revision（非空字符串）、now、timezone（有效 IANA 名称）、horizon_end、tasks、availability、busy_events、locked_blocks、strategy、parameters。

strategy 为 edf / importance / risk。parameters 为对象，只允许 min_block_minutes（默认15）和 max_block_minutes（默认60），正整数且 min <= max。risk 的三个等权参数冻结，不暴露未验证调参入口。

时间为有显式偏移的 ISO 8601 字符串 YYYY-MM-DDTHH:MM[:00](Z 或 ±HH:MM)，秒和微秒必须为零，偏移为整分钟且小时不超过23、分钟不超过59。内部 UTC；输出按 timezone 转换。timezone 只负责展示，不重新解释输入墙钟时间：DST 回拨的两个 01:30 必须用各自偏移明确，跳时前后按实际经过分钟计算。拒绝无偏移时间。horizon_end > now。转换到展示时区若产生历史秒级偏移或超出 datetime 范围，会作为 InputError 拒绝；输入端点和生成端点均检查。

Task 必需字段：task_id、title、estimated_minutes、remaining_minutes、importance、deadline、earliest_start、splittable。可选 status，默认 active，允许 active / completed / deleted。分钟为非负整数，remaining <= estimated；importance 为1–5整数；splittable 为 bool；earliest_start <= deadline。completed/deleted 必须 remaining=0；remaining=0 的任务不计入计划指标的任务分母。

availability / busy_events 元素均为 {start, end}，必须 start < end；半开区间允许重叠并先合并，允许位于规划窗口外，计算时裁剪。busy 不携带任务完成含义。

locked_blocks 元素为 {locked_id, task_id, start, end}；task_id 可为 null，表示只占容量的固定预留。locked_id 不重复；任务 ID 必须存在且 active、remaining>0。只接受完全位于 [now,horizon_end] 的未来锁定块，已过去或跨 now 的块须调用方先结算和裁剪。锁定块必须在合并后的 availability 内，不与 busy 或彼此重叠；带任务的锁定块还必须满足 earliest_start 与 deadline。

**remaining_minutes 包含未来锁定工作。** 先扣除对应锁定分钟，再调度差额；锁定总分钟不得超过 remaining。不可拆任务若已锁定，必须恰好一个锁定块且覆盖全部 remaining；否则拒绝输入。锁定块不受自动拆分块长限制，原样保留；所有锁定块都从共享空闲容量中扣除。

每次调用是一个完整快照。既有未锁定计划不在输入中，重排会重新生成。调用方保存计划前应比较 input_revision；CLI 不连接数据库、不写入完成状态。

## Python API / 文件责任

models.py：InputError；Task、Interval、LockedBlock、Parameters、ScheduleRequest、ScheduleBlock、UnscheduledTask、ScheduleResult dataclasses；parse_request(dict)->ScheduleRequest；parse_datetime(value,path)->UTC datetime；result_to_dict(result, timezone)->dict。

字段命名与 JSON 相同。ScheduleRequest 的时间字段已是 UTC datetime，tasks / intervals / locks 为 tuple；parameters 为 Parameters。Interval(start,end)；LockedBlock(locked_id,task_id,start,end)。ScheduleBlock(task_id,start,end,minutes,source,locked_id=None)。UnscheduledTask(task_id,minutes,reasons: tuple[str,...])。ScheduleResult(request_id,input_revision,strategy,strategy_version,blocks: tuple,unscheduled: tuple,metrics: dict)。序列化统一输出全部字段。

availability.py：merge_intervals(intervals)、subtract_intervals(intervals, exclusions)、free_intervals(request)，均返回 tuple[Interval,...]；free_intervals 已裁剪 now/horizon 并扣除 busy 和全部 locks。duration_minutes(start,end)->int。

engine.py：schedule(request)->ScheduleResult；只依赖 metrics.compute_metrics，不依赖 validation；CLI 在输出前必须调用独立校验器。strategies.py 提供三策略排序及版本，risk 每次分配后更新剩余与可用容量；所有策略共用引擎约束。同分以 deadline / task_id 决胜；EDF 优先 deadline / task_id，importance 优先 -importance / deadline / task_id。

metrics.py：compute_metrics(request, blocks)->dict。validation.py：validate_result(request,result)->list[str]，空列表为通过；不调用 engine / availability / strategies 的正确性逻辑。可以共享 models 类型；需独立计算覆盖、分钟、锁定与计数。

## 分配规则

只在 [now,horizon_end]、earliest_start 以后和 deadline 之前分配，端点相等可用。splittable=false 需一个连续块覆盖全部 remaining；自动块不受 max 限制。splittable=true 自动块最长 max，最短 min；仅当该块覆盖任务最后剩余的全部分钟时允许短尾段。尾段是最后一次分配的余额，可回填时间上较早的小空档；每任务至多一个短自动块，且自动总量必须等于 remaining 减去全部带任务锁定。每次尝试按策略挑选可分配任务，在其最早合法空档分配一块，再重新排序；不可分配候选跳过，不能阻塞其他任务。

risk score = (1/(1+max(0,(deadline-now)小时)) + importance/5 + min(R/A,1))/3，R 为扣除全部已保留和新安排块后的剩余分钟，A 为当前空闲中该任务窗口的总分钟；A=0 候选跳过。降序评分后 deadline / task_id 稳定决胜。此为启发式，不声称最优。

未排项只列 minutes>0 的任务，minutes 等于 remaining - 带任务锁定 - 自动安排。reasons 为一个明确原因码：deadline_passed（deadline<=now）、outside_window（earliest_start>=min(deadline,horizon_end)）、no_available_capacity（最终该窗口空闲为0）、insufficient_contiguous_capacity（不可拆且有空闲但容不下整体）、below_min_block（可拆、剩余>=min、所有可用段<min）、insufficient_capacity（其他不足）。按上述顺序选择；原因描述的是该策略结束后的容量，不是不可行性的最优证明。

## 输出与 CLI

输出包含 request_id、input_revision、strategy、strategy_version、blocks、unscheduled、metrics。blocks 按 start/end/task_id 排序；source 为 locked 或请求策略，locked_id 仅锁定块非空；锁定块 task_id 可为 null。result_to_dict 的时间为请求时区 ISO 字符串，UTC 可用 +00:00。

metrics 固定字段：eligible_tasks、fully_scheduled_tasks、completion_ratio、weighted_completion_ratio、requested_minutes、scheduled_minutes、unscheduled_minutes、available_minutes、reserved_minutes、utilization_ratio。eligible=active且remaining>0；completion_ratio=完整安排任务/eligible；weighted=完整安排任务importance和/eligible importance和；无任务两比例为null。scheduled 包含带任务锁定；reserved 仅 task_id=null 锁定；available=合并裁剪availability扣除busy（未扣locks）；utilization=(scheduled+reserved)/available，无容量为null。不包含墙钟耗时，以保证相同输入结果完全一致。

安装命令提供 academic-scheduler 与 python -m academic_scheduler。`schedule INPUT`（INPUT=- 表示 stdin），可选 `--output PATH`；`compare INPUT` 对同一个快照依次跑 edf/importance/risk，输出 {request_id,input_revision,results:[三个结果]}；`validate INPUT RESULT` 校验已保存结果（RESULT 不接受 stdin；INPUT 可为 -）。默认 stdout 只输出 JSON；--output 成功只写文件、stdout 为空。输出文件采用临时文件后原子替换，不允许与输入路径相同。错误 stderr JSON {error:{code,message}}，stdout 为空。

退出码：0=生成/比较/校验成功（允许容量不足）；2=输入/参数/文件/JSON/结果文件结构错误；3=结果约束校验失败；1=意外内部异常。CLI schedule/compare 必须先独立校验再输出。validate 使用 models.parse_result(dict)->ScheduleResult（结构严格，整数/时间/字段按输入同等严格；metrics 字段与值由独立校验核对）。拒绝 JSON 重复键和 NaN/Infinity。输入文件采用 UTF-8，可接受 UTF-8 BOM。
