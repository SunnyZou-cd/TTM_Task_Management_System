import { useEffect, useState } from 'react';
import { api } from './api';
export function DesktopSettings() {
  const [mode,setMode]=useState<'window'|'desktop'>('window'), [busy,setBusy]=useState(false), [error,setError]=useState('');
  useEffect(()=>{let active=true;const refresh=()=>api.getMainDisplayMode().then(value=>{if(active)setMode(value);}).catch(()=>{});void refresh();const timer=setInterval(refresh,5000);return()=>{active=false;clearInterval(timer);};},[]);
  async function change(value:'window'|'desktop') {setBusy(true);setError('');try{await api.setMainDisplayMode(value);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setMode(await api.getMainDisplayMode());setBusy(false);}}
  return <section className="desktop-settings"><h3>主窗口显示方式</h3><div className="tabs">{([['window','普通窗口'],['desktop','嵌入桌面']] as const).map(([value,label])=><button key={value} disabled={busy} aria-pressed={mode===value} className={mode===value?'selected':''} onClick={()=>void change(value)}>{label}</button>)}</div><p className="help">{mode==='desktop'?'主界面驻留桌面层。双击托盘图标可找回窗口。':'从托盘打开主窗口，或切换到桌面层。'}</p>{error&&<p className="inline-error" role="alert">{error}</p>}</section>;
}
