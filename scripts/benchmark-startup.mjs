import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import assert from 'node:assert/strict';
const file = path.resolve(process.argv[2] ?? 'release/Pinboard-0.1.0-Windows.exe');
const directory = fs.mkdtempSync(path.resolve('work/package-test-'));
const server = net.createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port; await new Promise(resolve => server.close(resolve));
const env = { ...process.env, PINBOARD_DATA_DIR: directory, PINBOARD_TEST_MODE: '1' }; delete env.ELECTRON_RUN_AS_NODE;
const started = performance.now();
const child = spawn(file, [`--remote-debugging-port=${port}`, '--remote-debugging-address=127.0.0.1'], { env, stdio: 'ignore' });
let socket;
try {
  let target;
  for (let i = 0; i < 1800; i++) {
    try { const response = await fetch(`http://127.0.0.1:${port}/json/list`); target = (await response.json()).find(t => t.type === 'page' && t.url.includes('index.html')); if (target) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.ok(target, '打包版必须成功加载本机界面');
  socket = new WebSocket(target.webSocketDebuggerUrl); await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let id = 0; const pending = new Map();
  socket.onmessage = event => { const result = JSON.parse(event.data); const handler = pending.get(result.id); if (handler) { pending.delete(result.id); handler(result); } };
  const evaluate = expression => new Promise((resolve, reject) => {
    const messageId = ++id;
    const timeout = setTimeout(() => { pending.delete(messageId); reject(new Error('打包版调用超时')); }, 10000);
    pending.set(messageId, result => { clearTimeout(timeout); if (result.error || result.result?.exceptionDetails) reject(new Error(JSON.stringify(result.error ?? result.result.exceptionDetails))); else resolve(result.result.result.value); });
    socket.send(JSON.stringify({ id: messageId, method: 'Runtime.evaluate', params: { expression, returnByValue: true, awaitPromise: true } }));
  });
  let heading;
  for (let i = 0; i < 100; i++) { heading = await evaluate("document.querySelector('h1')?.textContent"); if (typeof heading === 'string' && heading.length > 0) break; await new Promise(resolve => setTimeout(resolve, 100)); }
  assert.ok(heading);
  const initial = await evaluate('window.pinboard.getSnapshot()');
  console.log(JSON.stringify({ executable: file, readyMs: Math.round(performance.now() - started), directory }));
  assert.equal(initial.desktop, true); assert.equal(initial.items.length, 0); assert.equal(initial.sync.status, 'unconfigured');
  await evaluate("window.pinboard.createItem({kind:'note',title:'打包版验收',body:'仅在独立测试目录'})");
  const state = await evaluate('window.pinboard.getSnapshot()'); assert.equal(state.items.length, 1);
  const disk = JSON.parse(fs.readFileSync(path.join(directory, 'database.json'), 'utf8')); assert.equal(disk.items[0].title, '打包版验收');
  fs.writeFileSync(path.join(directory, 'result.json'), JSON.stringify({ passed: true, executable: file, checks: ['packaged launch', 'renderer loaded', 'secure preload bridge', 'persisted note', 'honest unconfigured state'] }, null, 2));
  // Close the local debugging connection and let the normal application lifecycle exit.
  await evaluate("window.pinboard.windowControl('quit')").catch(() => {});
  console.log(`打包版启动与保存验收通过：${directory}`);
} finally { socket?.close(); if (child.exitCode === null) child.kill(); }
