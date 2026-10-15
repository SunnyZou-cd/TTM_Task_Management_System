// Runs only in a hidden, on-demand helper. Explorer windows are read, never altered.
export const desktopNativeSource = String.raw`
using System;
using System.Text;
using System.Diagnostics;
using System.Runtime.InteropServices;
public static class PinboardDesktop {
  delegate bool EnumProc(IntPtr hwnd, IntPtr param);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc callback, IntPtr param);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder text, int count);
  [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hwnd);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
  [DllImport("user32.dll")] static extern IntPtr GetParent(IntPtr hwnd);
  [DllImport("user32.dll", SetLastError=true)] static extern IntPtr SetParent(IntPtr hwnd, IntPtr parent);
  [DllImport("user32.dll", EntryPoint="GetWindowLongW")] static extern int GetWindowLong32(IntPtr hwnd, int index);
  [DllImport("user32.dll", EntryPoint="SetWindowLongW", SetLastError=true)] static extern int SetWindowLong32(IntPtr hwnd, int index, int value);
  [DllImport("user32.dll", EntryPoint="SetWindowLongPtrW", SetLastError=true)] static extern IntPtr SetWindowLong64(IntPtr hwnd, int index, IntPtr value);
  [DllImport("kernel32.dll", EntryPoint="SetLastError")] static extern void ClearError(uint value);
  [DllImport("user32.dll")] static extern IntPtr GetWindowDpiAwarenessContext(IntPtr hwnd);
  [DllImport("user32.dll")] static extern int GetAwarenessFromDpiAwarenessContext(IntPtr context);
  [DllImport("user32.dll")] static extern bool AreDpiAwarenessContextsEqual(IntPtr a, IntPtr b);
  [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
  [DllImport("user32.dll")] static extern bool ScreenToClient(IntPtr hwnd, ref Point point);
  [DllImport("user32.dll", SetLastError=true)] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int width, int height, uint flags);
  [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hwnd, int command);
  [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hwnd, uint message, IntPtr wparam, IntPtr lparam);
  [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] struct Rect { public int Left, Top, Right, Bottom; }
  static IntPtr child, host, view, previousParent;
  static uint childPid, hostPid, originalStyle, originalExStyle;
  static Rect originalRect;
  static bool attached;
  static string Class(IntPtr hwnd) { var name = new StringBuilder(128); GetClassName(hwnd, name, name.Capacity); return name.ToString(); }
  static uint Pid(IntPtr hwnd) { uint pid; GetWindowThreadProcessId(hwnd, out pid); return pid; }
  static void Own(IntPtr hwnd, uint pid) {
    if (!IsWindow(hwnd) || Pid(hwnd) != pid) throw new InvalidOperationException("目标窗口不属于 Pinboard 主进程。");
  }
  static void Style(IntPtr hwnd, int index, uint value) {
    ClearError(0);
    IntPtr result = IntPtr.Size == 8 ? SetWindowLong64(hwnd, index, new IntPtr((long)value)) : new IntPtr(SetWindowLong32(hwnd, index, unchecked((int)value)));
    if (result == IntPtr.Zero && Marshal.GetLastWin32Error() != 0) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
  }
  static bool DesktopValid() {
    if (!IsWindow(host) || !IsWindow(view) || Pid(host) != hostPid || GetParent(view) != host) return false;
    return (Class(host) == "WorkerW" || Class(host) == "Progman") && Class(view) == "SHELLDLL_DefView";
  }
  static void Discover() {
    host = IntPtr.Zero; view = IntPtr.Zero;
    EnumWindows((candidate, unused) => {
      string cls = Class(candidate);
      if (cls != "WorkerW" && cls != "Progman") return true;
      IntPtr shellView = FindWindowEx(candidate, IntPtr.Zero, "SHELLDLL_DefView", null);
      if (shellView == IntPtr.Zero || !IsWindowVisible(candidate)) return true;
      uint pid = Pid(candidate);
      try { if (!string.Equals(Process.GetProcessById((int)pid).ProcessName, "explorer", StringComparison.OrdinalIgnoreCase)) return true; }
      catch { return true; }
      host = candidate; view = shellView; hostPid = pid; return false;
    }, IntPtr.Zero);
    if (host == IntPtr.Zero) throw new InvalidOperationException("未找到可用的 Windows Explorer 桌面图标宿主。");
  }
  public static string Prepare(string handle, uint pid) {
    if (attached) throw new InvalidOperationException("窗口已进入桌面模式。");
    child = new IntPtr(long.Parse(handle)); childPid = pid; Own(child, childPid);
    Discover();
    IntPtr dpi = GetWindowDpiAwarenessContext(child);
    if (dpi == IntPtr.Zero || !AreDpiAwarenessContextsEqual(dpi, GetWindowDpiAwarenessContext(host)))
      throw new InvalidOperationException("Pinboard 与 Explorer 的 DPI 模式不同，已保留普通窗口，避免跨进程 DPI 重置。窗口=" + dpi.ToInt64() + "/" + GetAwarenessFromDpiAwarenessContext(dpi) + "，桌面=" + GetWindowDpiAwarenessContext(host).ToInt64() + "/" + GetAwarenessFromDpiAwarenessContext(GetWindowDpiAwarenessContext(host)));
    previousParent = GetParent(child);
    if (previousParent != IntPtr.Zero) throw new InvalidOperationException("该窗口已有父窗口，不能安全嵌入桌面。");
    originalStyle = unchecked((uint)GetWindowLong32(child, -16)); originalExStyle = unchecked((uint)GetWindowLong32(child, -20));
    IntPtr previousDpi = SetThreadDpiAwarenessContext(dpi);
    try { if (!GetWindowRect(child, out originalRect)) throw new InvalidOperationException("无法读取原窗口位置。"); }
    finally { if (previousDpi != IntPtr.Zero) SetThreadDpiAwarenessContext(previousDpi); }
    return "{\"handle\":\"" + handle + "\",\"pid\":" + pid + ",\"style\":" + originalStyle + ",\"exStyle\":" + originalExStyle + ",\"left\":" + originalRect.Left + ",\"top\":" + originalRect.Top + ",\"width\":" + (originalRect.Right-originalRect.Left) + ",\"height\":" + (originalRect.Bottom-originalRect.Top) + "}";
  }
  public static string Attach(string handle, uint pid) {
    Prepare(handle, pid);
    IntPtr oldDpi = SetThreadDpiAwarenessContext(GetWindowDpiAwarenessContext(child));
    try {
      if (!GetWindowRect(child, out originalRect)) throw new InvalidOperationException("无法读取原窗口位置。");
      Point location = new Point { X=originalRect.Left, Y=originalRect.Top };
      if (!ScreenToClient(host, ref location)) throw new InvalidOperationException("无法计算桌面位置。");
      attached = true; // Any subsequent failure must restore styles and parent.
      Style(child, -16, (originalStyle & ~0x80000000U) | 0x40000000U | 0x04000000U);
      Style(child, -20, (originalExStyle & ~0x00040008U) | 0x00000080U);
      ClearError(0); SetParent(child, host);
      if (GetParent(child) != host) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "桌面嵌入失败。");
      if (!SetWindowPos(child, IntPtr.Zero, location.X, location.Y, originalRect.Right-originalRect.Left, originalRect.Bottom-originalRect.Top, 0x0020U | 0x0010U))
        throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
      // Initialize UI state only on our window (WM_CHANGEUISTATE, UIS_INITIALIZE).
      SendMessage(child, 0x0127U, new IntPtr(3), IntPtr.Zero);
      return Inspect();
    } catch { Restore(); throw; }
    finally { if (oldDpi != IntPtr.Zero) SetThreadDpiAwarenessContext(oldDpi); }
  }
  public static string Inspect() {
    bool own = IsWindow(child) && Pid(child) == childPid;
    bool healthy = attached && own && DesktopValid() && GetParent(child) == host;
    return "{\"attached\":" + (healthy ? "true" : "false") + ",\"windowAlive\":" + (own ? "true" : "false") + ",\"parent\":\"" + (own ? GetParent(child).ToInt64().ToString() : "0") + "\",\"host\":\"" + host.ToInt64().ToString() + "\",\"hostPid\":" + hostPid + "}";
  }
  public static string Restore() {
    if (!attached) return "{\"restored\":true}";
    if (!IsWindow(child) || Pid(child) != childPid) { attached = false; return "{\"restored\":true,\"windowAlive\":false}"; }
    Own(child, childPid);
    IntPtr oldDpi = SetThreadDpiAwarenessContext(GetWindowDpiAwarenessContext(child));
    try {
      // Never restore a stale Explorer parent after it has restarted.
      IntPtr parent = previousParent != IntPtr.Zero && IsWindow(previousParent) ? previousParent : IntPtr.Zero;
      ClearError(0); SetParent(child, parent);
      Style(child, -16, originalStyle); Style(child, -20, originalExStyle);
      if (GetParent(child) != parent) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "无法恢复普通窗口。");
      if (!SetWindowPos(child, new IntPtr(-2), originalRect.Left, originalRect.Top, originalRect.Right-originalRect.Left, originalRect.Bottom-originalRect.Top, 0x0020U | 0x0010U))
        throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
      attached = false;
      return "{\"restored\":true,\"windowAlive\":true}";
    } finally { if (oldDpi != IntPtr.Zero) SetThreadDpiAwarenessContext(oldDpi); }
  }
  // The Electron parent retains this snapshot, so a replacement helper can recover
  // its own HWND even when the original helper terminated before its finally ran.
  public static string Recover(string handle, uint pid, uint style, uint exStyle, int left, int top, int width, int height) {
    child = new IntPtr(long.Parse(handle)); childPid = pid; Own(child, childPid);
    previousParent = IntPtr.Zero; originalStyle = style; originalExStyle = exStyle;
    originalRect = new Rect { Left=left, Top=top, Right=left+width, Bottom=top+height };
    attached = true;
    return Restore();
  }
  public static string Show() {
    Own(child, childPid);
    if (!attached || !DesktopValid()) throw new InvalidOperationException("桌面宿主已失效。");
    ShowWindow(child, 5);
    SetWindowPos(child, IntPtr.Zero, 0, 0, 0, 0, 0x0001U | 0x0002U | 0x0010U);
    return Inspect();
  }
}
`;
