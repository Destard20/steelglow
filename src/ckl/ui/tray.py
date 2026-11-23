"""System tray icon and menu."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .controller import Controller, autostart_enabled, set_autostart


def make_icon(paused: bool = False) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 64, 64)
    if paused:
        g.setColorAt(0, QColor("#777"))
        g.setColorAt(1, QColor("#444"))
    else:
        for i, c in enumerate(("#ff0055", "#ffaa00", "#00e676", "#00b0ff", "#d500f9")):
            g.setColorAt(i / 4, QColor(c))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(2, 14, 60, 36), 8, 8)
    p.setBrush(QColor(20, 20, 24))
    for row in range(3):
        for col in range(6 if row < 2 else 4):
            x = 7 + col * 8.6 + (4 if row == 2 else 0)
            w = 6 if row < 2 else (20 if col == 1 else 6)
            if row == 2 and col > 1:
                x += 14
            p.drawRoundedRect(QRectF(x, 18 + row * 10, w, 7), 1.5, 1.5)
    p.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, ctrl: Controller, open_editor) -> None:
        super().__init__(make_icon())
        self.ctrl = ctrl
        self.open_editor = open_editor
        self.menu = QMenu()
        self.status_action = self.menu.addAction("Starting…")
        self.status_action.setEnabled(False)
        self.preview_action = self.menu.addAction("Stop preview", lambda: ctrl.set_preview(None))
        self.preview_action.setVisible(False)
        self.menu.addSeparator()
        self.menu.addAction("Open editor…", open_editor)
        self.profiles_menu = self.menu.addMenu("Default profile")
        self.profiles_menu.aboutToShow.connect(self._fill_profiles)
        self.brightness_menu = self.menu.addMenu("Master brightness")
        self.brightness_menu.aboutToShow.connect(self._fill_brightness)
        self.auto_action = QAction("Auto-switch per app", self.menu, checkable=True)
        self.auto_action.setChecked(ctrl.store.settings.auto_switch)
        self.auto_action.toggled.connect(ctrl.set_auto_switch)
        self.menu.addAction(self.auto_action)
        self.pause_action = QAction("Pause (give lights back to GG)", self.menu, checkable=True)
        self.pause_action.toggled.connect(self._pause)
        self.menu.addAction(self.pause_action)
        self.autostart_action = QAction("Start with Windows", self.menu, checkable=True)
        self.autostart_action.setChecked(autostart_enabled())
        self.autostart_action.toggled.connect(self._autostart)
        self.menu.addAction(self.autostart_action)
        self.menu.addSeparator()
        self.menu.addAction("Quit", QApplication.instance().quit)
        self.setContextMenu(self.menu)
        self.activated.connect(self._activated)
        ctrl.activeProfileChanged.connect(self._update_tip)
        ctrl.statusChanged.connect(self._status)
        ctrl.previewChanged.connect(self._preview_changed)
        ctrl.pausedChanged.connect(self._paused_changed)
        self._connected = False
        self._update_tip()

    def _preview_changed(self, name) -> None:
        self.preview_action.setVisible(name is not None)
        if name is not None:
            self.preview_action.setText(f"Previewing “{name}” — stop preview")
        self._update_tip()

    def _paused_changed(self, paused: bool) -> None:
        self.pause_action.blockSignals(True)
        self.pause_action.setChecked(paused)
        self.pause_action.blockSignals(False)
        self.setIcon(make_icon(paused=paused))
        self._update_tip()

    def _fill_profiles(self) -> None:
        self.profiles_menu.clear()
        group = QActionGroup(self.profiles_menu)
        for name in self.ctrl.store.profiles:
            a = QAction(name, self.profiles_menu, checkable=True)
            a.setChecked(name == self.ctrl.store.settings.default_profile)
            a.triggered.connect(lambda _=False, n=name: self.ctrl.set_default_profile(n))
            group.addAction(a)
            self.profiles_menu.addAction(a)

    def _fill_brightness(self) -> None:
        self.brightness_menu.clear()
        group = QActionGroup(self.brightness_menu)
        current = round(self.ctrl.store.settings.master_brightness * 100)
        for pct in (100, 75, 50, 25, 10, 0):
            a = QAction("Off" if pct == 0 else f"{pct} %", self.brightness_menu, checkable=True)
            a.setChecked(pct == current)
            a.triggered.connect(lambda _=False, p=pct: self.ctrl.set_master_brightness(p / 100.0))
            group.addAction(a)
            self.brightness_menu.addAction(a)
        if current not in (100, 75, 50, 25, 10, 0):
            self.brightness_menu.addSeparator()
            self.brightness_menu.addAction(f"Current: {current} %").setEnabled(False)

    def _pause(self, on: bool) -> None:
        self.ctrl.set_paused(on)
        self.setIcon(make_icon(paused=on))
        self._update_tip()

    def _autostart(self, on: bool) -> None:
        try:
            set_autostart(on)
        except OSError as exc:
            self.showMessage("Custom Keyboard Lights", f"Could not change autostart: {exc}")

    def _status(self, connected: bool, msg: str) -> None:
        self._connected = connected
        self.status_action.setText(msg[:80])
        self._update_tip()

    def _update_tip(self, *_):
        state = "paused" if self.ctrl.engine.paused else (self.ctrl.active or "—")
        if self.ctrl.preview_profile and not self.ctrl.engine.paused:
            state += " (preview)"
        conn = "" if self._connected else " (waiting for GG)"
        self.setToolTip(f"Custom Keyboard Lights\nProfile: {state}{conn}")

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.open_editor()
