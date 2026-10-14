import fs from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { afterEach, describe, expect, it } from 'vitest';
import { ObsidianBridge, parseMarkdown, scanMarkdown, type ObsidianState } from '../src/main/obsidian';
import type { Item } from '../src/shared/types';

const directories: string[] = [];
async function vault() {
  const root = await fs.mkdtemp(path.join(process.cwd(), 'work', 'obsidian-test-'));
  directories.push(root);
  return root;
}
afterEach(async () => { for (const directory of directories.splice(0)) await fs.rm(directory, { recursive: true, force: true }); });
function setup() {
  let state: ObsidianState | null = null;
  let scope = 'guest';
  const items: Item[] = [];
  const bridge = new ObsidianBridge({
    loadState: () => structuredClone(state), saveState: value => { state = structuredClone(value); },
    getScope: () => scope, getItems: () => items.filter(i => i.ownerId === (scope === 'guest' ? null : scope)),
    createItem: async input => {
      const item: Item = { ...input, body: input.body ?? '', color: 'sage', completed: false, id: randomUUID(), ownerId: scope === 'guest' ? null : scope, dueDate: null, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), deletedAt: null, deviceId: 'test' };
      items.push(item); return item;
    },
    updateItem: async (id, patch) => { const item = items.find(i => i.id === id)!; Object.assign(item, patch); return item; },
  });
  return { bridge, items, state: () => state!, setScope: (value: string) => { scope = value; } };
}

describe('Obsidian import safety', () => {
  it('preserves full Unicode Markdown, BOM and CRLF while excluding frontmatter and fenced code', () => {
    const body = '\uFEFF---\r\n- [ ] not a task\r\n---\r\n# 学习\r\n```md\r\n- [ ] sample\r\n```\r\n  - [X] 完成阅读\r\n1. [ ] 写作\r\n';
    const parsed = parseMarkdown(body, '学习.md');
    expect(parsed.body).toBe(body);
    expect(parsed.tasks.map(t => [t.title, t.completed])).toEqual([['完成阅读', true], ['写作', false]]);
    expect(parsed.tasks.map(t => body[t.markerOffset])).toEqual(['X', ' ']);
  });
  it('skips hidden metadata, oversized and non-UTF8 files', async () => {
    const root = await vault();
    await fs.mkdir(path.join(root, '.obsidian'));
    await fs.writeFile(path.join(root, '.obsidian', 'private.md'), '- [ ] hidden');
    await fs.writeFile(path.join(root, 'large.md'), 'a'.repeat(100_001));
    await fs.writeFile(path.join(root, 'bad.md'), Buffer.from([0xff, 0xfe, 0x00]));
    await fs.writeFile(path.join(root, 'good.md'), '# 笔记\n- [ ] task');
    const result = await scanMarkdown(root);
    expect(result.preview.files).toBe(1);
    expect(result.preview.tasks).toBe(1);
    expect(result.preview.warnings).toHaveLength(2);
  });
  it('imports each checkbox and complete source once, with account-isolated local links', async () => {
    const root = await vault();
    const source = '# Notes\n- [x] Same\n- [ ] Same\n\nKeep this paragraph.\n';
    await fs.writeFile(path.join(root, 'notes.md'), source);
    const env = setup();
    expect((await env.bridge.import(root)).imported).toBe(3);
    expect((await env.bridge.import(root)).imported).toBe(0);
    expect(env.items.map(i => i.completed)).toEqual([false, true, false]);
    expect(env.items[0].body).toBe(source);
    expect(JSON.stringify(env.items)).not.toContain(root.replaceAll('\\', '\\\\'));
    env.setScope('account-two');
    expect((await env.bridge.import(root)).imported).toBe(3);
    expect(env.state().vaults).toHaveLength(2);
    expect(await fs.readFile(path.join(root, 'notes.md'), 'utf8')).toBe(source);
  });
  it('writes only checkbox characters with a byte-exact backup and preserves BOM / CRLF', async () => {
    const root = await vault();
    const source = '\uFEFF# 学习\r\n- [ ] 阅读\r\n- [X] 写作\r\n正文不变。\r\n';
    const file = path.join(root, '中文.md');
    await fs.writeFile(file, source);
    const env = setup();
    await env.bridge.import(root);
    env.items.find(i => i.title === '阅读')!.completed = true;
    env.items.find(i => i.title === '写作')!.completed = false;
    expect((await env.bridge.sync()).updated).toBe(2);
    expect(await fs.readFile(file, 'utf8')).toBe(source.replace('[ ] 阅读', '[x] 阅读').replace('[X] 写作', '[ ] 写作'));
    const backups = await fs.readdir(path.join(root, '.pinboard-backups'));
    expect(backups).toHaveLength(1);
    expect(await fs.readFile(path.join(root, '.pinboard-backups', backups[0]), 'utf8')).toBe(source);
    expect((await env.bridge.sync()).updated).toBe(0);
    expect((await scanMarkdown(root)).preview.files).toBe(1);
  });
  it('refuses source edits and missing source without overwriting or resurrecting deleted tasks', async () => {
    const root = await vault();
    const file = path.join(root, 'notes.md');
    await fs.writeFile(file, '- [ ] Task\n');
    const env = setup(); await env.bridge.import(root);
    env.items.find(i => i.kind === 'task')!.completed = true;
    await fs.writeFile(file, '- [ ] Task\nUser edit\n');
    const result = await env.bridge.sync();
    expect(result.conflicts).toHaveLength(1);
    expect(await fs.readFile(file, 'utf8')).toBe('- [ ] Task\nUser edit\n');
    await fs.unlink(file);
    expect((await env.bridge.sync()).conflicts).toHaveLength(1);
    expect(await fs.readdir(root)).toHaveLength(0);
  });
  it('aborts writeback if the backup location is unusable', async () => {
    const root = await vault(); const file = path.join(root, 'notes.md');
    await fs.writeFile(file, '- [ ] Task\n');
    const env = setup(); await env.bridge.import(root);
    env.items.find(i => i.kind === 'task')!.completed = true;
    await fs.writeFile(path.join(root, '.pinboard-backups'), 'not a folder');
    expect((await env.bridge.sync()).conflicts).toHaveLength(1);
    expect(await fs.readFile(file, 'utf8')).toBe('- [ ] Task\n');
  });
  it('does not traverse junctions or write another workspace’s source', async () => {
    const root = await vault(); const outside = await vault();
    await fs.writeFile(path.join(root, 'local.md'), '- [ ] Local\n');
    await fs.writeFile(path.join(outside, 'private.md'), '- [ ] Outside\n');
    await fs.symlink(outside, path.join(root, 'linked'), 'junction');
    expect((await scanMarkdown(root)).preview.files).toBe(1);
    const env = setup(); await env.bridge.import(root);
    env.items.find(i => i.kind === 'task')!.completed = true;
    env.setScope('other-account');
    expect(env.bridge.getStatus()).toEqual({ vaults: 0, files: 0, tasks: 0 });
    expect((await env.bridge.sync()).updated).toBe(0);
    expect(await fs.readFile(path.join(root, 'local.md'), 'utf8')).toBe('- [ ] Local\n');
  });
});
