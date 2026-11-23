"""Small reusable widgets: color buttons, color lists, parameter forms."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QWidget,
)

from ..engine.effects import Param


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color: str = "#ffffff", parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._color = color
        self._refresh()
        self.clicked.connect(self._pick)

    def color(self) -> str:
        return self._color

    def setColor(self, color: str) -> None:
        self._color = color
        self._refresh()

    def _refresh(self) -> None:
        self.setStyleSheet(f"background:{self._color}; border:1px solid #888; border-radius:4px;")
        self.setToolTip(self._color)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Pick color")
        if c.isValid():
            self._color = c.name()
            self._refresh()
            self.colorChanged.emit(self._color)


class ColorListEditor(QWidget):
    changed = Signal(list)

    def __init__(self, colors: list[str], parent=None) -> None:
        super().__init__(parent)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(4)
        self.colors = list(colors)
        self._build()

    def _build(self) -> None:
        while self.row.count():
            w = self.row.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, c in enumerate(self.colors):
            b = ColorButton(c)
            b.setFixedSize(28, 24)
            b.colorChanged.connect(lambda col, i=i: self._set(i, col))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda _pos, i=i: self._remove(i))
            b.setToolTip(f"{c} — right-click to remove")
            self.row.addWidget(b)
        add = QToolButton()
        add.setText("+")
        add.setToolTip("Add color")
        add.clicked.connect(self._add)
        self.row.addWidget(add)
        self.row.addStretch(1)

    def _set(self, i: int, col: str) -> None:
        self.colors[i] = col
        self.changed.emit(list(self.colors))

    def _add(self) -> None:
        self.colors.append(self.colors[-1] if self.colors else "#ffffff")
        self._build()
        self.changed.emit(list(self.colors))

    def _remove(self, i: int) -> None:
        if len(self.colors) > 1:
            self.colors.pop(i)
            self._build()
            self.changed.emit(list(self.colors))


class FloatSlider(QWidget):
    """Slider + spin box for a float parameter."""

    valueChanged = Signal(float)

    def __init__(self, lo: float, hi: float, step: float, value: float, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lo, self.step = lo, step or 0.01
        steps = max(1, round((hi - lo) / self.step))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, steps)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(self.step)
        self.spin.setDecimals(max(0, len(f"{self.step:g}".split(".")[1]) if "." in f"{self.step:g}" else 0))
        self.spin.setMinimumWidth(96)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self._set(value)
        self.slider.valueChanged.connect(lambda v: self._from_slider(v))
        self.spin.valueChanged.connect(lambda v: self._from_spin(v))

    def _set(self, v: float) -> None:
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(round((v - self.lo) / self.step))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)

    def _from_slider(self, i: int) -> None:
        v = self.lo + i * self.step
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.valueChanged.emit(v)

    def _from_spin(self, v: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(round((v - self.lo) / self.step))
        self.slider.blockSignals(False)
        self.valueChanged.emit(v)


class ParamForm(QWidget):
    """Builds editors for an effect's parameter schema. Emits ``changed(key, value)``."""

    changed = Signal(str, object)

    def __init__(self, params: list[Param], values: dict, parent=None) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        for p in params:
            if p.kind == "keycolors":  # edited by painting on the keyboard
                hint = QLabel("Choose <b>Paint</b> under the keyboard, pick a brush color, then left-drag over keys "
                              "to paint them (right-drag erases). With Paint selected, the Quick select buttons "
                              "fill whole key groups.")
                hint.setWordWrap(True)
                form.addRow(hint)
                continue
            v = values.get(p.key, p.default)
            w = self._editor(p, v)
            form.addRow(p.label, w)

    def _editor(self, p: Param, v) -> QWidget:
        emit = lambda val, k=p.key: self.changed.emit(k, val)  # noqa: E731
        if p.kind == "color":
            w = ColorButton(v)
            w.colorChanged.connect(emit)
        elif p.kind == "colors":
            w = ColorListEditor(v)
            w.changed.connect(emit)
        elif p.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(v))
            w.toggled.connect(emit)
        elif p.kind == "choice":
            w = QComboBox()
            w.addItems(p.choices)
            w.setCurrentText(str(v))
            w.currentTextChanged.connect(emit)
        elif p.kind == "int":
            w = QSpinBox()
            w.setRange(int(p.min or 0), int(p.max or 100))
            w.setValue(int(v))
            w.valueChanged.connect(emit)
        else:
            w = FloatSlider(float(p.min or 0), float(p.max or 1), float(p.step or 0.01), float(v))
            w.valueChanged.connect(emit)
        return w
