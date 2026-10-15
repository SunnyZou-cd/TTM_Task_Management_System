import { app, BrowserWindow, dialog, Menu, nativeImage, screen, Tray } from 'electron';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { atomicWrite } from './persistence';
import type { AppSnapshot } from '../shared/types';
import { createDesktopCompatibleWindow, DesktopHost, type MainDisplayMode } from './desktop-host';

export class WindowManager {
  main: BrowserWindow | null = null;
  notes = new Map<string, BrowserWindow>();
  quitting = false;
  private tray: Tray | null = null;
  private bounds: Record<string, Electron.Rectangle> = {};
  private compact = new Map<string, Electron.Rectangle>();
  private boundsFile: string;
  private removed = new Set<number>();
  private loaded = new Set<number>();
  private closing = new Set<number>();
  private pending = new Map<string, { contents: Electron.WebContents; finish: (success: boolean) => void }>();
  private guards = new Map<number, Promise<boolean>>();
  private desktopHost: DesktopHost | null = null;
  private displayMode: MainDisplayMode = 'window';
  private displayModeReason = '';
  private displayModeQueue: Promise<unknown> = Promise.resolve();
  private windowPlacement: { bounds: Electron.Rectangle; maximized: boolean; fullscreen: boolean; alwaysOnTop: boolean; visible: boolean } | null = null;
  readonly rendererUrl: string;
  constructor(directory: string, private unpin: (id: string) => Promise<void>) {
    this.boundsFile = path.join(directory, 'window-bounds.json');
    this.rendererUrl = process.env.PINBOARD_DEV_URL || pathToFileURL(path.join(__dirname, '../../dist/index.html')).href;
    if (process.env.PINBOARD_DEV_URL) {
      const url = new URL(this.rendererUrl);
      if (!['http:', 'https:'].includes(url.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) throw new Error('开发页面必须使用本机地址。');
    }
    if (fs.existsSync(this.boundsFile)) {
      try {
        const parsed: unknown = JSON.parse(fs.readFileSync(this.boundsFile, 'utf8'));
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('格式错误');
        this.bounds = parsed as Record<string, Electron.Rectangle>;
      }
      catch { throw new Error('窗口位置文件损坏，原文件已保留，请备份 window-bounds.json 后重试。'); }
    }
    screen.on('display-removed', () => this.reposition());
  }
  trustedUrl(value: string) {
    try {
      const actual = new URL(value), expected = new URL(this.rendererUrl);
      return actual.origin === expected.origin && actual.protocol === expected.protocol && actual.pathname === expected.pathname;
    } catch { return false; }
  }
  owns(contents: Electron.WebContents) {
    return [this.main, ...this.notes.values()].some(w => w && !w.isDestroyed() && w.webContents === contents);
  }
  closeResult(contents: Electron.WebContents, requestId: string, success: boolean) {
    const pending = this.pending.get(requestId);
    if (pending?.contents === contents) pending.finish(success);
  }
  private reportCloseFailure() {
    const message = '便笺内容尚未保存，已取消关闭。请重试保存后再关闭应用。';
    if (process.env.PINBOARD_TEST_MODE === '1') console.error(message);
    else dialog.showErrorBox('无法关闭便笺', message);
  }
  guard(window: BrowserWindow): Promise<boolean> {
    if (window.isDestroyed() || !this.loaded.has(window.id)) return Promise.resolve(true);
    const existing = this.guards.get(window.id);
    if (existing) return existing;
    const requestId = randomUUID();
    const result = new Promise<boolean>(resolve => {
      const finish = (success: boolean) => { clearTimeout(timer); this.pending.delete(requestId); resolve(success); };
      const timer = setTimeout(() => finish(false), 20_000);
      this.pending.set(requestId, { contents: window.webContents, finish });
      window.webContents.send('pinboard:before-close', requestId);
    }).then(success => { this.guards.delete(window.id); if (!success) this.reportCloseFailure(); return success; });
    this.guards.set(window.id, result);
    return result;
  }
  async prepareQuit() {
    return (await Promise.all([...this.notes.values()].map(window => this.guard(window)))).every(Boolean);
  }
  private clamp(value?: Electron.Rectangle, minimumHeight = 220): Electron.Rectangle {
    const candidate = value && [value.x, value.y, value.width, value.height].every(Number.isFinite)
      ? value : { x: screen.getPrimaryDisplay().workArea.x + 70, y: screen.getPrimaryDisplay().workArea.y + 70, width: 340, height: 380 };
    const area = screen.getDisplayMatching(candidate).workArea;
    const width = Math.min(Math.max(260, candidate.width), area.width);
    const height = Math.min(Math.max(minimumHeight, candidate.height), area.height);
    return { width, height, x: Math.max(area.x, Math.min(candidate.x, area.x + area.width - width)), y: Math.max(area.y, Math.min(candidate.y, area.y + area.height - height)) };
  }
  private make(noteId?: string) {
    const create = () => new BrowserWindow({
      ...(noteId ? this.clamp(this.bounds[noteId]) : { width: 1120, height: 780 }),
      minWidth: noteId ? 260 : 760, minHeight: noteId ? 220 : 560,
      title: noteId ? 'Pinboard 便笺' : 'Pinboard', frame: false, resizable: true,
      alwaysOnTop: !!noteId, show: false, backgroundColor: '#ffffff',
      webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true, backgroundThrottling: process.env.PINBOARD_TEST_MODE !== '1' },
    });
    const window = noteId ? create() : createDesktopCompatibleWindow(create);
    const contents = window.webContents;
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', (event, url) => { if (!this.trustedUrl(url)) event.preventDefault(); });
    window.webContents.on('will-redirect', (event, url) => { if (!this.trustedUrl(url)) event.preventDefault(); });
    window.webContents.on('will-attach-webview', event => event.preventDefault());
    window.webContents.on('did-finish-load', () => this.loaded.add(window.id));
    window.on('closed', () => {
      this.loaded.delete(window.id); this.closing.delete(window.id);
      for (const pending of this.pending.values()) if (pending.contents === contents) pending.finish(false);
    });
    window.setMenuBarVisibility(false);
    window.once('ready-to-show', () => { if (process.env.PINBOARD_TEST_MODE !== '1') window.show(); });
    const url = new URL(this.rendererUrl);
    if (noteId) url.searchParams.set('note', noteId);
    void window.loadURL(url.href);
    if (noteId) {
      const save = () => {
        if (window.isDestroyed()) return;
        const actual = window.getBounds(), expanded = this.compact.get(noteId);
        this.bounds[noteId] = expanded ? { ...expanded, x: actual.x, y: actual.y } : actual;
        if (expanded) this.compact.set(noteId, this.bounds[noteId]);
        try { atomicWrite(this.boundsFile, JSON.stringify(this.bounds)); }
        catch (error) { console.error('无法保存便笺位置', error); }
      };
      let pendingSave: ReturnType<typeof setTimeout> | undefined;
      const scheduleSave = () => { clearTimeout(pendingSave); pendingSave = setTimeout(save, 120); };
      window.on('move', scheduleSave); window.on('resize', scheduleSave);
      window.on('moved', save); window.on('resized', save);
      window.on('closed', () => clearTimeout(pendingSave));
      window.on('close', event => {
        save();
        if (!this.quitting && !this.removed.has(window.id)) {
          event.preventDefault();
          if (this.closing.has(window.id)) return;
          this.closing.add(window.id);
          void this.guard(window).then(success => success ? this.unpin(noteId) : undefined).catch(error => {
            if (process.env.PINBOARD_TEST_MODE === '1') console.error(error);
            else dialog.showErrorBox('无法关闭便笺', error instanceof Error ? error.message : String(error));
          }).finally(() => this.closing.delete(window.id));
        }
      });
      window.on('closed', () => { this.notes.delete(noteId); this.compact.delete(noteId); this.removed.delete(window.id); });
    }
    return window;
  }
  openMain() {
    if (this.main && !this.main.isDestroyed()) {
      if (process.env.PINBOARD_TEST_MODE !== '1') {
        if (this.displayMode === 'desktop' && this.desktopHost) void this.desktopHost.show().catch(error => this.recoverDesktop(String(error)));
        else { this.main.show(); this.main.restore(); this.main.focus(); }
      }
      return;
    }
    this.main = this.make();
    this.main.on('closed', () => {
      this.main = null;
      this.displayMode = 'window'; this.windowPlacement = null;
      const host = this.desktopHost; this.desktopHost = null;
      if (host) void host.dispose().catch(error => console.error('桌面辅助进程清理失败', error));
    });
  }
  getMainDisplayMode(): MainDisplayMode { return this.displayMode; }
  getMainDisplayModeReason() { return this.displayModeReason; }
  /** Requests are serialized so rapid settings changes cannot strand a child HWND. */
  setMainDisplayMode(mode: MainDisplayMode): Promise<MainDisplayMode> {
    if (mode !== 'window' && mode !== 'desktop') return Promise.reject(new Error('未知窗口显示模式。'));
    const operation = this.displayModeQueue.then(async () => {
      if (!this.main || this.main.isDestroyed()) this.openMain();
      const window = this.main!;
      if (mode === this.displayMode) return this.displayMode;
      this.displayModeReason = '';
      if (mode === 'window') { await this.recoverDesktop(); return this.displayMode; }
      this.windowPlacement = { bounds: window.getNormalBounds(), maximized: window.isMaximized(), fullscreen: window.isFullScreen(), alwaysOnTop: window.isAlwaysOnTop(), visible: window.isVisible() };
      if (window.isFullScreen()) window.setFullScreen(false);
      if (window.isMaximized()) window.unmaximize();
      if (window.isMinimized()) window.restore();
      window.setAlwaysOnTop(false);
      const host = new DesktopHost(reason => this.recoverDesktop(reason));
      this.desktopHost = host;
      try {
        await host.attach(window);
        if (window.isDestroyed() || this.main !== window || this.desktopHost !== host) throw new Error('主窗口或桌面连接已关闭。');
        window.setSkipTaskbar(true);
        this.displayMode = 'desktop';
        if (process.env.PINBOARD_TEST_MODE !== '1') await host.show();
        this.notifyDisplayMode();
      } catch (error) {
        await this.recoverDesktop(error instanceof Error ? error.message : String(error));
      }
      return this.displayMode;
    });
    this.displayModeQueue = operation.catch(() => undefined);
    return operation;
  }
  private notifyDisplayMode() {
    if (this.main && !this.main.isDestroyed()) this.main.webContents.send('pinboard:display-mode', { mode: this.displayMode, reason: this.displayModeReason });
  }
  private async recoverDesktop(reason = '') {
    const host = this.desktopHost;
    this.desktopHost = null;
    const placement = this.windowPlacement;
    this.windowPlacement = null;
    let failed = false;
    if (host) {
      try { await host.dispose(); }
      catch (error) { failed = true; console.error('恢复桌面窗口失败', error); }
    }
    this.displayMode = 'window'; this.displayModeReason = reason;
    // If a stale Explorer HWND was destroyed, recreate only our own BrowserWindow.
    if (failed && this.main && !this.main.isDestroyed()) { this.main.destroy(); }
    if (!this.main || this.main.isDestroyed()) {
      if (!this.quitting && placement) this.openMain();
    }
    const window = this.main;
    if (window && !window.isDestroyed() && placement) {
      window.setSkipTaskbar(false);
      window.setBounds(placement.bounds);
      window.setAlwaysOnTop(placement.alwaysOnTop);
      if (placement.maximized) window.maximize();
      if (placement.fullscreen) window.setFullScreen(true);
      if (process.env.PINBOARD_TEST_MODE !== '1' && placement.visible) window.show();
    }
    this.notifyDisplayMode();
  }
  pinsChanged(ids: string[]) {
    if (this.quitting) return;
    for (const [id, window] of this.notes) if (!ids.includes(id)) { this.removed.add(window.id); window.close(); }
    for (const id of ids) if (!this.notes.has(id)) this.notes.set(id, this.make(id));
  }
  broadcast(snapshot: AppSnapshot) {
    for (const window of [this.main, ...this.notes.values()]) if (window && !window.isDestroyed()) window.webContents.send('pinboard:snapshot', snapshot);
  }
  setAlwaysOnTop(id: string, enabled: boolean) {
    const window = this.notes.get(id);
    if (!window || window.isDestroyed()) throw new Error('该便笺窗口未打开。');
    if (typeof enabled !== 'boolean') throw new Error('置顶设置必须为开或关。');
    window.setAlwaysOnTop(enabled);
  }
  setNoteExpanded(id: string, expanded: boolean) {
    const window = this.notes.get(id);
    if (!window || window.isDestroyed()) throw new Error('该便笺窗口未打开。');
    if (typeof expanded !== 'boolean') throw new Error('展开设置必须为开或关。');
    const saved = this.compact.get(id);
    if (!expanded && !saved) {
      const bounds = window.getBounds();
      this.compact.set(id, bounds);
      window.setMinimumSize(260, 120);
      window.setBounds(this.clamp({ ...bounds, height: 120 }, 120));
      window.setResizable(false);
    } else if (expanded && saved) {
      // Keep the compact card's current location, but restore its full editor size.
      const location = window.getBounds();
      this.compact.delete(id);
      window.setResizable(true);
      window.setMinimumSize(260, 220);
      window.setBounds(this.clamp({ ...saved, x: location.x, y: location.y }));
    }
  }
  private reposition() {
    for (const [id, window] of this.notes) window.setBounds(this.clamp(window.getBounds(), this.compact.has(id) ? 120 : 220));
  }
  createTray() {
    if (process.env.PINBOARD_TEST_MODE === '1') return;
    const pixels = Buffer.alloc(16 * 16 * 4);
    for (let y = 2; y < 14; y++) for (let x = 3; x < 13; x++) {
      const offset = (y * 16 + x) * 4;
      pixels[offset] = 82; pixels[offset + 1] = 113; pixels[offset + 2] = 90; pixels[offset + 3] = 255;
    }
    this.tray = new Tray(nativeImage.createFromBitmap(pixels, { width: 16, height: 16 }));
    this.tray.setToolTip('Pinboard — 任务与便笺');
    this.tray.setContextMenu(Menu.buildFromTemplate([{ label: '打开 Pinboard', click: () => this.openMain() }, { type: 'separator' }, { label: '退出', click: () => app.quit() }]));
    this.tray.on('double-click', () => this.openMain());
  }
}
