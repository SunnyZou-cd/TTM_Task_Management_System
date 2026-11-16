# 课程版本重构

标准：USACO银牌/大二可读性。保留实际功能，用普通函数、列表/字典和一个Tkinter类表达；不要求读者先理解模型协议、工作区事务层和源码生成器。

主入口demo1.py仅负责启动，实际代码放course_demo/的三个模块：scheduler.py（时间和调度）、storage.py（JSON读写）、ui.py（Tkinter日历）。既有python_scheduler模块保留为历史/回归参考，默认入口不再导入它们，不再生成根目录源码。

保留：日/周日历、任务CRUD/进度、三策略、忙碌、锁定重排、英文/中文、本机时间、保存恢复。必要检查限于用户字段、重叠/工作量和存档格式；不引入插件、协议、dataclasses、动态代码生成、第三方库。数据为普通字典，使用整数时间戳分钟计算。

新默认存档work/course-demo/workspace.json，与旧存档隔离；提供显式导入旧工作区且不覆盖原文件。保存保留基本.bak和磁盘修改检查。验收真实Tk用户流程及手算算法案例，文档解释每个模块和数据结构。

完成状态：课程版实现与29项测试通过；历史高级版104项回归通过，真实窗口截图已检查。详见COURSE_REFACTOR_VERIFICATION.md。最终提交与远端核对由完成报告记录。

## 模块契约

data = {"format":"course-demo-1", "tasks":[], "busy":[], "locks":[], "plan":[], "settings":{"strategy":"edf","min_block":15,"max_block":60,"days":7}}。
task={id:int,title:str,total:int,remaining:int,importance:int,start:int,deadline:int,splittable:bool}；remaining=0表示完成。busy={start:int,end:int}；locks/plan={task_id:int,start:int,end:int,locked:bool}。时间均为Unix分钟，显示/输入使用本机时间。

scheduler：new_data()、now_minutes()、parse_time(str)->int、format_time(int)->str（YYYY-MM-DD HH:MM）、validate_data(data)->None（失败ValueError英文）、make_plan(data,now=None)->dict（返回{"blocks":list,"unscheduled":list[{task_id,minutes,reason}],"metrics":dict}，不修改输入）。metrics requested/scheduled/unscheduled/complete/tasks/weighted_ratio。固定三策略edf/importance/risk；risk等权urgency/importance/remaining-capacity，分配后重排。所有锁计入remaining，过去锁要求先解除，不推断完成。

storage：load(path)->data、save(path,data,previous_bytes=None)->bytes（已存在时必须与previous_bytes完全一致；返回写入bytes）、import_legacy(path)->data（只读转换原工作区，独立保存）。普通JSON读写、备份和临时替换，无额外类。

ui：PlannerApp(root,path=None)、run(path=None)->int；self.data普通字典。root入口用argparse仅支持--data。新/编辑任务聚焦表单，默认remaining=total，简单高级字段；不要恢复Time页面。所有测试临时文件work/。
