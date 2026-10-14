import { useState } from 'react';
import { FolderOpen, Import, RefreshCw } from 'lucide-react';
import type { AppSnapshot } from '../shared/types';
import type { ObsidianPreview, ObsidianResult } from '../shared/obsidian';
import { api } from './api';

export function ObsidianPanel({ snapshot }: { snapshot: AppSnapshot }) {
  const [preview, setPreview] = useState<(ObsidianPreview & { token: string }) | null>(null);
  const [result, setResult] = useState<ObsidianResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function act(fn: () => Promise<void>) {
    setBusy(true); setError('');
    try { await fn(); } catch (error) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  return <section className="obsidian-panel" aria-label="Obsidian 导入与完成状态同步">
    <div className="heading"><h1>Obsidian</h1></div>
    <p>把 Markdown 笔记与勾选任务带到桌面。导入保留正文，任务会单独显示在任务列表。</p>
    <p className="help">当前目标：{snapshot.sync.email ? `账号 ${snapshot.sync.email}（将参与云端同步）` : snapshot.sync.configured && snapshot.sync.status === 'offline' ? '当前缓存工作区（账号数据可能在恢复连接后同步）' : '本机工作区'}。关联路径只保存在这台电脑。</p>
    {!snapshot.desktop && <p className="preview-banner">请在 Windows 应用中选择本机文件夹。</p>}
    <button disabled={busy || !snapshot.desktop} onClick={() => act(async () => { const chosen = await api.chooseObsidianFolder(); if (chosen) { setPreview(chosen); setResult(null); } })}><FolderOpen size={16}/>{busy ? '处理中…' : '选择文件夹并预览'}</button>
    {preview && <section className="obsidian-preview" aria-labelledby="obsidian-selection">
      <h2 id="obsidian-selection">{preview.folderName}</h2>
      <p>{preview.files} 份 Markdown · {preview.tasks} 条任务</p>
      <p className="help">导入会重新读取所选目录。重复导入跳过已关联记录；源文件变化不会直接覆盖已导入的内容。</p>
      <button className="primary" disabled={busy || !preview.files} onClick={() => act(async () => setResult(await api.importObsidian(preview.token)))}><Import size={16}/>导入到当前工作区</button>
      {!!preview.warnings.length && <ul className="operation-details">{preview.warnings.map((text, index) => <li key={index}>{text}</li>)}</ul>}
    </section>}
    <section className="obsidian-writeback" aria-labelledby="obsidian-writeback-heading">
      <h2 id="obsidian-writeback-heading">写回任务完成状态</h2>
      <p className="help">只更新已关联 Markdown 的勾选框，不改标题或正文。先备份原文件；文件自导入后有其他变化时跳过并报告冲突。此操作不会删除文件，也不自动监听笔记库。</p>
      <button disabled={busy || !snapshot.desktop} onClick={() => act(async () => setResult(await api.syncObsidian()))}><RefreshCw size={16}/>备份并写回完成状态</button>
    </section>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {result && <section className="obsidian-result" aria-live="polite"><h2>操作结果</h2><p>导入 {result.imported} · 更新 {result.updated} · 跳过 {result.skipped}</p>{!!result.conflicts.length && <><h3>冲突：原文件未覆盖</h3><ul className="operation-details">{result.conflicts.map((text,index) => <li key={index}>{text}</li>)}</ul></>}{!!result.warnings.length && <ul className="operation-details">{result.warnings.map((text,index) => <li key={index}>{text}</li>)}</ul>}</section>}
  </section>;
}
