const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const directory = process.env.PINBOARD_DATA_DIR;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const code = (window, source) => window.webContents.executeJavaScript(source, true);
async function wait(check, label) {
  for (let i = 0; i < 120; i++) { try { const result = await check(); if (result) return result; } catch {} await delay(100); }
  throw new Error(`等待超时：${label}`);
}
async function capture(window, name) {
  window.showInactive();
  await delay(500);
  fs.writeFileSync(path.join(directory, name), (await window.webContents.capturePage()).toPNG());
}
const nav = label => ` [...document.querySelectorAll('.sidebar nav button')].find(b=>b.textContent.includes(${JSON.stringify(label)})).click()`;
require('../dist-main/main/main.js');
void (async () => {
  await app.whenReady();
  const main = await wait(() => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('index.html') && !w.webContents.getURL().includes('?note=')), '主窗口');
  await wait(() => code(main, '!!window.pinboard && !!document.querySelector(".heading")'), '主界面和 API');
  assert.deepEqual(main.getMinimumSize(), [760, 560], '主窗口最小尺寸应为 760×560');
  main.setBounds({ ...main.getBounds(), width: 760, height: 560 });
  await delay(300);
  const minimumBounds = main.getBounds();
  assert.ok(minimumBounds.width <= 800 && minimumBounds.height <= 600, `窗口应按最小尺寸验收，实际为 ${minimumBounds.width}×${minimumBounds.height}`);
  const monthStart = new Date();
  const dateKeys = [1, 2, 3].map(day => `${monthStart.getFullYear()}-${String(monthStart.getMonth()+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`);
  const fixture = [];
  for (let i = 0; i < 355; i++) {
    const completed = i >= 350;
    fixture.push(await code(main, `window.pinboard.createItem(${JSON.stringify({ kind: 'task', title: `Workflow fixture ${String(i+1).padStart(3,'0')}`, body: `Fixture record ${i+1}`, dueDate: dateKeys[i % dateKeys.length], tags: [i % 2 ? 'fixture-odd' : 'fixture-even'] })})`));
    if (completed) await code(main, `window.pinboard.updateItem(${JSON.stringify(fixture[i].id)}, {completed:true})`);
  }
  const note = await code(main, `window.pinboard.createItem(${JSON.stringify({ kind: 'note', title: 'Markdown workflow', body: '# Workflow heading\n\n**Strong text**\n\n- List item', tags: ['markdown-fixture'] })})`);
  const initial = await code(main, 'window.pinboard.getSnapshot()');
  assert.equal(initial.items.length, 356, '工作流 fixture 应有 355 个任务和 1 条便笺');
  assert.equal(initial.items.filter(item => item.kind === 'task' && item.completed).length, 5);

  const listCount = await code(main, 'document.querySelectorAll(".item-card.task").length');
  assert.equal(listCount, 50, '任务列表单页最多显示 50 项');
  assert.equal(await code(main, 'document.querySelector(".pagination span").textContent'), '1 / 7');
  for (let page = 2; page <= 7; page++) {
    await code(main, 'document.querySelector(".pagination button:last-child").click()');
    await wait(() => code(main, `document.querySelector(".pagination span")?.textContent === "${page} / 7"`), `列表第 ${page} 页`);
  }
  await code(main, 'document.querySelector(".main-content").scrollTo(0, document.querySelector(".main-content").scrollHeight)');
  await wait(() => code(main, 'document.querySelector(".main-content").scrollTop > 0'), '主内容滚动');
  const pinnedLayout = await code(main, `(() => { const side=document.querySelector('.sidebar').getBoundingClientRect(); const settings=document.querySelector('.sidebar-bottom').getBoundingClientRect(); return {sideTop:side.top,sideBottom:side.bottom,settingsBottom:settings.bottom,height:innerHeight,scroll:document.querySelector('.main-content').scrollTop}; })()`);
  assert.ok(pinnedLayout.scroll > 0);
  assert.ok(pinnedLayout.sideTop >= 0 && pinnedLayout.sideBottom <= pinnedLayout.height, '侧栏应始终留在窗口视口内');
  assert.ok(pinnedLayout.settingsBottom <= pinnedLayout.height, '设置入口应始终留在窗口视口内');
  await capture(main, 'workflow-list-bottom.png');

  await code(main, 'document.querySelector(".main-content").scrollTo(0,0)');
  await code(main, 'document.querySelector("[aria-label=按标签筛选]").value="fixture-odd"; document.querySelector("[aria-label=按标签筛选]").dispatchEvent(new Event("change",{bubbles:true}))');
  await wait(() => code(main, 'document.querySelector(".collection-tools > span")?.textContent === "175 项"'), '标签筛选');
  assert.equal(await code(main, 'document.querySelectorAll(".item-card.task").length'), 50);
  await code(main, 'document.querySelector("[aria-label=按标签筛选]").value=""; document.querySelector("[aria-label=按标签筛选]").dispatchEvent(new Event("change",{bubbles:true}))');

  await code(main, `document.querySelectorAll('.sidebar nav button')[3].click()`);
  await wait(() => code(main, '!!document.querySelector(".calendar-days")'), '月历');
  await code(main, 'document.querySelector(".calendar-controls button").click()');
  for (const date of dateKeys) {
    await code(main, `(() => { const day=[...document.querySelectorAll('.calendar-days button')].find(button=>button.getAttribute('aria-label')?.startsWith(${JSON.stringify(date)})); if(!day)throw Error('月历缺少日期 '+${JSON.stringify(date)}); day.click(); })()`);
  }
  await wait(() => code(main, 'document.querySelectorAll(".calendar-day-panel").length === 3'), '多日期任务面板');
  const calendarState = await code(main, '({selected:document.querySelectorAll(".calendar-days button[aria-pressed=true]").length,panels:document.querySelectorAll(".calendar-day-panel").length,days:[...document.querySelectorAll(".calendar-panel-heading h2")].map(h=>h.textContent)})');
  assert.equal(calendarState.selected, 3); assert.equal(calendarState.panels, 3);
  assert.ok(calendarState.days.every(text => dateKeys.some(date => text.includes(date))));
  await capture(main, 'workflow-calendar-multiple.png');

  await code(main, `window.pinboard.updateItem(${JSON.stringify(fixture[0].id)}, {completed:true})`);
  await code(main, nav('任务'));
  await wait(() => code(main, '!!document.querySelector(".task-list")'), '任务列表');
  await code(main, 'document.querySelector(".tabs button:nth-child(3)").click()');
  await wait(() => code(main, 'document.querySelector(".tabs button[aria-pressed=true]")?.textContent === "已归档"'), '已归档筛选');
  assert.equal(await code(main, 'document.querySelectorAll(".item-card.task").length'), 6, '完成即进入归档列表');
  await code(main, `window.pinboard.updateItem(${JSON.stringify(fixture[0].id)}, {completed:false})`);
  await wait(() => code(main, 'document.querySelectorAll(".item-card.task").length === 5'), '恢复未完成任务');

  await code(main, nav('便笺'));
  await wait(() => code(main, '!!document.querySelector(".item-card.note")'), '便笺列表');
  await code(main, `window.pinboard.pinItem(${JSON.stringify(note.id)})`);
  const floating = await wait(() => BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('?note=')), 'Markdown 悬浮窗口');
  await wait(() => code(floating, '!!document.querySelector(".floating-markdown-body [contenteditable=true]")'), 'Markdown 编辑器');
  floating.showInactive();
  await code(floating, 'document.querySelector(".compact-preview")?.click()');
  await wait(() => code(floating, 'document.querySelector(".floating").classList.contains("expanded")'), '展开便笺');
  await code(floating, `(() => { const leaf=[...document.querySelectorAll('.floating-markdown-body [contenteditable=true]')].find(el=>el.textContent==='Strong text'); if(!leaf)throw Error('找不到粗体文本叶子'); leaf.textContent='Edited strong text'; leaf.dispatchEvent(new Event('input',{bubbles:true})); leaf.dispatchEvent(new FocusEvent('blur',{bubbles:true})); })()`);
  await wait(() => JSON.parse(fs.readFileSync(path.join(directory, 'database.json'), 'utf8')).items.some(item => item.id === note.id && item.body.includes('Edited strong text')), 'Markdown 草稿保存');
  const edited = JSON.parse(fs.readFileSync(path.join(directory, 'database.json'), 'utf8')).items.find(item => item.id === note.id).body;
  assert.match(edited, /^# Workflow heading/m, '标题格式应保留');
  assert.match(edited, /\*\*Edited strong text\*\*/, '粗体格式应保留');
  assert.match(edited, /- List item/, '列表格式应保留');
  await capture(floating, 'workflow-markdown.png');
  await code(floating, 'document.querySelector("[aria-label=取消固定并关闭]").click()');
  await wait(() => floating.isDestroyed(), '关闭并卸载便笺');
  const disk = JSON.parse(fs.readFileSync(path.join(directory, 'database.json'), 'utf8'));
  assert.ok(disk.items.some(item => item.id === note.id && item.body === edited), '关闭后 Markdown 内容应写入磁盘');
  fs.writeFileSync(path.join(directory, 'workflow-result.json'), JSON.stringify({ passed: true, taskCount: 355, completedFixtureTasks: 5, minimumWindow: `${minimumBounds.width}x${minimumBounds.height}`, screenshots: ['workflow-list-bottom.png','workflow-calendar-multiple.png','workflow-markdown.png'], markdown: edited }, null, 2));
  console.log(`工作流 smoke 通过。独立测试数据和截图：${directory}`);
  app.quit();
})().catch(error => { console.error(error); app.exit(1); });
