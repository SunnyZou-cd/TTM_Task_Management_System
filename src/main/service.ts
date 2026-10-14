import { randomUUID } from 'node:crypto';
import type { AppSnapshot, CloudConfig, CreateItemInput, Database, Item, ItemPatch, RuntimeHooks, SyncState } from '../shared/types';
import { createCloud, validateConfig, type CloudAdapter } from './cloud';

type Stored = Database & { projectCaches?: Record<string, { items: Item[]; dirtyIds: string[] }> };
function validDate(value: string | null) { return value === null || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value); }
export function compareItems(a: Item, b: Item): number {
  const time = Date.parse(a.updatedAt) - Date.parse(b.updatedAt);
  return time || (a.deviceId === b.deviceId ? 0 : a.deviceId > b.deviceId ? 1 : -1);
}
function validItem(value: unknown): value is Item {
  const i = value as Item;
  return !!i && typeof i.id === 'string' && (i.ownerId === null || typeof i.ownerId === 'string') && ['task', 'note'].includes(i.kind) && typeof i.title === 'string' && typeof i.body === 'string' && validDate(i.dueDate) && typeof i.completed === 'boolean' && ['sage','yellow','blue','rose'].includes(i.color) && typeof i.deviceId === 'string' && Number.isFinite(Date.parse(i.createdAt)) && Number.isFinite(Date.parse(i.updatedAt)) && (i.deletedAt === null || Number.isFinite(Date.parse(i.deletedAt)));
}
function validateDatabase(d: Stored) {
  if (!d || d.version !== 1 || typeof d.deviceId !== 'string' || !Array.isArray(d.items) || !d.items.every(validItem) || !Array.isArray(d.dirtyIds) || !d.dirtyIds.every(x => typeof x === 'string') || !d.pins || typeof d.pins !== 'object' || !Object.values(d.pins).every(x => Array.isArray(x) && x.every(y => typeof y === 'string')) || !(d.activeOwnerId === null || typeof d.activeOwnerId === 'string')) throw new Error('本地数据损坏，请保留数据文件并恢复备份');
  if (Array.isArray(d.pins) || !(d.config === null || (typeof d.config === 'object' && typeof d.config.url === 'string' && typeof d.config.publicKey === 'string')) || !(d.lastSyncedAt === null || Number.isFinite(Date.parse(d.lastSyncedAt)))) throw new Error('本地配置损坏');
  if (d.config) validateConfig(d.config);
  for (const cache of Object.values(d.projectCaches ?? {})) if (!Array.isArray(cache.items) || !cache.items.every(validItem) || !Array.isArray(cache.dirtyIds) || !cache.dirtyIds.every(x => typeof x === 'string')) throw new Error('本地项目缓存损坏');
}
export class AppService {
  private db: Stored = { version: 1, deviceId: randomUUID(), items: [], dirtyIds: [], pins: {}, config: null, activeOwnerId: null, lastSyncedAt: null };
  private cloud: CloudAdapter | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  private timer: ReturnType<typeof setInterval> | null = null;
  private sync: SyncState = { configured: false, status: 'unconfigured', email: null, pending: 0, lastSyncedAt: null, error: null };
  constructor(private hooks: RuntimeHooks, private factory: (config: CloudConfig, hooks: RuntimeHooks) => CloudAdapter = createCloud) {}
  private serial<T>(fn: () => Promise<T>): Promise<T> { const result = this.queue.then(fn); this.queue = result.catch(() => {}); return result; }
  private commit(next: Stored) { this.hooks.saveData(next); this.db = next; }
  private scope() { return this.db.activeOwnerId ? `${this.db.config?.url ?? 'local'}:${this.db.activeOwnerId}` : 'local:guest'; }
  private publish() { const snapshot = this.getSnapshot(); this.hooks.broadcast(snapshot); this.hooks.pinsChanged(snapshot.pinnedIds); }
  getSnapshot(): AppSnapshot {
    const items = this.db.items.filter(i => i.ownerId === this.db.activeOwnerId && !i.deletedAt);
    return structuredClone({ items, pinnedIds: (this.db.pins[this.scope()] ?? []).filter(id => items.some(i => i.id === id)), sync: { ...this.sync, pending: this.db.items.filter(i => i.ownerId === this.db.activeOwnerId && this.db.dirtyIds.includes(i.id)).length, lastSyncedAt: this.db.lastSyncedAt }, desktop: true });
  }
  async initialize() { return this.serial(async () => {
    const data = this.hooks.loadData(); if (data) { validateDatabase(data); this.db = structuredClone(data); } else this.commit(this.db);
    this.sync.configured = !!this.db.config;
    if (this.db.config) {
      this.cloud = this.factory(this.db.config, this.hooks);
      try { const user = await this.cloud.identity(); this.commit({ ...this.db, activeOwnerId: user?.id ?? null }); this.sync.email = user?.email ?? null; this.sync.status = user ? 'offline' : 'signed-out'; }
      catch { this.sync.status = this.db.activeOwnerId ? 'offline' : 'signed-out'; this.sync.error = '暂时无法验证云端会话'; }
    }
    this.publish(); this.timer = setInterval(() => { if (this.db.activeOwnerId) void this.syncNow().catch(() => {}); }, 30000); this.timer.unref?.();
    if (this.db.activeOwnerId) void this.syncNow().catch(() => {});
  }); }
  dispose() { if (this.timer) clearInterval(this.timer); }
  private find(id: string) { const item = this.db.items.find(i => i.id === id && i.ownerId === this.db.activeOwnerId && !i.deletedAt); if (!item) throw new Error('条目不存在'); return item; }
  private timestamp(previous?: string) { return new Date(Math.max(Date.now(), previous ? Date.parse(previous) + 1 : 0)).toISOString(); }
  private saveItem(item: Item) { const next = structuredClone(this.db); const index = next.items.findIndex(i => i.id === item.id && i.ownerId === item.ownerId); if (index < 0) next.items.push(item); else next.items[index] = item; if (!next.dirtyIds.includes(item.id)) next.dirtyIds.push(item.id); this.commit(next); if (this.db.activeOwnerId) this.sync.status = 'offline'; this.publish(); }
  createItem(input: CreateItemInput) { return this.serial(async () => { if (!input || typeof input !== 'object' || typeof input.title !== 'string') throw new Error('条目内容无效'); const now = this.timestamp(); const item: Item = { id: randomUUID(), ownerId: this.db.activeOwnerId, kind: input.kind, title: input.title.trim(), body: input.body ?? '', dueDate: input.dueDate ?? null, color: input.color ?? 'sage', completed: false, createdAt: now, updatedAt: now, deletedAt: null, deviceId: this.db.deviceId }; if (!validItem(item) || !item.title || item.title.length > 300 || item.body.length > 100000) throw new Error('条目内容无效'); this.saveItem(item); return structuredClone(item); }); }
  updateItem(id: string, patch: ItemPatch) { return this.serial(async () => { if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new Error('更新字段无效'); const old = this.find(id); const allowed = ['title','body','dueDate','completed','color']; if (Object.keys(patch).some(k => !allowed.includes(k))) throw new Error('更新字段无效'); const item = { ...old, ...patch, updatedAt: this.timestamp(old.updatedAt), deviceId: this.db.deviceId }; if (!validItem(item) || !item.title.trim() || item.title.length > 300 || item.body.length > 100000) throw new Error('条目内容无效'); this.saveItem(item); return structuredClone(item); }); }
  deleteItem(id: string) { return this.serial(async () => { const old = this.find(id); const now = this.timestamp(old.updatedAt); this.saveItem({ ...old, deletedAt: now, updatedAt: now, deviceId: this.db.deviceId }); }); }
  pinItem(id: string) { return this.serial(async () => { this.find(id); const next = structuredClone(this.db); next.pins[this.scope()] = [...new Set([...(next.pins[this.scope()] ?? []), id])]; this.commit(next); this.publish(); }); }
  unpinItem(id: string) { return this.serial(async () => { const next = structuredClone(this.db); next.pins[this.scope()] = (next.pins[this.scope()] ?? []).filter(x => x !== id); this.commit(next); this.publish(); }); }
  async getCloudConfig() { return structuredClone(this.db.config); }
  setCloudConfig(config: CloudConfig) { return this.serial(async () => {
    const valid = validateConfig(config); const next = structuredClone(this.db); const oldUrl = next.config?.url ?? 'local';
    next.projectCaches ??= {}; next.projectCaches[oldUrl] = { items: next.items.filter(i => i.ownerId !== null), dirtyIds: next.dirtyIds.filter(id => next.items.some(i => i.id === id && i.ownerId !== null)) };
    const guest = next.items.filter(i => i.ownerId === null); const guestDirty = next.dirtyIds.filter(id => guest.some(i => i.id === id)); const cache = next.projectCaches[valid.url] ?? { items: [], dirtyIds: [] };
    next.items = [...guest, ...cache.items]; next.dirtyIds = [...guestDirty, ...cache.dirtyIds]; next.config = valid; next.activeOwnerId = null; next.lastSyncedAt = null;
    await this.hooks.writeSecret(null); this.commit(next); this.cloud = this.factory(valid, this.hooks); this.sync = { configured: true, status: 'signed-out', email: null, pending: 0, lastSyncedAt: null, error: null }; this.publish();
  }); }
  sendOtp(email: string) { return this.serial(async () => { if (!this.cloud) throw new Error('请先配置云端'); if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('邮箱格式无效'); await this.cloud.sendOtp(email.trim()); }); }
  verifyOtp(email: string, token: string) { return this.serial(async () => {
    if (!this.cloud) throw new Error('请先配置云端'); if (!/^\d{6,10}$/.test(token)) throw new Error('请输入邮件中的数字验证码');
    const user = await this.cloud.verifyOtp(email.trim(), token); try { this.commit({ ...this.db, activeOwnerId: user.id, lastSyncedAt: null }); } catch (error) { await this.cloud.signOut(); await this.hooks.writeSecret(null); throw error; }
    this.sync.email = user.email; this.sync.status = 'offline'; this.sync.error = null; this.publish(); await this.runSync().catch(() => {});
  }); }
  signOut() { return this.serial(async () => { await this.hooks.writeSecret(null); this.commit({ ...this.db, activeOwnerId: null, lastSyncedAt: null }); if (this.db.config) this.cloud = this.factory(this.db.config, this.hooks); this.sync.email = null; this.sync.status = this.db.config ? 'signed-out' : 'unconfigured'; this.sync.error = null; this.publish(); }); }
  syncNow() { return this.serial(() => this.runSync()); }
  private async runSync() {
    if (!this.cloud || !this.db.activeOwnerId) return;
    this.sync.status = 'syncing'; this.sync.error = null; this.publish();
    try {
      const owner = this.db.activeOwnerId; const identity = await this.cloud.identity(); if (!identity || identity.id !== owner) throw new Error('云端登录已失效，请退出后重新登录');
      const outgoing = this.db.items.filter(i => i.ownerId === owner && this.db.dirtyIds.includes(i.id));
      await this.cloud.upload(outgoing); const incoming = await this.cloud.download(owner);
      if (!incoming.every(i => validItem(i) && i.ownerId === owner)) throw new Error('云端返回的数据无效');
      const next = structuredClone(this.db); for (const item of incoming) { const index = next.items.findIndex(i => i.id === item.id && i.ownerId === owner); if (index < 0) next.items.push(item); else if (compareItems(item, next.items[index]) >= 0) next.items[index] = item; }
      next.dirtyIds = next.dirtyIds.filter(id => !outgoing.some(i => i.id === id)); next.lastSyncedAt = new Date().toISOString(); this.commit(next); this.sync.status = 'synced'; this.sync.email = identity.email; this.publish();
    } catch { this.sync.status = 'offline'; this.sync.error = '云端同步未完成。更改已保留在本机，请检查网络、登录和项目配置后重试。'; this.publish(); throw new Error(this.sync.error); }
  }
  exportData() { return this.serial(async () => this.hooks.exportJson(JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), items: this.getSnapshot().items }, null, 2))); }
}
