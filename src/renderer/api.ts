import type { AppSnapshot, Item, PinboardAPI } from '../shared/types';

const emptySync = { configured: false, status: 'unconfigured' as const, email: null, pending: 0, lastSyncedAt: null, error: null };
function previewAPI(): PinboardAPI {
  const key = 'pinboard-preview-v1';
  const raw = localStorage.getItem(key);
  let items: Item[] = raw ? JSON.parse(raw) : [];
  const listeners = new Set<(value: AppSnapshot) => void>();
  const snapshot = (): AppSnapshot => ({ items: items.filter(i => !i.deletedAt), pinnedIds: [], sync: emptySync, desktop: false });
  const publish = () => { localStorage.setItem(key, JSON.stringify(items)); listeners.forEach(fn => fn(snapshot())); };
  const desktopOnly = async () => { throw new Error('网页预览不支持桌面置顶或云端账号，请使用 Windows 应用。'); };
  return {
    async getSnapshot() { return snapshot(); },
    async createItem(input) { const now = new Date().toISOString(); const item: Item = { id: crypto.randomUUID(), ownerId: null, kind: input.kind, title: input.title, body: input.body ?? '', dueDate: input.dueDate ?? null, color: input.color ?? 'sage', completed: false, createdAt: now, updatedAt: now, deletedAt: null, deviceId: 'browser-preview' }; items = [...items, item]; publish(); return item; },
    async updateItem(id, patch) { const existing = items.find(i => i.id === id); if (!existing) throw new Error('找不到这条记录。'); const item = { ...existing, ...patch, updatedAt: new Date().toISOString() }; items = items.map(i => i.id === id ? item : i); publish(); return item; },
    async deleteItem(id) { items = items.filter(i => i.id !== id); publish(); },
    pinItem: desktopOnly, unpinItem: desktopOnly, setAlwaysOnTop: desktopOnly, setNoteExpanded: desktopOnly, chooseObsidianFolder: desktopOnly, importObsidian: desktopOnly, syncObsidian: desktopOnly, openMain: desktopOnly, windowControl: desktopOnly,
    async getCloudConfig() { return null; }, setCloudConfig: desktopOnly, sendOtp: desktopOnly, verifyOtp: desktopOnly, signOut: desktopOnly, syncNow: desktopOnly,
    async exportData() { const url = URL.createObjectURL(new Blob([JSON.stringify({ version: 1, items }, null, 2)], { type: 'application/json' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'pinboard-preview-backup.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); return true; },
    onCloseRequest() { return () => {}; },
    subscribe(callback) { listeners.add(callback); return () => listeners.delete(callback); },
  };
}
export const api = window.pinboard ?? previewAPI();
