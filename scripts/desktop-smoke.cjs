const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const directory = process.env.PINBOARD_DATA_DIR;
const phase = process.env.PINBOARD_TEST_PHASE;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function wait(check, message) {
  for (let i = 0; i < 100; i++) { try { const result = await check(); if (result) return result; } catch {} await delay(100); }
  throw new Error(`等待超时：${message}`);
}
const code = (window, source) => window.webContents.executeJavaScript(source, true);
const snapshot = window => code(window, 'window.pinboard.getSnapshot()');
async function click(window, selector) {
  await wait(() => code(window, `!!document.querySelector(${JSON.stringify(selector)})`), selector);
  await code(window, `document.querySelector(${JSON.stringify(selector)}).click()`);
}
function fill(window, selector, value) {
  return code(window, `(() => { const element = document.querySelector(${JSON.stringify(selector)}); if (!element) throw Error('找不到输入框'); const proto = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, ${JSON.stringify(value)}); element.dispatchEvent(new Event('input', {bubbles:true})); element.dispatchEvent(new Event('change', {bubbles:true})); })()`);
}
async function capture(window, name) { await delay(200); fs.writeFileSync(path.join(directory, name), (await window.webContents.capturePage()).toPNG()); }
require('../dist-main/main/main.js');
app.on('web-contents-created', (_event, contents) => {
  contents.on('preload-error', (_event, location, error) => console.error('Preload error:', location, error));
  contents.on('console-message', event => { if (event.level === 'error') console.error('Renderer:', event.message); });
});
void (async () => {
  await app.whenReady();
  const main = await wait(() => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('index.html') && !w.webContents.getURL().includes('?note=')), '主窗口');
  const errors = [];
  main.webContents.on('console-message', (_event, ...args) => { if (args[0] === 3) errors.push(args[1]); });
  await wait(() => code(main, "!!document.querySelector('.heading')"), '任务界面');
  assert.equal((await snapshot(main)).desktop, true);
  assert.equal((await snapshot(main)).sync.status, 'unconfigured');
  assert.equal(main.webContents.getLastWebPreferences().nodeIntegration, false);
  assert.equal(main.webContents.getLastWebPreferences().contextIsolation, true);
  assert.equal(main.webContents.getLastWebPreferences().sandbox, true);
  if (phase === 'create') {
    await code(main, "localStorage.setItem('pinboard.compact.v1','off')");
    assert.equal((await snapshot(main)).items.length, 0);
    await capture(main, 'empty.png');
    console.log('Checking UI task creation');
    await code(main, "document.querySelector('.heading button.primary').click()");
    await wait(() => code(main, "!!document.querySelector('[role=dialog]')"), '新建任务表单');
    await fill(main, 'form label input', '桌面验收任务');
    await fill(main, 'form textarea', '输入后可在主界面和便笺中继续编辑。');
    await fill(main, 'form input[type=date]', '2026-10-20');
    await code(main, "document.querySelector('form').requestSubmit()");
    await wait(async () => (await snapshot(main)).items.length === 1, '任务保存');
    const item = (await snapshot(main)).items[0];
    assert.equal(item.dueDate, '2026-10-20');
    await wait(() => code(main, "!!document.querySelector('.check-button')"), '任务列表');
    await code(main, "document.querySelector('.check-button').click()");
    await wait(async () => (await snapshot(main)).items[0].completed, '勾选完成');
    console.log('Checking pinning and window controls');
    await click(main, '[aria-label="固定为悬浮便笺"]');
    const note = await wait(() => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('?note=')), '悬浮窗口');
    await wait(() => code(note, "!!document.querySelector('.floating')"), '便笺编辑器');
    assert.equal(note.isAlwaysOnTop(), true); assert.equal(note.isResizable(), true);
    await fill(note, '.floating-body', '主界面与便笺保持一致。\n刚输入就关闭也应保存。');
    await wait(async () => (await snapshot(main)).items[0].body.includes('保持一致'), '跨窗口内容更新');
    await click(note, '[aria-label="关闭始终置顶"]');
    await wait(() => !note.isAlwaysOnTop(), '取消置顶');
    await click(note, '[aria-label="开启始终置顶"]');
    await wait(() => note.isAlwaysOnTop(), '重新置顶');
    await capture(main, 'tasks.png'); await capture(note, 'floating.png');
    note.setBounds({ x: 120, y: 120, width: 260, height: 220 });
    await capture(note, 'floating-small.png');
    const overflow = await code(note, 'document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight');
    assert.equal(overflow, false, '最小便笺窗口不应产生整页滚动');
    await fill(note, '.floating-title', '');
    note.close();
    await wait(() => code(note, "document.querySelector('.toast')?.textContent.includes('标题')"), '空标题关闭被阻止');
    assert.equal(note.isDestroyed(), false, '保存失败不得关闭便笺');
    assert.equal((await snapshot(main)).items[0].title, '桌面验收任务', '失败保存不得覆盖已存内容');
    await fill(note, '.floating-title', '桌面验收任务');
    await fill(note, '.floating-body', '原生关闭前最后一次输入');
    note.close();
    await wait(() => note.isDestroyed(), '原生关闭保存');
    assert.equal((await snapshot(main)).items[0].body, '原生关闭前最后一次输入');
    assert.equal((await snapshot(main)).pinnedIds.length, 0);
    assert.equal((await snapshot(main)).items.length, 1, '关闭便笺不删除内容');
    await code(main, `window.pinboard.pinItem(${JSON.stringify(item.id)})`);
    const restoredNote = await wait(() => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('?note=')), '重新固定');
    await wait(() => code(restoredNote, "!!document.querySelector('.floating')"), '重新固定内容');
    // Position deliberately off screen: next launch must clamp it back into a display.
    restoredNote.setBounds({ x: -5000, y: -5000, width: 340, height: 380 });
    await fill(restoredNote, '.floating-body', '退出应用前最后一次输入');
    await code(main, "document.querySelector('.sidebar-bottom button').click()");
    await wait(() => code(main, "!!document.querySelector('.settings-dialog')"), '账号与设置');
    assert.match(await code(main, 'document.querySelector(".settings-status").textContent'), /未配置云端/);
    await capture(main, 'settings.png');
    await code(main, "document.querySelector('[aria-label=关闭设置]').click()");
    main.close();
    await wait(() => main.isDestroyed(), '主窗口关闭');
    assert.equal(restoredNote.isDestroyed(), false, '便笺应在主窗口关闭后继续运行');
    await fill(restoredNote, '.floating-body', '退出应用前最后一次输入');
    fs.writeFileSync(path.join(directory, 'test-meta.json'), JSON.stringify({ id: item.id, phase: 'create' }));
    app.quit();
  } else {
    const meta = JSON.parse(fs.readFileSync(path.join(directory, 'test-meta.json'), 'utf8'));
    const state = await snapshot(main);
    assert.equal(state.items.length, 1);
    assert.equal(state.items[0].body, '退出应用前最后一次输入');
    assert.equal(state.items[0].completed, true);
    assert.deepEqual(state.pinnedIds, [meta.id]);
    const note = await wait(() => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('?note=')), '重启固定便笺');
    await wait(() => code(note, "!!document.querySelector('.floating')"), '重启便笺内容');
    const bounds = note.getBounds();
    const area = require('electron').screen.getDisplayMatching(bounds).workArea;
    assert.ok(bounds.x >= area.x && bounds.y >= area.y && bounds.x + bounds.width <= area.x + area.width && bounds.y + bounds.height <= area.y + area.height, '重启后便笺应在屏幕内');
    assert.equal(note.isAlwaysOnTop(), true);
    await capture(main, 'restored.png');
    await code(main, `window.pinboard.deleteItem(${JSON.stringify(meta.id)})`);
    await wait(() => note.isDestroyed(), '删除记录关闭便笺');
    assert.equal((await snapshot(main)).items.length, 0);
    assert.equal((await snapshot(main)).pinnedIds.length, 0);
    fs.writeFileSync(path.join(directory, 'result.json'), JSON.stringify({ passed: true, phases: ['create', 'restore'], verified: ['UI create', 'completion', 'topmost', 'resize', 'cross-window update', 'native-close flush', 'main-close keeps notes', 'quit flush', 'restart persistence', 'offscreen clamp', 'tombstone delete', 'sandbox IPC'] }, null, 2));
    app.quit();
  }
  assert.deepEqual(errors, [], '界面不应输出 JavaScript 错误');
  console.log(`Electron ${phase} 验收通过`);
})().catch(error => { console.error(error); app.exit(1); });
