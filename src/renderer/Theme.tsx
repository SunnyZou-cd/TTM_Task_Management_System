import { useEffect, useState } from 'react';
export type Theme = 'system'|'light'|'dark';
const key = 'pinboard.theme.v1';
const changed = 'pinboard-theme-changed';
function readTheme(): Theme {try {const value=localStorage.getItem(key);return value==='light'||value==='dark'?value:'system';}catch{return 'system';}}
export function useTheme() {
  const [theme,setThemeState]=useState<Theme>(readTheme);
  useEffect(() => {
    const media=matchMedia('(prefers-color-scheme: dark)');
    const apply=() => {const value=readTheme();setThemeState(value);document.documentElement.dataset.theme=value==='system'?(media.matches?'dark':'light'):value;};
    apply();window.addEventListener('storage',apply);window.addEventListener(changed,apply);media.addEventListener('change',apply);
    return () => {window.removeEventListener('storage',apply);window.removeEventListener(changed,apply);media.removeEventListener('change',apply);};
  },[]);
  const setTheme=(value:Theme) => {localStorage.setItem(key,value);window.dispatchEvent(new Event(changed));};
  return {theme,setTheme};
}
export function ThemeSettings() {
  const {theme,setTheme}=useTheme();
  return <section className="theme-settings"><h3>外观主题</h3><div className="tabs" aria-label="外观主题">{([['system','跟随系统'],['light','浅色'],['dark','深色']] as const).map(([value,label]) => <button key={value} aria-pressed={theme===value} className={theme===value?'selected':''} onClick={() => setTheme(value)}>{label}</button>)}</div><p className="help">主题同时应用于主窗口和所有悬浮便笺。</p></section>;
}

export function readAutoCompact() { try {return localStorage.getItem('pinboard.compact.v1')!=='off';}catch{return true;} }
export function CompactSettings() {
  const [enabled,setEnabled]=useState(readAutoCompact);
  return <section className="theme-settings"><h3>悬浮便笺</h3><label className="compact-setting"><input type="checkbox" checked={enabled} onChange={event=>{const next=event.target.checked;localStorage.setItem('pinboard.compact.v1',next?'on':'off');setEnabled(next);window.dispatchEvent(new Event('pinboard-compact-changed'));}}/>鼠标离开后自动收起</label><p className="help">移入或用键盘聚焦可展开。正在编辑时保持展开，离开后先保存内容。</p></section>;
}
