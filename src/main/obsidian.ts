import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import type { CreateItemInput, Item, ItemPatch } from '../shared/types';
import { parseTaskMetadata } from '../shared/task-rules';
import type { ObsidianPreview, ObsidianResult, ObsidianState, ObsidianFileLink as FileLink } from '../shared/obsidian';
export type { ObsidianPreview, ObsidianResult, ObsidianState } from '../shared/obsidian';

const MAX_FILES = 500;
const MAX_BYTES = 100_000;
const MAX_TOTAL_BYTES = 5_000_000;
export interface MarkdownTask { key: string; title: string; completed: boolean; line: number; markerOffset: number }
export interface MarkdownDocument { relativePath: string; title: string; body: string; hash: string; tasks: MarkdownTask[] }
export interface ObsidianHooks {
  loadState(): ObsidianState | null;
  saveState(state: ObsidianState): void;
  getScope(): string;
  getItems(): Item[];
  createItem(input: CreateItemInput): Promise<Item>;
  updateItem(id: string, patch: ItemPatch): Promise<Item>;
}
const digest = (value: Buffer | string) => createHash('sha256').update(value).digest('hex');
const safeRelative = (value: unknown): value is string => typeof value === 'string' && !!value && !path.isAbsolute(value) && !value.split(/[\\/]/).some(part => part === '..' || part === '.' || part.startsWith('.')) && path.extname(value).toLowerCase() === '.md';
function validState(value: ObsidianState): boolean {
  return !!value && value.version === 1 && Array.isArray(value.vaults) && value.vaults.every(v =>
    v && typeof v.root === 'string' && path.isAbsolute(v.root) && typeof v.scope === 'string' && !!v.scope && Array.isArray(v.files) && v.files.every(f =>
      f && safeRelative(f.relativePath) && /^[a-f0-9]{64}$/.test(f.hash) && typeof f.noteId === 'string' && !!f.noteId && typeof f.noteBody === 'string' && Array.isArray(f.tasks) && f.tasks.every(t =>
        t && typeof t.key === 'string' && /^[a-f0-9]{64}:\d+$/.test(t.key) && typeof t.id === 'string' && !!t.id && typeof t.baseCompleted === 'boolean')));
}

/** Back up first, then replace atomically. Check again immediately before replacement. */
async function replaceWithBackup(root: string, relative: string, expected: string, body: string): Promise<void> {
  if (await safeRoot(root) !== root) throw new Error('文件夹位置发生变化，请重新关联。');
  const target = await checkedPath(root, relative);
  const before = await fs.readFile(target);
  if (digest(before) !== expected) throw new Error('源文件已变更，未写回。');
  const backupDir = path.join(path.dirname(target), '.pinboard-backups');
  await fs.mkdir(backupDir, { recursive: true });
  if ((await fs.lstat(backupDir)).isSymbolicLink()) throw new Error('备份目录不能是符号链接。');
  const suffix = `${Date.now()}-${randomUUID()}`;
  const backup = path.join(backupDir, `${path.basename(target)}.${suffix}.bak`);
  const backupHandle = await fs.open(backup, 'wx', 0o600);
  try { await backupHandle.writeFile(before); await backupHandle.sync(); } finally { await backupHandle.close(); }
  const temp = `${target}.${suffix}.tmp`;
  try {
    const handle = await fs.open(temp, 'wx', 0o600);
    try { await handle.writeFile(body, 'utf8'); await handle.sync(); } finally { await handle.close(); }
    await checkedPath(root, relative);
    if (digest(await fs.readFile(target)) !== expected) throw new Error('源文件在写回期间发生变化，已停止；备份已保留。');
    await fs.rename(temp, target);
  } finally { await fs.rm(temp, { force: true }); }
}

/** Keep the original Markdown intact; offsets address only the checkbox character. */
export function parseMarkdown(body: string, relativePath: string): MarkdownDocument {
  const tasks: MarkdownTask[] = [];
  const occurrences = new Map<string, number>();
  let fence: { character: string; length: number } | null = null;
  let offset = 0;
  let inFrontmatter = false;
  const lines = body.split(/(?<=\n)/);
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index].replace(/[\r\n]+$/, '');
    const visible = index === 0 ? line.replace(/^\uFEFF/, '') : line;
    if (index === 0 && visible === '---') inFrontmatter = true;
    else if (inFrontmatter && /^(---|\.\.\.)\s*$/.test(visible)) inFrontmatter = false;
    else if (!inFrontmatter) {
      const delimiter = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(visible);
      if (fence) {
        if (delimiter && delimiter[1][0] === fence.character && delimiter[1].length >= fence.length && !delimiter[2].trim()) fence = null;
      } else if (delimiter) fence = { character: delimiter[1][0], length: delimiter[1].length };
      else {
        const match = /^(\s*(?:[-+*]|\d+[.)])\s+\[)([ xX])(\]\s+)(.+)$/.exec(visible);
        if (match) {
          const title = match[4].trim();
          const occurrence = occurrences.get(title) ?? 0;
          occurrences.set(title, occurrence + 1);
          tasks.push({ key: `${digest(title)}:${occurrence}`, title, completed: match[2].toLowerCase() === 'x', line: index + 1, markerOffset: offset + match[1].length + (line.startsWith('\uFEFF') ? 1 : 0) });
        }
      }
    }
    offset += lines[index].length;
  }
  const title = path.basename(relativePath, path.extname(relativePath)).slice(0, 300) || '未命名笔记';
  return { relativePath, title, body, hash: digest(Buffer.from(body, 'utf8')), tasks };
}

async function safeRoot(root: string): Promise<string> {
  const resolved = path.resolve(root);
  const stat = await fs.lstat(resolved);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('请选择本机普通文件夹，不能使用符号链接。');
  return fs.realpath(resolved);
}
async function checkedPath(root: string, relative: string): Promise<string> {
  const full = path.resolve(root, relative);
  if (full === root || !full.startsWith(root + path.sep)) throw new Error('笔记路径超出选择的文件夹。');
  let current = root;
  for (const part of path.relative(root, full).split(path.sep)) {
    current = path.join(current, part);
    if ((await fs.lstat(current)).isSymbolicLink()) throw new Error('已跳过符号链接。');
  }
  return full;
}
async function readMarkdown(root: string, relative: string): Promise<MarkdownDocument> {
  const full = await checkedPath(root, relative);
  const stat = await fs.stat(full);
  if (!stat.isFile() || stat.size > MAX_BYTES) throw new Error('文件超过 100 KB 或不是普通文件。');
  const bytes = await fs.readFile(full);
  if (bytes.length > MAX_BYTES) throw new Error('文件超过 100 KB。');
  // ignoreBOM preserves the BOM in body, making round trips byte-exact.
  const body = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
  return parseMarkdown(body, relative);
}
export async function scanMarkdown(root: string): Promise<{ root: string; documents: MarkdownDocument[]; preview: ObsidianPreview }> {
  root = await safeRoot(root);
  const documents: MarkdownDocument[] = [];
  const warnings: string[] = [];
  let totalBytes = 0;
  let visited = 0;
  async function walk(directory: string, depth: number) {
    if (depth > 20) { warnings.push('已跳过超过 20 层的子文件夹。'); return; }
    const entries = await fs.readdir(directory, { withFileTypes: true });
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (++visited > 10_000) throw new Error('文件夹条目过多，请选择较小的子文件夹。');
      if (entry.name.startsWith('.') || entry.isSymbolicLink()) continue;
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) { await walk(full, depth + 1); continue; }
      if (!entry.isFile() || path.extname(entry.name).toLowerCase() !== '.md') continue;
      if (documents.length >= MAX_FILES) throw new Error('超过 500 份 Markdown，请选择较小的子文件夹。');
      const relative = path.relative(root, full);
      try {
        const document = await readMarkdown(root, relative);
        totalBytes += Buffer.byteLength(document.body);
        if (totalBytes > MAX_TOTAL_BYTES) throw new Error('所选 Markdown 总量超过 5 MB。');
        documents.push(document);
        if (documents.reduce((count, doc) => count + doc.tasks.length, 0) > 3000) throw new Error('超过 3000 条任务，请选择较小的子文件夹。');
      } catch (error) {
        if (totalBytes > MAX_TOTAL_BYTES || documents.reduce((count, doc) => count + doc.tasks.length, 0) > 3000) throw error;
        warnings.push(`${relative}：${error instanceof Error ? error.message : '无法读取'}`);
      }
    }
  }
  await walk(root, 0);
  return { root, documents, preview: { folderName: path.basename(root), files: documents.length, tasks: documents.reduce((sum, d) => sum + d.tasks.length, 0), warnings } };
}

export class ObsidianBridge {
  private queue: Promise<unknown> = Promise.resolve();
  constructor(private hooks: ObsidianHooks) {}
  private serial<T>(fn: () => Promise<T>) { const result = this.queue.then(fn); this.queue = result.catch(() => {}); return result; }
  private state(): ObsidianState {
    const state = this.hooks.loadState() ?? { version: 1, vaults: [] };
    if (!validState(state)) throw new Error('Obsidian 关联文件损坏，请保留文件并恢复备份。');
    return structuredClone(state);
  }
  async preview(root: string): Promise<ObsidianPreview> { return (await scanMarkdown(root)).preview; }
  getStatus(): { vaults: number; files: number; tasks: number } {
    const vaults = this.state().vaults.filter(v => v.scope === this.hooks.getScope());
    return { vaults: vaults.length, files: vaults.reduce((sum, v) => sum + v.files.length, 0), tasks: vaults.reduce((sum, v) => sum + v.files.reduce((count, f) => count + f.tasks.length, 0), 0) };
  }
  import(root: string): Promise<ObsidianResult> { return this.serial(async () => {
    const scope = this.hooks.getScope();
    const scanned = await scanMarkdown(root);
    const state = this.state();
    let vault = state.vaults.find(v => v.scope === scope && v.root === scanned.root);
    if (!vault) { vault = { root: scanned.root, scope, files: [] }; state.vaults.push(vault); }
    const result: ObsidianResult = { imported: 0, updated: 0, skipped: 0, conflicts: [], warnings: scanned.preview.warnings };
    for (const document of scanned.documents) {
      if (this.hooks.getScope() !== scope) throw new Error('账户已切换，请重新开始导入。');
      // A second import is deliberately non-destructive. Sync is a separate explicit action.
      let file = vault.files.find(f => f.relativePath === document.relativePath);
      if (file && file.hash !== document.hash) { result.skipped++; continue; }
      if (!file) {
        const note = await this.hooks.createItem({ kind: 'note', title: document.title, body: document.body });
        file = { relativePath: document.relativePath, hash: document.hash, noteId: note.id, noteBody: document.body, tasks: [] };
        vault.files.push(file);
        this.hooks.saveState(state);
        result.imported++;
      } else result.skipped++;
      for (const task of document.tasks) {
        if (file.tasks.some(t => t.key === task.key)) continue;
        if (task.title.length > 300) { result.warnings.push(`${document.relativePath}:${task.line} 任务标题超过 300 字，保留在笔记正文中。`); continue; }
        if (this.hooks.getScope() !== scope) throw new Error('账户已切换，请重新开始导入。');
        const metadata = parseTaskMetadata(task.title);
        const item = await this.hooks.createItem({ kind: 'task', title: task.title, body: `来源：${document.relativePath}`, dueDate: metadata.dueDate ?? null, tags: metadata.tags });
        if (task.completed) await this.hooks.updateItem(item.id, { completed: true });
        file.tasks.push({ key: task.key, id: item.id, baseCompleted: task.completed });
        this.hooks.saveState(state);
        result.imported++;
      }
    }
    return result;
  }); }
  /** Explicit completion-only writeback. Source edits always win by blocking writeback. */
  sync(): Promise<ObsidianResult> { return this.serial(async () => {
    const scope = this.hooks.getScope();
    const state = this.state();
    const result: ObsidianResult = { imported: 0, updated: 0, skipped: 0, conflicts: [], warnings: [] };
    for (const vault of state.vaults.filter(v => v.scope === scope)) {
      for (const file of vault.files) {
        if (this.hooks.getScope() !== scope) throw new Error('账户已切换，已停止写回。');
        const items = this.hooks.getItems();
        const changes = file.tasks.flatMap(link => {
          const item = items.find(i => i.id === link.id && !i.deletedAt && i.kind === 'task');
          return item && item.completed !== link.baseCompleted ? [{ link, completed: item.completed }] : [];
        });
        if (!changes.length) { result.skipped++; continue; }
        try {
          if (await safeRoot(vault.root) !== vault.root) throw new Error('文件夹位置发生变化。');
          const document = await readMarkdown(vault.root, file.relativePath);
          if (document.hash !== file.hash) throw new Error('源文件已变更，请先核对原文件；未覆盖。');
          let body = document.body;
          for (const change of changes) {
            const task = document.tasks.find(t => t.key === change.link.key);
            if (!task) throw new Error('源任务无法定位，未覆盖。');
            body = body.slice(0, task.markerOffset) + (change.completed ? 'x' : ' ') + body.slice(task.markerOffset + 1);
          }
          if (this.hooks.getScope() !== scope) throw new Error('账户已切换，已停止写回。');
          await replaceWithBackup(vault.root, file.relativePath, file.hash, body);
          file.hash = digest(Buffer.from(body, 'utf8'));
          for (const change of changes) change.link.baseCompleted = change.completed;
          this.hooks.saveState(state);
          result.updated += changes.length;
        } catch (error) { result.conflicts.push(`${file.relativePath}：${error instanceof Error ? error.message : '写回失败，原文件已保留。'}`); }
      }
    }
    return result;
  }); }
}
