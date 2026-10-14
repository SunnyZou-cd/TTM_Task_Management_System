import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const require = createRequire(import.meta.url);
const base = path.resolve('work'); fs.mkdirSync(base, { recursive: true });
const directory = fs.mkdtempSync(path.join(base, 'desktop-test-'));
for (const phase of ['create', 'restore']) {
  const env = { ...process.env, PINBOARD_TEST_MODE: '1', PINBOARD_DATA_DIR: directory, PINBOARD_TEST_PHASE: phase };
  delete env.ELECTRON_RUN_AS_NODE;
  const child = spawn(require('electron'), [path.resolve('scripts/desktop-smoke.cjs')], { env, stdio: 'inherit' });
  const timeout = setTimeout(() => child.kill(), 60000);
  const code = await new Promise(resolve => child.once('exit', resolve)); clearTimeout(timeout);
  if (code !== 0) throw new Error(`桌面验收 ${phase} 失败 (${code})，测试数据：${directory}`);
}
console.log(`桌面端两轮验收通过，截图和测试数据：${directory}`);
