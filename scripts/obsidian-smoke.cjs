const { app, BrowserWindow, dialog } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const vault = path.resolve(process.env.PINBOARD_TEST_VAULT);
dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [vault] });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function wait(check, label) {
  for (let i = 0; i < 150; i++) { try { const value = await check(); if (value) return value; } catch {} await delay(100); }
  throw new Error(`等待超时：${label}`);
}
const run = (window, expression) => window.webContents.executeJavaScript(expression, true);
require('../dist-main/main/main.js');

void (async () => {
  await app.whenReady();
  const window = await wait(() => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('index.html') && !w.webContents.getURL().includes('?note=')), '主窗口');
  await wait(() => run(window, '!!window.pinboard'), 'preload API');
  const preview = await run(window, 'window.pinboard.chooseObsidianFolder()');
  assert.equal(preview.folderName, 'vault');
  assert.equal(preview.files, 1);
  assert.equal(preview.tasks, 1);
  await assert.rejects(run(window, `window.pinboard.importObsidian('invalid-token')`), /目录选择已失效/);
  const imported = await run(window, `window.pinboard.importObsidian(${JSON.stringify(preview.token)})`);
  assert.equal(imported.imported, 2, '应导入一条笔记和一个任务');
  const initial = await run(window, 'window.pinboard.getSnapshot()');
  assert.equal(initial.items.length, 2);
  const task = initial.items.find(item => item.kind === 'task');
  assert.ok(task);
  const duplicate = await run(window, `window.pinboard.importObsidian(${JSON.stringify(preview.token)})`);
  assert.equal(duplicate.imported, 0);
  assert.equal((await run(window, 'window.pinboard.getSnapshot()')).items.length, 2, '重复导入不得新增条目');

  await run(window, `window.pinboard.updateItem(${JSON.stringify(task.id)}, { completed: true })`);
  const synced = await run(window, 'window.pinboard.syncObsidian()');
  assert.equal(synced.updated, 1);
  const notePath = path.join(vault, 'roadmap.md');
  assert.match(fs.readFileSync(notePath, 'utf8'), /- \[x\] Ship the bridge/);
  const backupDir = path.join(vault, '.pinboard-backups');
  assert.equal(fs.readdirSync(backupDir).filter(name => name.endsWith('.bak')).length, 1, '写回应创建原文备份');

  await run(window, `window.pinboard.updateItem(${JSON.stringify(task.id)}, { completed: false })`);
  const externalEdit = '# Roadmap\n\n外部编辑保留\n- [x] Ship the bridge\n';
  fs.writeFileSync(notePath, externalEdit, 'utf8');
  const conflicted = await run(window, 'window.pinboard.syncObsidian()');
  assert.equal(conflicted.updated, 0);
  assert.equal(conflicted.conflicts.length, 1);
  assert.match(conflicted.conflicts[0], /源文件已变更/);
  assert.equal(fs.readFileSync(notePath, 'utf8'), externalEdit, '冲突时不得覆盖外部编辑');
  console.log('通过：IPC 目录预览、token 校验、重复导入、任务完成状态、备份写回、外部编辑冲突保护。');
  app.quit();
})().catch(error => { console.error(error); app.exit(1); });
