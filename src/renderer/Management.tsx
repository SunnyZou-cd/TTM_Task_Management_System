import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import type { Item } from '../shared/types';
import { dateKey, monthDays, taskStats } from './management-logic';
export type ManagementView = 'overview' | 'calendar' | 'progress';
type Props = { view: ManagementView; items: Item[]; edit: (item: Item) => void; create: (date?: string) => void };
const titles = { overview: '工作概览', calendar: '任务日历', progress: '完成进度' };
export function Management({ view, items, edit, create }: Props) {
  const today = dateKey(new Date());
  const stats = taskStats(items, today);
  const tasks = items.filter(item => item.kind === 'task');
  const [selected, setSelected] = useState(today);
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1, 12));
  const days = monthDays(month.getFullYear(), month.getMonth());
  const byDate = useMemo(() => {
    const map = new Map<string, Item[]>();
    for (const task of items) if (task.kind === 'task' && task.dueDate) map.set(task.dueDate, [...(map.get(task.dueDate) ?? []), task]);
    return map;
  }, [items]);
  const attention = tasks.filter(task => !task.completed && task.dueDate && task.dueDate <= today).sort((a,b) => a.dueDate!.localeCompare(b.dueDate!));
  return <section className="management"><div className="heading"><h1>{titles[view]}</h1><button className="primary" onClick={() => create(view === 'calendar' ? selected : undefined)}><Plus size={17}/>新建任务</button></div>
    {view === 'calendar' ? <><div className="calendar-heading"><h2>{month.getFullYear()} 年 {month.getMonth()+1} 月</h2><div><button aria-label="上个月" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth()-1, 1, 12))}><ChevronLeft size={17}/></button><button onClick={() => {setSelected(today);setMonth(new Date(new Date().getFullYear(),new Date().getMonth(),1,12));}}>今天</button><button aria-label="下个月" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth()+1, 1, 12))}><ChevronRight size={17}/></button></div></div><div className="calendar-week" aria-hidden="true">{['一','二','三','四','五','六','日'].map(day => <span key={day}>{day}</span>)}</div><div className="calendar-days" aria-label="选择截止日期">{days.map(day => {const scheduled=byDate.get(day.key) ?? [];const pending=scheduled.filter(item => !item.completed).length;return <button key={day.key} aria-label={`${day.key}，${scheduled.length} 项任务，${pending} 项未完成`} aria-pressed={selected===day.key} aria-current={day.key===today?'date':undefined} className={`${day.inMonth?'':'outside'} ${selected===day.key?'selected':''}`} onClick={() => setSelected(day.key)}><span>{day.day}</span>{scheduled.length>0 && <small>{pending ? `${pending} 待办` : '已完成'}</small>}</button>;})}</div><section className="management-section"><h2>{selected} 的任务</h2><TaskRows items={byDate.get(selected) ?? []} edit={edit} empty="这一天没有到期任务。点击“新建任务”安排一项。"/></section></>
    : <><dl className="overview-summary"><div><dt>全部任务</dt><dd>{stats.total}</dd></div><div><dt>已完成</dt><dd>{stats.completed}</dd></div><div><dt>今天待办</dt><dd>{stats.today}</dd></div><div><dt>已逾期</dt><dd>{stats.overdue}</dd></div></dl><section className="management-section progress-section"><div className="progress-label"><h2>当前完成比例</h2><strong>{stats.percentage}%</strong></div><progress max={100} value={stats.percentage} aria-label="当前任务完成比例"/><p className="help">{stats.total ? `已完成 ${stats.completed} / ${stats.total} 项，剩余 ${stats.remaining} 项。` : '还没有任务，添加后会显示完成比例。'} 统计当前工作区全部任务，不代表历史趋势。</p></section>{view === 'overview' ? <section className="management-section"><h2>需要关注</h2><p className="help">今天到期和已逾期的未完成任务，按截止日期排列。</p><TaskRows items={attention} edit={edit} empty="没有今天到期或已逾期的待办。"/></section> : <><section className="management-section"><h2>剩余任务分布</h2><dl className="progress-breakdown"><div><dt>已逾期</dt><dd>{stats.overdue} 项</dd></div><div><dt>今天到期</dt><dd>{stats.today} 项</dd></div><div><dt>未来到期</dt><dd>{stats.remaining-stats.overdue-stats.today-stats.undated} 项</dd></div><div><dt>未设日期</dt><dd>{stats.undated} 项</dd></div></dl></section><section className="management-section"><h2>未完成任务</h2><TaskRows items={tasks.filter(task => !task.completed)} edit={edit} empty={stats.total?'全部任务已完成。':'还没有任务。'}/></section></>}</>}
  </section>;
}
function TaskRows({items, edit, empty}: {items: Item[]; edit: (item: Item) => void; empty: string}) {
  return items.length ? <div className="management-tasks">{items.map(item => <button key={item.id} onClick={() => edit(item)}><span><strong>{item.title}</strong><small>{item.completed?'已完成':'未完成'} · {item.dueDate ?? '未设日期'}</small></span><span>编辑</span></button>)}</div> : <p className="management-empty">{empty}</p>;
}
