import { createClient } from '@supabase/supabase-js';
import type { CloudConfig, Item, RuntimeHooks } from '../shared/types';

export interface CloudIdentity { id: string; email: string | null }
export interface CloudAdapter {
  identity(): Promise<CloudIdentity | null>;
  sendOtp(email: string): Promise<void>;
  verifyOtp(email: string, token: string): Promise<CloudIdentity>;
  signOut(): Promise<void>;
  upload(items: Item[]): Promise<void>;
  download(ownerId: string): Promise<Item[]>;
}
export function validateConfig(config: CloudConfig): CloudConfig {
  if (!config || typeof config.url !== 'string' || typeof config.publicKey !== 'string') throw new Error('云端配置无效');
  const url = new URL(config.url.trim());
  if (url.protocol !== 'https:' || !/^[a-z0-9-]+\.supabase\.co$/.test(url.hostname) || url.port || url.username || url.password || (url.pathname !== '/' && url.pathname !== '') || url.search || url.hash) throw new Error('请输入 HTTPS Supabase 项目地址');
  const key = config.publicKey.trim();
  let valid = /^sb_publishable_[A-Za-z0-9_-]+$/.test(key);
  if (key.split('.').length === 3) {
    try { valid = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()).role === 'anon'; } catch { valid = false; }
  }
  if (!valid || key.startsWith('sb_secret_')) throw new Error('仅接受 publishable 或 anon 公开密钥，不能使用服务密钥');
  return { url: url.origin, publicKey: key };
}
export function createCloud(config: CloudConfig, hooks: RuntimeHooks): CloudAdapter {
  const client = createClient(config.url, config.publicKey, {
    global: { fetch: (url, options) => fetch(url, { ...options, signal: options?.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000) }) },
    auth: { autoRefreshToken: false, persistSession: true, detectSessionInUrl: false, storage: {
      getItem: () => hooks.readSecret(), setItem: (_key, value) => hooks.writeSecret(value), removeItem: () => hooks.writeSecret(null),
    } },
  });
  const identity = async () => {
    const session = await client.auth.getSession();
    if (session.error) throw session.error;
    if (!session.data.session) return null;
    if ((session.data.session.expires_at ?? 0) * 1000 < Date.now() + 60000) {
      const refreshed = await client.auth.refreshSession();
      if (refreshed.error) throw refreshed.error;
    }
    const result = await client.auth.getUser();
    if (result.error) throw result.error;
    return result.data.user ? { id: result.data.user.id, email: result.data.user.email ?? null } : null;
  };
  return {
    identity,
    async sendOtp(email) { const { error } = await client.auth.signInWithOtp({ email }); if (error) throw error; },
    async verifyOtp(email, token) {
      const { data, error } = await client.auth.verifyOtp({ email, token, type: 'email' });
      if (error) throw error;
      if (!data.user) throw new Error('登录未返回用户');
      return { id: data.user.id, email: data.user.email ?? null };
    },
    async signOut() { const { error } = await client.auth.signOut({ scope: 'local' }); if (error) throw error; },
    async upload(items) {
      for (const item of items) { const { error } = await client.rpc('merge_pinboard_item', { record: item }); if (error) throw error; }
    },
    async download(ownerId) {
      const items: Item[] = [];
      for (let offset = 0; ; offset += 500) {
        const { data, error } = await client.from('pinboard_items').select('record').eq('owner_id', ownerId).order('id').range(offset, offset + 499);
        if (error) throw error;
        items.push(...(data ?? []).map(row => row.record as Item));
        if ((data ?? []).length < 500) break;
      }
      return items;
    },
  };
}
