import { afterEach, describe, expect, it } from 'vitest';
import { AppService, compareItems } from '../src/main/service';
import type { CloudAdapter } from '../src/main/cloud';
import type { Database, Item, RuntimeHooks } from '../src/shared/types';
const services: AppService[] = [];
afterEach(() => { services.splice(0).forEach(service => service.dispose()); });
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
  it('queues edits behind sync without clearing new work', async () => {
    const env = setup(); const service = env.make(); await service.initialize(); await login(service); const item = await service.createItem({ kind: 'task', title: 'before' });
    let release!: () => void; env.setGate(new Promise<void>(resolve => { release = resolve; })); const sync = service.syncNow(); const edit = service.updateItem(item.id, { title: 'after' }); release(); await sync; await edit;
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
