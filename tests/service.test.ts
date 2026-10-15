import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppService, compareItems } from '../src/main/service';
import type { CloudAdapter } from '../src/main/cloud';
import type { Database, Item, RuntimeHooks } from '../src/shared/types';
const services: AppService[] = [];
afterEach(() => { services.splice(0).forEach(service => service.dispose()); vi.useRealTimers(); });
function setup() {
  let stored: Database | null = null; let failSave = false; let online = true; let user = 'account-a'; let authenticated = false;
  const server = new Map<string, Item>(); let gate: Promise<void> | null = null;
  const hooks: RuntimeHooks = { loadData: () => structuredClone(stored), saveData: d => { if (failSave) throw new Error('disk full'); stored = structuredClone(d); }, readSecret: async () => null, writeSecret: async () => {}, broadcast: () => {}, pinsChanged: () => {}, exportJson: async () => true };
  const cloud: CloudAdapter = {
    identity: async () => { if (!online) throw new Error('offline'); return authenticated ? { id: user, email: 'user@example.com' } : null; },
    sendOtp: async () => {}, verifyOtp: async () => { authenticated = true; return { id: user, email: 'user@example.com' }; }, signOut: async () => { authenticated = false; },
    upload: async items => { if (gate) await gate; if (!online) throw new Error('offline'); for (const item of items) { const old = server.get(item.id); if (!old || compareItems(item, old) > 0) server.set(item.id, structuredClone(item)); } },
    download: async owner => { if (!online) throw new Error('offline'); return [...server.values()].filter(i => i.ownerId === owner).map(i => structuredClone(i)); },
  };
  const make = () => { const service = new AppService(hooks, () => cloud); services.push(service); return service; };
  return { make, server, hooks, setFail: (v: boolean) => { failSave = v; }, setOnline: (v: boolean) => { online = v; }, setUser: (v: string) => { user = v; }, setGate: (v: Promise<void> | null) => { gate = v; } };
}
const config = { url: 'https://abc.supabase.co', publicKey: 'sb_publishable_test' };
async function login(service: AppService) { await service.setCloudConfig(config); await service.verifyOtp('user@example.com', '123456'); }
describe('durable isolated application state', () => {
  it('rejects impossible calendar dates and malformed patches', async () => {
    const env = setup(); const service = env.make(); await service.initialize();
    await expect(service.createItem({ kind: 'task', title: 'bad date', dueDate: '2026-02-30' })).rejects.toThrow('无效');
    const item = await service.createItem({ kind: 'note', title: 'valid' });
    await expect(service.updateItem(item.id, null as unknown as {})).rejects.toThrow('无效');
  });
  it('uses deterministic device IDs for equal-time conflicts', () => {
    const base = { updatedAt: '2026-10-14T12:00:00.000Z', deviceId: 'a' } as Item;
    expect(compareItems({ ...base, deviceId: 'b' }, base)).toBeGreaterThan(0);
    expect(compareItems(base, { ...base, deviceId: 'b' })).toBeLessThan(0);
  });
  it('does not publish or retain a mutation when persistence fails', async () => {
    const env = setup(); const service = env.make(); await service.initialize(); env.setFail(true);
    await expect(service.createItem({ kind: 'task', title: 'lost' })).rejects.toThrow('disk full'); expect(service.getSnapshot().items).toHaveLength(0);
  });
  it('retains offline changes across restart and syncs after recovery', async () => {
    const env = setup(); const service = env.make(); await service.initialize(); await login(service); env.setOnline(false);
    const item = await service.createItem({ kind: 'task', title: 'offline' }); await expect(service.syncNow()).rejects.toThrow(); service.dispose();
    const restarted = env.make(); await restarted.initialize(); expect(restarted.getSnapshot().items[0].id).toBe(item.id); expect(restarted.getSnapshot().sync.pending).toBe(1);
    env.setOnline(true); await restarted.syncNow(); expect(env.server.has(item.id)).toBe(true); expect(restarted.getSnapshot().sync.status).toBe('synced');
  });
  it('keeps guest content out of accounts and isolates account switching', async () => {
    const env = setup(); const service = env.make(); await service.initialize(); const guest = await service.createItem({ kind: 'note', title: 'guest' }); await login(service);
    expect(service.getSnapshot().items).toHaveLength(0); expect(env.server.has(guest.id)).toBe(false);
    const account = await service.createItem({ kind: 'note', title: 'private' }); await service.syncNow(); await service.signOut(); expect(service.getSnapshot().items.map(i => i.id)).toEqual([guest.id]);
    env.setUser('account-b'); await service.verifyOtp('user@example.com', '123456'); expect(service.getSnapshot().items).toHaveLength(0); expect(service.getSnapshot().pinnedIds).not.toContain(account.id);
  });
  it('does not migrate pending account data to another project', async () => {
    const env = setup(); const service = env.make(); await service.initialize(); await login(service); const item = await service.createItem({ kind: 'task', title: 'project-a' });
    await service.setCloudConfig({ ...config, url: 'https://xyz.supabase.co' }); await service.verifyOtp('user@example.com', '123456'); expect(service.getSnapshot().items).toHaveLength(0); expect(env.server.has(item.id)).toBe(false);
    await service.setCloudConfig(config); await service.verifyOtp('user@example.com', '123456'); expect(service.getSnapshot().items[0].id).toBe(item.id);
  });
  it('allows edits during sync without clearing new work', async () => {
    const env = setup(); const service = env.make(); await service.initialize(); await login(service); const item = await service.createItem({ kind: 'task', title: 'before' });
    let release!: () => void; env.setGate(new Promise<void>(resolve => { release = resolve; })); const sync = service.syncNow(); await service.updateItem(item.id, { title: 'after' }); expect(service.getSnapshot().items[0].title).toBe('after'); release(); await sync;
    expect(service.getSnapshot().items[0].title).toBe('after'); expect(service.getSnapshot().sync.pending).toBe(1); expect(env.server.get(item.id)?.title).toBe('before');
  });
  it('honors a newer server tombstone instead of reviving it', async () => {
    const env = setup(); const service = env.make(); await service.initialize(); await login(service); const item = await service.createItem({ kind: 'task', title: 'old edit' });
    const future = new Date(Date.now() + 10000).toISOString(); env.server.set(item.id, { ...item, updatedAt: future, deletedAt: future }); await service.syncNow(); expect(service.getSnapshot().items).toHaveLength(0); expect(service.getSnapshot().sync.pending).toBe(0);
  });
  it('rejects corrupt storage rather than silently replacing it', async () => {
    const env = setup(); env.hooks.loadData = () => ({ version: 1, items: [{ title: 'broken' }] } as unknown as Database); await expect(env.make().initialize()).rejects.toThrow('损坏');
  });
});

describe('task labels, archives, and fixed schedules', () => {
  function freeze() { vi.useFakeTimers(); vi.setSystemTime(new Date(2026, 9, 14, 10)); }
  it('normalizes labels and rejects malformed metadata', async () => {
    const env = setup(), service = env.make(); await service.initialize();
    const task = await service.createItem({ kind: 'task', title: 'label', tags: ['  研究 ', '研究'], dueDate: '2026-10-14', dueTime: '12:00' }); expect(task.tags).toEqual(['研究']);
    await expect(service.updateItem(task.id, { dueTime: '25:00' })).rejects.toThrow('无效');
    await expect(service.updateItem(task.id, { tags: [''] })).rejects.toThrow('无效');
    await expect(service.createItem({ kind: 'task', title: 'bad', recurrence: { frequency: 'daily', interval: 1 } })).rejects.toThrow('无效');
    await expect(service.createItem({ kind: 'note', title: 'bad', dueDate: '2026-10-14', recurrence: { frequency: 'daily', interval: 1 } })).rejects.toThrow('无效');
  });
  it('keeps completed items available while removing their desktop pins', async () => {
    const env = setup(), service = env.make(); await service.initialize();
    const item = await service.createItem({ kind: 'task', title: 'done' }); await service.pinItem(item.id); await service.updateItem(item.id, { completed: true });
    expect(service.getSnapshot().items[0].completed).toBe(true); expect(service.getSnapshot().pinnedIds).not.toContain(item.id);
    await service.updateItem(item.id, { completed: false }); expect(service.getSnapshot().pinnedIds).toContain(item.id);
  });
  it('generates scheduled instances regardless of completion, and repeated calls do not duplicate', async () => {
    freeze(); const env = setup(), service = env.make(); await service.initialize();
    const root = await service.createItem({ kind: 'task', title: 'daily', dueDate: '2026-10-13', dueTime: '09:00', tags: ['routine'], recurrence: { frequency: 'daily', interval: 1 } });
    expect(service.getSnapshot().items).toHaveLength(2); const child = service.getSnapshot().items.find(item => item.seriesId === root.id)!;
    expect(child).toMatchObject({ dueDate: '2026-10-14', recurrence: null, recurrenceIndex: 1, tags: ['routine'], completed: false });
    await service.updateItem(root.id, { completed: true }); await service.updateItem(root.id, { completed: true }); expect(await service.materializeRecurring()).toBe(0);
    vi.setSystemTime(new Date(2026, 9, 15, 10)); expect(await service.materializeRecurring()).toBe(1); expect(service.getSnapshot().items).toHaveLength(3);
  });
  it('commits a completion and its scheduled children atomically and rolls all back on save failure', async () => {
    freeze(); const env = setup(), service = env.make(); await service.initialize();
    const root = await service.createItem({ kind: 'task', title: 'daily', dueDate: '2026-10-14', recurrence: { frequency: 'daily', interval: 1 } });
    vi.setSystemTime(new Date(2026, 9, 15, 10)); env.setFail(true);
    await expect(service.updateItem(root.id, { completed: true })).rejects.toThrow('disk full'); expect(service.getSnapshot().items).toHaveLength(1); expect(service.getSnapshot().items[0].completed).toBe(false);
    env.setFail(false); let saves = 0; const save = env.hooks.saveData; env.hooks.saveData = database => { saves++; save(database); };
    await service.updateItem(root.id, { completed: true }); expect(saves).toBe(1); expect(service.getSnapshot().items).toHaveLength(2);
  });
  it('stops future generation when the root is disabled and never revives a deleted occurrence', async () => {
    freeze(); const env = setup(), service = env.make(); await service.initialize();
    const root = await service.createItem({ kind: 'task', title: 'daily', dueDate: '2026-10-13', recurrence: { frequency: 'daily', interval: 1 } });
    const child = service.getSnapshot().items.find(item => item.seriesId)!; await service.deleteItem(child.id); expect(await service.materializeRecurring()).toBe(0);
    await expect(service.updateItem(child.id, { recurrence: { frequency: 'daily', interval: 1 } })).rejects.toThrow();
    await service.updateItem(root.id, { recurrence: null }); vi.setSystemTime(new Date(2026, 9, 20)); expect(await service.materializeRecurring()).toBe(0); expect(service.getSnapshot().items).toHaveLength(1);
  });
  it('accepts old v1 records, enriches only explicit imported metadata, and preserves explicit dates', async () => {
    freeze(); const env = setup(), service = env.make(); await service.initialize();
    const imported = await service.createItem({ kind: 'task', title: 'Lab 📅 2026-08-30 #physics [[Projects/Lab]]', body: '来源：Daily.md' });
    const explicit = await service.createItem({ kind: 'task', title: 'Keep 📅 2026-08-30', body: '来源：Daily.md', dueDate: '2026-10-15' });
    const ordinary = await service.createItem({ kind: 'task', title: 'Plain 📅 2026-08-30 #physics' });
    const oldLoad = env.hooks.loadData; env.hooks.loadData = () => { const data = oldLoad()!; for (const item of data.items) { delete item.tags; delete item.dueTime; delete item.recurrence; } return data; };
    const restarted = env.make(); await restarted.initialize();
    expect(restarted.getSnapshot().items.find(item => item.id === imported.id)).toMatchObject({ dueDate: '2026-08-30', tags: ['physics', 'Lab'], dueTime: null });
    expect(restarted.getSnapshot().items.find(item => item.id === explicit.id)?.dueDate).toBe('2026-10-15');
    expect(restarted.getSnapshot().items.find(item => item.id === ordinary.id)).toMatchObject({ dueDate: null, tags: [] });
    // Once migrated, intentional metadata removal must survive another restart.
    env.hooks.loadData = oldLoad;
    await restarted.updateItem(imported.id, { dueDate: null, tags: [] });
    const again = env.make(); await again.initialize();
    expect(again.getSnapshot().items.find(item => item.id === imported.id)).toMatchObject({ dueDate: null, tags: [] });
  });
  it('uses identical legal UUID occurrence IDs after independent offline device generation', async () => {
    freeze(); const env = setup(), first = env.make(); await first.initialize();
    const root = await first.createItem({ kind: 'task', title: 'same series', dueDate: '2026-10-14', recurrence: { frequency: 'daily', interval: 1 } });
    const seed = env.hooks.loadData()!; env.hooks.loadData = () => ({ ...structuredClone(seed), deviceId: 'second-device' }); const second = env.make(); await second.initialize();
    vi.setSystemTime(new Date(2026, 9, 15, 10)); await first.materializeRecurring(); await second.materializeRecurring();
    const a = first.getSnapshot().items.find(item => item.seriesId === root.id)!, b = second.getSnapshot().items.find(item => item.seriesId === root.id)!;
    expect(a.id).toBe(b.id); expect(a.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/); expect(a.deviceId).not.toBe(b.deviceId);
  });
  it('rejects malformed newly present optional fields in stored data', async () => {
    const env = setup(), service = env.make(); await service.initialize(); await service.createItem({ kind: 'task', title: 'valid' });
    const oldLoad = env.hooks.loadData; env.hooks.loadData = () => { const data = oldLoad()!; data.items[0].tags = 'bad' as unknown as string[]; return data; };
    await expect(env.make().initialize()).rejects.toThrow('损坏');
  });
});
