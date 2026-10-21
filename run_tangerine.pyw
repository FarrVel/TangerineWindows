# Launcher tanpa jendela konsol (dijalankan dengan pythonw.exe)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tangerine.main import main  # noqa: E402

sys.exit(main())
