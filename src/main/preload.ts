import { contextBridge, ipcRenderer } from 'electron';
import type { AppSnapshot, PinboardAPI } from '../shared/types';

const api: PinboardAPI = {
  getSnapshot: () => ipcRenderer.invoke('pinboard:getSnapshot'),
  createItem: input => ipcRenderer.invoke('pinboard:createItem', input),
  updateItem: (id, patch) => ipcRenderer.invoke('pinboard:updateItem', id, patch),
  deleteItem: id => ipcRenderer.invoke('pinboard:deleteItem', id),
  pinItem: id => ipcRenderer.invoke('pinboard:pinItem', id),
  unpinItem: id => ipcRenderer.invoke('pinboard:unpinItem', id),
  setAlwaysOnTop: (id, enabled) => ipcRenderer.invoke('pinboard:setAlwaysOnTop', id, enabled),
  openMain: () => ipcRenderer.invoke('pinboard:openMain'),
  windowControl: action => ipcRenderer.invoke('pinboard:windowControl', action),
  getCloudConfig: () => ipcRenderer.invoke('pinboard:getCloudConfig'),
  setCloudConfig: config => ipcRenderer.invoke('pinboard:setCloudConfig', config),
  sendOtp: email => ipcRenderer.invoke('pinboard:sendOtp', email),
  verifyOtp: (email, token) => ipcRenderer.invoke('pinboard:verifyOtp', email, token),
  signOut: () => ipcRenderer.invoke('pinboard:signOut'),
  syncNow: () => ipcRenderer.invoke('pinboard:syncNow'),
  exportData: () => ipcRenderer.invoke('pinboard:exportData'),
  onCloseRequest(callback) {
    const listener = async (_event: Electron.IpcRendererEvent, requestId: unknown) => {
      if (typeof requestId !== 'string') return;
      let success = false;
      try { success = (await callback()) === true; } catch { /* Keep the window open on failed saves. */ }
      ipcRenderer.send('pinboard:close-result', requestId, success);
    };
    ipcRenderer.on('pinboard:before-close', listener);
    return () => ipcRenderer.removeListener('pinboard:before-close', listener);
  },
  subscribe(callback) {
    const listener = (_event: Electron.IpcRendererEvent, snapshot: AppSnapshot) => callback(snapshot);
    ipcRenderer.on('pinboard:snapshot', listener);
    return () => ipcRenderer.removeListener('pinboard:snapshot', listener);
  },
};
contextBridge.exposeInMainWorld('pinboard', api);
