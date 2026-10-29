<div align="center">

# 🍊 Tangerine for Windows
**Alat Utilitas Konversi & Manipulasi File Cepat via Drag + SHIFT (Terinspirasi dari Tangerine di macOS)**

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-orange.svg)](https://www.microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*Tangerine for Windows bekerja senyap di latar belakang (System Tray). Cukup seret (drag) file apa saja dari File Explorer atau Desktop sambil menahan tombol **SHIFT**, dan Menu Melingkar (Radial Menu) modern Windows 11 akan langsung muncul di ujung kursor Anda.*

</div>

---

## ✨ Fitur Unggulan

### 1. 🎯 Gesture Pintar: Drag + SHIFT
- **Zero Click Start**: Menampilkan Radial Menu modern tepat di posisi kursor saat file di-drag sambil menahan `SHIFT`.
- **Aman 100%**: File asli tidak akan dipindah/dihapus (selalu diatur sebagai safe copy OLE).
- **Auto-Dismiss**: Batal seketika saat kursor digerakkan menjauh atau menekan tombol `ESC`.
- **Mode Toggle**: Tekan `CTRL` saat menu aktif untuk beralih mode antara **Konversi** dan **Alat Cepat**.

### 2. 📝 Integrasi Microsoft MarkItDown (Konversi Serba Markdown)
Mengubah hampir semua file menjadi format `.md` terstruktur rapi (otomatis disalin ke clipboard):
- **Dokumen Office**: Word (`.docx`), Excel (`.xlsx`, `.xls`), PowerPoint (`.pptx`).
- **Dokumen Teks & Web**: PDF, HTML, CSV, JSON, XML, eBook (`.epub`), Outlook Email (`.msg`).
- **Arsip**: ZIP (otomatis menguraikan dan membaca seluruh file di dalamnya).
- **Gambar (OCR & EXIF)**: Ekstrak teks di dalam foto via Windows Native OCR Engine + metadata kamera & GPS.
- **Audio (Speech-to-Text)**: Membaca metadata dan mentranskripsi ucapan menjadi teks.

### 3. 🎬 YouTube Downloader & Transkrip
- Tarik tautan/URL YouTube dari browser + SHIFT, atau gunakan menu tray **YouTube / URL**:
  - 🎵 **Unduh MP3**: Audio resolusi tinggi (320 kbps) lengkap dengan thumbnail cover & metadata.
  - 🎥 **Unduh MP4**: Video MP4 hingga resolusi 1080p/terbaik.
  - 📄 **Tarik Transkrip**: Mengambil teks subtitle/transkrip video menjadi file Markdown.

### 4. 🎙️ Konverter Pesan Suara (Voice Notes) & Audio
- Konversi rekaman suara WhatsApp (`.opus`, `.ogg`) atau Voice Recorder ponsel (`.m4a`, `.amr`, `.wav`) ke format universal: **MP3, WAV, M4A, OGG**.
- **Fitur ENHANCE**: Memperjelas vokal, membuang desis (noise reduction), dan menormalkan volume secara offline.
- **Fitur COMPRESS**: Mengompres rekaman suara menjadi sangat ringan tanpa merusak kejernihan suara.
- **Fitur Transkripsi Offline**: Mentranskripsi rekaman menjadi teks `.txt` menggunakan engine AI lokal (`whisper.cpp`).

### 5. 🖼️ Image Toolkit & Editor Lengkap
- **Konversi Gambar Cepat**: PNG, JPG, WEBP, HEIC (iPhone), AVIF, TIFF, BMP, PDF, DOCX, ICO.
- **Editor Bawaan**: Crop (rasio bebas/1:1/16:9), Anotasi (Pena, Panah, Kotak, Teks), Redact (Sensor/Pixelate/Blok Hitam), Sesuaikan (Brightness, Contrast, Saturation).
- **Hapus Metadata**: Menghilangkan data sensitif EXIF, lokasi GPS, dan model perangkat.
- **QR Code Scanner**: Membaca QR code dari gambar atau PDF secara instan ke clipboard.

### 6. 🔄 Selalu Aktif & Auto-Restart (Supervisor Process)
- **Auto-Startup**: Otomatis mendaftarkan diri ke Windows Startup (`HKCU\...\Run`), langsung aktif saat laptop menyala.
- **Crash Resilience**: Dilengkapi launcher supervisor yang otomatis membangkitkan aplikasi jika tertutup mendadak.
- **Hemat Daya**: Menggunakan polling Win32 API ringan (~20ms) tanpa membebani CPU maupun baterai laptop.

---

## 🚀 Panduan Instalasi & Menjalankan

### Cara Cepat (Rekomendasi)
1. Clone repositori ini:
   ```bash
   git clone https://github.com/USERNAME/REPO-NAME.git
   cd REPO-NAME
   ```
2. Klik 2x file **`install.bat`**.
   *Skrip otomatis membuat Virtual Environment (`.venv`), memasang dependensi, membuat shortcut di Desktop lengkap dengan logo Tangerine, dan menjalankan aplikasi.*

### Cara Manual
```bash
# 1. Buat virtual environment
python -m venv .venv

# 2. Pasang dependensi
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install --no-deps "markitdown>=0.1.3"
.venv\Scripts\pip install --ignore-requires-python "youtube-transcript-api>=1.0"

# 3. Jalankan aplikasi di latar belakang
.venv\Scripts\pythonw run_tangerine.pyw
```

---

## 🎮 Cara Penggunaan

1. **Konversi File**:
   - Tarik satu atau beberapa file dari File Explorer / Desktop.
   - Sambil men-drag, **tahan tombol SHIFT** → Menu radial muncul di posisi kursor.
   - Lepas file (drop) ke segmen yang diinginkan (misal: `DOCX`, `PNG`, `MP3`, `MD`).
   - Hasil konversi langsung tersimpan di folder asal dengan suffix (contoh: `dokumen_converted.docx`).
2. **Ganti Menu Konversi ↔ Alat**:
   - Tekan tombol `CTRL` saat radial menu terbuka, atau tahan `CTRL + SHIFT` sejak awal drag.
3. **Menu System Tray**:
   - Klik kanan ikon 🍊 pada area notifikasi Windows (pojok kanan bawah dekat jam) untuk mengakses fitur manual, URL dialog, log error, atau keluar.

---

## 🛠️ Struktur Proyek

```
tangerine-windows/
├── tangerine/
│   ├── actions.py          # Registry aksi & filter kategori ekstensi
│   ├── editor.py           # GUI Editor gambar (Crop, Redact, Anotasi)
│   ├── hook.py             # Global mouse/keyboard watcher (Win32 API)
│   ├── icons.py            # Rendering prosedural logo jeruk Tangerine
│   ├── main.py             # System Tray, controller & lifecycle
│   ├── markitdown_conv.py  # Integrasi MarkItDown & Windows Native OCR
│   ├── media.py            # YouTube downloader (yt-dlp) & voice processor
│   ├── processors.py       # Core offline converters (Pillow, MuPDF, dll.)
│   ├── radial_menu.py      # Antarmuka melingkar acrylic Windows 11
│   ├── url_dialog.py       # Modal dialog pemrosesan URL/YouTube
│   └── win_ocr.ps1         # Bridge PowerShell ke Windows.Media.Ocr
├── install.bat             # Skrip instalasi 1-klik untuk pengguna
├── make_shortcut.ps1       # Generator shortcut Desktop & Start Menu
├── requirements.txt        # Daftar pustaka Python
├── run.bat                 # Runner cepat
└── run_tangerine.pyw       # Launcher background supervisor
```

---

## 📄 Lisensi
Proyek ini dilisensikan di bawah lisensi **MIT**. Silakan gunakan, pelajari, dan modifikasi secara bebas.
