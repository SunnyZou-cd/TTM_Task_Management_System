# Demo 1 验收记录

## 2026-11-14：单文件补充验收

根目录 `demo1.py` 包含完整可读Python源码和内置三案例；不依赖本地项目包或外部JSON。默认UTC展示，内置演示无需第三方包；自定义命名时区沿用系统数据/tzdata要求。

Windows / Python 3.14.3 全套51项unittest通过（原44项、新增7项）。新增测试在项目work/的独立临时目录中只复制demo1.py，并使用`python -I -S -B demo1.py`运行：隔离PYTHONPATH、用户配置与site-packages，正常显示三个案例各三策略，并且默认运行不生成文件。

另已验证：`--json`九份结果与模块版同快照（仅展示时区改UTC）逐项相等；筛选结果与重复输出一致；JSON文件/stdin的schedule/compare/validate完整往返；篡改revision退出3；非法选项、重复键与孤立代理字符退出2且stderr为JSON；构建脚本`--check`确认生成文件同步。全部结果保持独立约束校验。

维护脚本`python_scheduler/scripts/build_single_file.py`从模块源码生成普通Python函数、dataclasses和嵌入示例，无运行时exec或编码载荷。正常生成会覆盖demo1.py，`--check`只读。以下2026-11-13记录保留作模块版初次交付证据。

验收日期：2026-11-13（America/Chicago）。基线为 main / 6fdf649，本次新增独立 Python 模块，未改 Electron 源码。未发布稳定版。

## 实际环境与安装

Windows x64、Python 3.14.3、academic-scheduler 0.1.0、tzdata 2026.6。声明支持 Python 3.11+，但其他 Python 版本和非 Windows 系统未实测。

从合成测试源副本创建全新 `work/demo1-acceptance/venv`，通过 PEP 517 构建 wheel 并安装；确认 import 路径位于该环境的 `Lib/site-packages`，没有依赖 PYTHONPATH；`pip check` 输出 `No broken requirements found`。构建和验收产物不进入 Git。

## 自动测试

在安装环境运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.\work\demo1-acceptance\venv\Scripts\python.exe -m unittest discover -s python_scheduler/tests -v
```

结果：44 项通过，最终 `OK`。其中一个测试包含随机种子71113的160份输入 × EDF/importance/risk共480组检查，并对相同输入再次运行确认完全一致。它是小规模约束验收，不是正式性能或策略优劣实验。

覆盖模型严格类型/字段/唯一性、空任务与零工作量、负数、错误时区/偏移、无容量、重叠可用区间与busy、跨午夜、DST春季跳时与秋季回拨、截止/earliest_start/horizon、不可拆、最小/最大块与短尾回填、锁定保留/计数/冲突、确定性、动态risk排序、指标手算。校验器拒绝篡改分钟、越界、重叠、错误锁定、超配、错误未排原因、过期版本和错误指标。

CLI测试含真实子进程：中文和BOM、文件与stdin、三策略比较、正常输出与stderr分离、原子文件替换、输入同路径和硬链接保护、重复JSON键、非有限常量、超长数字/过深JSON、错误参数。审查发现的超大比例整数（10**400）和孤立Unicode代理字符均有回归覆盖。

## 安装后的实际演示

各案例用 `python -m academic_scheduler schedule ... --output ...` 生成，再用 `validate` 独立校验，均返回 `{"valid": true}`。

| 合成案例 | 任务需求 | 已安排 | 未排 | 锁定/预留 | 结果 |
| --- | ---: | ---: | ---: | --- | --- |
| feasible | 150分钟 | 150分钟 | 0 | 无 | 2/2任务完整安排 |
| overloaded | 180分钟 | 120分钟 | 60分钟 | 无 | 两任务各缺30分钟，原因 no_available_capacity |
| replan | 150分钟 | 150分钟 | 0 | 带任务锁定30分钟、固定预留30分钟 | 两块原样保留，所有块不早于now |

直接执行安装后的 `academic-scheduler.exe compare -`，stdin 输入同一快照，三结果可解析，连续两次stdout字节一致。`--output` 成功时stdout为空。负数输入和包含孤立代理字符的未知JSON键返回2及可解析stderr JSON；篡改结果为超大比例整数返回3及validation_failed，stdout为空。

本机原始产物位于 `work/demo1-acceptance/`：三份结果、comparison.json、report.json及临时验收脚本。它们为可重新生成的本地证据，不提交。

## 契约决策与边界

- remaining包含未来带任务锁定；先扣锁定再安排差额，task_id=null只预留容量。
- 锁定需完全位于未来规划窗口，已开始的块由调用方先结算裁剪；不可拆任务锁定必须一次覆盖其全部余额。
- 短尾是最后分配的完整余额，可回填时间更早的小空档；最多一个短自动块，且任务必须排满。
- 输入时间以显式偏移确定绝对时刻；请求IANA时区负责展示。历史秒级偏移或展示日期溢出明确拒绝。
- 结果input_revision用于检测过期；CLI没有连接数据主库，实际保存前的原子版本比较仍属于未来集成层。
- 指标描述计划分配；Risk-Aware是冻结等权启发式，不声称优于基线或全局最优。

UI、Electron IPC、真实数据/云端同步、正式实验报告、课程批准和真实课程演示不属于本次已验证交付。
