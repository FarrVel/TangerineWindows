"""
Tangerine for Windows — aplikasi utama (system tray).

Menghubungkan:
  hook.DragWatcher  -> mendeteksi drag file + SHIFT
  radial_menu       -> menu melingkar di posisi kursor (drop-target)
  worker.py         -> SEMUA pemrosesan & editor berjalan di proses worker terpisah
                       yang langsung keluar setelah selesai (Strategi B)
  QSystemTrayIcon   -> ikon tray + Windows toast notification

Daemon ini sengaja tidak pernah memuat library konversi (PyMuPDF, pandas,
yt-dlp, MarkItDown, Pillow, ...) sehingga pemakaian RAM saat idle tetap kecil.
"""
from __future__ import annotations

import ctypes
import gc
import json
import os
import subprocess
import sys
import tempfile
import traceback
import winreg
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QColorDialog, QFileDialog, QMenu, QMessageBox,
                               QSystemTrayIcon)

from . import __version__
from . import markitdown_conv as MD
from . import media as M
from .actions import Action
from .hook import DragWatcher
from .icons import logo_icon
from .radial_menu import RadialMenu

APP_NAME = "Tangerine for Windows"
APP_ID = "TangerineForWindows"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_ID
CONFIG_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = CONFIG_DIR / "tangerine.log"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
EXIT_ALREADY_RUNNING = 3  # dikenali supervisor (run_tangerine.pyw): jangan restart
ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULTS = {"enabled": True, "any_app": False, "open_folder_on_click": True, "autostart": True}


def log(msg: str):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  Manajemen memori
# --------------------------------------------------------------------------- #

_psapi = ctypes.WinDLL("psapi")
_k32 = ctypes.WinDLL("kernel32")
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]


def trim_memory():
    """Bebaskan objek Python yang tidak terpakai lalu kembalikan halaman RAM yang
    sedang tidak dipakai ke Windows (EmptyWorkingSet). Halaman akan dimuat ulang
    otomatis saat dibutuhkan lagi."""
    try:
        gc.collect()
        _psapi.EmptyWorkingSet(_k32.GetCurrentProcess())
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  Worker process (Strategi B)
# --------------------------------------------------------------------------- #

def worker_python() -> str:
    """Interpreter untuk worker: pythonw.exe (tanpa jendela konsol) bila ada."""
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return str(pyw if pyw.exists() else exe)


class WorkerJob(QObject):
    """Satu pekerjaan = satu proses `python -m tangerine.worker` yang keluar setelah selesai."""
    progress = Signal(object, str)          # (job, teks)
    done = Signal(object, dict)             # (job, hasil)
    failed = Signal(object, str, str)       # (job, judul, pesan)
    ended = Signal(object)                  # (job) proses sudah keluar

    def __init__(self, action: Action, args: list[str], parent=None, quiet_exit: bool = False):
        super().__init__(parent)
        self.action = action
        self.quiet_exit = quiet_exit        # editor: ditutup tanpa simpan bukan error
        self._buf = b""
        self._reported = False
        self.proc = QProcess(self)
        self.proc.setProgram(worker_python())
        self.proc.setArguments(["-m", "tangerine.worker", *args])
        self.proc.setWorkingDirectory(str(ROOT_DIR))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)

    def start(self):
        self.proc.start()

    def _read(self):
        self._buf += bytes(self.proc.readAllStandardOutput())
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            kind = msg.get("type")
            if kind == "progress":
                self.progress.emit(self, msg.get("msg", ""))
            elif kind == "done":
                self._reported = True
                self.done.emit(self, msg)
            elif kind == "error":
                self._reported = True
                self.failed.emit(self, msg.get("title") or self.action.label, msg.get("message", ""))

    def _finished(self, code, _status):
        self._read()
        if not self._reported and not (self.quiet_exit and code == 0):
            err = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace").strip()
            if err:
                log(err)
            tail = err.splitlines()[-1] if err else f"proses worker berhenti (kode {code})"
            self.failed.emit(self, self.action.label, tail[:250])
        self.ended.emit(self)

    def _error(self, err):
        if err == QProcess.FailedToStart:
            self._reported = True
            self.failed.emit(self, self.action.label, "Proses worker gagal dijalankan.")
            self.ended.emit(self)


# --------------------------------------------------------------------------- #
#  Aplikasi
# --------------------------------------------------------------------------- #

class TangerineApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = self._load_settings()
        self._jobs: set[WorkerJob] = set()
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
        self._ensure_startup()

        # rapikan memori saat idle: sesaat setelah start & berkala tiap 60 detik
        self._trim_timer = QTimer(self)
        self._trim_timer.setInterval(60_000)
        self._trim_timer.timeout.connect(self._trim_if_idle)
        self._trim_timer.start()
        QTimer.singleShot(4000, self._trim_if_idle)

    def _trim_if_idle(self):
        if not self.menu.isVisible() and not QApplication.activePopupWidget() \
                and not QApplication.activeModalWidget():
            trim_memory()

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
        a_url = QAction("YouTube / URL → MP3, MP4, Transkrip…", m)
        a_url.triggered.connect(self.open_url_dialog)
        m.addAction(a_url)
        a_dl = QAction("Buka folder unduhan", m)
        a_dl.triggered.connect(lambda: os.startfile(M.download_dir()))
        m.addAction(a_dl)
        m.addSeparator()

        self.a_whisper = QAction(m)
        self.a_whisper.triggered.connect(self.setup_whisper)
        self._refresh_whisper_action()
        m.addAction(self.a_whisper)
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

    def _ensure_startup(self):
        """Autostart aktif secara default: daftarkan/segarkan entri Run setiap kali
        aplikasi berjalan (agar path tetap benar walau folder dipindah)."""
        if not self.settings.get("autostart", True):
            return
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
                cmd = self._startup_command()
                try:
                    cur, _ = winreg.QueryValueEx(k, APP_ID)
                except OSError:
                    cur = None
                if cur != cmd:
                    winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, cmd)
            # pastikan tidak dinonaktifkan lewat Task Manager > Startup apps
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
                                    0, winreg.KEY_SET_VALUE) as k2:
                    winreg.SetValueEx(k2, APP_ID, 0, winreg.REG_BINARY, b"\x02" + b"\x00" * 11)
            except OSError:
                pass
            self.a_startup.blockSignals(True)
            self.a_startup.setChecked(True)
            self.a_startup.blockSignals(False)
        except OSError:
            log(traceback.format_exc())

    def _toggle_startup(self, on: bool):
        self.settings["autostart"] = on
        self._save_settings()
        if on:
            self._ensure_startup()
            return
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                try:
                    winreg.DeleteValue(k, APP_ID)
                except FileNotFoundError:
                    pass
        except OSError as e:
            self.notify("Gagal mengubah startup", str(e), error=True)

    # ---------------- YouTube / URL & transkripsi ----------------
    def open_url_dialog(self):
        from .url_dialog import UrlDialog
        dlg = UrlDialog()
        dlg.chosen.connect(self._url_chosen)
        self._url_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _url_chosen(self, kind: str, url: str, quality: str):
        self._url_dialog = None
        if kind == "MD":
            act = Action("dlg_md", "Transkrip")
            self.run_action(act, [url])
        else:
            act = Action(f"dlg_{kind.lower()}", kind, progress=True)
            self.run_action(act, [url], {"quality": quality})

    def _refresh_whisper_action(self):
        if MD.whisper_ready():
            self.a_whisper.setText("✓ Transkripsi audio offline siap")
            self.a_whisper.setEnabled(False)
        else:
            self.a_whisper.setText("Siapkan transkripsi audio offline (unduh ±150 MB)…")
            self.a_whisper.setEnabled(True)

    def setup_whisper(self):
        r = QMessageBox.question(
            None, APP_NAME,
            "Tangerine akan mengunduh mesin transkripsi whisper.cpp dan model suara multibahasa "
            "(±150 MB, sekali saja).\n\nSetelah itu transkripsi voice note / audio / video berjalan "
            "100% offline di laptop Anda. Lanjutkan?")
        if r != QMessageBox.Yes:
            return
        act = Action("whisper_setup", "Persiapan transkripsi", progress=True)
        self.a_whisper.setEnabled(False)
        self.a_whisper.setText("Mengunduh mesin transkripsi…")
        self.run_action(act, ["setup"])

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
        QTimer.singleShot(3000, self._trim_if_idle)

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
            "<p><b>Fitur lain:</b></p><ul>"
            "<li><b>MD (MarkItDown)</b>: PDF, Word, Excel, PowerPoint, gambar (EXIF + OCR), audio "
            "(metadata + transkripsi), HTML, CSV/JSON/XML, ZIP, EPUB, Outlook .msg → Markdown.</li>"
            "<li><b>YouTube</b>: drag link dari browser + SHIFT, atau menu tray "
            "<i>YouTube / URL</i> → MP3, MP4, atau transkrip.</li>"
            "<li><b>Voice note</b> (WhatsApp .opus/.ogg, perekam .m4a/.amr): konversi ke MP3/WAV/M4A/OGG, "
            "perjelas suara, kompres, transkripsi teks.</li></ul>"
            "<p>Hasil disimpan di folder yang sama dengan akhiran <code>_converted</code>, "
            "<code>_compressed</code>, <code>_clean</code>, dst. Klik notifikasi untuk membuka foldernya.</p>"
            "<p style='color:gray'>Berjalan 100% Offline | Hasil disimpan di folder asal</p>")
        box.exec()

    # ---------------- eksekusi aksi (di proses worker) ----------------
    def run_action(self, action: Action, paths: list[str], extra: dict | None = None):
        if not paths:
            return
        if action.editor_mode:
            self._open_editor(paths[0], action.editor_mode)
            return
        kwargs = dict(extra or {})
        if action.prompt == "color":
            c = QColorDialog.getColor(QColor(255, 255, 255), None, "Pilih warna latar belakang")
            if not c.isValid():
                return
            kwargs["color"] = [c.red(), c.green(), c.blue()]

        fd, job_file = tempfile.mkstemp(prefix="tangerine_job_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"action": action.key, "paths": paths, "kwargs": kwargs}, f, ensure_ascii=False)

        job = WorkerJob(action, [job_file], self)
        self._connect_job(job)
        what = "URL" if paths[0].startswith("http") else f"{len(paths)} file"
        self.tray.setToolTip(f"{APP_NAME}\nMemproses {what} ({action.label})…")
        if action.progress or action.key in ("url_md", "dlg_md", "markdown", "transcript", "img_ocr") \
                or action.key.startswith(("vid_", "aud_")):
            # proses yang bisa lama: beri tahu bahwa pekerjaan sudah dimulai
            self.notify(f"⏳ {action.label} dimulai", "Berjalan di latar belakang. Anda akan diberi tahu "
                                                       "saat selesai.")
        job.start()

    def _connect_job(self, job: WorkerJob):
        job.done.connect(self._job_done)
        job.failed.connect(self._job_failed)
        job.progress.connect(self._job_progress)
        job.ended.connect(self._job_ended)
        self._jobs.add(job)

    def _job_progress(self, job: WorkerJob, msg: str):
        self.tray.setToolTip(f"{APP_NAME}\n{job.action.label}: {msg}"[:120])

    def _job_ended(self, job: WorkerJob):
        self._jobs.discard(job)
        if job.action.key == "whisper_setup":
            self._refresh_whisper_action()
        if not self._jobs:
            self.tray.setToolTip(f"{APP_NAME}\nTahan SHIFT saat men-drag file")
        job.deleteLater()
        QTimer.singleShot(2000, self._trim_if_idle)

    def _job_done(self, job: WorkerJob, res: dict):
        title = res.get("title") or job.action.label
        clip = res.get("clipboard")
        outputs = res.get("outputs") or []
        if clip:
            QGuiApplication.clipboard().setText(clip)
        if outputs:
            self._last_output = outputs[0]
        if job.action.editor_mode:
            self.notify("✅ Gambar disimpan", res.get("message") or "")
            return
        ok = bool(outputs) or bool(clip)
        head = f"✅ {title} selesai" if ok else f"ℹ️ {title}"
        self.notify(head, res.get("message") or "Selesai.")

    def _job_failed(self, job: WorkerJob, title: str, err: str):
        self.notify(f"❌ {title} gagal", (err or "Terjadi kesalahan.")[:250], error=True)

    def _open_editor(self, path: str, mode: str):
        act = Action(f"editor_{mode}", "Editor", editor_mode=mode)
        job = WorkerJob(act, ["--editor", path, mode], self, quiet_exit=True)
        self._connect_job(job)
        job.start()

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
        return EXIT_ALREADY_RUNNING
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        # saat Windows baru menyala, taskbar bisa belum siap — tunggu hingga 90 detik
        import time
        for _ in range(90):
            app.processEvents()
            time.sleep(1)
            if QSystemTrayIcon.isSystemTrayAvailable():
                break
        else:
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
