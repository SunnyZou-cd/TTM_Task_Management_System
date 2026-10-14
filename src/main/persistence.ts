import fs from 'node:fs';
import path from 'node:path';
import { safeStorage } from 'electron';
import type { Database } from '../shared/types';

export function atomicWrite(file: string, data: string | Buffer): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.${process.pid}.tmp`;
  try {
    const fd = fs.openSync(temp, 'w', 0o600);
    try { fs.writeFileSync(fd, data); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(temp, file);
  } finally { if (fs.existsSync(temp)) fs.unlinkSync(temp); }
}

export function persistence(directory: string) {
  const databaseFile = path.join(directory, 'database.json');
  const secretFile = path.join(directory, 'session.enc');
  let corrupt = false;
  return {
    loadData(): Database | null {
      if (!fs.existsSync(databaseFile)) return null;
      try {
        const value = JSON.parse(fs.readFileSync(databaseFile, 'utf8')) as Database;
        if (value.version !== 1 || typeof value.deviceId !== 'string' || !Array.isArray(value.items) || !Array.isArray(value.dirtyIds) || !value.pins || typeof value.pins !== 'object') throw new Error('格式不正确');
        return value;
      } catch {
        corrupt = true;
        throw new Error(`本地数据无法读取。原文件已保留，请备份并检查：${databaseFile}`);
      }
    },
    saveData(value: Database) {
      if (corrupt) throw new Error('数据文件损坏，已停止保存以保护原文件。');
      atomicWrite(databaseFile, JSON.stringify(value, null, 2));
    },
    async readSecret(): Promise<string | null> {
      if (!fs.existsSync(secretFile)) return null;
      if (!safeStorage.isEncryptionAvailable()) throw new Error('Windows 安全加密不可用，无法读取登录凭据。');
      try { return safeStorage.decryptString(fs.readFileSync(secretFile)); }
      catch { throw new Error('登录凭据无法解密，请保留数据并重新登录。'); }
    },
    async writeSecret(value: string | null) {
      if (value === null) { if (fs.existsSync(secretFile)) fs.unlinkSync(secretFile); return; }
      if (!safeStorage.isEncryptionAvailable()) throw new Error('Windows 安全加密不可用，已拒绝保存登录凭据。');
      atomicWrite(secretFile, safeStorage.encryptString(value));
    },
  };
}
