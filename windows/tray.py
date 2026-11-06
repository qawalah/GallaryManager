"""The icon by the clock, drawn with nothing but Windows itself.

A program with no window needs somewhere to be seen, and somewhere to be
stopped from that is not Task Manager. This is that: an icon in the notification
area, a menu on right-click, a balloon the first time so you know where it went.

Why ctypes and not pystray or a GUI toolkit: the app is the standard library
plus optional extras, and the one thing a desktop program must never do is fail
to start because a package is missing. Everything a tray needs is five calls
into user32 and shell32 that have not changed since Windows 2000, so this
depends on nothing that pip could get wrong.

What the menu says and what each entry does is decided in `core/desktop.py`
(`tray_menu`), as data, so it is tested without Windows. This file only draws
it and hands back which entry was picked. It imports on any system - every
Windows call is made inside `Tray` - so the tests can at least load it.

The rules it follows, each one a bug avoided:

- The window and the message loop live on the thread that made them (the main
  one). The server runs on another.
- Removing the icon is done straight away, from whichever thread is quitting:
  an icon left behind by a program that has gone stays by the clock until the
  mouse crosses it.
- Explorer restarting takes every tray icon with it. Windows says so with a
  "TaskbarCreated" message, and the icon is put back.
- The menu is opened with the window in front and a WM_NULL after, or it does
  not close when you click elsewhere - a twenty-five-year-old Windows quirk.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

MUTEX_NAME = "Local\\PhotoManager.Desktop"

# Messages and flags, by their Windows names.
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_TRAY = WM_APP + 1

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_USER = 0x04

MF_STRING, MF_GRAYED, MF_CHECKED, MF_SEPARATOR = 0x0, 0x1, 0x8, 0x800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x2, 0x80, 0x100

IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
SM_CXSMICON, SM_CYSMICON = 49, 50
IDI_APPLICATION = 32512

MB_YESNO, MB_ICONWARNING, MB_ICONERROR = 0x4, 0x30, 0x10
MB_SETFOREGROUND, MB_TOPMOST = 0x10000, 0x40000
IDYES = 6

ERROR_ALREADY_EXISTS = 183
TICK_MS = 4000


def already_running() -> bool:
    """Is another copy of the program running for this Windows user?

    A named mutex rather than "is the port answering": a port can be busy with
    something else entirely, and a copy that is still starting up has not
    opened its port yet. The handle is kept open on purpose - closing it would
    let the next copy in - and Windows lets go of it when the process ends,
    however it ends.
    """
    if not sys.platform.startswith("win"):
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                      wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    _KEEP.append(handle)
    return bool(handle) and ctypes.get_last_error() == ERROR_ALREADY_EXISTS


_KEEP: list = []          # handles and callbacks that must outlive their call


def message(text: str, title: str = "Photo Manager", ask: bool = False,
            error: bool = False) -> bool:
    """A Windows message box. With `ask`, True when the answer was Yes.

    Used for the two things that cannot wait for the page: "are you sure" before
    a Quit that would stop a run, and "it could not start" when there is no page
    to say so on.
    """
    if not sys.platform.startswith("win"):
        return not ask
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                   wintypes.LPCWSTR, wintypes.UINT]
    user32.MessageBoxW.restype = ctypes.c_int
    flags = MB_SETFOREGROUND | MB_TOPMOST
    flags |= (MB_YESNO | MB_ICONWARNING) if ask else (MB_ICONERROR if error else 0)
    return user32.MessageBoxW(None, text, title, flags) == IDYES


class Tray:
    """One icon in the notification area, and its menu.

    `menu()` returns the entries to show, as `core.desktop.tray_menu` makes
    them. `picked(id)` is called with the chosen entry's id. `tip()` is asked
    every few seconds for the words under the mouse. All three run on the
    tray's own thread, so they must be quick.
    """

    def __init__(self, icon_path: str, menu, picked, tip=None,
                 title: str = "Photo Manager"):
        self.icon_path = icon_path
        self.menu, self.picked, self.tip = menu, picked, tip
        self.title = title
        self.hwnd = None
        self.hicon = None
        self._tip_now = ""
        self._added = False
        self._explorer_back = None
        self._last_click = 0.0
        self._bind()

    # ------------------------------------------------------------- the API

    def _bind(self) -> None:
        """Declare every call's types. On 64-bit Windows a handle passed
        without them is cut to 32 bits, and the crash comes later."""
        LRESULT = ctypes.c_ssize_t
        self.WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT),
                        ("lpfnWndProc", self.WNDPROC),
                        ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE),
                        ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE),
                        ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR),
                        ("lpszClassName", wintypes.LPCWSTR)]

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("hWnd", wintypes.HWND),
                        ("uID", wintypes.UINT),
                        ("uFlags", wintypes.UINT),
                        ("uCallbackMessage", wintypes.UINT),
                        ("hIcon", wintypes.HICON),
                        ("szTip", wintypes.WCHAR * 128),
                        ("dwState", wintypes.DWORD),
                        ("dwStateMask", wintypes.DWORD),
                        ("szInfo", wintypes.WCHAR * 256),
                        ("uVersion", wintypes.UINT),
                        ("szInfoTitle", wintypes.WCHAR * 64),
                        ("dwInfoFlags", wintypes.DWORD),
                        ("guidItem", GUID),
                        ("hBalloonIcon", wintypes.HICON)]

        self.WNDCLASSW, self.NOTIFYICONDATAW = WNDCLASSW, NOTIFYICONDATAW
        u = self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        s = self.shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        k = self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        H, UINT, INT = wintypes.HWND, wintypes.UINT, ctypes.c_int
        # A list, not a dict: ctypes function pointers cannot be hashed, so a
        # dict keyed by them fails on every Windows (found on a real PC).
        sig = [
            (u.RegisterClassW, [ctypes.POINTER(WNDCLASSW)], wintypes.ATOM),
            (u.CreateWindowExW, [wintypes.DWORD, wintypes.LPCWSTR,
                                 wintypes.LPCWSTR, wintypes.DWORD, INT, INT,
                                 INT, INT, H, wintypes.HMENU,
                                 wintypes.HINSTANCE, wintypes.LPVOID], H),
            (u.DefWindowProcW, [H, UINT, wintypes.WPARAM, wintypes.LPARAM],
                               LRESULT),
            (u.DestroyWindow, [H], wintypes.BOOL),
            (u.PostMessageW, [H, UINT, wintypes.WPARAM, wintypes.LPARAM],
                             wintypes.BOOL),
            (u.PostQuitMessage, [INT], None),
            (u.GetMessageW, [ctypes.POINTER(wintypes.MSG), H, UINT, UINT],
                            wintypes.BOOL),
            (u.TranslateMessage, [ctypes.POINTER(wintypes.MSG)], wintypes.BOOL),
            (u.DispatchMessageW, [ctypes.POINTER(wintypes.MSG)], LRESULT),
            (u.RegisterWindowMessageW, [wintypes.LPCWSTR], UINT),
            (u.CreatePopupMenu, [], wintypes.HMENU),
            (u.AppendMenuW, [wintypes.HMENU, UINT, ctypes.c_size_t,
                             wintypes.LPCWSTR], wintypes.BOOL),
            (u.SetMenuDefaultItem, [wintypes.HMENU, UINT, UINT], wintypes.BOOL),
            (u.TrackPopupMenu, [wintypes.HMENU, UINT, INT, INT, INT, H,
                                ctypes.c_void_p], INT),
            (u.DestroyMenu, [wintypes.HMENU], wintypes.BOOL),
            (u.GetCursorPos, [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            (u.SetForegroundWindow, [H], wintypes.BOOL),
            (u.LoadImageW, [wintypes.HINSTANCE, wintypes.LPCWSTR, UINT, INT,
                            INT, UINT], wintypes.HANDLE),
            (u.LoadIconW, [wintypes.HINSTANCE, ctypes.c_void_p], wintypes.HICON),
            (u.GetSystemMetrics, [INT], INT),
            (u.SetTimer, [H, ctypes.c_size_t, UINT, ctypes.c_void_p],
                         ctypes.c_size_t),
            (u.KillTimer, [H, ctypes.c_size_t], wintypes.BOOL),
            (s.Shell_NotifyIconW, [wintypes.DWORD,
                                   ctypes.POINTER(NOTIFYICONDATAW)],
                                  wintypes.BOOL),
            (k.GetModuleHandleW, [wintypes.LPCWSTR], wintypes.HMODULE),
        ]
        for fn, args, res in sig:
            fn.argtypes, fn.restype = args, res

    def _sharp(self) -> None:
        """Ask for the real screen resolution. Without it, on a laptop at 150%
        Windows draws a 16px icon and menu and stretches them: both blurry."""
        try:
            self.user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            if self.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
        except AttributeError:
            pass
        try:
            self.user32.SetProcessDPIAware()
        except AttributeError:
            pass

    def _load_icon(self):
        size_x = self.user32.GetSystemMetrics(SM_CXSMICON) or 16
        size_y = self.user32.GetSystemMetrics(SM_CYSMICON) or 16
        icon = self.user32.LoadImageW(None, self.icon_path, IMAGE_ICON,
                                      size_x, size_y, LR_LOADFROMFILE)
        if not icon:
            # A missing .ico is not a reason for no tray: Windows' own
            # program icon stands in, and Quit is still there.
            icon = self.user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        return icon

    def _data(self, flags: int = 0):
        nid = self.NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(self.NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = flags
        return nid

    # ------------------------------------------------------------- the icon

    def _add(self) -> None:
        nid = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.hicon
        nid.szTip = (self._tip_now or self.title)[:127]
        self._added = bool(self.shell32.Shell_NotifyIconW(NIM_ADD,
                                                          ctypes.byref(nid)))

    def remove(self) -> None:
        """Take the icon away. Safe from any thread, and more than once."""
        if self.hwnd and self._added:
            nid = self._data()
            self.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            self._added = False

    def set_tip(self, text: str) -> None:
        text = (text or self.title)[:127]
        if text == self._tip_now:
            return
        self._tip_now = text
        if self.hwnd and self._added:
            nid = self._data(NIF_TIP)
            nid.szTip = text
            self.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def notify(self, title: str, text: str) -> None:
        """A balloon (a notification, on Windows 10 and 11) from the icon."""
        if not (self.hwnd and self._added):
            return
        nid = self._data(NIF_INFO)
        nid.szInfoTitle = title[:63]
        nid.szInfo = text[:255]
        nid.dwInfoFlags = NIIF_USER
        nid.hBalloonIcon = self.hicon
        self.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # ------------------------------------------------------------- the menu

    def _show_menu(self) -> None:
        entries = self.menu() or []
        handle = self.user32.CreatePopupMenu()
        ids: dict = {}
        default = 0
        for n, entry in enumerate(entries, 1):
            if entry is None:
                self.user32.AppendMenuW(handle, MF_SEPARATOR, 0, None)
                continue
            flags = MF_STRING
            if entry.get("checked"):
                flags |= MF_CHECKED
            if entry.get("enabled") is False:
                flags |= MF_GRAYED
            self.user32.AppendMenuW(handle, flags, n, entry["label"])
            ids[n] = entry["id"]
            if entry.get("default"):
                default = n
        if default:
            self.user32.SetMenuDefaultItem(handle, default, 0)
        point = wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(point))
        self.user32.SetForegroundWindow(self.hwnd)
        chosen = self.user32.TrackPopupMenu(
            handle, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            point.x, point.y, 0, self.hwnd, None)
        self.user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        self.user32.DestroyMenu(handle)
        if chosen in ids:
            self._pick(ids[chosen])

    def _default(self) -> None:
        # A double-click is two clicks to Windows. Opening the page twice for
        # it is the kind of thing that makes a program feel broken.
        now = time.monotonic()
        if now - self._last_click < 1.5:
            return
        self._last_click = now
        for entry in self.menu() or []:
            if entry and entry.get("default"):
                self._pick(entry["id"])
                return

    def _pick(self, what: str) -> None:
        try:
            self.picked(what)
        except Exception:                                  # noqa: BLE001
            import traceback
            traceback.print_exc()

    # ------------------------------------------------------------- the loop

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                if lparam == WM_LBUTTONUP:
                    self._default()
                elif lparam == WM_RBUTTONUP:
                    self._show_menu()
                return 0
            if msg == self._explorer_back:
                self._add()                # Explorer restarted; put it back
                return 0
            if msg == WM_TIMER:
                if self.tip:
                    self.set_tip(self.tip())
                return 0
            if msg == WM_CLOSE:
                self.user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                self.user32.KillTimer(hwnd, 1)
                self.remove()
                self.user32.PostQuitMessage(0)
                return 0
        except Exception:                                  # noqa: BLE001
            import traceback
            traceback.print_exc()
        return self.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self, ready=None) -> None:
        """Put the icon up and answer it until `close()`. Blocks."""
        self._sharp()
        instance = self.kernel32.GetModuleHandleW(None)
        self._wndproc = self.WNDPROC(self._proc)   # kept, or it is collected
        cls = self.WNDCLASSW()
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = instance
        cls.lpszClassName = "PhotoManagerTray"
        self.user32.RegisterClassW(ctypes.byref(cls))
        # A real window that is never shown, not a message-only one: only
        # real windows hear "TaskbarCreated" when Explorer comes back.
        self.hwnd = self.user32.CreateWindowExW(
            0, cls.lpszClassName, self.title, 0, 0, 0, 0, 0,
            None, None, instance, None)
        self._explorer_back = self.user32.RegisterWindowMessageW("TaskbarCreated")
        self.hicon = self._load_icon()
        if self.tip:
            self._tip_now = (self.tip() or self.title)[:127]
        self._add()
        self.user32.SetTimer(self.hwnd, 1, TICK_MS, None)
        if ready:
            ready(self)
        msg = wintypes.MSG()
        while self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            self.user32.TranslateMessage(ctypes.byref(msg))
            self.user32.DispatchMessageW(ctypes.byref(msg))

    def close(self) -> None:
        """End `run()`. Safe from any thread."""
        if self.hwnd:
            self.user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
