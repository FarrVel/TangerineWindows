"""
Registry aksi: menentukan segmen radial menu berdasarkan tipe file.

Dua mode menu:
  - "convert" : konversi format
  - "tools"   : alat cepat (compress, metadata, edit, dst.)

"Item" bisa berupa path file lokal ATAU URL (http/https) yang di-drag dari browser.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable

from . import markitdown_conv as MD
from . import media as M
from . import processors as P


@dataclass
class Action:
    key: str                      # id unik
    label: str                    # teks utama di segmen (mis. "DOCX")
    sub: str = ""                 # teks kecil di bawah label (mis. "Word")
    func: Callable | None = None  # func(path, **kw) -> Result  (atau func(paths) jika batch)
    batch: bool = False           # True = func menerima list path sekaligus
    editor_mode: str | None = None  # buka editor gambar interaktif (crop/redact/annotate/edit)
    prompt: str | None = None     # dialog tambahan di UI thread sebelum diproses (mis. "color")
    progress: bool = False        # func menerima kwarg progress=callable(str)


URL_RE = re.compile(r"^https?://", re.I)


def is_url(item: str) -> bool:
    return bool(URL_RE.match(item or ""))


def category_of(path: str) -> str:
    if is_url(path):
        return "url"
    p = Path(path)
    if p.is_dir():
        return "folder"
    ext = p.suffix.lower()
    if ext in P.PDF_EXTS:
        return "pdf"
    if ext in P.IMAGE_EXTS:
        return "image"
    if ext in P.DOCX_EXTS:
        return "docx"
    if ext in (".xlsx", ".xls"):
        return "excel"
    if ext == ".pptx":
        return "pptx"
    if ext in M.AUDIO_EXTS:
        return "audio"
    if ext in M.VIDEO_EXTS:
        return "video"
    if ext == ".epub":
        return "epub"
    if ext == ".msg":
        return "msg"
    if ext == ".url":
        return "urlfile"
    if ext in (".csv", ".json", ".jsonl", ".xml", ".ipynb", ".rss", ".atom"):
        return "data"
    if ext in P.TEXT_EXTS:
        return "text"
    if ext == ".zip":
        return "zip"
    return "other"


def files_category(paths: list[str]) -> str:
    cats = {category_of(p) for p in paths}
    return cats.pop() if len(cats) == 1 else "mixed"


ZIP = Action("zip", "ZIP", "Arsipkan", P.make_zip, batch=True)
MARKDOWN = Action("markdown", "MD", "MarkItDown", MD.any_to_markdown)
TRANSCRIPT = Action("transcript", "TXT", "Transkrip", M.audio_transcribe_txt)


def _image_convert_actions(paths: list[str]) -> list[Action]:
    exts = {Path(p).suffix.lower() for p in paths}
    acts: list[Action] = []
    if exts != {".png"}:
        acts.append(Action("img_png", "PNG", "Lossless", partial(P.image_convert, fmt="PNG")))
    if not exts <= {".jpg", ".jpeg", ".jfif"}:
        acts.append(Action("img_jpg", "JPG", "Foto", partial(P.image_convert, fmt="JPEG")))
    acts += [
        Action("img_webp", "WEBP", "Web", partial(P.image_convert, fmt="WEBP")),
        Action("img_heic", "HEIC", "Apple", partial(P.image_convert, fmt="HEIC")),
        Action("img_tiff", "TIFF", "Cetak", partial(P.image_convert, fmt="TIFF")),
        Action("img_avif", "AVIF", "Modern", partial(P.image_convert, fmt="AVIF")),
        Action("img_bmp", "BMP", "Bitmap", partial(P.image_convert, fmt="BMP")),
        Action("img_pdf", "PDF", "Dokumen" if len(paths) == 1 else "Gabung", P.images_to_pdf, batch=True),
        Action("img_docx", "DOCX", "Word", P.image_to_docx),
        Action("img_ico", "ICO", "Ikon", partial(P.image_convert, fmt="ICO")),
    ]
    return [a for a in acts if not (a.key == "img_heic" and exts <= {".heic", ".heif"})
            and not (a.key == "img_webp" and exts == {".webp"})
            and not (a.key == "img_avif" and exts == {".avif"})
            and not (a.key == "img_tiff" and exts <= {".tif", ".tiff"})
            and not (a.key == "img_bmp" and exts == {".bmp"})
            and not (a.key == "img_ico" and exts == {".ico"})]


def _audio_convert_actions(paths: list[str]) -> list[Action]:
    exts = {Path(p).suffix.lower() for p in paths}
    acts = []
    for fmt, sub in (("MP3", "Universal"), ("WAV", "Lossless"), ("M4A", "AAC"), ("OGG", "WhatsApp")):
        if exts != {"." + fmt.lower()}:
            acts.append(Action(f"aud_{fmt.lower()}", fmt, sub, partial(M.audio_convert, fmt=fmt)))
    return acts + [TRANSCRIPT, MARKDOWN]


def get_actions(paths: list[str], mode: str) -> list[Action]:
    cat = files_category(paths)
    multi = len(paths) > 1

    if cat == "url":
        yt = all(M.YOUTUBE_RE.match(p) for p in paths)
        acts = [
            Action("yt_mp3", "MP3", "Audio", partial(M.youtube_download, fmt="MP3"), progress=True),
            Action("yt_mp4", "MP4", "Video", partial(M.youtube_download, fmt="MP4"), progress=True),
            Action("url_md", "MD", "Transkrip" if yt else "Halaman", MD.url_to_markdown),
        ]
        return acts

    if cat == "urlfile":
        return [MARKDOWN, ZIP]

    if cat == "pdf":
        if mode == "convert":
            acts = [
                Action("pdf_docx", "DOCX", "Word", P.pdf_to_docx),
                Action("pdf_txt", "TXT", "Teks", P.pdf_to_txt),
                Action("pdf_jpg", "JPG", "Gambar", partial(P.pdf_to_images, fmt="JPEG")),
                Action("pdf_png", "PNG", "Gambar", partial(P.pdf_to_images, fmt="PNG")),
                Action("pdf_epub", "EPUB", "eBook", P.pdf_to_epub),
                MARKDOWN,
            ]
            if multi:
                acts.append(Action("pdf_merge", "MERGE", "Gabung PDF", P.pdfs_merge, batch=True))
            return acts
        return [
            Action("pdf_compress", "COMPRESS", "Perkecil", P.pdf_compress),
            Action("pdf_meta", "METADATA", "Hapus", P.pdf_strip_metadata),
            Action("pdf_qr", "QR", "Scan", P.pdf_scan_qr),
            ZIP,
        ]

    if cat == "image":
        if mode == "convert":
            return _image_convert_actions(paths)
        acts = [
            Action("img_compress", "COMPRESS", "Perkecil", P.image_compress),
            Action("img_meta", "METADATA", "Hapus EXIF", P.image_strip_metadata),
            Action("img_qr", "QR", "Baca", P.image_read_qr),
            Action("img_ocr", "OCR", "EXIF + Teks", MD.file_to_markdown),
            Action("img_bg", "ADD BG", "Latar", P.image_add_background, prompt="color"),
        ]
        if not multi:  # alat interaktif hanya untuk satu gambar
            acts[2:2] = [
                Action("img_edit", "EDIT", "Sesuaikan", editor_mode="edit"),
                Action("img_annotate", "ANNOTATE", "Coret", editor_mode="annotate"),
            ]
            acts += [
                Action("img_crop", "CROP", "Potong", editor_mode="crop"),
                Action("img_redact", "REDACT", "Sensor", editor_mode="redact"),
            ]
        return acts

    if cat == "docx":
        if mode == "convert":
            return [
                Action("docx_pdf", "PDF", "Dokumen", P.docx_to_pdf),
                Action("docx_txt", "TXT", "Teks", P.docx_to_txt),
                Action("docx_html", "HTML", "Web", P.docx_to_html),
                Action("docx_epub", "EPUB", "eBook", P.docx_to_epub),
                MARKDOWN,
            ]
        return [
            Action("docx_compress", "COMPRESS", "Perkecil", P.office_compress),
            Action("docx_meta", "METADATA", "Hapus", P.docx_strip_metadata),
            ZIP,
        ]

    if cat in ("excel", "pptx"):
        if mode == "convert":
            return [MARKDOWN, ZIP]
        exts = {Path(p).suffix.lower() for p in paths}
        if exts <= {".xlsx", ".pptx"}:
            return [Action("office_compress", "COMPRESS", "Perkecil", P.office_compress), ZIP]
        return [ZIP]

    if cat == "audio":
        if mode == "convert":
            return _audio_convert_actions(paths)
        return [
            Action("aud_enhance", "ENHANCE", "Perjelas", M.audio_enhance),
            Action("aud_compress", "COMPRESS", "Perkecil", M.audio_compress),
            TRANSCRIPT,
            ZIP,
        ]

    if cat == "video":
        if mode == "convert":
            return [
                Action("vid_mp3", "MP3", "Audio", M.video_to_mp3),
                Action("vid_mp4", "MP4", "H.264", M.video_to_mp4),
                TRANSCRIPT,
                MARKDOWN,
            ]
        return [Action("vid_compress", "COMPRESS", "Perkecil", M.video_compress), TRANSCRIPT, ZIP]

    if cat in ("epub", "msg", "data"):
        if mode == "convert":
            acts = [MARKDOWN]
            if cat == "data":
                acts += [Action("txt_pdf", "PDF", "Dokumen", P.text_to_pdf),
                         Action("txt_html", "HTML", "Web", P.text_to_html)]
            return acts + [ZIP]
        return [ZIP]

    if cat == "text":
        if mode == "convert":
            acts = [
                Action("txt_pdf", "PDF", "Dokumen", P.text_to_pdf),
                Action("txt_docx", "DOCX", "Word", P.text_to_docx),
                Action("txt_epub", "EPUB", "eBook", P.text_to_epub),
            ]
            if not all(Path(p).suffix.lower() in (".html", ".htm") for p in paths):
                acts.append(Action("txt_html", "HTML", "Web", P.text_to_html))
            if all(Path(p).suffix.lower() in (".html", ".htm") for p in paths):
                acts.append(MARKDOWN)
            return acts
        return [ZIP]

    if cat == "zip":
        if mode == "convert":
            return [Action("unzip", "EXTRACT", "Ekstrak", P.extract_zip), MARKDOWN]
        return [ZIP]

    if cat == "mixed":
        if any(is_url(p) for p in paths):
            return [MARKDOWN]
        return [MARKDOWN, ZIP]

    # folder / other
    return [ZIP] if cat == "folder" else [MARKDOWN, ZIP]


def has_tools(paths: list[str]) -> bool:
    return files_category(paths) in ("pdf", "image", "docx", "excel", "pptx", "audio", "video")
