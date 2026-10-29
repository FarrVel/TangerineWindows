"""
Fitur multimedia:
  - YouTube (dan situs lain yang didukung yt-dlp) -> MP3 / MP4
  - Konverter pesan suara / rekaman (WhatsApp .ogg/.opus, perekam ponsel .m4a/.amr, dll.)
    -> MP3 / WAV / M4A / OGG, perjelas suara, kompres, transkripsi teks
  - Video lokal -> MP3 (ekstrak audio) / MP4 (H.264)

Semua proses audio/video memakai ffmpeg lokal (dari paket imageio-ffmpeg), offline.
Hanya unduhan YouTube yang membutuhkan internet.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .processors import ProcessingError, Result, human_size, unique_path

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "TangerineForWindows"
BIN_DIR = CONFIG_DIR / "bin"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".oga", ".opus", ".aac", ".wma",
              ".amr", ".3gp", ".3ga", ".aiff", ".aif", ".caf", ".weba", ".mka"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg", ".ts"}

URL_RE = re.compile(r"^https?://", re.I)
YOUTUBE_RE = re.compile(r"^https?://(www\.|m\.|music\.)?(youtube\.com/|youtu\.be/)", re.I)


# --------------------------------------------------------------------------- #
#  ffmpeg
# --------------------------------------------------------------------------- #

def ffmpeg_exe() -> str:
    """Path ffmpeg.exe. Binari imageio-ffmpeg disalin sebagai 'ffmpeg.exe' agar
    yt-dlp & tool lain mengenalinya."""
    local = BIN_DIR / "ffmpeg.exe"
    if local.exists():
        return str(local)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        src = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise ProcessingError("ffmpeg tidak ditemukan. Jalankan install.bat ulang.")
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, local)
        return str(local)
    except OSError:
        return src


def _run_ffmpeg(args: list[str], timeout: int = 3600):
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", *args]
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ProcessingError("ffmpeg gagal: " + (err[-1] if err else f"kode {p.returncode}"))


def media_duration(path: str | Path) -> float | None:
    try:
        import mutagen
        f = mutagen.File(str(path))
        if f is not None and getattr(f.info, "length", None):
            return float(f.info.length)
    except Exception:
        pass
    # fallback: parse output ffmpeg -i
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True,
                       creationflags=NO_WINDOW)
    m = re.search(rb"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    if m:
        h, mi, s = m.groups()
        return int(h) * 3600 + int(mi) * 60 + float(s)
    return None


def _fmt_dur(sec: float | None) -> str:
    if not sec:
        return ""
    sec = int(round(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# --------------------------------------------------------------------------- #
#  Konverter audio (voice notes & rekaman)
# --------------------------------------------------------------------------- #

AUDIO_PRESETS = {
    # fmt: (ekstensi, argumen encoder)
    "MP3": (".mp3", ["-c:a", "libmp3lame", "-q:a", "2"]),
    "WAV": (".wav", ["-c:a", "pcm_s16le"]),
    "M4A": (".m4a", ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]),
    "OGG": (".ogg", ["-c:a", "libopus", "-b:a", "64k", "-application", "voip"]),
    "FLAC": (".flac", ["-c:a", "flac"]),
}


def audio_convert(path: str, fmt: str = "MP3") -> Result:
    src = Path(path)
    ext, enc = AUDIO_PRESETS[fmt.upper()]
    out = unique_path(src, "converted", ext)
    _run_ffmpeg(["-i", str(src), "-vn", "-map_metadata", "0", *enc, str(out)])
    dur = _fmt_dur(media_duration(out))
    return Result([str(out)], f"{src.name} → {out.name}" + (f"\nDurasi {dur} · {human_size(out.stat().st_size)}" if dur else ""))


def audio_enhance(path: str) -> Result:
    """Perjelas suara: buang dengung rendah, kurangi noise, normalisasi volume."""
    src = Path(path)
    out = unique_path(src, "enhanced", ".mp3")
    af = ("highpass=f=80,lowpass=f=12000,afftdn=nf=-25,"
          "dynaudnorm=f=150:g=15,loudnorm=I=-16:TP=-1.5:LRA=11")
    _run_ffmpeg(["-i", str(src), "-vn", "-af", af, "-ar", "44100", "-c:a", "libmp3lame", "-q:a", "2", str(out)])
    return Result([str(out)], f"Suara diperjelas & volume dinormalkan → {out.name}")


def audio_compress(path: str) -> Result:
    """Kompres untuk suara: mono 64 kbps MP3 (sangat kecil, tetap jelas)."""
    src = Path(path)
    out = unique_path(src, "compressed", ".mp3")
    _run_ffmpeg(["-i", str(src), "-vn", "-ac", "1", "-ar", "32000", "-c:a", "libmp3lame", "-b:a", "64k", str(out)])
    a, b = src.stat().st_size, out.stat().st_size
    return Result([str(out)], f"{out.name}\n{human_size(a)} → {human_size(b)}")


def audio_transcribe_txt(path: str) -> Result:
    """Transkripsi ucapan -> .txt (whisper.cpp lokal)."""
    from .markitdown_conv import transcribe_audio
    src = Path(path)
    try:
        text = transcribe_audio(src)
    except ProcessingError as e:
        if str(e) == "NOT_READY":
            raise ProcessingError("Transkripsi offline belum disiapkan. Klik kanan ikon Tangerine di tray → "
                                  "'Siapkan transkripsi audio offline' (unduh sekali ±150 MB).")
        raise
    out = unique_path(src, "transcript", ".txt")
    out.write_text(text + "\n", encoding="utf-8")
    preview = text[:120] + ("…" if len(text) > 120 else "")
    return Result([str(out)], f"{out.name} (disalin ke clipboard)\n{preview or '(tidak ada ucapan terdeteksi)'}",
                  text or None)


# --------------------------------------------------------------------------- #
#  Video lokal
# --------------------------------------------------------------------------- #

def video_to_mp3(path: str) -> Result:
    src = Path(path)
    out = unique_path(src, "converted", ".mp3")
    _run_ffmpeg(["-i", str(src), "-vn", "-c:a", "libmp3lame", "-q:a", "0", str(out)])
    return Result([str(out)], f"Audio diekstrak → {out.name}")


def video_to_mp4(path: str) -> Result:
    src = Path(path)
    out = unique_path(src, "converted", ".mp4")
    _run_ffmpeg(["-i", str(src), "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)],
                timeout=6 * 3600)
    return Result([str(out)], f"{src.name} → {out.name} ({human_size(out.stat().st_size)})")


def video_compress(path: str) -> Result:
    src = Path(path)
    out = unique_path(src, "compressed", ".mp4")
    _run_ffmpeg(["-i", str(src), "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "slow",
                 "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
                 str(out)], timeout=6 * 3600)
    a, b = src.stat().st_size, out.stat().st_size
    if b >= a:
        out.unlink(missing_ok=True)
        return Result([], f"{src.name} sudah teroptimasi, tidak bisa dikompres lebih kecil.")
    return Result([str(out)], f"{out.name}\n{human_size(a)} → {human_size(b)}")


# --------------------------------------------------------------------------- #
#  YouTube downloader (yt-dlp)
# --------------------------------------------------------------------------- #

def download_dir() -> Path:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            v, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
            base = Path(os.path.expandvars(v))
    except OSError:
        base = Path.home() / "Downloads"
    d = base / "Tangerine"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _js_runtime_opts() -> dict:
    """yt-dlp butuh runtime JavaScript (deno) untuk YouTube versi terbaru."""
    try:
        import deno
        exe = deno.find_deno_bin()
        if exe and os.path.exists(exe):
            return {"js_runtimes": {"deno": {"path": exe}}}
    except Exception:
        pass
    return {}


class _Logger:
    def __init__(self):
        self.errors: list[str] = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.errors.append(re.sub(r"\x1b\[[0-9;]*m", "", str(msg)))


def youtube_download(url: str, fmt: str = "MP3", quality: str = "best",
                     progress: Callable[[str], None] | None = None,
                     out_dir: Path | None = None) -> Result:
    """fmt: 'MP3' atau 'MP4'. quality untuk MP4: 'best', '1080', '720', '480', '360'."""
    try:
        import yt_dlp
    except ImportError:
        raise ProcessingError("Library 'yt-dlp' belum terpasang. Jalankan install.bat ulang.")
    url = url.strip()
    if not URL_RE.match(url):
        raise ProcessingError("Bukan URL yang valid.")
    out_dir = out_dir or download_dir()
    fmt = fmt.upper()
    ff = ffmpeg_exe()

    last = {"pct": -10}

    def hook(d):
        if not progress:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            if total:
                pct = int(done * 100 / total)
                if pct - last["pct"] >= 10:
                    last["pct"] = pct
                    progress(f"Mengunduh {pct}% ({human_size(done)} / {human_size(total)})")
        elif d.get("status") == "finished":
            progress("Memproses dengan ffmpeg…")

    logger = _Logger()
    opts: dict = {
        "outtmpl": str(out_dir / "%(title).120B.%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": logger,
        "progress_hooks": [hook],
        "ffmpeg_location": ff,
        "overwrites": False,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        **_js_runtime_opts(),
    }
    if fmt == "MP3":
        opts.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail"},
            ],
        })
    else:
        h = "" if quality in ("best", "", None) else f"[height<={int(quality)}]"
        opts.update({
            "format": (f"bv*{h}[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/"
                       f"bv*{h}[ext=mp4]+ba[ext=m4a]/b{h}[ext=mp4]/bv*{h}+ba/b{h}/best"),
            "merge_output_format": "mp4",
            "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
        })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:  # noqa: BLE001
        msg = logger.errors[-1] if logger.errors else str(e)
        msg = re.sub(r"^ERROR:\s*", "", re.sub(r"\x1b\[[0-9;]*m", "", msg)).strip()
        if "getaddrinfo" in msg or "Failed to resolve" in msg or "Unable to download webpage" in msg:
            msg = "Tidak ada koneksi internet / situs tidak dapat dijangkau."
        raise ProcessingError(msg[:250])

    if info is None:
        raise ProcessingError("Video tidak ditemukan.")
    if info.get("_type") == "playlist" and info.get("entries"):
        info = next(e for e in info["entries"] if e)

    path = None
    for rd in info.get("requested_downloads") or []:
        path = rd.get("filepath") or rd.get("_filename")
    if not path:
        path = ydl.prepare_filename(info)
    p = Path(path)
    want = ".mp3" if fmt == "MP3" else ".mp4"
    if p.suffix.lower() != want and p.with_suffix(want).exists():
        p = p.with_suffix(want)
    if not p.exists():
        raise ProcessingError("Unduhan selesai tetapi file hasil tidak ditemukan.")
    title = info.get("title") or p.stem
    dur = _fmt_dur(info.get("duration"))
    return Result([str(p)], f"{title}\n{p.name} · {human_size(p.stat().st_size)}" + (f" · {dur}" if dur else ""))
