<div align="center">

# 🍊 Tangerine for Windows
**Utilitas Konversi & Manipulasi File Cepat via Drag + SHIFT (Terinspirasi dari Tangerine di macOS)**

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-orange.svg)](https://www.microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*Tangerine for Windows bekerja senyap di latar belakang (System Tray). Cukup seret (drag) file apa saja dari File Explorer atau Desktop sambil menahan tombol **SHIFT**, dan Menu Melingkar (Radial Menu) modern Windows 11 akan langsung muncul di ujung kursor Anda.*

</div>

---

## 📋 Daftar Lengkap Fitur Berdasarkan Jenis File

Berikut adalah matriks fungsionalitas dan menu yang tersedia di Tangerine for Windows:

| Kategori File | Ekstensi yang Didukung | Opsi Konversi (Mode `KONVERSI`) | Alat Cepat (Mode `ALAT`) |
| :--- | :--- | :--- | :--- |
| **Dokumen PDF** | `.pdf` | • **DOCX** (ke Microsoft Word)<br>• **TXT** (ekstrak teks)<br>• **JPG / PNG** (tiap halaman jadi gambar)<br>• **EPUB** (buku digital)<br>• **MD** (MarkItDown komprehensif)<br>• **MERGE** (jika drag banyak PDF) | • **COMPRESS** (perkecil ukuran PDF)<br>• **METADATA** (bersihkan info penulis/edit)<br>• **QR** (scan semua QR code di lembar PDF)<br>• **ZIP** (arsipkan) |
| **Dokumen Word** | `.docx` | • **PDF** (via Word/LibreOffice/Native)<br>• **TXT** (ekstrak teks polos)<br>• **HTML** (halaman web bersih)<br>• **EPUB** (e-book reader)<br>• **MD** (MarkItDown) | • **COMPRESS** (kompres gambar internal docx)<br>• **METADATA** (hapus info privasi & revisi)<br>• **ZIP** (arsipkan) |
| **Excel & Spreadsheet** | `.xlsx`, `.xls`, `.csv` | • **MD** (ekstrak jadi tabel Markdown rapi)<br>• **PDF** *(khusus .csv)*<br>• **HTML** *(khusus .csv)* | • **COMPRESS** *(khusus xlsx)*<br>• **ZIP** (arsipkan) |
| **PowerPoint** | `.pptx` | • **MD** (ekstrak teks & slide Markdown) | • **COMPRESS** (kompres media internal pptx)<br>• **ZIP** (arsipkan) |
| **Gambar & Foto** | `.png`, `.jpg`, `.jpeg`, `.webp`, `.heic`, `.avif`, `.tiff`, `.bmp`, `.ico` | • **PNG / JPG / WEBP / BMP**<br>• **HEIC / AVIF / TIFF / ICO**<br>• **PDF** (satu gambar atau gabung banyak foto)<br>• **DOCX** (sematkan langsung ke Word) | • **COMPRESS** (kompresi cerdas tanpa pecah)<br>• **METADATA** (hapus EXIF, kamera, GPS)<br>• **QR** (deteksi & decode QR code ke clipboard)<br>• **OCR** (baca teks dalam gambar via Windows OCR)<br>• **ADD BG** (tambah warna latar belakang transparan)<br>• **CROP** (potong rasio bebas / 1:1 / 16:9)<br>• **REDACT** (sensor/pixelate/blok hitam)<br>• **ANNOTATE** (pena, panah, kotak, teks)<br>• **EDIT** (kecerahan, kontras, rotasi, grayscale) |
| **Pesan Suara & Audio** | `.opus`, `.ogg` *(WhatsApp)*<br>`.m4a`, `.amr`, `.3gp` *(Perekam HP)*<br>`.mp3`, `.wav`, `.flac`, `.aac` | • **MP3** (audio standar universal 320k)<br>• **WAV** (lossless tanpa kompresi)<br>• **M4A** (format ringkas Apple/Android)<br>• **OGG** (format voice note)<br>• **TXT** (transkripsi ucapan speech-to-text)<br>• **MD** (metadata + transkripsi lengkap) | • **ENHANCE** (perjelas vokal, buang desis/noise, normalkan volume)<br>• **COMPRESS** (perkecil ukuran audio/suara)<br>• **TXT** (transkrip cepat ke clipboard)<br>• **ZIP** (arsipkan) |
| **Video** | `.mp4`, `.mkv`, `.webm`, `.mov`, `.avi` | • **MP3** (ekstrak audio musik/suara)<br>• **MP4** (standardisasi ke H.264/AAC)<br>• **TXT** (transkripsi suara dalam video)<br>• **MD** (MarkItDown) | • **COMPRESS** (perkecil ukuran video)<br>• **TXT** (transkrip teks audio)<br>• **ZIP** (arsipkan) |
| **Data & Web** | `.html`, `.json`, `.xml`, `.ipynb`, `.epub`, `.msg` *(Outlook)* | • **MD** (konversi struktur ke Markdown)<br>• **TXT / PDF / HTML** *(sesuai ekstensi)* | • **ZIP** (arsipkan) |
| **Arsip ZIP** | `.zip` | • **EXTRACT** (ekstrak isi folder)<br>• **MD** (inspeksi & konversi seluruh isi zip) | • **ZIP** (rekursif) |
| **Link YouTube / Web** | URL `youtube.com`, `youtu.be`, atau link web apapun | • **MP3** (unduh lagu kualitas 320 kbps + cover)<br>• **MP4** (unduh video hingga 1080p)<br>• **MD** (tarik transkrip subtitle YouTube / halaman web) | — |

---

## 🌟 Rincian Fitur Utama

### 1. 🎯 Gesture Pintar: Drag + SHIFT
- **Zero Click**: Menampilkan Radial Menu modern bergaya Windows 11 tepat di ujung kursor saat file di-drag sambil menahan `SHIFT`.
- **Aman 100%**: File asli tidak pernah dipindah atau dihapus (selalu diatur sebagai safe copy OLE).
- **Auto-Dismiss**: Menu otomatis menutup jika kursor bergerak menjauh, tidak ada aksi dalam 2.5 detik, atau menekan tombol `ESC`.
- **Mode Toggle**: Tekan tombol `CTRL` saat menu aktif untuk berganti antara mode **Konversi** dan mode **Alat Cepat**.

### 2. 📝 Integrasi Microsoft MarkItDown
Mengubah dokumen apa saja menjadi Markdown bersih yang siap dimasukkan ke LLM (ChatGPT/Claude/Gemini):
- Membaca tabel Excel & CSV menjadi format Markdown pipe `|`.
- Menelusuri isi file `.zip` dan mengonversi seluruh dokumen di dalamnya secara otomatis.
- Menarik transkrip video YouTube beserta ringkasan bab/timestamp video.
- Hasil Markdown langsung tersimpan di folder asal dan otomatis disalin ke **clipboard**.

### 3. 🎬 YouTube Downloader & Transcriber
- Bisa digunakan lewat **drag URL** langsung dari address bar browser + SHIFT, atau via menu tray **YouTube / URL**:
  - 🎵 **MP3**: Konversi ke audio 320 kbps jernih + metadata ID3 + cover album.
  - 🎥 **MP4**: Unduh video dengan opsi resolusi (Terbaik, 1080p, 720p, 480p, 360p).
  - 📄 **Transkrip**: Menarik teks ucapan di video YouTube langsung ke format Markdown.

### 4. 🎙️ Pemrosesan Pesan Suara (Voice Notes)
- Mengonversi voice note WhatsApp (`.opus`, `.ogg`) atau rekaman HP bawaan (`.m4a`, `.amr`) agar bisa diputar di PC maupun player mobil.
- **Audio Enhance**: Menggunakan filter audio lanjutan (highpass, lowpass, FFT denoiser, dynaudnorm) untuk menjernihkan rekaman kuliah, rapat, atau voice note yang bising.
- **Offline Speech-to-Text**: Mentranskripsi suara ucapan ke teks menggunakan AI `whisper.cpp` model multibahasa (termasuk Bahasa Indonesia) 100% offline.

### 5. 🖼️ Image Editor & OCR Bawaan
- Membuka editor bawaan saat memilih menu **EDIT, ANNOTATE, CROP,** atau **REDACT**.
- **OCR Offline**: Menggunakan API engine OCR Windows (`Windows.Media.Ocr`) untuk mengenali teks pada struk belanja, screenshot, dokumen scan, dan foto tanpa koneksi internet.
- **Sanitasi Metadata**: Menghapus data rahasia seperti lokasi koordinat GPS kamera, nama pemilik, dan tipe perangkat pada foto.

### 6. 🔄 Selalu Aktif di Latar Belakang (Persistent Background)
- **Auto-Startup**: Otomatis mendaftarkan diri ke Windows Startup (`HKCU\...\Run`), langsung aktif saat laptop menyala.
- **Supervisor Process**: Jika aplikasi crash atau ditutup tidak sengaja, supervisor otomatis menjalankannya kembali secara senyap.
- **Hemat Resource**: Dirancang tanpa window utama yang berat, hanya polling API Windows ringan (~20ms) sehingga tidak memboroskan RAM maupun baterai.

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
   - Hasil konversi langsung tersimpan di folder asal dengan akhiran nama (contoh: `dokumen_converted.docx`).
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
