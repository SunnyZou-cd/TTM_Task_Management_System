import { createHash, randomUUID } from 'node:crypto';
import type { AppSnapshot, CloudConfig, CreateItemInput, Database, Item, ItemPatch, RuntimeHooks, SyncState } from '../shared/types';
import { createCloud, validateConfig, type CloudAdapter } from './cloud';
import { dueOccurrences, parseTaskMetadata, validCalendarDate, validDueTime, validRecurrence, validTags } from '../shared/task-rules';

type Stored = Database & { projectCaches?: Record<string, { items: Item[]; dirtyIds: string[] }> };
function occurrenceId(seriesId: string, dueDate: string) {
  const bytes = createHash('sha256').update(JSON.stringify(['pinboard-occurrence-v1', seriesId, dueDate])).digest().subarray(0, 16);
  bytes[6] = (bytes[6] & 15) | 80; bytes[8] = (bytes[8] & 63) | 128;
  const hex = bytes.toString('hex'); return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
export function compareItems(a: Item, b: Item): number {
  const time = Date.parse(a.updatedAt) - Date.parse(b.updatedAt);
  return time || (a.deviceId === b.deviceId ? 0 : a.deviceId > b.deviceId ? 1 : -1);
}
function validItem(value: unknown): value is Item {
  const i = value as Item;
  return !!i && typeof i.id === 'string' && (i.ownerId === null || typeof i.ownerId === 'string') && ['task', 'note'].includes(i.kind) && typeof i.title === 'string' && typeof i.body === 'string' && validCalendarDate(i.dueDate) && typeof i.completed === 'boolean' && ['sage','yellow','blue','rose'].includes(i.color) && typeof i.deviceId === 'string' && Number.isFinite(Date.parse(i.createdAt)) && Number.isFinite(Date.parse(i.updatedAt)) && (i.deletedAt === null || Number.isFinite(Date.parse(i.deletedAt)))
    && (i.tags === undefined || validTags(i.tags)) && (i.dueTime === undefined || validDueTime(i.dueTime)) && (i.recurrence === undefined || validRecurrence(i.recurrence))
    && (!i.dueTime || !!i.dueDate) && (!i.recurrence || (i.kind === 'task' && !!i.dueDate && i.seriesId === undefined))
    && ((i.seriesId === undefined && i.recurrenceIndex === undefined) || (typeof i.seriesId === 'string' && !!i.seriesId && i.seriesId !== i.id && i.kind === 'task' && Number.isSafeInteger(i.recurrenceIndex) && i.recurrenceIndex! >= 1));
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
  private syncFlight: Promise<void> | null = null;
  private sessionEpoch = 0;
  private disposed = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  private sync: SyncState = { configured: false, status: 'unconfigured', email: null, pending: 0, lastSyncedAt: null, error: null };
  constructor(private hooks: RuntimeHooks, private factory: (config: CloudConfig, hooks: RuntimeHooks) => CloudAdapter = createCloud) {}
  private serial<T>(fn: () => Promise<T>): Promise<T> { const result = this.queue.then(fn); this.queue = result.catch(() => {}); return result; }
  private commit(next: Stored) { this.hooks.saveData(next); this.db = next; }
  getWorkspaceKey() { return this.scope(); }
  private scope() { return this.db.activeOwnerId ? `${this.db.config?.url ?? 'local'}:${this.db.activeOwnerId}` : 'local:guest'; }
  private publish() { const snapshot = this.getSnapshot(); this.hooks.broadcast(snapshot); this.hooks.pinsChanged(snapshot.pinnedIds); }
  getSnapshot(): AppSnapshot {
    const items = this.db.items.filter(i => i.ownerId === this.db.activeOwnerId && !i.deletedAt);
    return structuredClone({ items: items.map(item => ({ ...item, tags: item.tags ?? [], dueTime: item.dueTime ?? null, recurrence: item.recurrence ?? null })), pinnedIds: (this.db.pins[this.scope()] ?? []).filter(id => items.some(i => i.id === id && !(i.kind === 'task' && i.completed))), sync: { ...this.sync, pending: this.db.items.filter(i => i.ownerId === this.db.activeOwnerId && this.db.dirtyIds.includes(i.id)).length, lastSyncedAt: this.db.lastSyncedAt }, desktop: true });
  }
  async initialize() { return this.serial(async () => {
    const data = this.hooks.loadData(); if (data) { validateDatabase(data); this.db = structuredClone(data); } else this.commit(this.db);
    this.sync.configured = !!this.db.config;
    if (this.db.config) {
      this.cloud = this.factory(this.db.config, this.hooks);
      this.sync.status = this.db.activeOwnerId ? 'offline' : 'signed-out';
    }
    const next = structuredClone(this.db); const migrated = this.migrateImportedMetadata(next); const added = this.appendOccurrences(next, new Date()); if (migrated || added) this.commit(next);
    this.publish(); this.timer = setInterval(() => { void this.materializeRecurring().then(() => { if (this.db.activeOwnerId) return this.syncNow(); }).catch(() => {}); }, 30000); this.timer.unref?.();
  }); }
  // Session recovery must never occupy the mutation queue while waiting for the network.
  async resumeCloudSession() {
    const cloud = this.cloud, epoch = this.sessionEpoch, owner = this.db.activeOwnerId;
    if (!cloud || this.disposed) return;
    let user: Awaited<ReturnType<CloudAdapter['identity']>>;
    try { user = await cloud.identity(); }
    catch {
      await this.serial(async () => {
        if (this.disposed || this.cloud !== cloud || this.sessionEpoch !== epoch || this.db.activeOwnerId !== owner) return;
        this.sync.status = owner ? 'offline' : 'signed-out'; this.sync.error = '暂时无法验证云端会话'; this.publish();
      });
      return;
    }
    await this.serial(async () => {
      if (this.disposed || this.cloud !== cloud || this.sessionEpoch !== epoch || this.db.activeOwnerId !== owner) return;
      this.commit({ ...this.db, activeOwnerId: user?.id ?? null });
      this.sync.email = user?.email ?? null; this.sync.status = user ? 'offline' : 'signed-out'; this.sync.error = null; this.publish();
    });
    if (!this.disposed && this.cloud === cloud && this.sessionEpoch === epoch && user && this.db.activeOwnerId === user.id) void this.syncNow().catch(() => {});
  }
  dispose() { this.disposed = true; this.sessionEpoch++; if (this.timer) clearInterval(this.timer); }
  private find(id: string) { const item = this.db.items.find(i => i.id === id && i.ownerId === this.db.activeOwnerId && !i.deletedAt); if (!item) throw new Error('条目不存在'); return item; }
  private timestamp(previous?: string) { return new Date(Math.max(Date.now(), previous ? Date.parse(previous) + 1 : 0)).toISOString(); }
  private migrateImportedMetadata(next: Stored) {
    let changed = 0;
    const migrate = (items: Item[], dirtyIds: string[]) => {
      for (const item of items) {
        if (item.kind !== 'task' || item.deletedAt || item.tags !== undefined || !item.body.startsWith('来源：')) continue;
        const metadata = parseTaskMetadata(item.title), tags = [...new Set([...(item.tags ?? []), ...metadata.tags])].slice(0, 30);
        if (item.tags === undefined) {
          item.dueDate ??= metadata.dueDate ?? null; item.tags = tags; item.updatedAt = this.timestamp(item.updatedAt); item.deviceId = next.deviceId;
          if (!dirtyIds.includes(item.id)) dirtyIds.push(item.id); changed++;
        }
      }
    };
    migrate(next.items, next.dirtyIds);
    for (const cache of Object.values(next.projectCaches ?? {})) migrate(cache.items, cache.dirtyIds);
    return changed;
  }
  private appendOccurrences(next: Stored, now: Date) {
    let added = 0;
    for (const root of [...next.items]) {
      if (root.ownerId !== next.activeOwnerId || root.deletedAt || !root.recurrence || !root.dueDate || root.seriesId) continue;
      for (const occurrence of dueOccurrences(root.dueDate, root.dueTime ?? null, root.recurrence, now)) {
        const id = occurrenceId(root.id, occurrence.dueDate);
        if (next.items.some(item => item.id === id && item.ownerId === root.ownerId)) continue;
        const stamp = now.toISOString();
        next.items.push({ ...root, id, dueDate: occurrence.dueDate, recurrence: null, seriesId: root.id, recurrenceIndex: occurrence.index, completed: false, createdAt: stamp, updatedAt: stamp, deletedAt: null, deviceId: next.deviceId });
        if (!next.dirtyIds.includes(id)) next.dirtyIds.push(id); added++;
      }
    }
    return added;
  }
  materializeRecurring(now = new Date()) { return this.serial(async () => {
    if (this.disposed) return 0;
    const next = structuredClone(this.db), added = this.appendOccurrences(next, now);
    if (added) { this.commit(next); if (next.activeOwnerId) this.sync.status = 'offline'; this.publish(); }
    return added;
  }); }
  private saveItem(item: Item) { const next = structuredClone(this.db); const index = next.items.findIndex(i => i.id === item.id && i.ownerId === item.ownerId); if (index < 0) next.items.push(item); else next.items[index] = item; if (!next.dirtyIds.includes(item.id)) next.dirtyIds.push(item.id); this.appendOccurrences(next, new Date()); this.commit(next); if (this.db.activeOwnerId) this.sync.status = 'offline'; this.publish(); }
  createItem(input: CreateItemInput) { return this.serial(async () => { if (!input || typeof input !== 'object' || Array.isArray(input) || typeof input.title !== 'string' || (input.tags !== undefined && !validTags(input.tags))) throw new Error('条目内容无效'); const now = this.timestamp(); const item: Item = { id: randomUUID(), ownerId: this.db.activeOwnerId, kind: input.kind, title: input.title.trim(), body: input.body ?? '', dueDate: input.dueDate ?? null, dueTime: input.dueTime ?? null, tags: [...new Set((input.tags ?? []).map(tag => tag.trim()))], recurrence: input.recurrence ?? null, color: input.color ?? 'sage', completed: false, createdAt: now, updatedAt: now, deletedAt: null, deviceId: this.db.deviceId }; if (!validItem(item) || !item.title || item.title.length > 300 || item.body.length > 100000) throw new Error('条目内容无效'); this.saveItem(item); return structuredClone(item); }); }
  updateItem(id: string, patch: ItemPatch) { return this.serial(async () => { if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new Error('更新字段无效'); const old = this.find(id); const allowed = ['title','body','dueDate','dueTime','tags','recurrence','completed','color']; if (Object.keys(patch).some(k => !allowed.includes(k)) || (patch.tags !== undefined && !validTags(patch.tags))) throw new Error('更新字段无效'); const item = { ...old, ...patch, ...(patch.tags ? { tags: [...new Set(patch.tags.map(tag => tag.trim()))] } : {}), updatedAt: this.timestamp(old.updatedAt), deviceId: this.db.deviceId }; if (!validItem(item) || !item.title.trim() || item.title.length > 300 || item.body.length > 100000) throw new Error('条目内容无效'); this.saveItem(item); return structuredClone(item); }); }
  deleteItem(id: string) { return this.serial(async () => { const old = this.find(id); const now = this.timestamp(old.updatedAt); this.saveItem({ ...old, deletedAt: now, updatedAt: now, deviceId: this.db.deviceId }); }); }
  pinItem(id: string) { return this.serial(async () => { this.find(id); const next = structuredClone(this.db); next.pins[this.scope()] = [...new Set([...(next.pins[this.scope()] ?? []), id])]; this.commit(next); this.publish(); }); }
  unpinItem(id: string) { return this.serial(async () => { const next = structuredClone(this.db); next.pins[this.scope()] = (next.pins[this.scope()] ?? []).filter(x => x !== id); this.commit(next); this.publish(); }); }
  async getCloudConfig() { return structuredClone(this.db.config); }
  setCloudConfig(config: CloudConfig) { return this.serial(async () => {
    const valid = validateConfig(config); this.sessionEpoch++; const next = structuredClone(this.db); const oldUrl = next.config?.url ?? 'local';
    next.projectCaches ??= {}; next.projectCaches[oldUrl] = { items: next.items.filter(i => i.ownerId !== null), dirtyIds: next.dirtyIds.filter(id => next.items.some(i => i.id === id && i.ownerId !== null)) };
    const guest = next.items.filter(i => i.ownerId === null); const guestDirty = next.dirtyIds.filter(id => guest.some(i => i.id === id)); const cache = next.projectCaches[valid.url] ?? { items: [], dirtyIds: [] };
    next.items = [...guest, ...cache.items]; next.dirtyIds = [...guestDirty, ...cache.dirtyIds]; next.config = valid; next.activeOwnerId = null; next.lastSyncedAt = null;
    await this.hooks.writeSecret(null); this.commit(next); this.cloud = this.factory(valid, this.hooks); this.sync = { configured: true, status: 'signed-out', email: null, pending: 0, lastSyncedAt: null, error: null }; this.publish();
  }); }
  sendOtp(email: string) { return this.serial(async () => { if (!this.cloud) throw new Error('请先配置云端'); if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('邮箱格式无效'); await this.cloud.sendOtp(email.trim()); }); }
  verifyOtp(email: string, token: string) { return this.serial(async () => {
    if (!this.cloud) throw new Error('请先配置云端'); if (!/^\d{6,10}$/.test(token)) throw new Error('请输入邮件中的数字验证码');
    this.sessionEpoch++;
    const user = await this.cloud.verifyOtp(email.trim(), token); try { this.commit({ ...this.db, activeOwnerId: user.id, lastSyncedAt: null }); } catch (error) { await this.cloud.signOut(); await this.hooks.writeSecret(null); throw error; }
    this.sync.email = user.email; this.sync.status = 'offline'; this.sync.error = null; this.publish();
  }).then(() => this.syncNow().catch(() => {})); }
  signOut() { return this.serial(async () => { this.sessionEpoch++; await this.hooks.writeSecret(null); this.commit({ ...this.db, activeOwnerId: null, lastSyncedAt: null }); if (this.db.config) this.cloud = this.factory(this.db.config, this.hooks); this.sync.email = null; this.sync.status = this.db.config ? 'signed-out' : 'unconfigured'; this.sync.error = null; this.publish(); }); }
  syncNow() {
    if (this.syncFlight) return this.syncFlight;
    const running = this.runSync();
    this.syncFlight = running;
    void running.finally(() => { if (this.syncFlight === running) this.syncFlight = null; }).catch(() => {});
    return running;
  }
  private async runSync() {
    const cloud = this.cloud, owner = this.db.activeOwnerId, epoch = this.sessionEpoch;
    if (!cloud || !owner || this.disposed) return;
    const current = () => !this.disposed && this.cloud === cloud && this.db.activeOwnerId === owner && this.sessionEpoch === epoch;
    const outgoing = structuredClone(this.db.items.filter(i => i.ownerId === owner && this.db.dirtyIds.includes(i.id)));
    this.sync.status = 'syncing'; this.sync.error = null; this.publish();
    try {
      const identity = await cloud.identity();
      if (!identity || identity.id !== owner) throw new Error('云端登录已失效，请退出后重新登录');
      if (!current()) return;
      await cloud.upload(outgoing);
      if (!current()) return;
      const incoming = await cloud.download(owner);
      if (!incoming.every(i => validItem(i) && i.ownerId === owner)) throw new Error('云端返回的数据无效');
      await this.serial(async () => {
        if (!current()) return;
        const next = structuredClone(this.db);
        // Only acknowledge the exact revisions sent; edits made during network I/O stay dirty.
        next.dirtyIds = next.dirtyIds.filter(id => {
          const sent = outgoing.find(i => i.id === id), local = next.items.find(i => i.id === id && i.ownerId === owner);
          return !sent || !local || compareItems(sent, local) !== 0;
        });
        for (const item of incoming) {
          const index = next.items.findIndex(i => i.id === item.id && i.ownerId === owner);
          if (index < 0) next.items.push(item);
          else if (compareItems(item, next.items[index]) >= 0) next.items[index] = item;
        }
        this.migrateImportedMetadata(next); this.appendOccurrences(next, new Date());
        next.lastSyncedAt = new Date().toISOString(); this.commit(next);
        this.sync.status = next.dirtyIds.some(id => next.items.some(i => i.id === id && i.ownerId === owner)) ? 'offline' : 'synced';
        this.sync.email = identity.email; this.publish();
      });
    } catch {
      if (!current()) return;
      this.sync.status = 'offline'; this.sync.error = '云端同步未完成。更改已保留在本机，请检查网络、登录和项目配置后重试。'; this.publish(); throw new Error(this.sync.error);
    }
  }
  exportData() { return this.serial(async () => this.hooks.exportJson(JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), items: this.getSnapshot().items }, null, 2))); }
}
