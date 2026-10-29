"""
Editor gambar ringan (offline) untuk aksi EDIT / ANNOTATE / CROP / REDACT.

Fitur:
  - Crop (seleksi bebas atau rasio tetap)
  - Redact (blok hitam / pixelate)
  - Anotasi: pena bebas, kotak, panah, teks; pilih warna & ketebalan
  - Edit: putar, balik, grayscale, brightness / contrast / saturasi
  - Undo (Ctrl+Z), simpan ke folder asal dengan suffix
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QImage, QKeySequence, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF, QShortcut, QTransform)
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QComboBox, QDialog, QHBoxLayout,
                               QInputDialog, QLabel, QMessageBox, QPushButton, QSlider, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget, QFrame)

from . import processors as P
from .icons import logo_icon

STYLE = """
QDialog, QWidget { background: #1e1e22; color: #e8e8ee; font-family: 'Segoe UI'; font-size: 10pt; }
QToolButton, QPushButton { background: #2c2c33; border: 1px solid #3a3a44; border-radius: 7px;
    padding: 6px 10px; color: #e8e8ee; }
QToolButton:hover, QPushButton:hover { background: #383842; }
QToolButton:checked { background: #ff8c1a; border-color: #ffb049; color: #1a1a1a; font-weight: 600; }
QPushButton#primary { background: #ff8c1a; color: #1a1a1a; font-weight: 600; border-color: #ffb049; }
QPushButton#primary:hover { background: #ffa040; }
QPushButton:disabled { color: #666; background: #26262b; }
QComboBox, QSpinBox { background: #2c2c33; border: 1px solid #3a3a44; border-radius: 6px; padding: 4px 8px; }
QSlider::groove:horizontal { height: 4px; background: #3a3a44; border-radius: 2px; }
QSlider::handle:horizontal { background: #ff8c1a; width: 14px; margin: -6px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #c96a10; border-radius: 2px; }
QLabel#muted { color: #9a9aa6; }
QFrame#sep { background: #3a3a44; max-width: 1px; min-width: 1px; }
"""


# --------------------------------------------------------------------------- #
#  Konversi QImage <-> PIL
# --------------------------------------------------------------------------- #

def qimage_to_pil(img: QImage):
    from PIL import Image
    im = img.convertToFormat(QImage.Format_RGBA8888)
    w, h, bpl = im.width(), im.height(), im.bytesPerLine()
    data = bytes(im.constBits())
    return Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", bpl, 1).copy()


def pil_to_qimage(pil) -> QImage:
    im = pil.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    q = QImage(data, im.width, im.height, im.width * 4, QImage.Format_RGBA8888)
    return q.convertToFormat(QImage.Format_ARGB32_Premultiplied).copy()


# --------------------------------------------------------------------------- #
#  Kanvas
# --------------------------------------------------------------------------- #

class Canvas(QWidget):
    changed = Signal()
    selection_changed = Signal(bool)

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        self.image = image
        self.preview: QImage | None = None
        self.undo_stack: list[QImage] = []
        self.tool = "pen"
        self.color = QColor(255, 59, 48)
        self.width_ui = 4
        self.redact_style = "Blok hitam"
        self.aspect: float | None = None
        self.sel: QRectF | None = None     # seleksi crop (koordinat gambar)
        self._drag_start: QPointF | None = None
        self._drag_now: QPointF | None = None
        self._pen_path: QPainterPath | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(640, 420)
        self.setCursor(Qt.CrossCursor)

    # ---------- geometri ----------
    def _fit(self) -> tuple[QRectF, float]:
        iw, ih = self.image.width(), self.image.height()
        m = 16
        aw, ah = max(1, self.width() - 2 * m), max(1, self.height() - 2 * m)
        s = min(aw / iw, ah / ih)
        dw, dh = iw * s, ih * s
        return QRectF((self.width() - dw) / 2, (self.height() - dh) / 2, dw, dh), s

    def to_img(self, p: QPointF) -> QPointF:
        r, s = self._fit()
        x = (p.x() - r.left()) / s
        y = (p.y() - r.top()) / s
        return QPointF(min(max(x, 0), self.image.width()), min(max(y, 0), self.image.height()))

    def to_widget(self, p: QPointF) -> QPointF:
        r, s = self._fit()
        return QPointF(r.left() + p.x() * s, r.top() + p.y() * s)

    def _img_width(self) -> float:
        return max(1.0, self.width_ui / self._fit()[1])

    # ---------- state ----------
    def push_undo(self):
        self.undo_stack.append(self.image.copy())
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)

    def undo(self):
        if self.undo_stack:
            self.image = self.undo_stack.pop()
            self.sel = None
            self.selection_changed.emit(False)
            self.changed.emit()
            self.update()

    def set_image(self, img: QImage, undoable=True):
        if undoable:
            self.push_undo()
        self.image = img
        self.sel = None
        self.selection_changed.emit(False)
        self.changed.emit()
        self.update()

    def set_tool(self, tool: str):
        self.tool = tool
        if tool != "crop":
            self.sel = None
            self.selection_changed.emit(False)
        self.update()

    # ---------- mouse ----------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        p = self.to_img(e.position())
        if self.tool == "text":
            self._add_text(p)
            return
        self._drag_start = p
        self._drag_now = p
        if self.tool == "pen":
            self._pen_path = QPainterPath(p)
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag_start is None:
            return
        p = self.to_img(e.position())
        if self.tool == "crop" and self.aspect:
            dx = p.x() - self._drag_start.x()
            dy = p.y() - self._drag_start.y()
            h = abs(dx) / self.aspect
            p = QPointF(p.x(), self._drag_start.y() + math.copysign(h, dy or 1))
            p.setY(min(max(p.y(), 0), self.image.height()))
        self._drag_now = p
        if self.tool == "pen" and self._pen_path is not None:
            self._pen_path.lineTo(p)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_start is None or e.button() != Qt.LeftButton:
            return
        a, b = self._drag_start, self._drag_now or self._drag_start
        rect = QRectF(a, b).normalized()
        self._drag_start = self._drag_now = None
        if self.tool == "crop":
            self.sel = rect if rect.width() > 3 and rect.height() > 3 else None
            self.selection_changed.emit(self.sel is not None)
        elif self.tool == "redact" and rect.width() > 2 and rect.height() > 2:
            self._redact(rect)
        elif self.tool == "pen" and self._pen_path is not None:
            path = self._pen_path
            self._pen_path = None
            self._commit(lambda p: p.drawPath(path))
        elif self.tool == "rect" and rect.width() > 2 and rect.height() > 2:
            self._commit(lambda p: p.drawRect(rect))
        elif self.tool == "arrow" and (b - a).manhattanLength() > 4:
            self._commit(lambda p: self._draw_arrow(p, a, b, self._img_width()))
        self.update()

    def _commit(self, fn):
        self.push_undo()
        img = self.image.copy()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.color, self._img_width(), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        fn(p)
        p.end()
        self.image = img
        self.changed.emit()

    @staticmethod
    def _draw_arrow(p: QPainter, a: QPointF, b: QPointF, w: float):
        p.drawLine(a, b)
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        size = max(10.0, w * 4)
        pts = [b,
               QPointF(b.x() - size * math.cos(ang - 0.45), b.y() - size * math.sin(ang - 0.45)),
               QPointF(b.x() - size * math.cos(ang + 0.45), b.y() - size * math.sin(ang + 0.45))]
        p.save()
        p.setBrush(p.pen().color())
        p.drawPolygon(QPolygonF(pts))
        p.restore()

    def _redact(self, rect: QRectF):
        r = rect.toAlignedRect().intersected(self.image.rect())
        if r.isEmpty():
            return
        self.push_undo()
        img = self.image.copy()
        p = QPainter(img)
        if self.redact_style.startswith("Pixel"):
            block = max(8, min(r.width(), r.height()) // 8)
            small = img.copy(r).scaled(max(1, r.width() // block), max(1, r.height() // block),
                                       Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            big = small.scaled(r.width(), r.height(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
            p.drawImage(r.topLeft(), big)
        elif self.redact_style.startswith("Putih"):
            p.fillRect(r, QColor(255, 255, 255))
        else:
            p.fillRect(r, QColor(0, 0, 0))
        p.end()
        self.image = img
        self.changed.emit()

    def _add_text(self, pos: QPointF):
        text, ok = QInputDialog.getText(self, "Tambah Teks", "Teks:")
        if not ok or not text.strip():
            return
        size = max(10.0, self.width_ui * 6 / self._fit()[1])

        def draw(p: QPainter):
            f = QFont("Segoe UI", 10, QFont.Bold)
            f.setPixelSize(int(size))
            p.setFont(f)
            # outline tipis supaya terbaca di semua latar
            path = QPainterPath()
            path.addText(pos.x(), pos.y() + size * 0.8, f, text)
            p.setPen(QPen(QColor(0, 0, 0, 160) if self.color.lightness() > 100 else QColor(255, 255, 255, 160),
                          max(1.0, size / 14)))
            p.setBrush(self.color)
            p.drawPath(path)
        self._commit(draw)
        self.update()

    def apply_crop(self):
        if not self.sel:
            return
        r = self.sel.toAlignedRect().intersected(self.image.rect())
        if r.width() < 2 or r.height() < 2:
            return
        self.set_image(self.image.copy(r))

    # ---------- painting ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(20, 20, 23))
        r, s = self._fit()
        # pola kotak-kotak untuk transparansi
        tile = 10
        p.save()
        p.setClipRect(r)
        p.fillRect(r, QColor(60, 60, 66))
        y = int(r.top())
        row = 0
        while y < r.bottom():
            x = int(r.left()) + (tile if row % 2 else 0)
            while x < r.right():
                p.fillRect(QRect(x, y, tile, tile), QColor(80, 80, 88))
                x += tile * 2
            y += tile
            row += 1
        p.restore()
        p.drawImage(r, self.preview if self.preview is not None else self.image)

        pen_w = self.width_ui
        # pratinjau gambar yang sedang dibuat
        if self._drag_start is not None and self._drag_now is not None:
            a, b = self.to_widget(self._drag_start), self.to_widget(self._drag_now)
            rect = QRectF(a, b).normalized()
            if self.tool in ("crop", "redact"):
                p.setPen(QPen(QColor(255, 140, 26), 1.5, Qt.DashLine))
                p.setBrush(QColor(0, 0, 0, 120) if self.tool == "redact" else Qt.NoBrush)
                p.drawRect(rect)
            elif self.tool == "rect":
                p.setPen(QPen(self.color, pen_w))
                p.setBrush(Qt.NoBrush)
                p.drawRect(rect)
            elif self.tool == "arrow":
                p.setPen(QPen(self.color, pen_w, Qt.SolidLine, Qt.RoundCap))
                self._draw_arrow(p, a, b, pen_w)
        if self.tool == "pen" and self._pen_path is not None:
            t = QTransform()
            t.translate(r.left(), r.top())
            t.scale(s, s)
            p.setPen(QPen(self.color, pen_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(t.map(self._pen_path))

        # seleksi crop
        if self.tool == "crop" and self.sel is not None and self._drag_start is None:
            sr = QRectF(self.to_widget(self.sel.topLeft()), self.to_widget(self.sel.bottomRight()))
            dim = QPainterPath()
            dim.addRect(r)
            hole = QPainterPath()
            hole.addRect(sr)
            p.fillPath(dim.subtracted(hole), QColor(0, 0, 0, 140))
            p.setPen(QPen(QColor(255, 140, 26), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(sr)
            # garis rule-of-thirds
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            for i in (1, 2):
                x = sr.left() + sr.width() * i / 3
                y = sr.top() + sr.height() * i / 3
                p.drawLine(QPointF(x, sr.top()), QPointF(x, sr.bottom()))
                p.drawLine(QPointF(sr.left(), y), QPointF(sr.right(), y))
            p.setPen(QColor(255, 255, 255))
            p.drawText(sr.adjusted(6, 4, 0, 0), Qt.AlignLeft | Qt.AlignTop,
                       f"{int(self.sel.width())} × {int(self.sel.height())}")
        p.end()


# --------------------------------------------------------------------------- #
#  Dialog editor
# --------------------------------------------------------------------------- #

class ImageEditor(QDialog):
    saved = Signal(str)

    TOOL_FOR_MODE = {"crop": "crop", "redact": "redact", "annotate": "pen", "edit": None}
    SUFFIX = {"crop": "cropped", "redact": "redacted", "annotate": "annotated", "edit": "edited"}

    def __init__(self, path: str, mode: str = "edit"):
        super().__init__(None)
        self.path = Path(path)
        self.mode = mode
        self.setWindowTitle(f"Tangerine Editor — {self.path.name}")
        self.setWindowIcon(logo_icon())
        self.setStyleSheet(STYLE)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint
                            | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        pil = P.open_image(self.path)
        self.canvas = Canvas(pil_to_qimage(pil))
        self.canvas.changed.connect(self._update_info)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ----- toolbar -----
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.tool_buttons = {}
        for key, label in (("crop", "✂ Crop"), ("redact", "▇ Redact"), ("pen", "✎ Pena"),
                           ("rect", "▭ Kotak"), ("arrow", "➜ Panah"), ("text", "T Teks")):
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self._select_tool(k))
            self.group.addButton(b)
            self.tool_buttons[key] = b
            bar.addWidget(b)
        bar.addWidget(self._sep())

        self.color_btn = QToolButton()
        self.color_btn.setToolTip("Warna")
        self.color_btn.clicked.connect(self._pick_color)
        self._refresh_color()
        bar.addWidget(self.color_btn)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 40)
        self.width_spin.setValue(4)
        self.width_spin.setToolTip("Ketebalan / ukuran teks")
        self.width_spin.valueChanged.connect(lambda v: setattr(self.canvas, "width_ui", v))
        bar.addWidget(self.width_spin)

        self.redact_combo = QComboBox()
        self.redact_combo.addItems(["Blok hitam", "Pixelate", "Putih"])
        self.redact_combo.currentTextChanged.connect(lambda t: setattr(self.canvas, "redact_style", t))
        bar.addWidget(self.redact_combo)

        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["Bebas", "1:1", "4:3", "3:2", "16:9", "9:16"])
        self.aspect_combo.currentTextChanged.connect(self._set_aspect)
        bar.addWidget(self.aspect_combo)
        self.crop_btn = QPushButton("✓ Terapkan Crop")
        self.crop_btn.setObjectName("primary")
        self.crop_btn.setEnabled(False)
        self.crop_btn.clicked.connect(self.canvas.apply_crop)
        self.canvas.selection_changed.connect(self.crop_btn.setEnabled)
        bar.addWidget(self.crop_btn)

        bar.addStretch(1)
        for text, tip, fn in (("⟲", "Putar kiri", lambda: self._transform(rot=-90)),
                              ("⟳", "Putar kanan", lambda: self._transform(rot=90)),
                              ("⇋", "Balik horizontal", lambda: self._transform(fh=True)),
                              ("⇵", "Balik vertikal", lambda: self._transform(fv=True)),
                              ("◐", "Grayscale", self._grayscale),
                              ("↶", "Undo (Ctrl+Z)", self.canvas.undo)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setMinimumWidth(40)
            b.setStyleSheet("font-size: 14pt; padding: 1px 8px;")
            b.clicked.connect(fn)
            bar.addWidget(b)
        root.addLayout(bar)

        # ----- adjust panel -----
        self.adjust = QWidget()
        adj = QHBoxLayout(self.adjust)
        adj.setContentsMargins(0, 0, 0, 0)
        self.sliders = {}
        for key, label in (("brightness", "Kecerahan"), ("contrast", "Kontras"), ("color", "Saturasi"),
                           ("sharpness", "Ketajaman")):
            lab = QLabel(label)
            lab.setObjectName("muted")
            s = QSlider(Qt.Horizontal)
            s.setRange(-100, 100)
            s.setValue(0)
            s.setMinimumWidth(110)
            s.valueChanged.connect(self._preview_adjust)
            s.sliderReleased.connect(self._preview_adjust)
            self.sliders[key] = s
            adj.addWidget(lab)
            adj.addWidget(s)
        self.apply_adj = QPushButton("Terapkan")
        self.apply_adj.clicked.connect(self._apply_adjust)
        reset = QPushButton("Reset")
        reset.clicked.connect(self._reset_sliders)
        adj.addWidget(self.apply_adj)
        adj.addWidget(reset)
        root.addWidget(self.adjust)

        root.addWidget(self.canvas, 1)

        # ----- footer -----
        foot = QHBoxLayout()
        self.info = QLabel()
        self.info.setObjectName("muted")
        foot.addWidget(self.info)
        foot.addStretch(1)
        off = QLabel("Berjalan 100% Offline | Hasil disimpan di folder asal")
        off.setObjectName("muted")
        foot.addWidget(off)
        foot.addSpacing(12)
        cancel = QPushButton("Batal")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("💾 Simpan")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(self.save_btn)
        root.addLayout(foot)

        QShortcut(QKeySequence.Undo, self, activated=self.canvas.undo)
        QShortcut(QKeySequence.Save, self, activated=self._save)
        QShortcut(QKeySequence(Qt.Key_Return), self, activated=self.canvas.apply_crop)
        QShortcut(QKeySequence(Qt.Key_Enter), self, activated=self.canvas.apply_crop)

        self._dirty = False
        self.canvas.changed.connect(lambda: setattr(self, "_dirty", True))

        tool = self.TOOL_FOR_MODE.get(mode)
        self.adjust.setVisible(mode == "edit")
        self._select_tool(tool or "pen" if mode != "edit" else "crop")
        if mode == "edit":
            self.tool_buttons["crop"].setChecked(True)
        self._update_info()

        # ukuran jendela proporsional dengan layar
        scr = self.screen().availableGeometry()
        self.resize(int(scr.width() * 0.72), int(scr.height() * 0.78))

    # ---------- helpers ----------
    @staticmethod
    def _sep():
        f = QFrame()
        f.setObjectName("sep")
        f.setFrameShape(QFrame.VLine)
        return f

    def _select_tool(self, key: str):
        self.tool_buttons[key].setChecked(True)
        self.canvas.set_tool(key)
        self.redact_combo.setVisible(key == "redact")
        self.aspect_combo.setVisible(key == "crop")
        self.crop_btn.setVisible(key == "crop")
        self.color_btn.setVisible(key in ("pen", "rect", "arrow", "text"))
        self.width_spin.setVisible(key in ("pen", "rect", "arrow", "text"))

    def _set_aspect(self, text: str):
        if text == "Bebas":
            self.canvas.aspect = None
        else:
            a, b = text.split(":")
            self.canvas.aspect = float(a) / float(b)

    def _refresh_color(self):
        c = self.canvas.color
        pm = QPixmap(18, 18)
        pm.fill(c)
        self.color_btn.setIcon(pm)
        self.color_btn.setIconSize(QSize(18, 18))

    def _pick_color(self):
        c = QColorDialog.getColor(self.canvas.color, self, "Pilih warna")
        if c.isValid():
            self.canvas.color = c
            self._refresh_color()

    def _update_info(self):
        img = self.canvas.image
        self.info.setText(f"{self.path.name}   ·   {img.width()} × {img.height()} px")

    def _transform(self, rot=0, fh=False, fv=False):
        img = self.canvas.image
        if rot:
            img = img.transformed(QTransform().rotate(rot), Qt.SmoothTransformation)
        if fh or fv:
            img = img.mirrored(fh, fv)
        self.canvas.set_image(img)

    def _grayscale(self):
        pil = qimage_to_pil(self.canvas.image)
        alpha = pil.getchannel("A")
        g = pil.convert("L").convert("RGBA")
        g.putalpha(alpha)
        self.canvas.set_image(pil_to_qimage(g))

    # ---------- adjustments ----------
    def _adjusted(self, pil):
        from PIL import ImageEnhance
        alpha = pil.getchannel("A")
        rgb = pil.convert("RGB")
        for key, enh in (("brightness", ImageEnhance.Brightness), ("contrast", ImageEnhance.Contrast),
                         ("color", ImageEnhance.Color), ("sharpness", ImageEnhance.Sharpness)):
            v = self.sliders[key].value()
            if v:
                factor = 1 + v / 100 * (2 if key == "sharpness" else 1)
                rgb = enh(rgb).enhance(max(0.0, factor))
        out = rgb.convert("RGBA")
        out.putalpha(alpha)
        return out

    def _preview_adjust(self):
        if all(s.value() == 0 for s in self.sliders.values()):
            self.canvas.preview = None
            self.canvas.update()
            return
        img = self.canvas.image
        small = img.scaled(1400, 1400, Qt.KeepAspectRatio, Qt.SmoothTransformation) \
            if max(img.width(), img.height()) > 1400 else img
        self.canvas.preview = pil_to_qimage(self._adjusted(qimage_to_pil(small)))
        self.canvas.update()

    def _apply_adjust(self):
        if all(s.value() == 0 for s in self.sliders.values()):
            return
        out = pil_to_qimage(self._adjusted(qimage_to_pil(self.canvas.image)))
        self.canvas.preview = None
        self._reset_sliders(silent=True)
        self.canvas.set_image(out)

    def _reset_sliders(self, silent=False):
        for s in self.sliders.values():
            s.blockSignals(True)
            s.setValue(0)
            s.blockSignals(False)
        self.canvas.preview = None
        self.canvas.update()

    # ---------- save ----------
    def _save(self):
        # terapkan penyesuaian yang belum diterapkan
        if any(s.value() for s in self.sliders.values()):
            self._apply_adjust()
        if self.mode == "crop" and self.canvas.sel is not None:
            self.canvas.apply_crop()
        ext = self.path.suffix.lower()
        fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".jfif": "JPEG", ".png": "PNG", ".webp": "WEBP",
               ".bmp": "BMP", ".tif": "TIFF", ".tiff": "TIFF", ".heic": "HEIC", ".heif": "HEIC",
               ".avif": "AVIF", ".gif": "GIF", ".ico": "ICO"}.get(ext, "PNG")
        if fmt == "PNG" and ext != ".png":
            ext = ".png"
        out = P.unique_path(self.path, self.SUFFIX.get(self.mode, "edited"), ext)
        try:
            pil = qimage_to_pil(self.canvas.image)
            if pil.getchannel("A").getextrema() == (255, 255):
                pil = pil.convert("RGB")
            P.save_image(pil, out, fmt, quality=95)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Gagal menyimpan", str(e))
            return
        self._dirty = False
        self.saved.emit(str(out))
        self.accept()

    def reject(self):
        if self._dirty:
            r = QMessageBox.question(self, "Buang perubahan?",
                                     "Perubahan belum disimpan. Tutup tanpa menyimpan?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        super().reject()

    def closeEvent(self, e):
        if self._dirty:
            r = QMessageBox.question(self, "Buang perubahan?",
                                     "Perubahan belum disimpan. Tutup tanpa menyimpan?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self._dirty = False
        super().closeEvent(e)
