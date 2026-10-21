# 🍊 Tangerine for Windows

Konversi & manipulasi file instan **100% offline** lewat gesture **Drag + SHIFT**, terinspirasi dari Tangerine di macOS.
Aplikasi berjalan di system tray; saat Anda men-drag file dan menekan SHIFT, muncul **menu radial** di posisi kursor.

## Instalasi

1. Pastikan Python 3.10+ terpasang (centang *Add Python to PATH*).
2. Klik dua kali **`install.bat`** → membuat `.venv`, memasang library, membuat shortcut di Desktop/Start Menu, lalu menjalankan aplikasi.
3. Selanjutnya cukup jalankan **`run.bat`** atau shortcut **Tangerine for Windows**.

Instalasi manual:
```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw run_tangerine.pyw
```

## Cara pakai

| Langkah | Aksi |
|---|---|
| 1 | Drag satu/beberapa file dari File Explorer atau Desktop |
| 2 | Sambil men-drag, **tekan SHIFT** → menu radial muncul di kursor |
| 3 | Arahkan ke segmen lalu **lepaskan** file |
| ⇄ | **CTRL** saat menu tampil (atau CTRL+SHIFT sejak awal) = ganti mode *Konversi ↔ Alat* |
| ✕ | Gerakkan kursor menjauh / ESC = batal |

Hasil disimpan di folder asal: `nama_converted.ext`, `_compressed`, `_clean`, `_cropped`, `_redacted`, `_annotated`, `_edited`, `_bg`, `_merged`.
Notifikasi Windows muncul setelah selesai; **klik notifikasi** untuk membuka folder hasil.

Menu tray: pilih file manual (mode klik), aktif/nonaktif, deteksi dari semua aplikasi, jalankan saat Windows start, log, keluar.

## Fitur per tipe file

| Tipe | Konversi | Alat |
|---|---|---|
| PDF | DOCX, TXT, JPG, PNG, EPUB, MERGE (multi) | COMPRESS, METADATA, QR scan, ZIP |
| Gambar (JPG/PNG/WEBP/HEIC/AVIF/TIFF/BMP/GIF/ICO) | PNG, JPG, WEBP, HEIC, TIFF, AVIF, BMP, PDF (gabung jika multi), DOCX, ICO | COMPRESS, METADATA, EDIT, ANNOTATE, QR, ADD BG, CROP, REDACT |
| DOCX | PDF, TXT, HTML, EPUB | COMPRESS, METADATA, ZIP |
| TXT/MD/HTML | PDF, DOCX, EPUB, HTML | ZIP |
| ZIP | EXTRACT | ZIP |
| Lainnya / folder | ZIP | — |

DOCX → PDF memakai Microsoft Word bila terpasang, lalu LibreOffice, lalu mesin internal (MuPDF) sebagai cadangan.

## Struktur kode

```
tangerine/
  hook.py         # watcher global mouse/keyboard (deteksi drag + SHIFT)
  radial_menu.py  # radial/pie menu translucent + drop-target OLE
  actions.py      # daftar segmen dinamis per tipe file
  processors.py   # semua fungsi konversi offline
  editor.py       # editor gambar (crop/redact/annotate/edit)
  icons.py        # logo jeruk (digambar prosedural)
  main.py         # tray, notifikasi, worker thread, pengaturan
```

## Catatan

- Menu selalu melaporkan aksi **Copy** ke Explorer, jadi file asli **tidak pernah dipindah/dihapus**, meski SHIFT biasanya berarti "move".
- Secara default menu hanya muncul saat drag dari Explorer/Desktop (dan file manager populer), supaya tidak mengganggu SHIFT+seleksi teks. Aktifkan *Deteksi drag dari semua aplikasi* di tray bila perlu.
- Jika Explorer berjalan sebagai Administrator, Tangerine juga harus dijalankan sebagai Administrator agar bisa menerima drop.
- Pengaturan & log: `%APPDATA%\TangerineForWindows\`.
