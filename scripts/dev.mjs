import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { setTimeout as delay } from 'node:timers/promises';
const require = createRequire(import.meta.url);
const run = (bin, args, env = process.env) => spawn(process.execPath, [require.resolve(bin), ...args], { stdio: 'inherit', env });
const compiler = run('typescript/bin/tsc', ['-p', 'tsconfig.main.json']);
const exitCode = await new Promise(resolve => compiler.on('exit', resolve));
if (exitCode !== 0) process.exit(exitCode || 1);
const vite = run('vite/bin/vite.js', []);
let ready = false;
for (let i = 0; i < 100; i++) { try { const response = await fetch('http://127.0.0.1:5178'); if (response.ok) { ready = true; break; } } catch {} await delay(200); }
if (!ready) { vite.kill(); throw new Error('开发服务器未能启动'); }
const env = { ...process.env, PINBOARD_DEV_URL: 'http://127.0.0.1:5178' };
delete env.ELECTRON_RUN_AS_NODE;
const electron = spawn(require('electron'), ['.'], { stdio: 'inherit', env });
const stop = () => { electron.kill(); vite.kill(); };
process.on('SIGINT', stop); process.on('SIGTERM', stop);
electron.on('exit', code => { vite.kill(); process.exit(code || 0); });
