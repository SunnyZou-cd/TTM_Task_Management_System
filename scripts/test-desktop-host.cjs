const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const moduleRoot = process.env.PINBOARD_NATIVE_PACKAGE_ROOT || path.resolve(__dirname, '..');
const koffi = require(require.resolve('koffi', { paths: [moduleRoot] }));
const { createDesktopCompatibleWindow, DesktopHost } = require(path.join(moduleRoot, 'dist-main/main/desktop-host'));
const { WindowManager } = require(path.join(moduleRoot, 'dist-main/main/windows'));

const directory = process.env.PINBOARD_NATIVE_TEST_DIR;
if (!directory || !path.resolve(directory).startsWith(path.resolve(__dirname, '../work') + path.sep)) throw Error('Test requires an isolated work directory.');
app.setPath('userData', directory);
process.env.PINBOARD_TEST_MODE = '1';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const api = koffi.load('user32.dll');
const parent = api.func('intptr_t __stdcall GetParent(intptr_t)');
const style = api.func('uint32_t __stdcall GetWindowLongW(intptr_t, int)');
const context = api.func('intptr_t __stdcall GetWindowDpiAwarenessContext(intptr_t)');
const thread = api.func('intptr_t __stdcall GetThreadDpiAwarenessContext()');
const equal = api.func('bool __stdcall AreDpiAwarenessContextsEqual(intptr_t, intptr_t)');
const handle = w => Number(w.getNativeWindowHandle().readBigUInt64LE());
const state = w => ({ handle: handle(w), parent: String(parent(handle(w))), style: style(handle(w), -16), exStyle: style(handle(w), -20), bounds: w.getBounds(), dpi: String(context(handle(w))) });
const report = { moduleRoot, koffiModule: require.resolve('koffi', { paths: [moduleRoot] }), checks: [], winD: 'Not exercised; native parentage does not prove Win+D behavior.' };
const check = (name, detail) => report.checks.push({ name, detail });
let manager;
app.whenReady().then(async () => {
  manager = new WindowManager(directory, async () => {});
  manager.rendererUrl = 'data:text/html,<title>Pinboard native host test</title><h1>Temporary test window</h1>';
  const threadBefore = thread();
  assert.throws(() => createDesktopCompatibleWindow(() => { throw Error('expected creation failure'); }), /expected creation failure/);
  assert.ok(equal(threadBefore, thread()), 'failed window creation restores caller thread DPI');
  manager.openMain();
  const main = manager.main;
  main.setBounds({ x: 80, y: 90, width: 800, height: 580 });
  await delay(200);
  const before = state(main);
  assert.ok(equal(threadBefore, thread()), 'main creation restores caller thread DPI');
  check('main creation restores thread DPI', { before: String(threadBefore), after: String(thread()), mainDpi: before.dpi });
  manager.pinsChanged(['isolated-test-note']);
  const note = manager.notes.get('isolated-test-note');
  const noteBefore = state(note);

  assert.equal(await manager.setMainDisplayMode('desktop'), 'desktop', manager.getMainDisplayModeReason());
  const firstHost = manager.desktopHost;
  const attached = await firstHost.inspect();
  assert.ok(attached.attached);
  assert.equal(attached.parent, attached.host);
  assert.equal(String(parent(handle(main))), attached.host);
  await firstHost.show();
  check('real HWND attaches to Explorer', attached);
  assert.equal(await manager.setMainDisplayMode('window'), 'window');
  await delay(100);
  assert.deepEqual(state(main), before, 'detach restores HWND, parent, styles, bounds and DPI');
  check('detach restores original HWND and geometry', state(main));

  assert.equal(await manager.setMainDisplayMode('desktop'), 'desktop', manager.getMainDisplayModeReason());
  const deadHost = manager.desktopHost;
  const helperPid = deadHost.child.pid;
  deadHost.child.kill(); // Only the helper spawned for this test; never Explorer.
  for (let attempt = 0; attempt < 100 && manager.getMainDisplayMode() !== 'window'; attempt++) await delay(100);
  assert.equal(manager.getMainDisplayMode(), 'window', 'helper exit automatically recovers');
  assert.equal(manager.main, main, 'recovery preserves original BrowserWindow');
  assert.deepEqual(state(main), before, 'replacement helper detaches and restores original styles and bounds');
  assert.match(manager.getMainDisplayModeReason(), /辅助进程/);
  check('forced helper death recovers same HWND', { helperPid, reason: manager.getMainDisplayModeReason(), restored: state(main) });
  assert.deepEqual(state(note), noteBefore, 'note HWND unaffected by main mode transitions');
  check('note HWND unchanged', noteBefore);

  const raw = new BrowserWindow({ width: 300, height: 220, show: false });
  const rawBefore = state(raw);
  const rawHost = new DesktopHost(() => {});
  try {
    if (!equal(context(handle(raw)), context(handle(main)))) {
      await assert.rejects(() => rawHost.attach(raw), /DPI/);
      assert.deepEqual(state(raw), rawBefore);
      check('incompatible DPI safely rejected without mutation', rawBefore);
    } else check('incompatible DPI case unavailable', { reason: 'default thread and desktop contexts match on this machine' });
  } finally { await rawHost.dispose(); raw.destroy(); }
  report.status = 'passed';
}).catch(error => { report.status = 'failed'; report.error = error.stack; process.exitCode = 1; })
.finally(async () => {
  if (manager) {
    manager.quitting = true;
    if (manager.desktopHost) await manager.desktopHost.dispose().catch(() => {});
  }
  for (const window of BrowserWindow.getAllWindows()) window.destroy();
  fs.writeFileSync(path.join(directory, 'result.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  app.exit(report.status === 'passed' ? 0 : 1);
});
