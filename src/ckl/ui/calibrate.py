"""Calibration wizard: learns exactly which key each of the 132 GameSense grid cells lights."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..gamesense.client import BITMAP_LEN, GRID_COLS
from .keyboard_view import KeyboardView


class CalibrationDialog(QDialog):
    _scan = Signal(int)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.ctrl = controller
        self.layout_ = controller.layout
        self.engine = controller.engine
        self.setWindowTitle("Calibrate keyboard lighting")
        self.setModal(True)
        self.resize(900, 520)
        self.cell = 0
        self.result: dict[int, str | None] = {}
        self._closing_ok = False

        v = QVBoxLayout(self)
        intro = QLabel(
            "<b>One grid cell at a time lights up white on your keyboard.</b><br>"
            "Press the key that is lit. If nothing is lit, click <i>Nothing lit</i>. "
            "Any key works here, including Esc, Enter, Space and Tab: none of them close this window or "
            "trigger buttons.<br>The SteelSeries (SS) key sends no key code, so use its button below."
        )
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.status = QLabel()
        self.status.setStyleSheet("font-size:16px; padding:6px;")
        v.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, BITMAP_LEN)
        v.addWidget(self.progress)
        self.view = KeyboardView(self.layout_)
        v.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.buttons = []
        for text, slot in (
            ("◀ Back", self.back),
            ("Nothing lit", lambda: self.record(None)),
            ("Rest of this row: nothing", self.rest_of_row_nothing),
            ("SS key is lit", lambda: self.record("ss")),
            ("Skip (keep default)", self.skip),
        ):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.setAutoDefault(False)
            b.clicked.connect(slot)
            row.addWidget(b)
            self.buttons.append(b)
        row.addStretch(1)
        self.save_btn = QPushButton("Finish && save")
        self.cancel_btn = QPushButton("Cancel")
        for b in (self.save_btn, self.cancel_btn):
            b.setFocusPolicy(Qt.NoFocus)
            b.setAutoDefault(False)
            row.addWidget(b)
        self.save_btn.clicked.connect(self.finish)
        self.cancel_btn.clicked.connect(self.cancel)
        v.addLayout(row)

        self._scan.connect(self.on_scan, Qt.QueuedConnection)
        self._sub = lambda scan: self._scan.emit(scan)
        self.engine.add_key_subscriber(self._sub)
        self.show_cell()

    # ------------------------------------------------------------------ flow
    def show_cell(self) -> None:
        if self.cell >= BITMAP_LEN:
            self.status.setText("All cells done — click <b>Finish & save</b>.")
            self.engine.set_raw_bitmap([[0, 0, 0]] * BITMAP_LEN)
            self.view.highlight_cell_key = None
            self.view.update()
            return
        r, c = divmod(self.cell, GRID_COLS)
        bm = [[0, 0, 0]] * BITMAP_LEN
        bm[self.cell] = [255, 255, 255]
        self.engine.set_raw_bitmap(bm)
        default_key = self.layout_.leds[self.layout_.default_cell_to_led[self.cell]].id
        self.status.setText(f"Cell {self.cell + 1}/{BITMAP_LEN} (row {r + 1}, column {c + 1}) — "
                            f"press the lit key. (Expected near: <b>{default_key}</b>)")
        self.view.highlight_cell_key = default_key
        self.progress.setValue(self.cell)
        # show recorded keys in the picture
        colors = np.zeros((self.layout_.n, 3), np.uint8)
        for kid in self.result.values():
            if kid in self.layout_.by_id:
                colors[self.layout_.by_id[kid].index] = (0, 140, 60)
        self.view.set_colors(colors)

    def on_scan(self, scan: int) -> None:
        led = self.layout_.by_scan.get(scan)
        if led is not None and led.device == "keyboard":
            self.record(led.id)

    def record(self, key_id: str | None) -> None:
        if self.cell >= BITMAP_LEN:
            return
        self.result[self.cell] = key_id
        self.cell += 1
        self.show_cell()

    def skip(self) -> None:
        if self.cell < BITMAP_LEN:
            self.result.pop(self.cell, None)
            self.cell += 1
            self.show_cell()

    def back(self) -> None:
        if self.cell > 0:
            self.cell -= 1
            self.result.pop(self.cell, None)
            self.show_cell()

    def rest_of_row_nothing(self) -> None:
        if self.cell >= BITMAP_LEN:
            return
        row_end = (self.cell // GRID_COLS + 1) * GRID_COLS
        for c in range(self.cell, row_end):
            self.result[c] = None
        self.cell = row_end
        self.show_cell()

    def finish(self) -> None:
        if not self.result:
            QMessageBox.information(self, "Calibration", "Nothing recorded yet.")
            return
        self.layout_.save_calibration(self.result)
        self._closing_ok = True
        self._cleanup()
        self.accept()

    def cancel(self) -> None:
        self._closing_ok = True
        self._cleanup()
        super().reject()

    # Esc must not close the dialog: the user may be calibrating the Esc key.
    def reject(self) -> None:
        if self._closing_ok:
            super().reject()

    def keyPressEvent(self, ev) -> None:
        ev.accept()  # swallow everything; keys are read from the global hook

    def closeEvent(self, ev) -> None:  # window close button
        self._closing_ok = True
        self._cleanup()
        super().closeEvent(ev)

    def _cleanup(self) -> None:
        self.engine.remove_key_subscriber(self._sub)
        self.engine.set_raw_bitmap(None)
