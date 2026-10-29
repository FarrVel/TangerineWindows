"""
Radial / Pie menu translucent ala Tangerine.

- Mode DRAG  : jendela menjadi drop-target OLE. File di-drag dari Explorer lalu
               dilepas (drop) di salah satu segmen.
- Mode KLIK  : (dari menu tray "Pilih file…") segmen dipilih dengan klik.

Hub tengah menampilkan logo, nama file, ukuran & mode aktif.
CTRL (saat drag) / klik hub / TAB  -> berganti mode Konversi <-> Alat.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRectF, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter,
                           QPainterPath, QPen, QRadialGradient, QLinearGradient)
from PySide6.QtWidgets import QWidget

from . import actions as A
from .icons import ORANGE, ORANGE_DARK, ORANGE_LIGHT, draw_logo
from .processors import human_size

W, H = 420, 470          # ukuran jendela (logical px)
CX, CY = W / 2, 205      # pusat lingkaran
R_OUT = 180              # radius luar
R_IN = 66                # radius hub
GAP_DEG = 1.4            # celah antar segmen (derajat)
FOOTER = "Berjalan 100% Offline  |  Hasil disimpan di folder asal"


def _pt(r: float, a_deg: float) -> QPointF:
    """Titik di radius r, sudut a (derajat, searah jarum jam dari atas)."""
    a = math.radians(a_deg)
    return QPointF(CX + r * math.sin(a), CY - r * math.cos(a))


def _segment_path(a0: float, a1: float, r_in: float, r_out: float) -> QPainterPath:
    path = QPainterPath()
    outer = QRectF(CX - r_out, CY - r_out, 2 * r_out, 2 * r_out)
    inner = QRectF(CX - r_in, CY - r_in, 2 * r_in, 2 * r_in)
    path.moveTo(_pt(r_out, a0))
    path.arcTo(outer, 90 - a0, -(a1 - a0))
    path.lineTo(_pt(r_in, a1))
    path.arcTo(inner, 90 - a1, (a1 - a0))
    path.closeSubpath()
    return path


class RadialMenu(QWidget):
    action_chosen = Signal(object, list)   # (Action, paths)
    dismissed = Signal()                   # ditutup tanpa memilih

    def __init__(self):
        super().__init__(None)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setMouseTracking(True)
        self.setFixedSize(W, H)
        self.setWindowTitle("Tangerine")

        self.paths: list[str] = []
        self.mode = "convert"
        self.actions: list[A.Action] = []
        self.hover = -1
        self.drag_mode = False
        self._hub_hover = False
        self._flash = 0.0

        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(lambda _: self.update())
        self._t = lambda: float(self._anim.currentValue() or 0.0)

        self._flash_anim = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=450)
        self._flash_anim.valueChanged.connect(self._on_flash)

        self.f_label = QFont("Segoe UI Variable Display", 11, QFont.Bold)
        self.f_label.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self.f_sub = QFont("Segoe UI", 8)
        self.f_hub = QFont("Segoe UI Semibold", 9)
        self.f_hub_small = QFont("Segoe UI", 8)
        self.f_mode = QFont("Segoe UI", 7, QFont.Bold)
        self.f_mode.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        self.f_footer = QFont("Segoe UI", 8)

    # ------------------------------------------------------------------ #
    #  API publik
    # ------------------------------------------------------------------ #
    def show_drag(self, tools: bool = False):
        """Tampilkan sebagai drop-target di posisi kursor (mode drag)."""
        self.drag_mode = True
        self.paths = []
        self.actions = []
        self.mode = "tools" if tools else "convert"
        self.hover = -1
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAcceptDrops(True)
        self._place_and_show()
        # bila tidak ada file/link yang masuk (mis. SHIFT + seleksi teks biasa), tutup otomatis
        self._show_id = getattr(self, "_show_id", 0) + 1
        sid = self._show_id
        QTimer.singleShot(2500, lambda: self._auto_close(sid))

    def _auto_close(self, sid: int):
        if sid == self._show_id and self.drag_mode and self.isVisible() and not self.paths:
            self.dismiss()

    def show_click(self, paths: list[str], tools: bool = False):
        """Tampilkan menu yang dipilih dengan klik (dari tray)."""
        self.drag_mode = False
        self.mode = "tools" if tools and A.has_tools(paths) else "convert"
        self.hover = -1
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAcceptDrops(False)
        self._set_files(paths)
        self._place_and_show()
        self.activateWindow()
        self.setFocus()

    def toggle_mode(self):
        if not self.paths:
            self.mode = "tools" if self.mode == "convert" else "convert"
            self.update()
            return
        if not A.has_tools(self.paths):
            self._flash_anim.start()
            return
        self.mode = "tools" if self.mode == "convert" else "convert"
        self.actions = A.get_actions(self.paths, self.mode)
        self.hover = -1
        self._anim.stop()
        self._anim.setDuration(140)
        self._anim.start()
        self.update()

    def dismiss(self):
        if self.isVisible():
            self.hide()
            self.dismissed.emit()

    # ------------------------------------------------------------------ #
    def _place_and_show(self):
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        x = int(pos.x() - CX)
        y = int(pos.y() - CY)
        x = max(geo.left(), min(x, geo.right() - W + 1))
        y = max(geo.top(), min(y, geo.bottom() - H + 1))
        self.move(x, y)
        self._anim.stop()
        self._anim.setDuration(170)
        self.show()
        self.raise_()
        self._anim.start()

    def _set_files(self, paths: list[str]):
        self.paths = paths
        self.actions = A.get_actions(paths, self.mode)
        self.hover = -1
        self.update()

    def _on_flash(self, v):
        self._flash = float(v)
        self.update()

    # ------------------------------------------------------------------ #
    #  Geometri
    # ------------------------------------------------------------------ #
    def _hit(self, pos: QPointF) -> tuple[str, int]:
        dx, dy = pos.x() - CX, pos.y() - CY
        d = math.hypot(dx, dy)
        if d <= R_IN:
            return "hub", -1
        if d > R_OUT + 6:
            return "out" if d > R_OUT + 45 else "near", -1
        n = len(self.actions)
        if n == 0:
            return "ring", -1
        a = (math.degrees(math.atan2(dy, dx)) + 90) % 360
        span = 360 / n
        return "seg", int(((a + span / 2) % 360) // span)

    def _update_hover(self, pos: QPointF) -> str:
        zone, idx = self._hit(pos)
        hub = zone == "hub"
        if idx != self.hover or hub != self._hub_hover:
            self.hover = idx
            self._hub_hover = hub
            self.update()
        return zone

    # ------------------------------------------------------------------ #
    #  Drag & drop (mode drag)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _local_paths(mime) -> list[str]:
        """Path file lokal, atau URL http(s) bila yang di-drag adalah link (mis. dari browser)."""
        out, urls = [], []
        if mime.hasUrls():
            for u in mime.urls():
                if u.isLocalFile():
                    p = os.path.normpath(u.toLocalFile())
                    if os.path.exists(p):
                        out.append(p)
                elif u.scheme() in ("http", "https"):
                    urls.append(u.toString())
        if not out and not urls and mime.hasText():
            t = mime.text().strip()
            if t.startswith(("http://", "https://")) and " " not in t and "\n" not in t:
                urls.append(t)
        return out or urls[:1]

    def _accept_copy(self, event):
        # PENTING: selalu laporkan CopyAction agar Explorer TIDAK menghapus
        # file asli (SHIFT di Explorer berarti "move").
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def dragEnterEvent(self, event):
        paths = self._local_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        if paths != self.paths:
            self._set_files(paths)
        self._update_hover(event.position())
        self._accept_copy(event)

    def dragMoveEvent(self, event):
        zone = self._update_hover(event.position())
        if zone == "out":
            event.ignore()
            QTimer.singleShot(0, self.dismiss)
            return
        if zone == "seg":
            self._accept_copy(event)
        else:
            # di hub / di luar ring: tampilkan kursor "tidak bisa"
            event.ignore()

    def dragLeaveEvent(self, event):
        # kursor bergerak menjauh dari menu -> sembunyikan
        QTimer.singleShot(0, self.dismiss)

    def dropEvent(self, event):
        zone, idx = self._hit(event.position())
        paths = self._local_paths(event.mimeData()) or self.paths
        if zone == "seg" and 0 <= idx < len(self.actions):
            self._accept_copy(event)
            act = self.actions[idx]
            # sembunyikan setelah panggilan OLE Drop selesai
            QTimer.singleShot(0, self.hide)
            QTimer.singleShot(0, lambda: self.action_chosen.emit(act, paths))
        else:
            event.ignore()
            QTimer.singleShot(0, self.dismiss)

    # ------------------------------------------------------------------ #
    #  Mouse / keyboard (mode klik)
    # ------------------------------------------------------------------ #
    def mouseMoveEvent(self, e):
        self._update_hover(e.position())

    def leaveEvent(self, e):
        if not self.drag_mode and self.isVisible():
            QTimer.singleShot(250, self._close_if_away)

    def _close_if_away(self):
        if self.isVisible() and not self.geometry().contains(QCursor.pos()):
            self.dismiss()

    def mousePressEvent(self, e):
        zone, idx = self._hit(e.position())
        if e.button() == Qt.RightButton:
            self.toggle_mode()
            return
        if zone == "hub":
            self.toggle_mode()
        elif zone == "seg" and 0 <= idx < len(self.actions):
            act = self.actions[idx]
            paths = list(self.paths)
            self.hide()
            QTimer.singleShot(0, lambda: self.action_chosen.emit(act, paths))
        elif zone in ("out", "near"):
            self.dismiss()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.dismiss()
        elif e.key() in (Qt.Key_Tab, Qt.Key_Control, Qt.Key_Space):
            self.toggle_mode()

    def focusNextPrevChild(self, nxt):  # agar TAB tidak berpindah fokus
        return False

    def hideEvent(self, e):
        self.hover = -1
        super().hideEvent(e)

    # ------------------------------------------------------------------ #
    #  Painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, _):
        t = self._t()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        # alpha=1 di seluruh jendela agar seluruh area tetap menjadi target drop
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))

        p.setOpacity(t)
        s = 0.86 + 0.14 * t
        p.translate(CX, CY)
        p.scale(s, s)
        p.translate(-CX, -CY)

        self._paint_body(p)
        self._paint_segments(p)
        self._paint_hub(p)
        p.resetTransform()
        p.setOpacity(t)
        self._paint_footer(p)
        p.end()

    def _paint_body(self, p: QPainter):
        # bayangan luar
        for i, a in enumerate((26, 16, 9)):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, a))
            r = R_OUT + 4 + i * 4
            p.drawEllipse(QPointF(CX, CY + 4), r, r)
        # "acrylic": gradien gelap translucent + tint jeruk tipis
        g = QRadialGradient(QPointF(CX, CY - R_OUT * 0.3), R_OUT * 1.4)
        g.setColorAt(0.0, QColor(52, 48, 50, 232))
        g.setColorAt(0.6, QColor(32, 31, 34, 238))
        g.setColorAt(1.0, QColor(22, 22, 25, 244))
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 38), 1.2))
        p.drawEllipse(QPointF(CX, CY), R_OUT, R_OUT)
        # highlight atas (efek kaca)
        hl = QLinearGradient(0, CY - R_OUT, 0, CY)
        hl.setColorAt(0, QColor(255, 255, 255, 22))
        hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hl)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(CX, CY), R_OUT - 1.5, R_OUT - 1.5)

    def _paint_segments(self, p: QPainter):
        n = len(self.actions)
        r_lab = (R_IN + R_OUT) / 2 + 4
        if n == 0:
            # placeholder sebelum file terdeteksi
            p.setPen(QPen(QColor(255, 255, 255, 30), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(CX, CY), r_lab, r_lab)
            p.setFont(self.f_sub)
            p.setPen(QColor(255, 255, 255, 140))
            p.drawText(QRectF(CX - 120, CY - R_OUT + 30, 240, 20), Qt.AlignCenter,
                       "Gerakkan file ke menu…")
            return
        span = 360 / n
        for i, act in enumerate(self.actions):
            c = i * span
            a0, a1 = c - span / 2 + GAP_DEG / 2, c + span / 2 - GAP_DEG / 2
            if n == 1:
                a0, a1 = -179.9, 179.9
            path = _segment_path(a0, a1, R_IN + 6, R_OUT - 6)
            hovered = i == self.hover
            if hovered:
                g = QRadialGradient(QPointF(CX, CY), R_OUT)
                g.setColorAt(0.35, QColor(ORANGE_LIGHT.red(), ORANGE_LIGHT.green(), ORANGE_LIGHT.blue(), 235))
                g.setColorAt(1.0, QColor(ORANGE_DARK.red(), ORANGE_DARK.green(), ORANGE_DARK.blue(), 235))
                p.setBrush(g)
                p.setPen(QPen(QColor(255, 210, 150, 200), 1.2))
            else:
                p.setBrush(QColor(255, 255, 255, 14))
                p.setPen(QPen(QColor(255, 255, 255, 22), 1))
            p.drawPath(path)

            pt = _pt(r_lab, c if n > 1 else 0)
            if n == 1:
                pt = QPointF(CX, CY - r_lab)
            fm = QFontMetrics(self.f_label)
            p.setFont(self.f_label)
            p.setPen(QColor(255, 255, 255) if hovered else QColor(240, 240, 245, 225))
            p.drawText(QRectF(pt.x() - 60, pt.y() - fm.height() + 3, 120, fm.height()),
                       Qt.AlignHCenter | Qt.AlignBottom, act.label)
            if act.sub:
                p.setFont(self.f_sub)
                p.setPen(QColor(255, 245, 235, 230) if hovered else QColor(200, 200, 210, 150))
                p.drawText(QRectF(pt.x() - 60, pt.y() + 3, 120, 16), Qt.AlignHCenter | Qt.AlignTop, act.sub)

    def _paint_hub(self, p: QPainter):
        # cincin jeruk
        ring = QColor(ORANGE)
        if self._flash > 0:
            ring = QColor(255, 70, 70)
        p.setPen(QPen(ring, 2.2 if not self._hub_hover else 3))
        g = QRadialGradient(QPointF(CX, CY - 20), R_IN * 1.3)
        g.setColorAt(0, QColor(48, 44, 46, 250))
        g.setColorAt(1, QColor(26, 25, 28, 252))
        p.setBrush(g)
        p.drawEllipse(QPointF(CX, CY), R_IN, R_IN)

        draw_logo(p, QRectF(CX - 13, CY - 56, 26, 26))

        if self.paths and self.paths[0].startswith(("http://", "https://")):
            from urllib.parse import urlparse
            u = urlparse(self.paths[0])
            host = (u.hostname or "").removeprefix("www.")
            yt = "youtu" in host
            name, sub = ("YouTube" if yt else host or "URL"), ("Video · online" if yt else "Halaman web")
        elif self.paths:
            first = Path(self.paths[0])
            name = first.name if len(self.paths) == 1 else f"{len(self.paths)} file"
            try:
                if len(self.paths) == 1:
                    size = human_size(first.stat().st_size) if first.is_file() else "Folder"
                else:
                    size = human_size(sum(Path(x).stat().st_size for x in self.paths if Path(x).is_file()))
            except OSError:
                size = ""
            ext = first.suffix.upper().lstrip(".") if len(self.paths) == 1 else ""
            sub = f"{ext} · {size}" if ext and size else size
        else:
            name, sub = "Tangerine", "Lepas di segmen"

        p.setFont(self.f_hub)
        p.setPen(QColor(250, 250, 252))
        fm = QFontMetrics(self.f_hub)
        p.drawText(QRectF(CX - 56, CY - 26, 112, 18), Qt.AlignCenter,
                   fm.elidedText(name, Qt.ElideMiddle, 108))
        p.setFont(self.f_hub_small)
        p.setPen(QColor(190, 190, 200))
        p.drawText(QRectF(CX - 56, CY - 8, 112, 16), Qt.AlignCenter, sub)

        # badge mode
        mode_txt = "KONVERSI" if self.mode == "convert" else "ALAT"
        p.setFont(self.f_mode)
        fmm = QFontMetrics(self.f_mode)
        bw = fmm.horizontalAdvance(mode_txt) + 16
        badge = QRectF(CX - bw / 2, CY + 12, bw, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ORANGE.red(), ORANGE.green(), ORANGE.blue(), 60))
        p.drawRoundedRect(badge, 8, 8)
        p.setPen(ORANGE_LIGHT)
        p.drawText(badge, Qt.AlignCenter, mode_txt)

        hint = "CTRL: ganti mode" if self.drag_mode else "Klik: ganti mode"
        if self.paths and not A.has_tools(self.paths):
            hint = ""
        p.setFont(self.f_hub_small)
        p.setPen(QColor(150, 150, 160))
        p.drawText(QRectF(CX - 56, CY + 31, 112, 16), Qt.AlignCenter, hint)

    def _paint_footer(self, p: QPainter):
        online = bool(self.paths) and self.paths[0].startswith(("http://", "https://"))
        text = "Butuh internet  |  Hasil disimpan di Downloads\\Tangerine" if online else FOOTER
        fm = QFontMetrics(self.f_footer)
        tw = fm.horizontalAdvance(text) + 28
        rect = QRectF(CX - tw / 2, CY + R_OUT + 20, tw, 26)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(QColor(26, 26, 30, 230))
        p.drawRoundedRect(rect, 13, 13)
        p.setPen(Qt.NoPen)
        p.setBrush(ORANGE)
        p.drawEllipse(QPointF(rect.left() + 13, rect.center().y()), 3, 3)
        p.setFont(self.f_footer)
        p.setPen(QColor(215, 215, 222))
        p.drawText(rect.adjusted(14, 0, 0, 0), Qt.AlignCenter, text)
