import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import path from 'node:path';
import { createInterface } from 'node:readline';
import type { BrowserWindow } from 'electron';
import { desktopNativeSource } from './desktop-host-native';

export type MainDisplayMode = 'window' | 'desktop';
export interface DesktopInspection { attached: boolean; windowAlive: boolean; parent: string; host: string; hostPid: number }
interface DesktopRecovery { handle: string; pid: number; style: number; exStyle: number; left: number; top: number; width: number; height: number }

/** DPI is fixed when an HWND is born. Never change the process DPI or an existing
 * window: scope this synchronous context change to creation of our main HWND. */
export function createDesktopCompatibleWindow<T>(create: () => T): T {
  if (process.platform !== 'win32') return create();
  let restore: (() => void) | undefined;
  try {
    const koffi = require('koffi') as typeof import('koffi');
    const api = koffi.load('user32.dll');
    const find = api.func('intptr_t __stdcall FindWindowExW(intptr_t, intptr_t, str16, str16)');
    const visible = api.func('bool __stdcall IsWindowVisible(intptr_t)');
    const context = api.func('intptr_t __stdcall GetWindowDpiAwarenessContext(intptr_t)');
    const set = api.func('intptr_t __stdcall SetThreadDpiAwarenessContext(intptr_t)');
    for (const cls of ['Progman', 'WorkerW']) {
      let candidate: number | bigint = 0;
      while ((candidate = find(0, candidate, cls, null))) {
        if (!visible(candidate) || !find(candidate, 0, 'SHELLDLL_DefView', null)) continue;
        const dpi = context(candidate);
        if (!dpi) continue;
        const previous = set(dpi);
        if (!previous) continue;
        restore = () => { set(previous); };
        break;
      }
      if (restore) break;
    }
  } catch { /* Normal window remains available when native DPI APIs are absent. */ }
  try { return create(); }
  finally { restore?.(); }
}

/** Async RPC keeps Add-Type and Win32 calls out of Electron's startup/UI thread. */
export class DesktopHost {
  private child: ChildProcessWithoutNullStreams | null = null;
  private sequence = 0;
  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  private startup: Promise<void> | null = null;
  private monitor: ReturnType<typeof setInterval> | null = null;
  private checking = false;
  private recovering: Promise<void> | null = null;
  private disposed = false;
  private closing = false;
  private recovery: DesktopRecovery | null = null;
  constructor(private onLost: (reason: string) => Promise<void> | void) {}

  private start(): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('桌面辅助进程已关闭。'));
    if (process.platform !== 'win32') return Promise.reject(new Error('桌面嵌入仅支持 Windows。'));
    if (this.startup) return this.startup;
    const script = `$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
Add-Type -TypeDefinition @'
${desktopNativeSource}
'@
[Console]::WriteLine('{"ready":true}')
while ($null -ne ($line = [Console]::ReadLine())) {
  $request = $null
  try {
    $request = $line | ConvertFrom-Json
    switch ($request.action) {
      'prepare' { $value = [PinboardDesktop]::Prepare([string]$request.handle, [uint32]$request.pid) }
      'attach' { $value = [PinboardDesktop]::Attach([string]$request.handle, [uint32]$request.pid) }
      'inspect' { $value = [PinboardDesktop]::Inspect() }
      'restore' { $value = [PinboardDesktop]::Restore() }
      'recover' { $value = [PinboardDesktop]::Recover([string]$request.handle, [uint32]$request.pid, [uint32]$request.style, [uint32]$request.exStyle, [int]$request.left, [int]$request.top, [int]$request.width, [int]$request.height) }
      'show' { $value = [PinboardDesktop]::Show() }
      default { throw '未知桌面操作。' }
    }
    [Console]::WriteLine((@{ id=$request.id; value=($value | ConvertFrom-Json) } | ConvertTo-Json -Compress))
  } catch { [Console]::WriteLine((@{ id=$request.id; error=$_.Exception.GetBaseException().Message } | ConvertTo-Json -Compress)) }
}
} catch { [Console]::WriteLine((@{ fatal=$_.Exception.GetBaseException().Message } | ConvertTo-Json -Compress)) }
finally { try { [PinboardDesktop]::Restore() | Out-Null } catch {} }
`;
    this.startup = new Promise((resolve, reject) => {
      // Use the Windows system binary, never a PATH-provided powershell executable.
      const executable = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
      const child = spawn(executable, ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], { windowsHide: true, stdio: 'pipe' });
      this.child = child;
      let ready = false;
      let failed = false;
      const timer = setTimeout(() => { reject(new Error('桌面能力检测超时。')); this.stop(); }, 12_000);
      const fail = (error: Error) => {
        if (failed) return;
        failed = true;
        clearTimeout(timer);
        if (!ready) reject(error);
        if (this.child !== child) return;
        for (const job of this.pending.values()) { clearTimeout(job.timer); job.reject(error); }
        this.pending.clear();
        if (this.child === child) { this.child = null; this.startup = null; }
        if (ready && !this.disposed && !this.closing && this.recovery) void this.lost('桌面辅助进程已停止，已退出桌面模式。');
      };
      child.on('error', fail);
      child.on('exit', () => fail(new Error('桌面辅助进程已退出。')));
      child.stdin.on('error', fail);
      child.stderr.resume();
      createInterface({ input: child.stdout }).on('line', line => {
        try {
          const message = JSON.parse(line);
          if (message.ready) { ready = true; clearTimeout(timer); resolve(); return; }
          if (message.fatal) { fail(new Error(String(message.fatal))); return; }
          const job = this.pending.get(message.id);
          if (!job) return;
          clearTimeout(job.timer); this.pending.delete(message.id);
          if (message.error) job.reject(new Error(String(message.error))); else job.resolve(message.value);
        } catch { /* Ignore non-protocol diagnostic lines. */ }
      });
    });
    return this.startup;
  }

  private async request<T>(action: string, extra: Record<string, unknown> = {}): Promise<T> {
    await this.start();
    const child = this.child;
    if (!child || child.killed || !child.stdin.writable) throw new Error('桌面辅助进程不可用。');
    return new Promise<T>((resolve, reject) => {
      const id = ++this.sequence;
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('桌面操作超时。')); this.stop(); }, 5000);
      this.pending.set(id, { resolve: value => resolve(value as T), reject, timer });
      child.stdin.write(JSON.stringify({ id, action, ...extra }) + '\n', error => {
        if (error) { clearTimeout(timer); this.pending.delete(id); reject(error); }
      });
    });
  }

  async attach(window: BrowserWindow): Promise<DesktopInspection> {
    const handle = window.getNativeWindowHandle();
    const value = handle.length >= 8 ? handle.readBigUInt64LE().toString() : handle.readUInt32LE().toString();
    // Persist before any mutation, including an interrupted attach RPC.
    this.recovery = await this.request<DesktopRecovery>('prepare', { handle: value, pid: process.pid });
    const inspection = await this.request<DesktopInspection>('attach', { handle: value, pid: process.pid });
    if (!inspection.attached || inspection.parent !== inspection.host) throw new Error('桌面父窗口验证失败。');
    this.monitor = setInterval(() => { void this.check(); }, 2000);
    this.monitor.unref();
    return inspection;
  }
  inspect() { return this.request<DesktopInspection>('inspect'); }
  show() { return this.request<DesktopInspection>('show'); }
  async restore() {
    if (this.monitor) clearInterval(this.monitor);
    this.monitor = null;
    if (this.recovery) {
      await this.request('recover', { ...this.recovery });
      this.recovery = null;
    } else if (this.child) await this.request('restore');
  }
  private async check() {
    if (this.checking || this.disposed) return;
    this.checking = true;
    try { if (!(await this.inspect()).attached) await this.lost('Windows 桌面宿主已变化，已恢复普通窗口；可重新选择桌面模式。'); }
    catch (error) { await this.lost(error instanceof Error ? error.message : String(error)); }
    finally { this.checking = false; }
  }
  private lost(reason: string) {
    if (this.recovering) return this.recovering;
    if (this.monitor) clearInterval(this.monitor);
    this.monitor = null;
    this.recovering = Promise.resolve(this.onLost(reason)).finally(() => { this.recovering = null; });
    return this.recovering;
  }
  private stop() {
    const child = this.child;
    if (child && !child.killed) child.stdin.end(); // finally restores our HWND before exiting.
  }
  async dispose() {
    this.closing = true;
    try { await this.restore(); } finally { this.disposed = true; this.stop(); }
  }
}
