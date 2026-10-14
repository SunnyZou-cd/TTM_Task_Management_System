import { app, BrowserWindow, dialog, ipcMain } from 'electron';
import path from 'node:path';
import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
import type { ObsidianBridge } from './obsidian';
import { AppService } from './service';
import { atomicWrite, persistence } from './persistence';
import { WindowManager } from './windows';

if (process.env.PINBOARD_DATA_DIR) app.setPath('userData', path.resolve(process.env.PINBOARD_DATA_DIR));
let windows: WindowManager | undefined;
let service: AppService;
const lock = app.requestSingleInstanceLock();
if (!lock) app.quit();
else {
  let preparingQuit = false;
  app.on('second-instance', () => windows?.openMain());
  app.on('before-quit', event => {
    if (!windows || windows.quitting) return;
    event.preventDefault();
    if (preparingQuit) return;
    preparingQuit = true;
    void windows.prepareQuit().then(success => {
      preparingQuit = false;
      if (success && windows) { windows.quitting = true; app.quit(); }
    }).catch(error => { preparingQuit = false; console.error('无法保存便笺并退出', error); });
  });
  app.on('window-all-closed', () => { if (!windows?.notes.size) app.quit(); });
  app.on('activate', () => windows?.openMain());
  void app.whenReady().then(async () => {
    const directory = app.getPath('userData');
    windows = new WindowManager(directory, id => service.unpinItem(id));
    let initialized = false;
    service = new AppService({
      ...persistence(directory),
      broadcast: snapshot => { if (initialized) windows?.broadcast(snapshot); },
      pinsChanged: ids => { if (initialized) windows?.pinsChanged(ids); },
      async exportJson(value) {
        const result = await dialog.showSaveDialog({ title: '导出 Pinboard 数据', defaultPath: 'Pinboard-backup.json', filters: [{ name: 'JSON 数据', extensions: ['json'] }] });
        if (result.canceled || !result.filePath) return false;
        atomicWrite(result.filePath, value);
        return true;
      },
    });
    await service.initialize();
    initialized = true;
    let restoring: Promise<void> = Promise.resolve();
    let workspaceQueue: Promise<unknown> = Promise.resolve();
    const workspaceOperation = <T,>(fn: () => Promise<T>): Promise<T> => {
      const result = workspaceQueue.then(async () => { await restoring; return fn(); });
      workspaceQueue = result.catch(() => {});
      return result;
    };
    let obsidian: ObsidianBridge | undefined;
    const getObsidian = async () => {
      if (!obsidian) {
        const { ObsidianBridge } = await import('./obsidian');
        const file = path.join(directory, 'obsidian-links.json');
        obsidian = new ObsidianBridge({
          loadState: () => fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : null,
          saveState: state => atomicWrite(file, JSON.stringify(state, null, 2)),
          getScope: () => service.getWorkspaceKey(),
          getItems: () => service.getSnapshot().items,
          createItem: input => service.createItem(input),
          updateItem: (id, patch) => service.updateItem(id, patch),
        });
      }
      return obsidian;
    };
    let selection: { token: string; root: string; scope: string } | null = null;
    ipcMain.on('pinboard:close-result', (event, requestId: unknown, success: unknown) => {
      if (!windows?.owns(event.sender) || !event.senderFrame || event.senderFrame !== event.sender.mainFrame || !windows.trustedUrl(event.senderFrame.url)) return;
      if (typeof requestId === 'string' && typeof success === 'boolean') windows.closeResult(event.sender, requestId, success);
    });
    const methods = ['getSnapshot', 'createItem', 'updateItem', 'deleteItem', 'pinItem', 'unpinItem', 'getCloudConfig', 'setCloudConfig', 'sendOtp', 'verifyOtp', 'signOut', 'syncNow', 'exportData'] as const;
    function register(name: string, callback: (event: Electron.IpcMainInvokeEvent, ...args: unknown[]) => unknown) {
      ipcMain.handle(`pinboard:${name}`, async (event, ...args: unknown[]) => {
        if (!windows?.owns(event.sender) || !event.senderFrame || event.senderFrame !== event.sender.mainFrame || !windows.trustedUrl(event.senderFrame.url)) throw new Error('页面无权操作本地数据。');
        try { return await callback(event, ...args); }
        catch (error) { throw new Error(error instanceof Error ? error.message : '操作失败，请重试。'); }
      });
    }
    for (const method of methods) register(method, (_event, ...args) => {
      // AppService validates all domain inputs; the IPC boundary restricts the allowed methods.
      const action = service[method] as (...values: unknown[]) => unknown;
      if (['setCloudConfig', 'verifyOtp', 'signOut'].includes(method)) return workspaceOperation(async () => action.apply(service, args));
      return action.apply(service, args);
    });
    register('chooseObsidianFolder', () => workspaceOperation(async () => {
      const chosen = await dialog.showOpenDialog({ title: '选择 Obsidian 笔记文件夹', properties: ['openDirectory'] });
      if (chosen.canceled || !chosen.filePaths[0]) return null;
      const bridge = await getObsidian();
      const preview = await bridge.preview(chosen.filePaths[0]);
      selection = { token: randomUUID(), root: chosen.filePaths[0], scope: service.getWorkspaceKey() };
      return { ...preview, token: selection.token };
    }));
    register('importObsidian', (_event, token) => workspaceOperation(async () => {
      if (!selection || typeof token !== 'string' || token !== selection.token || selection.scope !== service.getWorkspaceKey()) throw new Error('目录选择已失效，请重新选择并预览。');
      return (await getObsidian()).import(selection.root);
    }));
    register('syncObsidian', () => workspaceOperation(async () => (await getObsidian()).sync()));
    register('openMain', () => windows?.openMain());
    register('setAlwaysOnTop', (_event, id, enabled) => {
      if (typeof id !== 'string' || typeof enabled !== 'boolean') throw new Error('便笺置顶参数不正确。');
      windows?.setAlwaysOnTop(id, enabled);
    });
    register('setNoteExpanded', (event, id, expanded) => {
      if (typeof id !== 'string' || typeof expanded !== 'boolean' || windows?.notes.get(id)?.webContents !== event.sender) throw new Error('只能调整当前便笺窗口。');
      windows?.setNoteExpanded(id, expanded);
    });
    register('windowControl', (event, action) => {
      const window = BrowserWindow.fromWebContents(event.sender);
      if (!window) throw new Error('窗口已关闭。');
      if (action === 'minimize') window.minimize();
      else if (action === 'close') window.close();
      else if (action === 'quit') app.quit();
      else throw new Error('不支持的窗口操作。');
    });
    windows.createTray();
    windows.openMain();
    windows.pinsChanged((await service.getSnapshot()).pinnedIds);
    restoring = service.resumeCloudSession().catch(error => { console.error('云端会话恢复失败', error); });
  }).catch(error => {
    dialog.showErrorBox('Pinboard 无法启动', error instanceof Error ? error.message : String(error));
    app.quit();
  });
}
