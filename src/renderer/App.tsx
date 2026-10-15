import { EditableMarkdown, MarkdownView, type EditableMarkdownHandle } from './Markdown';
import { DesktopSettings } from './DesktopSettings';
import { Main } from './MainView';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pin, X, ArrowLeft, Download, RefreshCw } from 'lucide-react';
import type { AppSnapshot, Item, ItemPatch } from '../shared/types';
import { api } from './api';
import { ThemeSettings, CompactSettings, readAutoCompact, useTheme } from './Theme';

const statusNames = { unconfigured: '本机保存 · 未配置云端', 'signed-out': '本机保存 · 未登录', syncing: '正在同步', synced: '已同步', offline: '离线 · 更改待同步', error: '同步失败' };
export function App() {
  useTheme();
  const [snapshot, setSnapshot] = useState<AppSnapshot | null>(null);
  const [error, setError] = useState(''); const [initialError, setInitialError] = useState('');
  const [settings, setSettings] = useState(false);
  const load = useCallback(() => { setInitialError(''); api.getSnapshot().then(setSnapshot).catch(e => setInitialError(String(e.message ?? e))); }, []);
  useEffect(() => { load(); return api.subscribe(setSnapshot); }, [load]);
  const run = useCallback(async (action: () => Promise<unknown>) => { try { await action(); return true; } catch (e) { setError(e instanceof Error ? e.message : String(e)); return false; } }, []);
  if (initialError) return <main className="loading"><h1>暂时无法打开数据</h1><p role="alert">{initialError}</p><button onClick={load}>重试</button></main>;
  if (!snapshot) return <main className="loading" role="status">正在打开便笺…</main>;
  const id = new URLSearchParams(location.search).get('note');
  const item = id ? snapshot.items.find(i => i.id === id) : undefined;
  return <>{id ? item ? <Floating item={item} snapshot={snapshot} run={run} /> : <main className="loading"><p>这条记录已删除或不属于当前账号。</p><button onClick={() => run(() => api.windowControl('close'))}>关闭窗口</button></main> : <Main snapshot={snapshot} run={run} openSettings={() => setSettings(true)} />}
    {error && <div className="toast" role="alert"><span>{error}</span><button aria-label="关闭错误提示" onClick={() => setError('')}><X size={16}/></button></div>}
    {settings && <SettingsPanel snapshot={snapshot} run={run} close={() => setSettings(false)} />}
  </>;
}
type Runner = (action: () => Promise<unknown>) => Promise<boolean>;
function Floating({ item,snapshot,run }: {item:Item;snapshot:AppSnapshot;run:Runner}) {
 const [title,setTitle]=useState(item.title);const [body,setBody]=useState(item.body);const [date,setDate]=useState(item.dueDate??'');const [top,setTop]=useState(true);const [saving,setSaving]=useState(false);const [dirty,setDirty]=useState(false);
 const [autoCompact,setAutoCompact]=useState(readAutoCompact);const [expanded,setExpanded]=useState(false);const inside=useRef(false);const expandedRef=useRef(false);
 const titleEditor=useRef<EditableMarkdownHandle>(null);const bodyEditor=useRef<EditableMarkdownHandle>(null);
 const draft=useRef<ItemPatch>({});const timer=useRef<ReturnType<typeof setTimeout>|null>(null);const savingChain=useRef(Promise.resolve(true));const revision=useRef(0);
 const flush=useCallback(async()=>{try{titleEditor.current?.flush();bodyEditor.current?.flush();}catch(e){await run(async()=>{throw e;});return false;}if(timer.current)clearTimeout(timer.current);if(!Object.keys(draft.current).length)return savingChain.current;const patch=draft.current;if(patch.title!==undefined&&!patch.title.trim()){await run(async()=>{throw new Error('标题不能为空。请填写标题后再保存或关闭便笺。');});return false;}draft.current={};const rev=revision.current;setSaving(true);const next=savingChain.current.then(()=>run(()=>api.updateItem(item.id,patch)));savingChain.current=next;const ok=await next;setSaving(false);if(!ok)draft.current={...patch,...draft.current};if(ok&&rev===revision.current)setDirty(false);return ok;},[item.id,run]);
 const change=(patch:ItemPatch)=>{draft.current={...draft.current,...patch};revision.current++;setDirty(true);if(timer.current)clearTimeout(timer.current);timer.current=setTimeout(()=>void flush(),500);};
 useEffect(()=>{if(!dirty){setTitle(item.title);setBody(item.body);setDate(item.dueDate??'');}},[item,dirty]);
 useEffect(()=>{const handler=()=>{void flush();};window.addEventListener('blur',handler);return()=>{window.removeEventListener('blur',handler);if(timer.current)clearTimeout(timer.current);void flush();};},[flush]);
 useEffect(()=>api.onCloseRequest(async()=>{let guardTimer:ReturnType<typeof setTimeout>;const timeout=new Promise<boolean>(resolve=>{guardTimer=setTimeout(()=>{void run(async()=>{throw new Error('保存等待超过 20 秒，已取消关闭。请检查网络或重试。');});resolve(false);},20000);});try{return await Promise.race([flush(),timeout]);}finally{clearTimeout(guardTimer!);}}),[flush,run]);
 const expand=useCallback(async()=>{if(expandedRef.current)return;expandedRef.current=true;setExpanded(true);if(!await run(()=>api.setNoteExpanded(item.id,true))){expandedRef.current=false;setExpanded(false);}},[item.id,run]);
 const collapse=useCallback(async()=>{if(!autoCompact||inside.current||!expandedRef.current)return;if(document.hasFocus()&&document.activeElement?.matches('input,textarea,[contenteditable=true]'))return;if(!await flush())return;if(inside.current||document.hasFocus()&&document.activeElement?.matches('input,textarea,[contenteditable=true]'))return;if(await run(()=>api.setNoteExpanded(item.id,false))){expandedRef.current=false;setExpanded(false);}},[autoCompact,flush,item.id,run]);
 useEffect(()=>{const changed=()=>setAutoCompact(readAutoCompact());window.addEventListener('storage',changed);window.addEventListener('pinboard-compact-changed',changed);return()=>{window.removeEventListener('storage',changed);window.removeEventListener('pinboard-compact-changed',changed);};},[]);
 useEffect(()=>{void run(()=>api.setNoteExpanded(item.id,false));},[item.id,run]);
 useEffect(()=>{if(!autoCompact)void expand();else void collapse();},[autoCompact,expand,collapse]);
 useEffect(()=>{const blur=()=>{inside.current=false;void collapse();};window.addEventListener('blur',blur);return()=>window.removeEventListener('blur',blur);},[collapse]);
 const close=async()=>{if(await flush())await run(()=>api.unpinItem(item.id));};
 return <main className={`floating ${item.color} ${expanded?'expanded':'compact'}`} onMouseEnter={()=>{inside.current=true;void expand();}} onMouseLeave={()=>{inside.current=false;void collapse();}} onFocusCapture={()=>void expand()} onBlurCapture={()=>{setTimeout(()=>void collapse(),0);}}><header className="floating-toolbar drag"><span>{item.kind==='task'?'任务':'便笺'}</span><div className="no-drag"><button aria-label="打开主界面" title="打开主界面" onClick={async()=>{if(await flush())run(()=>api.openMain());}}><ArrowLeft size={16}/></button><button aria-label={top?'关闭始终置顶':'开启始终置顶'} title={top?'关闭始终置顶':'开启始终置顶'} aria-pressed={top} onClick={async()=>{if(await run(()=>api.setAlwaysOnTop(item.id,!top)))setTop(!top);}}><Pin size={16}/></button><button aria-label="取消固定并关闭" title="取消固定并关闭" onClick={close}><X size={16}/></button></div></header>{!expanded&&<button className="compact-preview" aria-label="展开便笺" onClick={()=>void expand()}><strong><MarkdownView value={title} inline/></strong><span><MarkdownView value={body} inline emptyText="移入以查看和编辑"/></span></button>}<div className="floating-markdown-title" hidden={!expanded}><EditableMarkdown ref={titleEditor} value={title} inline ariaLabel="便笺标题" onDirty={()=>setDirty(true)} onChange={value=>{setTitle(value);change({title:value});}}/></div><div className="floating-markdown-body" hidden={!expanded}><EditableMarkdown ref={bodyEditor} value={body} ariaLabel="便笺内容" onDirty={()=>setDirty(true)} onChange={value=>{setBody(value);change({body:value});}}/></div><footer className="floating-footer" hidden={!expanded}>{item.kind==='task'&&<label className="complete-label"><input type="checkbox" checked={item.completed} onChange={e=>run(()=>api.updateItem(item.id,{completed:e.target.checked}))}/>已完成</label>}<input aria-label="截止日期" type="date" value={date} onChange={e=>{setDate(e.target.value);change({dueDate:e.target.value||null});}} onBlur={()=>void flush()}/><span role="status">{saving?'保存中…':dirty?'未保存':snapshot.sync.email?statusNames[snapshot.sync.status]:'已保存到本机'}</span></footer></main>;
}
function SettingsPanel({snapshot,run,close}:{snapshot:AppSnapshot;run:Runner;close:()=>void}) {
 useDialogFocus();
 const [url,setUrl]=useState('');const [key,setKey]=useState('');const [email,setEmail]=useState('');const [token,setToken]=useState('');const [sent,setSent]=useState(false);const [busy,setBusy]=useState(false);const [notice,setNotice]=useState('');const oldConfig=useRef<{url:string;publicKey:string}|null>(null);
 useEffect(()=>{api.getCloudConfig().then(c=>{if(c){oldConfig.current=c;setUrl(c.url);setKey(c.publicKey);}}).catch(e=>setNotice(String(e)));},[]);
 const action=async(fn:()=>Promise<unknown>,message:string)=>{setBusy(true);const ok=await run(fn);setBusy(false);if(ok)setNotice(message);return ok;};
 return <div className="modal-backdrop" onKeyDown={e=>{if(e.key==='Escape'&&!busy)close();}}><section className="dialog settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-heading"><div className="dialog-heading"><h2 id="settings-heading">账号与设置</h2><button aria-label="关闭设置" disabled={busy} onClick={close}><X size={18}/></button></div><ThemeSettings/>{snapshot.desktop&&<DesktopSettings/>}<CompactSettings/><p className="settings-status">{snapshot.desktop?statusNames[snapshot.sync.status]:'网页预览仅保存到当前浏览器，不支持账号登录。'}</p>{snapshot.sync.error&&<p className="inline-error" role="alert">{snapshot.sync.error}</p>}{snapshot.desktop&&<><p className="help">登录前的便笺保留在本机。账号数据单独保存，不会自动上传本机便笺；退出登录后可继续使用本机数据。</p><form onSubmit={e=>{e.preventDefault();const next={url:url.trim(),publicKey:key.trim()};if(oldConfig.current?.url===next.url&&oldConfig.current?.publicKey===next.publicKey){setNotice('配置没有变化，无需保存。');return;}void action(async()=>{await api.setCloudConfig(next);oldConfig.current=next;},'云端配置已保存。');}}><h3>连接 Supabase</h3><label>项目 URL<input type="url" required placeholder="https://your-project.supabase.co" value={url} onChange={e=>setUrl(e.target.value)}/></label><label>公开客户端密钥<input required value={key} onChange={e=>setKey(e.target.value)} placeholder="Publishable key 或 anon key"/></label><p className="help">只填写公开密钥，勿填写 service_role 或 secret key。完整配置步骤见项目 README。</p><button disabled={busy} type="submit">保存配置</button><p className="help">更改配置会退出当前账号，账号数据保留。</p></form>{snapshot.sync.email?<div className="account"><h3>当前账号</h3><p>{snapshot.sync.email}</p><p className="help">待同步记录：{snapshot.sync.pending}{snapshot.sync.lastSyncedAt&&` · 上次同步 ${new Date(snapshot.sync.lastSyncedAt).toLocaleString()}`}</p><button disabled={busy} onClick={()=>action(()=>api.syncNow(),'同步操作已完成，请查看同步状态。')}><RefreshCw size={16}/>立即同步</button><button disabled={busy} onClick={()=>action(()=>api.signOut(),'已退出，回到本机数据。')}>退出登录</button></div>:<form onSubmit={async e=>{e.preventDefault();if(await action(()=>api.sendOtp(email.trim()),'验证码已发送，请查收邮件。'))setSent(true);}}><h3>邮箱登录</h3><label>邮箱<input type="email" required value={email} onChange={e=>{setEmail(e.target.value);setSent(false);}} placeholder="you@example.com"/></label><button disabled={busy||!snapshot.sync.configured}>{busy?'处理中…':sent?'重新发送验证码':'发送验证码'}</button>{sent&&<><label>邮件验证码<input inputMode="numeric" autoComplete="one-time-code" value={token} onChange={e=>setToken(e.target.value)} /></label><button className="primary" type="button" disabled={busy||!token.trim()} onClick={()=>action(()=>api.verifyOtp(email.trim(),token.trim()),'登录成功。')}>验证并登录</button></>}</form>}</>}{notice&&<p role="status">{notice}</p>}<div className="settings-export"><h3>数据备份</h3><p className="help">导出当前数据范围的 JSON 备份。</p><button disabled={busy} onClick={()=>action(async()=>{const saved=await api.exportData();if(!saved)throw new Error('导出已取消。');},'备份已导出。')}><Download size={16}/>导出备份</button></div></section></div>;
}

function useDialogFocus() {
 useEffect(() => {
  const previous = document.activeElement as HTMLElement | null;
  const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
  const selector = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex="0"]';
  const initial = dialog?.querySelector<HTMLElement>('input') ?? dialog?.querySelector<HTMLElement>(selector);
  initial?.focus();
  const handler = (event: KeyboardEvent) => {
   if (event.key !== 'Tab' || !dialog) return;
   const elements = Array.from(dialog.querySelectorAll<HTMLElement>(selector));
   const first = elements[0]; const last = elements[elements.length-1];
   if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
   if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  };
  document.addEventListener('keydown', handler);
  return () => { document.removeEventListener('keydown', handler); previous?.focus(); };
 }, []);
}
