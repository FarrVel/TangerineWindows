"""
Integrasi Microsoft MarkItDown: konversi banyak format ke Markdown.

Format: PDF, Word, Excel (.xlsx/.xls), PowerPoint, gambar (EXIF + OCR), audio
(metadata + transkripsi), HTML, CSV/JSON/XML, ZIP (isi ditelusuri), URL YouTube
(transkrip), EPUB, dan Outlook .msg.

Agar tetap OFFLINE, konverter bawaan MarkItDown untuk gambar & audio (yang
memakai exiftool / LLM / Google Speech API) diganti dengan:
  - Gambar : EXIF via Pillow + OCR engine bawaan Windows (Windows.Media.Ocr)
  - Audio  : metadata via mutagen + transkripsi whisper.cpp lokal (opsional,
             model diunduh sekali lewat menu tray)
Hanya URL (YouTube/web) yang tentu saja membutuhkan internet.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .processors import ProcessingError, Result, human_size, unique_path

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "TangerineForWindows"
WHISPER_DIR = CONFIG_DIR / "whisper"
WHISPER_MODEL = WHISPER_DIR / "ggml-base.bin"
WHISPER_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin"
WHISPER_RELEASES = "https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=15"
OCR_SCRIPT = Path(__file__).with_name("win_ocr.ps1")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".heic",
              ".heif", ".avif", ".jfif"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".oga", ".opus", ".aac", ".wma",
              ".mp4", ".webm", ".mkv", ".mov", ".amr", ".aiff", ".aif"}
MD_EXTS = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".html", ".htm", ".csv", ".json",
           ".jsonl", ".xml", ".rss", ".atom", ".zip", ".epub", ".msg", ".ipynb", ".txt",
           ".url"} | IMAGE_EXTS | AUDIO_EXTS

YOUTUBE_RE = re.compile(r"^https?://(www\.|m\.)?(youtube\.com/(watch|shorts|live)|youtu\.be/)", re.I)


# --------------------------------------------------------------------------- #
#  Shim "magika": paket aslinya butuh onnxruntime yang belum tersedia untuk
#  semua versi Python. MarkItDown otomatis memakai deteksi berbasis ekstensi
#  bila magika mengembalikan status selain "ok".
# --------------------------------------------------------------------------- #

def _install_magika_shim():
    try:
        import magika  # noqa: F401
        return
    except Exception:
        pass

    class _Res:
        status = "unavailable"
        prediction = None

    class Magika:  # noqa: D401
        def identify_stream(self, _stream):
            return _Res()

        def identify_bytes(self, _b):
            return _Res()

        def identify_path(self, _p):
            return _Res()

    mod = types.ModuleType("magika")
    mod.Magika = Magika
    mod.__version__ = "0.0-shim"
    sys.modules["magika"] = mod


# --------------------------------------------------------------------------- #
#  OCR (Windows.Media.Ocr via PowerShell — bawaan Windows 10/11, offline)
# --------------------------------------------------------------------------- #

def windows_ocr(image_path: str | Path) -> tuple[str, str]:
    """Kembalikan (teks, kode_bahasa). Gambar dinormalisasi ke PNG dulu."""
    from .processors import open_image, _flatten
    img = _flatten(open_image(image_path))
    w, h = img.size
    # engine OCR Windows maksimal 10000 px; teks kecil lebih akurat bila diperbesar
    if max(w, h) > 9000:
        img.thumbnail((9000, 9000))
    elif max(w, h) < 1000:
        f = min(3.0, 1500 / max(w, h))
        img = img.resize((int(w * f), int(h * f)))
    fd, tmp = tempfile.mkstemp(suffix=".png", prefix="tangerine_ocr_")
    os.close(fd)
    try:
        img.save(tmp, "PNG")
        ps = shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        proc = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(OCR_SCRIPT), "-Path", tmp],
            capture_output=True, timeout=120, creationflags=NO_WINDOW)
        out = proc.stdout.decode("utf-8", "replace").strip()
        if proc.returncode != 0 or not out:
            err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            raise ProcessingError("OCR Windows gagal: " + (err[0] if err else "tidak ada output"))
        data = json.loads(out.splitlines()[-1])
        return (data.get("text") or "").strip(), data.get("lang") or ""
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def image_exif_markdown(img) -> list[str]:
    from PIL import ExifTags
    lines: list[str] = []
    try:
        exif = img.getexif()
    except Exception:
        return lines
    if not exif:
        return lines
    skip = {"MakerNote", "UserComment", "PrintImageMatching", "ExifOffset", "GPSInfo"}
    for k, v in exif.items():
        name = ExifTags.TAGS.get(k, str(k))
        if name in skip or isinstance(v, bytes):
            continue
        lines.append(f"- **{name}**: {v}")
    try:
        sub = exif.get_ifd(ExifTags.IFD.Exif)
        for k, v in sub.items():
            name = ExifTags.TAGS.get(k, str(k))
            if name in skip or isinstance(v, bytes):
                continue
            lines.append(f"- **{name}**: {v}")
    except Exception:
        pass
    try:
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        if gps:
            def deg(vals, ref):
                d, m, s = (float(x) for x in vals)
                r = d + m / 60 + s / 3600
                return -r if ref in ("S", "W") else r
            if 2 in gps and 4 in gps:
                lat = deg(gps[2], gps.get(1, "N"))
                lon = deg(gps[4], gps.get(3, "E"))
                lines.append(f"- **GPS**: {lat:.6f}, {lon:.6f}")
    except Exception:
        pass
    return lines


# --------------------------------------------------------------------------- #
#  Transkripsi audio (whisper.cpp lokal)
# --------------------------------------------------------------------------- #

def ffmpeg_exe() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def whisper_cli() -> Path | None:
    if not WHISPER_DIR.exists():
        return None
    for name in ("whisper-cli.exe", "main.exe"):
        for p in WHISPER_DIR.rglob(name):
            return p
    return None


def whisper_ready() -> bool:
    return whisper_cli() is not None and WHISPER_MODEL.exists() and WHISPER_MODEL.stat().st_size > 10_000_000


def _download(url: str, dest: Path, progress: Callable[[str], None] | None = None, label: str = ""):
    req = urllib.request.Request(url, headers={"User-Agent": "Tangerine-for-Windows"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        last = -1
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                pct = done * 100 // total
                if pct // 10 != last:
                    last = pct // 10
                    progress(f"{label} {pct}% ({human_size(done)} / {human_size(total)})")
    tmp.replace(dest)


def setup_whisper(progress: Callable[[str], None] | None = None) -> Result:
    """Unduh whisper.cpp (CPU, x64) + model multibahasa 'base' (~150 MB). Sekali saja."""
    WHISPER_DIR.mkdir(parents=True, exist_ok=True)
    if whisper_cli() is None:
        req = urllib.request.Request(WHISPER_RELEASES, headers={"User-Agent": "Tangerine-for-Windows",
                                                                "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            releases = json.load(r)
        asset = None
        for rel in releases:
            for a in rel.get("assets", []):
                if a.get("name") == "whisper-bin-x64.zip":
                    asset = a
                    break
            if asset:
                break
        if not asset:
            raise ProcessingError("Paket whisper-bin-x64.zip tidak ditemukan di rilis whisper.cpp.")
        zpath = WHISPER_DIR / "whisper-bin-x64.zip"
        _download(asset["browser_download_url"], zpath, progress, "Mengunduh whisper.cpp")
        with zipfile.ZipFile(zpath) as z:
            z.extractall(WHISPER_DIR / "bin")
        zpath.unlink(missing_ok=True)
        if whisper_cli() is None:
            raise ProcessingError("whisper-cli.exe tidak ditemukan setelah ekstraksi.")
    if not (WHISPER_MODEL.exists() and WHISPER_MODEL.stat().st_size > 10_000_000):
        _download(WHISPER_MODEL_URL, WHISPER_MODEL, progress, "Mengunduh model suara")
    return Result([str(WHISPER_DIR)], "Transkripsi audio offline siap dipakai (whisper.cpp, model base multibahasa).")


def transcribe_audio(path: str | Path) -> str:
    cli = whisper_cli()
    if not (cli and whisper_ready()):
        raise ProcessingError("NOT_READY")
    ff = ffmpeg_exe()
    if not ff:
        raise ProcessingError("ffmpeg tidak tersedia untuk membaca audio.")
    tmpdir = Path(tempfile.mkdtemp(prefix="tangerine_asr_"))
    try:
        wav = tmpdir / "audio.wav"
        p = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
                            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                           capture_output=True, timeout=1800, creationflags=NO_WINDOW)
        if p.returncode != 0 or not wav.exists():
            raise ProcessingError("Gagal membaca audio: " + p.stderr.decode("utf-8", "replace")[:200])
        base = tmpdir / "out"
        threads = str(max(2, min(8, os.cpu_count() or 4)))
        p = subprocess.run([str(cli), "-m", str(WHISPER_MODEL), "-f", str(wav), "-l", "auto",
                            "-t", threads, "-otxt", "-of", str(base), "-np"],
                           capture_output=True, timeout=7200, creationflags=NO_WINDOW,
                           cwd=str(cli.parent))
        txt = base.with_suffix(".txt")
        if not txt.exists():
            raise ProcessingError("whisper.cpp gagal: " + p.stderr.decode("utf-8", "replace")[-300:])
        return txt.read_text(encoding="utf-8", errors="replace").strip()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def audio_metadata_markdown(path: str | Path) -> list[str]:
    lines: list[str] = []
    try:
        import mutagen
        f = mutagen.File(str(path), easy=True)
        if f is None:
            return lines
        info = getattr(f, "info", None)
        if info is not None:
            if getattr(info, "length", None):
                m, s = divmod(int(info.length), 60)
                h, m = divmod(m, 60)
                lines.append(f"- **Durasi**: {h:d}:{m:02d}:{s:02d}" if h else f"- **Durasi**: {m:d}:{s:02d}")
            if getattr(info, "bitrate", None):
                lines.append(f"- **Bitrate**: {info.bitrate // 1000} kbps")
            if getattr(info, "sample_rate", None):
                lines.append(f"- **Sample rate**: {info.sample_rate} Hz")
            if getattr(info, "channels", None):
                lines.append(f"- **Kanal**: {info.channels}")
        for key in ("title", "artist", "album", "albumartist", "date", "genre", "tracknumber",
                    "composer", "comment"):
            try:
                v = f.get(key)
            except Exception:
                v = None
            if v:
                lines.append(f"- **{key.capitalize()}**: {', '.join(map(str, v))}")
    except Exception:
        pass
    return lines


# --------------------------------------------------------------------------- #
#  Konverter kustom untuk MarkItDown
# --------------------------------------------------------------------------- #

def _make_converters():
    from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo  # noqa: F401

    def _ext(stream_info) -> str:
        ext = (stream_info.extension or "").lower()
        if not ext and stream_info.filename:
            ext = Path(stream_info.filename).suffix.lower()
        if not ext and stream_info.local_path:
            ext = Path(stream_info.local_path).suffix.lower()
        return ext

    def _materialize(file_stream: BinaryIO, stream_info, ext: str) -> tuple[str, bool]:
        """Pastikan ada path lokal (untuk file di dalam ZIP, tulis ke temp)."""
        lp = stream_info.local_path
        if lp and os.path.isfile(lp):
            return lp, False
        fd, tmp = tempfile.mkstemp(suffix=ext or ".bin", prefix="tangerine_md_")
        with os.fdopen(fd, "wb") as f:
            pos = file_stream.tell()
            shutil.copyfileobj(file_stream, f)
            file_stream.seek(pos)
        return tmp, True

    class OfflineImageConverter(DocumentConverter):
        def accepts(self, file_stream, stream_info, **kwargs):
            mt = (stream_info.mimetype or "").lower()
            return _ext(stream_info) in IMAGE_EXTS or mt.startswith("image/")

        def convert(self, file_stream, stream_info, **kwargs):
            from .processors import open_image
            ext = _ext(stream_info)
            path, temp = _materialize(file_stream, stream_info, ext)
            try:
                img = open_image(path)
                name = stream_info.filename or Path(path).name
                md = [f"# {name}", "", "## Info Gambar", "",
                      f"- **Format**: {(img.format or ext.lstrip('.')).upper()}",
                      f"- **Dimensi**: {img.width} × {img.height} px",
                      f"- **Mode warna**: {img.mode}"]
                from PIL import Image as _I
                with _I.open(path) as raw:
                    exif = image_exif_markdown(raw)
                if exif:
                    md += ["", "## Metadata EXIF", ""] + exif
                try:
                    text, lang = windows_ocr(path)
                except ProcessingError as e:
                    text, lang = f"_({e})_", ""
                md += ["", f"## Teks dalam Gambar (OCR{', ' + lang if lang else ''})", ""]
                md.append(text if text else "_Tidak ada teks yang terdeteksi._")
                return DocumentConverterResult(markdown="\n".join(md).strip() + "\n", title=name)
            finally:
                if temp:
                    os.remove(path)

    class OfflineAudioConverter(DocumentConverter):
        def accepts(self, file_stream, stream_info, **kwargs):
            mt = (stream_info.mimetype or "").lower()
            return _ext(stream_info) in AUDIO_EXTS or mt.startswith("audio/")

        def convert(self, file_stream, stream_info, **kwargs):
            ext = _ext(stream_info)
            path, temp = _materialize(file_stream, stream_info, ext)
            try:
                name = stream_info.filename or Path(path).name
                md = [f"# {name}", ""]
                meta = audio_metadata_markdown(path)
                if meta:
                    md += ["## Metadata Audio", ""] + meta + [""]
                md += ["## Transkripsi Ucapan", ""]
                try:
                    md.append(transcribe_audio(path) or "_Tidak ada ucapan yang terdeteksi._")
                except ProcessingError as e:
                    if str(e) == "NOT_READY":
                        md.append("_Transkripsi offline belum disiapkan. Klik kanan ikon Tangerine di "
                                  "tray → **Siapkan transkripsi audio offline** (unduh sekali ±150 MB)._")
                    else:
                        md.append(f"_({e})_")
                return DocumentConverterResult(markdown="\n".join(md).strip() + "\n", title=name)
            finally:
                if temp:
                    os.remove(path)

    return OfflineImageConverter(), OfflineAudioConverter()


_MD = None


def get_markitdown():
    global _MD
    if _MD is None:
        _install_magika_shim()
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")
        warnings.filterwarnings("ignore", message=".*ffmpeg.*")
        try:
            from markitdown import MarkItDown
        except ImportError:
            raise ProcessingError("Library 'markitdown' belum terpasang. Jalankan install.bat ulang.")
        md = MarkItDown(enable_plugins=False)
        img_conv, audio_conv = _make_converters()
        # prioritas lebih kecil = dicoba lebih dulu (menggantikan konverter bawaan)
        md.register_converter(img_conv, priority=-1.0)
        md.register_converter(audio_conv, priority=-1.0)
        _MD = md
    return _MD


# --------------------------------------------------------------------------- #
#  API publik (dipakai actions.py)
# --------------------------------------------------------------------------- #

def _read_url_shortcut(path: Path) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().lower().startswith("url="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def _finish(markdown: str, out: Path, src_label: str) -> Result:
    out.write_text(markdown, encoding="utf-8")
    words = len(markdown.split())
    clip = markdown if len(markdown) <= 2_000_000 else None
    msg = f"{src_label} → {out.name}\n{words:,} kata".replace(",", ".")
    if clip:
        msg += " · disalin ke clipboard"
    return Result([str(out)], msg, clip)


def file_to_markdown(path: str) -> Result:
    src = Path(path)
    if src.suffix.lower() == ".url":
        url = _read_url_shortcut(src)
        if url:
            return url_to_markdown(url, out_dir=src.parent, base_name=src.stem)
    if src.is_dir():
        raise ProcessingError("Folder tidak didukung — kompres dulu menjadi ZIP.")
    md = get_markitdown()
    try:
        res = md.convert_local(str(src))
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        if name in ("UnsupportedFormatException",):
            raise ProcessingError(f"Format {src.suffix or '(tanpa ekstensi)'} tidak didukung MarkItDown.")
        if name == "FileConversionException":
            raise ProcessingError(f"Gagal mengonversi {src.name}: {str(e).splitlines()[0][:200]}")
        raise
    text = (res.markdown or "").strip()
    if not text:
        text = f"# {src.name}\n\n_Tidak ada konten teks yang bisa diekstrak._"
    return _finish(text + "\n", unique_path(src, "converted", ".md"), src.name)


def _safe_name(s: str, fallback: str = "halaman") -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", s).strip().strip(".")
    s = re.sub(r"\s+", " ", s)
    return (s[:90] or fallback)


def default_url_dir() -> Path:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            v, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
            base = Path(os.path.expandvars(v))
    except OSError:
        base = Path.home() / "Downloads"
    d = base / "Tangerine Markdown"
    d.mkdir(parents=True, exist_ok=True)
    return d


def url_to_markdown(url: str, out_dir: Path | None = None, base_name: str | None = None) -> Result:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        raise ProcessingError("Bukan URL http/https yang valid.")
    md = get_markitdown()
    try:
        res = md.convert_uri(url)
    except Exception as e:  # noqa: BLE001
        msg = str(e).splitlines()[0][:200] if str(e) else type(e).__name__
        raise ProcessingError(f"Gagal mengambil URL (butuh internet): {msg}")
    text = (res.markdown or "").strip()
    is_yt = bool(YOUTUBE_RE.match(url))
    if is_yt and "### Transcript" not in text:
        text += "\n\n### Transcript\n_Transkrip tidak tersedia untuk video ini._"
    title = res.title or base_name or ("youtube" if is_yt else "halaman")
    out_dir = out_dir or default_url_dir()
    stem = _safe_name(base_name or title)
    out = out_dir / f"{stem}_converted.md"
    i = 1
    while out.exists():
        out = out_dir / f"{stem}_converted ({i}).md"
        i += 1
    header = f"<!-- Sumber: {url} -->\n\n"
    return _finish(header + text + "\n", out, "YouTube" if is_yt else "URL")


def any_to_markdown(item: str) -> Result:
    """Item bisa berupa path file lokal atau URL."""
    if re.match(r"^https?://", item, re.I):
        return url_to_markdown(item)
    return file_to_markdown(item)
