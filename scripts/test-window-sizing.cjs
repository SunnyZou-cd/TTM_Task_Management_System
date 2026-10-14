const { app, ipcMain } = require('electron');
ipcMain.handle('pinboard:getSnapshot', () => ({ items: [], pinnedIds: [], sync: { configured: false, status: 'unconfigured', email: null, pending: 0, lastSyncedAt: null, error: null }, desktop: true }));
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const directory = fs.mkdtempSync(path.resolve('work/window-sizing-'));
app.setPath('userData', directory);
process.env.PINBOARD_TEST_MODE = '1';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
app.whenReady().then(async () => {
  const { WindowManager } = require('../dist-main/main/windows.js');
  const windows = new WindowManager(directory, async () => {});
  try {
    windows.pinsChanged(['test-note']);
    const note = windows.notes.get('test-note');
    await delay(500);
    note.setBounds({ x: 80, y: 80, width: 360, height: 420 }); await delay(250);
    windows.setNoteExpanded('test-note', false); await delay(250);
    assert.ok(Math.abs(note.getBounds().height - 120) <= 2, 'compact height allows native DPI rounding'); assert.equal(note.isResizable(), false);
    note.setPosition(120, 130); await delay(250);
    const stored = JSON.parse(fs.readFileSync(path.join(directory, 'window-bounds.json'), 'utf8'));
    assert.equal(stored['test-note'].height, 420); assert.equal(stored['test-note'].width, 360);
    windows.setNoteExpanded('test-note', true); await delay(250);
    assert.equal(note.getBounds().height, 420); assert.equal(note.getBounds().width, 360);
    assert.equal(note.getBounds().x, 120); assert.equal(note.isResizable(), true);
    windows.setNoteExpanded('test-note', true); assert.equal(note.getBounds().height, 420);
    windows.setNoteExpanded('test-note', false); await delay(250);
    assert.equal(JSON.parse(fs.readFileSync(path.join(directory, 'window-bounds.json'), 'utf8'))['test-note'].height, 420);
    console.log('Native compact/expand, moved bounds and durable expanded dimensions passed:', directory);
  } finally { windows.quitting = true; app.exit(); }
}).catch(error => { console.error(error); app.exit(1); });
