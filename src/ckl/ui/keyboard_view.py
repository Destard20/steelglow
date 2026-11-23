"""Clickable keyboard + mouse picture showing live colors.

Modes:
  * ``select`` - click / drag over keys to toggle them in the current layer's key set
  * ``paint``  - left-drag paints the brush color, right-drag erases (Per-key paint layers)
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..layout import Layout

PAD = 0.12  # gap between keys, in key units


class KeyboardView(QWidget):
    keysToggled = Signal(list, bool)  # key ids, new state (select mode)
    keysPainted = Signal(list, object)  # key ids, hex color or None (erase)

    def __init__(self, layout: Layout, parent=None) -> None:
        super().__init__(parent)
        self.layout_ = layout
        self.colors = np.zeros((layout.n, 3), np.uint8)
        self.selected: set[str] = set()
        self.select_enabled = False
        self.mode = "select"
        self.brush = "#ff0000"
        self.highlight_cell_key: str | None = None
        self._drag_state: bool | None = None
        self._drag_erase = False
        self._touched: set[str] = set()
        self.setMouseTracking(True)
        self.setMinimumSize(640, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ------------------------------------------------------------------ api
    def set_colors(self, colors: np.ndarray) -> None:
        self.colors = colors
        self.update()

    def set_selection(self, ids: set[str], enabled: bool) -> None:
        self.selected = set(ids)
        self.select_enabled = enabled
        self.update()

    # ------------------------------------------------------------------ geometry
    def _transform(self) -> tuple[float, float, float]:
        L = self.layout_
        w_units, h_units = L.width + 0.4, L.height + 0.4
        s = min(self.width() / w_units, self.height() / h_units)
        ox = (self.width() - w_units * s) / 2 + 0.2 * s
        oy = (self.height() - h_units * s) / 2 + 0.2 * s
        return s, ox, oy

    def _rect(self, led) -> QRectF:
        s, ox, oy = self._transform()
        return QRectF(ox + (led.x + PAD / 2) * s, oy + (led.y + PAD / 2) * s, (led.w - PAD) * s, (led.h - PAD) * s)

    def led_at(self, pos: QPointF):
        for led in self.layout_.leds:
            if self._rect(led).contains(pos):
                return led
        return None

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, ox, oy = self._transform()
        pal = self.palette()
        p.fillRect(self.rect(), pal.window())
        # device bodies
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(28, 28, 32))
        kb = [l for l in self.layout_.leds if l.device == "keyboard"]
        p.drawRoundedRect(QRectF(ox - 0.15 * s, oy - 0.15 * s, (max(l.x + l.w for l in kb) + 0.3) * s,
                                 (self.layout_.height + 0.3) * s), 0.25 * s, 0.25 * s)
        mouse = self.layout_.mouse
        if mouse:
            mx, my0, my1 = mouse[0].x, min(l.y for l in mouse), max(l.y + l.h for l in mouse)
            body = QPainterPath()
            body.addRoundedRect(QRectF((mx - 0.35) * s + ox, (my0 - 0.9) * s + oy, 1.7 * s, (my1 - my0 + 1.8) * s),
                                0.85 * s, 0.85 * s)
            p.drawPath(body)

        font = QFont(self.font())
        font.setPixelSize(max(8, int(s * 0.24)))
        p.setFont(font)
        for led in self.layout_.leds:
            r = self._rect(led)
            c = self.colors[led.index]
            fill = QColor(int(c[0]), int(c[1]), int(c[2]))
            p.setBrush(fill)
            sel = self.select_enabled and led.id in self.selected
            if self.highlight_cell_key == led.id:
                p.setPen(QPen(QColor("#ffff00"), max(2.0, s * 0.08)))
            elif sel:
                p.setPen(QPen(QColor("#00e5ff"), max(2.0, s * 0.07)))
            else:
                p.setPen(QPen(QColor(70, 70, 78), 1))
            p.drawRoundedRect(r, s * 0.12, s * 0.12)
            lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
            p.setPen(QColor(20, 20, 20) if lum > 140 else QColor(230, 230, 235))
            p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, led.label)
            if sel:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#00e5ff"))
                p.drawEllipse(QPointF(r.right() - s * 0.14, r.top() + s * 0.14), s * 0.06, s * 0.06)
        p.end()

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, ev) -> None:
        led = self.led_at(ev.position())
        if led is None:
            return
        self._touched = set()
        if self.mode == "paint":
            self._drag_erase = ev.button() == Qt.RightButton
            self._apply(led)
        elif self.select_enabled and ev.button() == Qt.LeftButton:
            self._drag_state = led.id not in self.selected
            self._apply(led)

    def mouseMoveEvent(self, ev) -> None:
        if not ev.buttons():
            led = self.led_at(ev.position())
            self.setToolTip(f"{led.label or led.id} ({led.id})" if led else "")
            return
        led = self.led_at(ev.position())
        if led is not None and led.id not in self._touched:
            if self.mode == "paint" or self._drag_state is not None:
                self._apply(led)

    def mouseReleaseEvent(self, _ev) -> None:
        self._drag_state = None
        self._touched = set()

    def _apply(self, led) -> None:
        self._touched.add(led.id)
        if self.mode == "paint":
            self.keysPainted.emit([led.id], None if self._drag_erase else self.brush)
        elif self._drag_state is not None:
            if self._drag_state:
                self.selected.add(led.id)
            else:
                self.selected.discard(led.id)
            self.keysToggled.emit([led.id], self._drag_state)
            self.update()
