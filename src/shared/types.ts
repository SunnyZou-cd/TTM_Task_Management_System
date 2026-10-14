import type { ObsidianPreview, ObsidianResult } from './obsidian';
export type ItemKind = 'task' | 'note';
export type NoteColor = 'sage' | 'yellow' | 'blue' | 'rose';
export interface Item {
  id: string;
  ownerId: string | null;
  kind: ItemKind;
  title: string;
  body: string;
  dueDate: string | null;
  completed: boolean;
  color: NoteColor;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  deviceId: string;
}
export interface CreateItemInput {
  kind: ItemKind;
  title: string;
  body?: string;
  dueDate?: string | null;
  color?: NoteColor;
}
export type ItemPatch = Partial<Pick<Item, 'title' | 'body' | 'dueDate' | 'completed' | 'color'>>;
export interface CloudConfig { url: string; publicKey: string }
export type SyncStatus = 'unconfigured' | 'signed-out' | 'syncing' | 'synced' | 'offline' | 'error';
export interface SyncState {
  configured: boolean;
  status: SyncStatus;
  email: string | null;
  pending: number;
  lastSyncedAt: string | null;
  error: string | null;
}
export interface AppSnapshot {
  items: Item[];
  pinnedIds: string[];
  sync: SyncState;
  desktop: boolean;
}
export interface PinboardAPI {
  getSnapshot(): Promise<AppSnapshot>;
  createItem(input: CreateItemInput): Promise<Item>;
  updateItem(id: string, patch: ItemPatch): Promise<Item>;
  deleteItem(id: string): Promise<void>;
  pinItem(id: string): Promise<void>;
  unpinItem(id: string): Promise<void>;
  setAlwaysOnTop(id: string, enabled: boolean): Promise<void>;
  setNoteExpanded(id: string, expanded: boolean): Promise<void>;
  chooseObsidianFolder(): Promise<(ObsidianPreview & { token: string }) | null>;
  importObsidian(token: string): Promise<ObsidianResult>;
  syncObsidian(): Promise<ObsidianResult>;
  openMain(): Promise<void>;
  windowControl(action: 'minimize' | 'close' | 'quit'): Promise<void>;
  getCloudConfig(): Promise<CloudConfig | null>;
  setCloudConfig(config: CloudConfig): Promise<void>;
  sendOtp(email: string): Promise<void>;
  verifyOtp(email: string, token: string): Promise<void>;
  signOut(): Promise<void>;
  syncNow(): Promise<void>;
  exportData(): Promise<boolean>;
  subscribe(callback: (snapshot: AppSnapshot) => void): () => void;
  onCloseRequest(callback: () => Promise<boolean>): () => void;
}
export interface Database {
  version: 1;
  deviceId: string;
  items: Item[];
  dirtyIds: string[];
  pins: Record<string, string[]>;
  config: CloudConfig | null;
  activeOwnerId: string | null;
  lastSyncedAt: string | null;
}
export interface RuntimeHooks {
  loadData(): Database | null;
  saveData(database: Database): void;
  readSecret(): Promise<string | null>;
  writeSecret(value: string | null): Promise<void>;
  broadcast(snapshot: AppSnapshot): void;
  pinsChanged(ids: string[]): void;
  exportJson(value: string): Promise<boolean>;
}
declare global { interface Window { pinboard?: PinboardAPI } }
