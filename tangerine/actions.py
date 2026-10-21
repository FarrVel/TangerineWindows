"""
Registry aksi: menentukan segmen radial menu berdasarkan tipe file.

Dua mode menu:
  - "convert" : konversi format
  - "tools"   : alat cepat (compress, metadata, edit, dst.)
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable

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


def category_of(path: str) -> str:
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
    if ext in (".xlsx", ".pptx"):
        return "office"
    if ext in P.TEXT_EXTS:
        return "text"
    if ext == ".zip":
        return "zip"
    return "other"


def files_category(paths: list[str]) -> str:
    cats = {category_of(p) for p in paths}
    return cats.pop() if len(cats) == 1 else "mixed"


ZIP = Action("zip", "ZIP", "Arsipkan", P.make_zip, batch=True)


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


def get_actions(paths: list[str], mode: str) -> list[Action]:
    cat = files_category(paths)
    multi = len(paths) > 1

    if cat == "pdf":
        if mode == "convert":
            acts = [
                Action("pdf_docx", "DOCX", "Word", P.pdf_to_docx),
                Action("pdf_txt", "TXT", "Teks", P.pdf_to_txt),
                Action("pdf_jpg", "JPG", "Gambar", partial(P.pdf_to_images, fmt="JPEG")),
                Action("pdf_png", "PNG", "Gambar", partial(P.pdf_to_images, fmt="PNG")),
                Action("pdf_epub", "EPUB", "eBook", P.pdf_to_epub),
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
            ]
        return [
            Action("docx_compress", "COMPRESS", "Perkecil", P.office_compress),
            Action("docx_meta", "METADATA", "Hapus", P.docx_strip_metadata),
            ZIP,
        ]

    if cat == "office":
        if mode == "convert":
            return [ZIP]
        return [Action("office_compress", "COMPRESS", "Perkecil", P.office_compress), ZIP]

    if cat == "text":
        if mode == "convert":
            acts = [
                Action("txt_pdf", "PDF", "Dokumen", P.text_to_pdf),
                Action("txt_docx", "DOCX", "Word", P.text_to_docx),
                Action("txt_epub", "EPUB", "eBook", P.text_to_epub),
            ]
            if not all(Path(p).suffix.lower() in (".html", ".htm") for p in paths):
                acts.append(Action("txt_html", "HTML", "Web", P.text_to_html))
            return acts
        return [ZIP]

    if cat == "zip":
        return [Action("unzip", "EXTRACT", "Ekstrak", P.extract_zip)] if mode == "convert" else [ZIP]

    # folder / other / mixed
    return [ZIP]


def has_tools(paths: list[str]) -> bool:
    return files_category(paths) in ("pdf", "image", "docx", "office")
