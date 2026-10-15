import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(import.meta.url);
const base = path.resolve('work');
fs.mkdirSync(base, { recursive: true });
const directory = fs.mkdtempSync(path.join(base, 'workflow-test-'));
const env = { ...process.env, PINBOARD_TEST_MODE: '1', PINBOARD_DATA_DIR: directory };
delete env.ELECTRON_RUN_AS_NODE;
const child = spawn(require('electron'), [path.resolve('scripts/workflow-smoke.cjs')], { env, stdio: 'inherit' });
const timer = setTimeout(() => child.kill(), 180000);
const status = await new Promise(resolve => child.once('exit', resolve));
clearTimeout(timer);
if (status !== 0) throw new Error(`工作流 smoke 失败：退出码 ${status}；独立测试数据：${directory}`);
console.log(`工作流集成验收通过；独立测试数据和截图：${directory}`);
