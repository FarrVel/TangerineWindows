@echo off
setlocal
cd /d "%~dp0"
title Tangerine for Windows - Instalasi
echo.
echo  ==== Tangerine for Windows - Instalasi ====
echo.
where python >nul 2>nul
if errorlevel 1 (
    echo  [!] Python tidak ditemukan. Install dari https://www.python.org/downloads/
    echo      dan centang "Add Python to PATH".
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo  [1/3] Membuat virtual environment...
    python -m venv .venv || goto :err
)
echo  [2/3] Menginstal library (butuh internet, hanya sekali)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
echo  [3/3] Membuat shortcut di Desktop dan Start Menu...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_shortcut.ps1"
echo.
echo  Selesai! Menjalankan Tangerine...
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0run_tangerine.pyw"
echo  Ikon jeruk muncul di system tray (pojok kanan bawah).
timeout /t 5 >nul
exit /b 0
:err
echo.
echo  [!] Instalasi gagal. Lihat pesan error di atas.
pause
exit /b 1
