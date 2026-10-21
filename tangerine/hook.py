"""
Global mouse/keyboard watcher untuk mendeteksi gesture "drag file + SHIFT".

Menggunakan polling ringan (GetAsyncKeyState + GetCursorPos dari user32) setiap
~20 ms. Pendekatan ini tidak memerlukan low-level hook yang bisa memperlambat
input sistem dan tidak terblokir oleh antivirus.

Alur:
  1. Tombol kiri mouse ditekan -> catat posisi & jendela di bawah kursor.
  2. Kursor bergerak > ambang batas sambil tombol masih ditekan -> "sedang drag".
  3. Saat drag dan SHIFT ditekan -> emit `trigger` (radial menu muncul di kursor).
  4. Radial menu adalah drop-target OLE, sehingga file yang di-drag dari
     Explorer langsung diterima beserta path lengkapnya.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer, Signal

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

VK_LBUTTON, VK_RBUTTON = 0x01, 0x02
VK_SHIFT, VK_CONTROL, VK_ESCAPE = 0x10, 0x11, 0x1B
SM_SWAPBUTTON = 23
GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Aplikasi file manager yang diizinkan memicu menu (mode default).
FILE_MANAGERS = {"explorer.exe", "totalcmd.exe", "totalcmd64.exe", "doublecmd.exe",
                 "xyplorer.exe", "files.exe", "directory opus.exe", "dopus.exe",
                 "onecommander.exe", "q-dir.exe", "q-dir_x64.exe", "freecommander.exe",
                 "7zfm.exe", "everything.exe", "everything64.exe"}


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def process_name_at(x: int, y: int) -> str:
    """Nama proses (lowercase) dari jendela di bawah titik layar (x, y)."""
    try:
        hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
        if not hwnd:
            return ""
        root = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
        if pid.value == os.getpid():
            return "__self__"
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


class DragWatcher(QObject):
    """Memantau gesture drag + SHIFT secara global."""

    trigger = Signal(bool)        # dipicu saat menu harus tampil; arg = CTRL ikut ditekan
    ctrl_pressed = Signal()       # CTRL ditekan (edge) selama drag -> ganti mode menu
    drag_ended = Signal()         # tombol mouse dilepas
    escape_pressed = Signal()

    DRAG_THRESHOLD = 12  # piksel fisik

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = True
        self.any_app = False
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._poll)
        self._reset()

    # ------------------------------------------------------------------ #
    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._reset()

    def _reset(self):
        self._down = False
        self._start = (0, 0)
        self._dragging = False
        self._eligible = False
        self._shown = False
        self._shift_prev = False
        self._ctrl_prev = False
        self._esc_prev = False
        self._await_shift_release = False

    def mark_dismissed(self):
        """Menu ditutup saat drag masih berlangsung: tunggu SHIFT dilepas & ditekan ulang."""
        if self._down:
            self._shown = False
            self._await_shift_release = True

    # ------------------------------------------------------------------ #
    def _poll(self):
        if not self.enabled:
            return
        lvk = VK_RBUTTON if user32.GetSystemMetrics(SM_SWAPBUTTON) else VK_LBUTTON
        down = key_down(lvk)
        shift = key_down(VK_SHIFT)
        ctrl = key_down(VK_CONTROL)
        esc = key_down(VK_ESCAPE)

        if down and not self._down:  # baru ditekan
            self._down = True
            self._start = cursor_pos()
            self._dragging = False
            self._shown = False
            proc = process_name_at(*self._start)
            self._eligible = proc != "__self__" and (self.any_app or proc in FILE_MANAGERS)
            self._shift_prev = shift
            self._ctrl_prev = ctrl
        elif down and self._down:
            if not self._dragging and self._eligible:
                x, y = cursor_pos()
                if abs(x - self._start[0]) + abs(y - self._start[1]) >= self.DRAG_THRESHOLD:
                    self._dragging = True
            if self._dragging:
                if not shift:
                    self._await_shift_release = False
                if not self._shown and shift and not self._await_shift_release:
                    # SHIFT ditekan (atau sudah ditahan sejak awal drag) -> tampilkan menu
                    self._shown = True
                    self.trigger.emit(ctrl)
                elif self._shown and ctrl and not self._ctrl_prev:
                    self.ctrl_pressed.emit()
                if self._shown and esc and not self._esc_prev:
                    self.escape_pressed.emit()
        elif not down and self._down:  # dilepas
            was = self._shown
            self._reset()
            if was:
                self.drag_ended.emit()

        self._shift_prev = shift
        self._ctrl_prev = ctrl
        self._esc_prev = esc
