import { app, BrowserWindow, dialog, ipcMain } from 'electron';
import path from 'node:path';
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
      return action.apply(service, args);
    });
    register('openMain', () => windows?.openMain());
    register('setAlwaysOnTop', (_event, id, enabled) => {
      if (typeof id !== 'string' || typeof enabled !== 'boolean') throw new Error('便笺置顶参数不正确。');
      windows?.setAlwaysOnTop(id, enabled);
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
  }).catch(error => {
    dialog.showErrorBox('Pinboard 无法启动', error instanceof Error ? error.message : String(error));
    app.quit();
  });
}
