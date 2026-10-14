import { describe, expect, it } from 'vitest';
import { AppService } from '../src/main/service';
import type { CloudAdapter, CloudIdentity } from '../src/main/cloud';
import type { Database, RuntimeHooks } from '../src/shared/types';
function fixture() {
  let finish!: (user: CloudIdentity | null) => void;
  const identity = new Promise<CloudIdentity | null>(resolve => { finish = resolve; });
  let stored: Database = { version: 1, deviceId: 'test', items: [], dirtyIds: [], pins: {}, config: { url: 'https://abc.supabase.co', publicKey: 'sb_publishable_test' }, activeOwnerId: 'old-account', lastSyncedAt: null };
  const hooks: RuntimeHooks = { loadData: () => stored, saveData: d => { stored = structuredClone(d); }, readSecret: async () => null, writeSecret: async () => {}, broadcast: () => {}, pinsChanged: () => {}, exportJson: async () => true };
  const cloud: CloudAdapter = { identity: () => identity, sendOtp: async () => {}, verifyOtp: async () => ({ id: 'new-account', email: null }), signOut: async () => {}, upload: async () => {}, download: async () => [] };
  return { service: new AppService(hooks, () => cloud), finish };
}
describe('non-blocking startup', () => {
  it('loads and edits local data while identity recovery is unresolved', async () => {
    const { service, finish } = fixture();
    try {
      await service.initialize(); const restoring = service.resumeCloudSession();
      expect(service.getSnapshot().sync.status).toBe('offline');
      const item = await service.createItem({ kind: 'task', title: 'available offline' });
      expect(item.ownerId).toBe('old-account');
      finish({ id: 'old-account', email: null }); await restoring;
      expect(service.getSnapshot().items[0].title).toBe('available offline');
    } finally { service.dispose(); }
  });
  it('does not restore an old account after sign-out during recovery', async () => {
    const { service, finish } = fixture();
    try {
      await service.initialize(); const restoring = service.resumeCloudSession();
      await service.signOut(); finish({ id: 'old-account', email: null }); await restoring;
      expect(service.getSnapshot().sync.status).toBe('signed-out');
      expect(service.getWorkspaceKey()).toBe('local:guest');
    } finally { service.dispose(); }
  });
});
