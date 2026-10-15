import { useEffect, useMemo, useState } from 'react';
import { Check, Pin, Plus, Settings, X, Minus, Trash2 } from 'lucide-react';
import type { AppSnapshot, Item } from '../shared/types';
import { api } from './api';
import { Management, type ManagementView } from './Management';
import { ObsidianPanel } from './ObsidianPanel';
import { ItemEditor } from './ItemEditor';
import { MarkdownView } from './Markdown';
export type Runner = (action: () => Promise<unknown>) => Promise<boolean>;
const PAGE_SIZE = 50;
export function Main({ snapshot, run, openSettings }: { snapshot: AppSnapshot; run: Runner; openSettings: () => void }) {
  const [view,setView] = useState<'task'|'note'|'obsidian'|ManagementView>('task');
  const [filter,setFilter] = useState('pending'), [search,setSearch] = useState(''), [tag,setTag] = useState('');
  const [page,setPage] = useState(0), [sort,setSort] = useState('due');
  const [creating,setCreating] = useState(false), [editing,setEditing] = useState<Item|null>(null), [createDate,setCreateDate] = useState('');
  const kind = view === 'note' ? 'note' : 'task';
  const today = new Date(); const localDate = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  const tags = useMemo(()=>[...new Set(snapshot.items.filter(i=>i.kind===kind).flatMap(i=>i.tags??[]))].sort(),[snapshot.items,kind]);
  const items = useMemo(()=>snapshot.items.filter(i=>i.kind===kind && (kind==='note'||filter==='all'||filter==='pending'&&!i.completed||filter==='completed'&&i.completed||filter==='today'&&!i.completed&&i.dueDate===localDate||filter==='recurring'&&!!i.recurrence) && (!tag||(i.tags??[]).includes(tag)) && `${i.title} ${i.body} ${(i.tags??[]).join(' ')}`.toLowerCase().includes(search.toLowerCase())).sort((a,b)=>sort==='title'?a.title.localeCompare(b.title):sort==='updated'?b.updatedAt.localeCompare(a.updatedAt):(a.dueDate??'9999').localeCompare(b.dueDate??'9999')||(a.dueTime??'').localeCompare(b.dueTime??'')||b.createdAt.localeCompare(a.createdAt)),[snapshot.items,kind,filter,localDate,tag,search,sort]);
  useEffect(()=>setPage(0),[view,filter,tag,search,sort]);
  const pages=Math.max(1,Math.ceil(items.length/PAGE_SIZE)), current=Math.min(page,pages-1);
  const switchView=(next:typeof view)=>{setView(next);setTag('');setSearch('');setCreateDate('');if(next==='task')setFilter('pending');};
  return <div className="app-shell"><header className="titlebar drag"><span>Pinboard</span>{snapshot.desktop&&<div className="window-controls no-drag"><button aria-label="最小化" onClick={()=>run(()=>api.windowControl('minimize'))}><Minus size={16}/></button><button aria-label="关闭主窗口" onClick={()=>run(()=>api.windowControl('close'))}><X size={16}/></button></div>}</header>
    <aside className="sidebar"><div className="brand">Pinboard</div><nav aria-label="主导航">{([['task','任务'],['note','便笺'],['overview','概览'],['calendar','日历'],['progress','进度'],['obsidian','Obsidian']] as const).map(([value,label])=><button key={value} className={view===value?'active':''} onClick={()=>switchView(value)}>{label}{value==='task'&&<span>{snapshot.items.filter(i=>i.kind==='task'&&!i.completed).length}</span>}</button>)}</nav><div className="sidebar-bottom"><p>{snapshot.sync.email??'本机工作区'}</p><button onClick={openSettings}><Settings size={16}/>账号与设置</button></div></aside>
    <main className="main-content" key={view}>{view==='obsidian'?<ObsidianPanel snapshot={snapshot}/>:view==='overview'||view==='calendar'||view==='progress'?<Management view={view} items={snapshot.items} edit={setEditing} create={date=>{setCreateDate(date??'');setCreating(true);}}/>:<>
      <div className="heading"><h1>{kind==='task'?'我的任务':'我的便笺'}</h1><button className="primary" onClick={()=>setCreating(true)}><Plus size={17}/>{kind==='task'?'新建任务':'新建便笺'}</button></div>
      <div className="list-tools">{kind==='task'&&<div className="tabs" aria-label="任务筛选">{[['pending','未完成'],['today','今天'],['completed','已归档'],['recurring','循环任务'],['all','全部']].map(([value,label])=><button key={value} aria-pressed={filter===value} className={filter===value?'selected':''} onClick={()=>setFilter(value)}>{label}</button>)}</div>}<input aria-label="搜索" className="search" placeholder="搜索任务、内容或标签" value={search} onChange={e=>setSearch(e.target.value)}/></div>
      <div className="collection-tools"><label>标签<select aria-label="按标签筛选" value={tag} onChange={e=>setTag(e.target.value)}><option value="">全部标签</option>{tags.map(value=><option key={value}>{value}</option>)}</select></label><label>排序<select aria-label="排序" value={sort} onChange={e=>setSort(e.target.value)}><option value="due">截止日期</option><option value="updated">最近修改</option><option value="title">标题</option></select></label><span>{items.length} 项</span></div>
      {items.length?<div className={kind==='task'?'task-list':'note-grid'}>{items.slice(current*PAGE_SIZE,(current+1)*PAGE_SIZE).map(item=><article key={item.id} className={`item-card ${kind} ${item.color} ${item.completed?'completed':''}`}>
        {kind==='task'&&<button className="check-button" aria-label={item.completed?'标记未完成':'完成任务'} aria-pressed={item.completed} onClick={()=>run(()=>api.updateItem(item.id,{completed:!item.completed}))}>{item.completed&&<Check size={16}/>}</button>}
        <button className="item-content" onClick={()=>setEditing(item)}><h2><MarkdownView value={item.title} inline/></h2>{item.body&&<div className="item-excerpt">{item.body}</div>}<div className="item-meta">{item.dueDate&&<span className={`due ${item.dueDate<localDate&&!item.completed?'overdue':''}`}>{item.dueDate}{item.dueTime&&` ${item.dueTime}`}</span>}{item.recurrence&&<span>循环</span>}{(item.tags??[]).map(t=><span className="tag" key={t}>{t}</span>)}</div></button>
        <div className="item-actions"><button disabled={!snapshot.desktop||(item.kind==='task'&&item.completed)} title={item.completed?'恢复为未完成后可固定':undefined} aria-label={snapshot.pinnedIds.includes(item.id)?'取消固定':'固定为悬浮便笺'} onClick={()=>run(()=>snapshot.pinnedIds.includes(item.id)?api.unpinItem(item.id):api.pinItem(item.id))}><Pin size={16}/></button><button aria-label={`删除 ${item.title}`} onClick={()=>{if(confirm(`删除“${item.title}”？`))run(()=>api.deleteItem(item.id));}}><Trash2 size={15}/></button></div>
      </article>)}</div>:<div className="empty"><h2>{search||tag?'没有匹配内容':filter==='completed'?'暂无归档任务':'暂无待办'}</h2><button onClick={()=>setCreating(true)}><Plus size={16}/>新建{kind==='task'?'任务':'便笺'}</button></div>}
      {pages>1&&<nav className="pagination" aria-label="列表分页"><button disabled={current===0} onClick={()=>{setPage(current-1);document.querySelector('.main-content')?.scrollTo(0,0);}}>上一页</button><span>{current+1} / {pages}</span><button disabled={current===pages-1} onClick={()=>{setPage(current+1);document.querySelector('.main-content')?.scrollTo(0,0);}}>下一页</button></nav>}
    </>}</main>{(creating||editing)&&<ItemEditor kind={editing?.kind??kind} defaultDate={createDate} item={editing} run={run} close={()=>{setCreating(false);setEditing(null);}}/>}
  </div>;
}
