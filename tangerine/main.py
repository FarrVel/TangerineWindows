"""
Tangerine for Windows — aplikasi utama (system tray).

Menghubungkan:
  hook.DragWatcher  -> mendeteksi drag file + SHIFT
  radial_menu       -> menu melingkar di posisi kursor (drop-target)
  actions/processors-> pemrosesan offline di thread terpisah
  editor            -> editor gambar interaktif
  QSystemTrayIcon   -> ikon tray + Windows toast notification
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
import winreg
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QColorDialog, QFileDialog, QMenu, QMessageBox,
                               QSystemTrayIcon)

from . import __version__
from .actions import Action
from .editor import ImageEditor
from .hook import DragWatcher
from .icons import logo_icon
from .processors import ProcessingError, Result
from .radial_menu import RadialMenu

APP_NAME = "Tangerine for Windows"
APP_ID = "TangerineForWindows"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_ID
CONFIG_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = CONFIG_DIR / "tangerine.log"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULTS = {"enabled": True, "any_app": False, "open_folder_on_click": True}


def log(msg: str):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  Worker thread
# --------------------------------------------------------------------------- #

class _Signals(QObject):
    done = Signal(object, str, object)      # (job, judul aksi, Result)
    failed = Signal(object, str, str)       # (job, judul aksi, pesan error)


class Job(QRunnable):
    def __init__(self, action: Action, paths: list[str], kwargs: dict):
        super().__init__()
        self.action, self.paths, self.kwargs = action, paths, kwargs
        self.signals = _Signals()

    def run(self):
        title = self.action.label
        try:
            if self.action.batch:
                res = self.action.func(self.paths, **self.kwargs)
            else:
                res = Result()
                msgs, clip = [], []
                errors = []
                for p in self.paths:
                    try:
                        r = self.action.func(p, **self.kwargs)
                        res.outputs += r.outputs
                        if r.message:
                            msgs.append(r.message)
                        if r.clipboard:
                            clip.append(r.clipboard)
                    except Exception as e:  # noqa: BLE001
                        log(traceback.format_exc())
                        errors.append(f"{Path(p).name}: {e}")
                if errors and not res.outputs and not msgs:
                    raise ProcessingError("\n".join(errors))
                if len(self.paths) == 1:
                    res.message = msgs[0] if msgs else ""
                else:
                    res.message = f"{len(self.paths) - len(errors)} dari {len(self.paths)} file berhasil diproses."
                    if errors:
                        res.message += "\nGagal: " + "; ".join(errors)[:200]
                res.clipboard = "\n".join(clip) if clip else None
            self.signals.done.emit(self, title, res)
        except ProcessingError as e:
            self.signals.failed.emit(self, title, str(e))
        except Exception as e:  # noqa: BLE001
            log(traceback.format_exc())
            self.signals.failed.emit(self, title, f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------- #
#  Aplikasi
# --------------------------------------------------------------------------- #

class TangerineApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = self._load_settings()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, min(4, os.cpu_count() or 2)))
        self._jobs: set[Job] = set()
        self._editors: list[ImageEditor] = []
        self._last_output: str | None = None
        self._icon_on = logo_icon()
        self._icon_off = logo_icon(disabled=True)

        # radial menu
        self.menu = RadialMenu()
        self.menu.action_chosen.connect(self.run_action)
        self.menu.dismissed.connect(self._on_menu_dismissed)

        # watcher
        self.watcher = DragWatcher(self)
        self.watcher.enabled = self.settings["enabled"]
        self.watcher.any_app = self.settings["any_app"]
        self.watcher.trigger.connect(self._on_trigger)
        self.watcher.ctrl_pressed.connect(self._on_ctrl)
        self.watcher.drag_ended.connect(self._on_drag_ended)
        self.watcher.escape_pressed.connect(self.menu.dismiss)
        self.watcher.start()

        self._build_tray()

    # ---------------- settings ----------------
    def _load_settings(self) -> dict:
        s = dict(DEFAULTS)
        try:
            s.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
        return s

    def _save_settings(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except Exception:
            log(traceback.format_exc())

    # ---------------- tray ----------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(self._icon_on if self.settings["enabled"] else self._icon_off)
        self.tray.setToolTip(f"{APP_NAME}\nTahan SHIFT saat men-drag file")
        m = QMenu()
        m.setStyleSheet("""
            QMenu { background: #202024; color: #eee; border: 1px solid #3a3a44; border-radius: 8px; padding: 6px; }
            QMenu::item { padding: 6px 22px 6px 12px; border-radius: 5px; }
            QMenu::item:selected { background: #ff8c1a; color: #111; }
            QMenu::item:disabled { color: #ff9f3d; font-weight: bold; }
            QMenu::separator { height: 1px; background: #3a3a44; margin: 5px 8px; }
            QMenu::indicator { width: 14px; height: 14px; }
        """)
        title = QAction(f"🍊  {APP_NAME}  v{__version__}", m)
        title.setEnabled(False)
        m.addAction(title)
        m.addSeparator()

        a_open = QAction("Pilih file untuk dikonversi…", m)
        a_open.triggered.connect(lambda: self.pick_files(False))
        m.addAction(a_open)
        a_tools = QAction("Pilih file untuk alat cepat…", m)
        a_tools.triggered.connect(lambda: self.pick_files(True))
        m.addAction(a_tools)
        m.addSeparator()

        self.a_enabled = QAction("Aktif (deteksi Drag + SHIFT)", m, checkable=True)
        self.a_enabled.setChecked(self.settings["enabled"])
        self.a_enabled.toggled.connect(self._toggle_enabled)
        m.addAction(self.a_enabled)

        self.a_anyapp = QAction("Deteksi drag dari semua aplikasi", m, checkable=True)
        self.a_anyapp.setChecked(self.settings["any_app"])
        self.a_anyapp.toggled.connect(self._toggle_anyapp)
        m.addAction(self.a_anyapp)

        self.a_startup = QAction("Jalankan saat Windows dinyalakan", m, checkable=True)
        self.a_startup.setChecked(self._startup_enabled())
        self.a_startup.toggled.connect(self._toggle_startup)
        m.addAction(self.a_startup)
        m.addSeparator()

        a_help = QAction("Cara pakai", m)
        a_help.triggered.connect(self.show_help)
        m.addAction(a_help)
        a_log = QAction("Buka log", m)
        a_log.triggered.connect(lambda: os.startfile(LOG_FILE) if LOG_FILE.exists()
                                else self.notify("Log kosong", "Belum ada error yang tercatat."))
        m.addAction(a_log)
        m.addSeparator()
        a_quit = QAction("Keluar", m)
        a_quit.triggered.connect(self.quit)
        m.addAction(a_quit)

        self.tray.setContextMenu(m)
        self._tray_menu = m
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._open_last_output)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.pick_files(False)

    def notify(self, title: str, msg: str, error: bool = False):
        icon = QSystemTrayIcon.Critical if error else QSystemTrayIcon.Information
        if not error:
            # pakai ikon jeruk untuk notifikasi sukses
            self.tray.showMessage(title, msg, self._icon_on, 5000)
        else:
            self.tray.showMessage(title, msg, icon, 7000)

    def _open_last_output(self):
        if self._last_output and os.path.exists(self._last_output):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self._last_output)])

    # ---------------- toggles ----------------
    def _toggle_enabled(self, on: bool):
        self.settings["enabled"] = on
        self.watcher.enabled = on
        self.tray.setIcon(self._icon_on if on else self._icon_off)
        self._save_settings()

    def _toggle_anyapp(self, on: bool):
        self.settings["any_app"] = on
        self.watcher.any_app = on
        self._save_settings()

    @staticmethod
    def _startup_command() -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        if pyw.exists():
            exe = pyw
        root = Path(__file__).resolve().parent.parent
        return f'"{exe}" "{root / "run_tangerine.pyw"}"'

    def _startup_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_ID)
                return True
        except OSError:
            return False

    def _toggle_startup(self, on: bool):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if on:
                    winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, self._startup_command())
                else:
                    try:
                        winreg.DeleteValue(k, APP_ID)
                    except FileNotFoundError:
                        pass
        except OSError as e:
            self.notify("Gagal mengubah startup", str(e), error=True)

    # ---------------- radial menu flow ----------------
    def _on_trigger(self, ctrl: bool):
        self.menu.show_drag(tools=ctrl)

    def _on_ctrl(self):
        if self.menu.isVisible() and self.menu.drag_mode:
            self.menu.toggle_mode()

    def _on_drag_ended(self):
        # beri waktu event drop OLE tiba sebelum menu disembunyikan
        QTimer.singleShot(700, self._hide_drag_menu)

    def _hide_drag_menu(self):
        if self.menu.isVisible() and self.menu.drag_mode:
            from .hook import VK_LBUTTON, key_down
            if not key_down(VK_LBUTTON):
                self.menu.hide()

    def _on_menu_dismissed(self):
        if self.menu.drag_mode:
            self.watcher.mark_dismissed()

    def pick_files(self, tools: bool):
        files, _ = QFileDialog.getOpenFileNames(None, "Pilih file — Tangerine", str(Path.home()),
                                                "Semua file (*.*)")
        if files:
            files = [os.path.normpath(f) for f in files]
            QTimer.singleShot(50, lambda: self.menu.show_click(files, tools=tools))

    def show_help(self):
        box = QMessageBox()
        box.setWindowTitle(APP_NAME)
        box.setWindowIcon(self._icon_on)
        box.setIconPixmap(self._icon_on.pixmap(64, 64))
        box.setTextFormat(Qt.RichText)
        box.setText(
            "<h3>Cara pakai Tangerine</h3>"
            "<ol>"
            "<li>Drag (seret) satu atau beberapa file dari File Explorer / Desktop.</li>"
            "<li>Sambil men-drag, <b>tekan &amp; tahan SHIFT</b> → menu melingkar muncul di kursor.</li>"
            "<li>Arahkan file ke salah satu segmen lalu <b>lepaskan</b> (drop).</li>"
            "<li>Tekan <b>CTRL</b> saat menu tampil untuk berganti mode <i>Konversi ↔ Alat</i> "
            "(atau tahan CTRL+SHIFT sejak awal).</li>"
            "<li>Gerakkan kursor menjauh / tekan ESC untuk membatalkan.</li>"
            "</ol>"
            "<p>Hasil disimpan di folder yang sama dengan akhiran <code>_converted</code>, "
            "<code>_compressed</code>, <code>_clean</code>, dst. Klik notifikasi untuk membuka foldernya.</p>"
            "<p style='color:gray'>Berjalan 100% Offline | Hasil disimpan di folder asal</p>")
        box.exec()

    # ---------------- eksekusi aksi ----------------
    def run_action(self, action: Action, paths: list[str]):
        if not paths:
            return
        if action.editor_mode:
            self._open_editor(paths[0], action.editor_mode)
            return
        kwargs = {}
        if action.prompt == "color":
            c = QColorDialog.getColor(QColor(255, 255, 255), None, "Pilih warna latar belakang")
            if not c.isValid():
                return
            kwargs["color"] = (c.red(), c.green(), c.blue())

        job = Job(action, paths, kwargs)
        job.setAutoDelete(False)
        # sambungkan ke method QObject (bukan lambda) agar slot dijalankan di UI thread
        job.signals.done.connect(self._job_done)
        job.signals.failed.connect(self._job_failed)
        self._jobs.add(job)
        self.tray.setToolTip(f"{APP_NAME}\nMemproses {len(paths)} file ({action.label})…")
        self.pool.start(job)

    def _job_finished(self, job: Job):
        self._jobs.discard(job)
        if not self._jobs:
            self.tray.setToolTip(f"{APP_NAME}\nTahan SHIFT saat men-drag file")

    def _job_done(self, job: Job, title: str, res: Result):
        self._job_finished(job)
        if res.clipboard:
            QGuiApplication.clipboard().setText(res.clipboard)
        if res.outputs:
            self._last_output = res.outputs[0]
        ok = bool(res.outputs) or bool(res.clipboard)
        head = f"✅ {title} selesai" if ok else f"ℹ️ {title}"
        self.notify(head, res.message or "Selesai.")

    def _job_failed(self, job: Job, title: str, err: str):
        self._job_finished(job)
        self.notify(f"❌ {title} gagal", err[:250], error=True)

    def _open_editor(self, path: str, mode: str):
        try:
            ed = ImageEditor(path, mode)
        except Exception as e:  # noqa: BLE001
            log(traceback.format_exc())
            self.notify("❌ Tidak bisa membuka gambar", str(e), error=True)
            return
        ed.saved.connect(self._editor_saved)
        ed.finished.connect(lambda _=0, e=ed: self._editors.remove(e) if e in self._editors else None)
        self._editors.append(ed)
        ed.show()
        ed.raise_()
        ed.activateWindow()

    def _editor_saved(self, out: str):
        self._last_output = out
        self.notify("✅ Gambar disimpan", Path(out).name)

    def quit(self):
        self.watcher.stop()
        self.tray.hide()
        self.app.quit()


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #

def _set_app_user_model_id():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def main():
    _set_app_user_model_id()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(logo_icon())

    # --- single instance ---
    server_name = f"{APP_ID}-{os.environ.get('USERNAME', 'user')}"
    sock = QLocalSocket()
    sock.connectToServer(server_name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        print("Tangerine sudah berjalan di system tray.")
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "System tray tidak tersedia.")
        return 1

    t = TangerineApp(app)

    def _on_new_instance():
        c = server.nextPendingConnection()
        if c:
            c.close()
        t.notify(APP_NAME, "Tangerine sudah berjalan. Drag file + tahan SHIFT untuk memulai.")
    server.newConnection.connect(_on_new_instance)

    t.notify("🍊 Tangerine aktif",
             "Drag file dari Explorer lalu tahan SHIFT untuk membuka menu konversi.")

    sys.excepthook = lambda et, ev, tb: log("".join(traceback.format_exception(et, ev, tb)))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
