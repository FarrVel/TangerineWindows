"""Logo jeruk "Tangerine" digambar secara prosedural (tanpa file aset)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)

ORANGE = QColor(255, 140, 26)
ORANGE_LIGHT = QColor(255, 186, 73)
ORANGE_DARK = QColor(226, 92, 0)
LEAF = QColor(76, 175, 80)


def draw_logo(p: QPainter, rect: QRectF):
    """Gambar buah jeruk dengan daun di dalam rect."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    s = min(rect.width(), rect.height())
    cx, cy = rect.center().x(), rect.center().y() + s * 0.06
    r = s * 0.40

    # bayangan halus
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 50))
    p.drawEllipse(QPointF(cx, cy + s * 0.03), r, r)

    # buah
    g = QRadialGradient(QPointF(cx - r * 0.35, cy - r * 0.4), r * 1.6)
    g.setColorAt(0.0, ORANGE_LIGHT)
    g.setColorAt(0.55, ORANGE)
    g.setColorAt(1.0, ORANGE_DARK)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r, r)

    # kilau
    p.setBrush(QColor(255, 255, 255, 90))
    p.drawEllipse(QPointF(cx - r * 0.38, cy - r * 0.38), r * 0.22, r * 0.14)

    # tangkai
    p.setPen(QPen(QColor(110, 70, 30), max(1.0, s * 0.045), Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx, cy - r * 0.92), QPointF(cx + s * 0.02, cy - r * 1.12))

    # daun
    leaf = QPainterPath()
    base = QPointF(cx + s * 0.02, cy - r * 1.05)
    tip = QPointF(cx + s * 0.34, cy - r * 1.30)
    leaf.moveTo(base)
    leaf.quadTo(QPointF(cx + s * 0.16, cy - r * 1.65), tip)
    leaf.quadTo(QPointF(cx + s * 0.20, cy - r * 0.85), base)
    p.setPen(Qt.NoPen)
    p.setBrush(LEAF)
    p.drawPath(leaf)
    p.restore()


def logo_pixmap(size: int = 64) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_logo(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def logo_icon(disabled: bool = False) -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        pm = logo_pixmap(s)
        if disabled:
            img = pm.toImage().convertToFormat(pm.toImage().Format.Format_ARGB32)
            for y in range(img.height()):
                for x in range(img.width()):
                    c = img.pixelColor(x, y)
                    gray = int(c.red() * 0.3 + c.green() * 0.59 + c.blue() * 0.11)
                    img.setPixelColor(x, y, QColor(gray, gray, gray, int(c.alpha() * 0.7)))
            pm = QPixmap.fromImage(img)
        icon.addPixmap(pm)
    return icon
