"""Dialog kecil untuk memproses URL YouTube / web: MP3, MP4, atau Markdown (transkrip)."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

from .editor import STYLE
from .icons import logo_icon, logo_pixmap
from .media import YOUTUBE_RE, download_dir

URL_RE = re.compile(r"https?://\S+", re.I)


class UrlDialog(QDialog):
    # (jenis, url, kualitas) — jenis: "MP3" | "MP4" | "MD"
    chosen = Signal(str, str, str)

    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("Tangerine — YouTube & URL")
        self.setWindowIcon(logo_icon())
        self.setStyleSheet(STYLE + """
            QLineEdit { background: #2c2c33; border: 1px solid #3a3a44; border-radius: 7px; padding: 8px 10px;
                        font-size: 11pt; selection-background-color: #ff8c1a; }
            QLineEdit:focus { border-color: #ff8c1a; }
            QPushButton#big { padding: 12px 16px; font-size: 11pt; font-weight: 600; }
        """)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(logo_pixmap(36))
        head.addWidget(logo)
        t = QLabel("<b style='font-size:13pt'>YouTube &amp; URL</b><br>"
                   "<span style='color:#9a9aa6'>Unduh MP3 / MP4 atau ambil transkrip sebagai Markdown</span>")
        head.addWidget(t, 1)
        root.addLayout(head)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Tempel URL YouTube atau halaman web… (Ctrl+V)")
        self.edit.textChanged.connect(self._validate)
        self.edit.returnPressed.connect(lambda: self._go("MP3"))
        root.addWidget(self.edit)

        q = QHBoxLayout()
        lab = QLabel("Kualitas video:")
        lab.setObjectName("muted")
        q.addWidget(lab)
        self.quality = QComboBox()
        for text, val in (("Terbaik", "best"), ("1080p", "1080"), ("720p", "720"), ("480p", "480"), ("360p", "360")):
            self.quality.addItem(text, val)
        q.addWidget(self.quality)
        q.addStretch(1)
        root.addLayout(q)

        btns = QHBoxLayout()
        self.b_mp3 = QPushButton("🎵  MP3  (audio 320 kbps)")
        self.b_mp4 = QPushButton("🎬  MP4  (video)")
        self.b_md = QPushButton("📝  Transkrip / Markdown")
        for b, kind in ((self.b_mp3, "MP3"), (self.b_mp4, "MP4"), (self.b_md, "MD")):
            b.setObjectName("big")
            b.clicked.connect(lambda _=False, k=kind: self._go(k))
            btns.addWidget(b)
        self.b_mp3.setProperty("primary", True)
        root.addLayout(btns)

        self.info = QLabel(f"Hasil unduhan disimpan di: {download_dir()}")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        # isi otomatis dari clipboard bila berisi URL
        clip = QGuiApplication.clipboard().text().strip()
        m = URL_RE.search(clip)
        if m:
            self.edit.setText(m.group(0))
            self.edit.selectAll()
        self._validate()

    def _validate(self):
        url = self.edit.text().strip()
        ok = bool(URL_RE.fullmatch(url))
        for b in (self.b_mp3, self.b_mp4, self.b_md):
            b.setEnabled(ok)
        if ok and not YOUTUBE_RE.match(url):
            self.b_md.setText("📝  Halaman → Markdown")
        else:
            self.b_md.setText("📝  Transkrip / Markdown")

    def _go(self, kind: str):
        url = self.edit.text().strip()
        if not URL_RE.fullmatch(url):
            return
        self.chosen.emit(kind, url, self.quality.currentData())
        self.accept()
