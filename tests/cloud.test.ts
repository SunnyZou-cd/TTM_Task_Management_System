import { describe, expect, it } from 'vitest';
import { validateConfig } from '../src/main/cloud';
describe('public cloud configuration', () => {
  it('normalizes a hosted URL and accepts a publishable key', () => {
    expect(validateConfig({ url: 'https://abc.supabase.co/', publicKey: 'sb_publishable_test' }).url).toBe('https://abc.supabase.co');
  });
  it('rejects arbitrary endpoints and privileged keys', () => {
    for (const url of ['http://abc.supabase.co', 'https://evil.example', 'https://abc.supabase.co/path', 'https://abc.supabase.co?x=1']) expect(() => validateConfig({ url, publicKey: 'sb_publishable_test' })).toThrow();
    const jwt = `header.${Buffer.from(JSON.stringify({ role: 'service_role' })).toString('base64url')}.signature`;
    for (const publicKey of ['sb_secret_test', jwt]) expect(() => validateConfig({ url: 'https://abc.supabase.co', publicKey })).toThrow();
  });
});
