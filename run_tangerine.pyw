# Launcher Tangerine (dijalankan dengan pythonw.exe, tanpa jendela konsol).
#
# Berperan sebagai "supervisor": menjalankan aplikasi sebagai proses anak dan
# otomatis menjalankannya ulang bila tertutup tidak wajar (crash). Aplikasi
# hanya benar-benar berhenti bila pengguna memilih "Keluar" dari menu tray
# (kode keluar 0) atau Windows sedang shutdown/logoff.
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

if "--child" in sys.argv:
    from tangerine.main import main  # noqa: E402
    sys.exit(main())

LOG_DIR = os.path.join(os.environ.get("APPDATA", ROOT), "TangerineForWindows")
EXIT_ALREADY_RUNNING = 3


def log(msg):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "tangerine.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except Exception:
        pass


def main():
    exe = sys.executable
    args = [exe, os.path.abspath(__file__), "--child"] + [a for a in sys.argv[1:] if a != "--child"]
    crashes = []
    while True:
        started = time.time()
        try:
            code = subprocess.call(args, cwd=ROOT)
        except KeyboardInterrupt:
            return 0
        if code in (0, EXIT_ALREADY_RUNNING):
            return 0  # keluar normal / sudah ada instance lain
        log(f"Tangerine berhenti tidak wajar (kode {code}); menjalankan ulang…")
        now = time.time()
        crashes = [t for t in crashes if now - t < 300] + [now]
        if len(crashes) >= 5:
            log("Terlalu sering crash dalam 5 menit; supervisor berhenti.")
            return 1
        # jeda singkat (lebih lama bila crash langsung saat start)
        time.sleep(2 if now - started > 30 else 8)


if __name__ == "__main__":
    sys.exit(main())
