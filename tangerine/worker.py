"""
Proses WORKER on-demand (Strategi B: arsitektur 2 proses).

Daemon di tray TIDAK pernah memuat library konversi (PyMuPDF, pandas, yt-dlp,
MarkItDown, Pillow, dll.). Setiap pekerjaan dijalankan di proses terpisah ini:

    pythonw -m tangerine.worker <job.json>

Worker memuat library yang dibutuhkan, memproses, melaporkan hasil ke daemon
lewat stdout (satu objek JSON per baris), lalu KELUAR sehingga seluruh memorinya
dikembalikan ke Windows.

Format pesan stdout:
    {"type": "progress", "msg": "..."}
    {"type": "done", "title": "...", "outputs": [...], "message": "...", "clipboard": "..."|null}
    {"type": "error", "title": "...", "message": "..."}
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "TangerineForWindows"
LOG_FILE = CONFIG_DIR / "tangerine.log"


def _emit(obj: dict):
    # ensure_ascii agar aman dari masalah encoding console Windows
    sys.stdout.write(json.dumps(obj, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def _log(text: str):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
    except Exception:
        pass


def _find_action(key: str, paths: list[str]):
    from . import actions as A
    for mode in ("convert", "tools"):
        for act in A.get_actions(paths, mode):
            if act.key == key:
                return act
    return None


def _special_action(key: str, kwargs: dict):
    """Aksi yang tidak berasal dari radial menu (dialog URL, setup whisper)."""
    from functools import partial
    from .actions import Action
    if key == "whisper_setup":
        from . import markitdown_conv as MD
        return Action(key, "Persiapan transkripsi", func=lambda _x, progress=None: MD.setup_whisper(progress),
                      progress=True)
    if key in ("dlg_mp3", "dlg_mp4"):
        from . import media as M
        fmt = "MP3" if key == "dlg_mp3" else "MP4"
        return Action(key, fmt, func=partial(M.youtube_download, fmt=fmt, quality=kwargs.pop("quality", "best")),
                      progress=True)
    if key == "dlg_md":
        from . import markitdown_conv as MD
        return Action(key, "Transkrip", func=MD.url_to_markdown)
    return None


def run_job(job: dict) -> int:
    from .processors import ProcessingError, Result

    key = job["action"]
    paths = job["paths"]
    kwargs = dict(job.get("kwargs") or {})
    if "color" in kwargs and isinstance(kwargs["color"], list):
        kwargs["color"] = tuple(kwargs["color"])

    act = _special_action(key, kwargs) or _find_action(key, paths)
    if act is None:
        _emit({"type": "error", "title": key, "message": f"Aksi '{key}' tidak dikenal."})
        return 2
    title = act.label
    if act.progress:
        kwargs["progress"] = lambda msg: _emit({"type": "progress", "msg": str(msg)})

    try:
        if act.batch:
            res = act.func(paths, **kwargs)
        else:
            res = Result()
            msgs, clip, errors = [], [], []
            for p in paths:
                try:
                    r = act.func(p, **kwargs)
                    res.outputs += r.outputs
                    if r.message:
                        msgs.append(r.message)
                    if r.clipboard:
                        clip.append(r.clipboard)
                except Exception as e:  # noqa: BLE001
                    _log(traceback.format_exc())
                    errors.append(f"{p if p.startswith('http') else Path(p).name}: {e}")
            if errors and not res.outputs and not msgs:
                raise ProcessingError("\n".join(errors))
            if len(paths) == 1:
                res.message = msgs[0] if msgs else ""
            else:
                res.message = f"{len(paths) - len(errors)} dari {len(paths)} file berhasil diproses."
                if errors:
                    res.message += "\nGagal: " + "; ".join(errors)[:200]
            res.clipboard = "\n".join(clip) if clip else None
        _emit({"type": "done", "title": title, "outputs": res.outputs, "message": res.message,
               "clipboard": res.clipboard})
        return 0
    except ProcessingError as e:
        _emit({"type": "error", "title": title, "message": str(e)})
        return 1
    except Exception as e:  # noqa: BLE001
        _log(traceback.format_exc())
        _emit({"type": "error", "title": title, "message": f"{type(e).__name__}: {e}"})
        return 1


def run_editor(path: str, mode: str) -> int:
    """Editor gambar interaktif juga berjalan di proses worker terpisah."""
    from PySide6.QtWidgets import QApplication
    from .editor import ImageEditor
    from .icons import logo_icon

    app = QApplication(sys.argv[:1])
    app.setWindowIcon(logo_icon())
    try:
        ed = ImageEditor(path, mode)
    except Exception as e:  # noqa: BLE001
        _log(traceback.format_exc())
        _emit({"type": "error", "title": "Editor", "message": f"Tidak bisa membuka gambar: {e}"})
        return 1
    ed.saved.connect(lambda out: _emit({"type": "done", "title": "Gambar disimpan", "outputs": [out],
                                        "message": Path(out).name, "clipboard": None}))
    ed.finished.connect(app.quit)
    ed.show()
    ed.raise_()
    ed.activateWindow()
    return app.exec()


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(argv) >= 3 and argv[0] == "--editor":
        return run_editor(argv[1], argv[2])
    if not argv:
        _emit({"type": "error", "title": "Worker", "message": "Tidak ada job."})
        return 2
    job_file = Path(argv[0])
    try:
        job = json.loads(job_file.read_text(encoding="utf-8-sig"))
    finally:
        try:
            job_file.unlink()
        except OSError:
            pass
    return run_job(job)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
