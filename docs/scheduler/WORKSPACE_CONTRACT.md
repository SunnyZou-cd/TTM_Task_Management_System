# 交互工作区接口

## workspace.py（sol负责）

`WorkspaceError(ValueError)`，面向用户可读错误；可包装models.InputError。Workspace保存原始request dict和当前result dict或None；对外snapshot/result均返回深拷贝，不能由菜单直接修改。

- `Workspace.new(now: datetime|None=None)`：空工作区，UTC，now按分钟向上取整、horizon=now+7天，edf，默认块长，ID和revision为uuid字符串。
- `Workspace.from_document(dict)`、`to_document()`：存档格式 `{format:"academic-scheduler-workspace",version:1,request:{...},result:{...}|null}`。严格验证元数据、请求和当前结果；不接受过期结果。保持JSON CLI输入与个人存档明确区分。
- `.snapshot` property -> request dict；`.result` property -> result dict|None。
- `.add_task(*,title,estimated_minutes,remaining_minutes,importance,deadline,earliest_start,splittable)->str`；`.update_task(task_id,**fields)`（不允许改ID）；`.delete_task(task_id)`（同时移除其锁定）；`.complete_task(task_id)`（remaining=0/status=completed，同时移除其锁定）。普通update不自动删锁，若计数冲突则拒绝且内存不变。
- `.set_window(start:str,end:str,timezone:str)`；`.set_strategy(strategy:str)`；`.set_parameters(min_block_minutes:int,max_block_minutes:int)`。
- `.add_interval(kind,start,end)`、`.remove_interval(kind,index)`；kind仅availability/busy_events，index零起。
- `.generate(*,now:datetime|None=None)->dict`：起点=max(已配置now,实际当前时间向上取整)。now参数只用于固定时钟测试。成功才更新request/revision/result，校验失败不部分修改；过期horizon要求重新设置窗口；已开始/过去锁定要求解锁和手动核对remaining，不自动计完成。
- `.compare(*,now:datetime|None=None)->list[dict]`：同一有效起点跑三策略并独立校验，不改变已保存策略/计划。
- `.lock_block(index:int,*,now:datetime|None=None)->str`：index为当前result.blocks零起；仅锁未锁定、尚未开始的块。保持原计划其他块不变，把该块转为locked，并更新request/revision/result后独立校验；允许连续锁多个块。
- `.unlock(locked_id)`：移除锁定并清空旧result。

所有普通编辑事务：拷贝→更新→parse_request→换revision→提交并清空旧result。失败保持原状态。不能把安排分钟当作实际完成分钟。

## storage.py（sol负责）

`StorageError(ValueError)`。`WorkspaceStore(path)`，`.path`为Path；`.load()->Workspace`，`.save(workspace)->None`。未load的新store仅能创建不存在的文件，存在时不得直接覆盖；load严格解析JSON（拒绝重复键、NaN/Infinity）、验证完整工作区后记录文件sha256。

save验证工作区，创建父目录；独占`.lock`保护合作进程，检查磁盘sha256与最近load/save一致；已有旧文件先备份为同路径加`.bak`，原子替换。异常清理自己的临时/锁文件；不静默覆盖并发修改、损坏文件、别的格式或未加载文件。保存失败不改变调用方内存。

## terminal.py（terra负责）

`run_terminal(data_path: str|Path|None=None)->int`。默认`Path.cwd()/work/demo1-data/workspace.json`。存在则启动加载，失败显示错误并退出非零，不能自动空白覆盖。不存在则新空工作区，不自动写文件。菜单显示路径、时区、规划窗口及dirty状态。

主菜单：1任务管理、2时间设置、3策略/块长、4生成/重排、5查看计划、6锁定管理、7比较策略、8保存、9重新加载、10另存为、0退出。另存为仅接受新路径；保存成功后切换当前store并清dirty，失败保持原store/数据/dirty，以便冲突或保存失败后导出内存修改。

任务菜单：1列表、2新增、3编辑、4删除（确认同时删锁）、5记录剩余分钟、6标记完成（确认）、0返回。按显示序号选择任务，内部ID稳定；编辑回车保留原值。

时间菜单：1设置窗口/时区、2列时段、3新增可用、4删除可用、5新增忙碌、6删除忙碌、0返回。锁定菜单：1列锁定、2从当前计划锁定（显示全块序号）、3按锁定序号解锁、0返回。

时间提示接受带偏移ISO或`YYYY-MM-DD HH:MM`（按工作区时区解释）。空白提示使用明确显示默认值，不推测任务工作量。DST本地不存在时间拒绝，歧义要求显式偏移。UTC不依赖tzdata；其他时区缺数据时给出安装提示。

保存成功清dirty；普通编辑/生成/锁定标dirty；比较不修改。重新加载前若dirty提示明确确认放弃。退出dirty时询问保存/放弃/取消。EOF/中断不擅自保存或覆盖存档；有未保存更改时说明未保存，EOF退出非零。操作错误返回菜单，不损坏内存。

默认无参数入口将调用run_terminal；`--demo`显式运行原合成案例；保留--json/--example/--strategy的显式案例及schedule/compare/validate。`--data PATH`指定交互存档位置。入口及单文件构建由主agent统一修改，terra不改cli或__main__。
