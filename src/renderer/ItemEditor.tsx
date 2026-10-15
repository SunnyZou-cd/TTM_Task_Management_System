import { useEffect, useRef, useState } from 'react';
import { Check, X } from 'lucide-react';
import type { Item, ItemPatch, NoteColor } from '../shared/types';
import { api } from './api';
import { MarkdownView } from './Markdown';
import type { Runner } from './MainView';
export function ItemEditor({kind,item,run,close,defaultDate=''}:{kind:'task'|'note';item:Item|null;run:Runner;close:()=>void;defaultDate?:string}) {
  const [title,setTitle]=useState(item?.title??''), [body,setBody]=useState(item?.body??''), [date,setDate]=useState(item?.dueDate??defaultDate), [time,setTime]=useState(item?.dueTime??''), [tags,setTags]=useState((item?.tags??[]).join(', '));
  const [frequency,setFrequency]=useState(item?.recurrence?.frequency??''), [interval,setInterval]=useState(item?.recurrence?.interval??1);
  const [color,setColor]=useState<NoteColor>(item?.color??'sage'), [saving,setSaving]=useState(false), [preview,setPreview]=useState(false);
  const dialog=useRef<HTMLElement>(null);
  useEffect(()=>{const previous=document.activeElement as HTMLElement;dialog.current?.querySelector('input')?.focus();return()=>previous?.focus();},[]);
  return <div className="modal-backdrop" onKeyDown={e=>{if(e.key==='Escape'&&!saving)close();if(e.key==='Tab'){const nodes=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),textarea,select:not([disabled])')??[]);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}}}><section ref={dialog} className="dialog item-editor" role="dialog" aria-modal="true" aria-labelledby="editor-heading"><div className="dialog-heading"><h2 id="editor-heading">{item?'编辑':'新建'}{kind==='task'?'任务':'便笺'}</h2><button aria-label="关闭编辑器" onClick={close} disabled={saving}><X size={18}/></button></div>
    <form onSubmit={async e=>{e.preventDefault();setSaving(true);const patch:ItemPatch={title:title.trim(),body,dueDate:date||null,dueTime:time||null,color,tags:tags.split(/[,，]/).map(t=>t.trim().replace(/^#/, '')).filter(Boolean),recurrence:kind==='task'&&frequency?{frequency:frequency as 'daily'|'weekly'|'monthly',interval}:null};const ok=await run(()=>item?api.updateItem(item.id,patch):api.createItem({kind,...patch,title:patch.title!}));setSaving(false);if(ok)close();}}>
      <label>标题<input required maxLength={300} value={title} onChange={e=>setTitle(e.target.value)}/></label>
      <div className="editor-mode tabs"><button type="button" aria-pressed={!preview} onClick={()=>setPreview(false)}>Markdown</button><button type="button" aria-pressed={preview} onClick={()=>setPreview(true)}>预览</button></div>
      {preview?<div className="editor-preview"><MarkdownView value={body} emptyText="暂无内容"/></div>:<label>内容<textarea rows={6} value={body} onChange={e=>setBody(e.target.value)} placeholder="支持标题、列表、加粗、链接和代码"/></label>}
      <label>标签<input value={tags} onChange={e=>setTags(e.target.value)} placeholder="学习, 工作（逗号分隔）"/></label>
      <div className="editor-row"><label>日期<input type="date" required={!!frequency} value={date} onChange={e=>setDate(e.target.value)}/></label><label>时间<input type="time" value={time} onChange={e=>setTime(e.target.value)}/></label></div>
      {kind==='task'&&<div className="editor-row"><label>重复<select aria-label="重复频率" value={frequency} disabled={!!item?.seriesId} onChange={e=>setFrequency(e.target.value)}><option value="">不重复</option><option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option></select></label>{frequency&&<label>间隔<input type="number" min={1} max={365} value={interval} onChange={e=>setInterval(Number(e.target.value))}/></label>}{item?.seriesId&&<button type="button" onClick={()=>run(()=>api.updateItem(item.seriesId!,{recurrence:null}))}>停止此系列循环</button>}</div>}
      {frequency&&<p className="help">按所选日期和时间生成；应用关闭期间的任务在下次启动时补齐最近 30 次。</p>}
      <fieldset className="color-picker"><legend>颜色</legend>{(['sage','yellow','blue','rose'] as const).map(c=><button type="button" key={c} className={`swatch ${c}`} aria-label={c} aria-pressed={color===c} onClick={()=>setColor(c)}>{color===c&&<Check size={15}/>}</button>)}</fieldset>
      <div className="dialog-footer"><button type="button" onClick={close} disabled={saving}>取消</button><button className="primary" disabled={saving||!title.trim()}>{saving?'保存中…':'保存'}</button></div>
    </form></section></div>;
}
