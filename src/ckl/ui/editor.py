"""Main editor window: profiles, layer stack, effect settings, per-app rules, settings."""
from __future__ import annotations

import copy
import os

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..engine.effects import EFFECTS
from ..engine.layer import BLEND_MODES, LayerConfig
from ..layout.groups import QUICK_SELECT, STATIC_GROUPS
from ..profiles import AppRule, Profile
from .calibrate import CalibrationDialog
from .controller import Controller, autostart_enabled, set_autostart
from .keyboard_view import KeyboardView
from .widgets import ColorButton, FloatSlider, ParamForm

QUICK_SETS = {label: STATIC_GROUPS[group] for label, group in QUICK_SELECT.items()}
MOUSE_DEVICE_TYPES = ["rgb-3-zone", "mouse", "rgb-2-zone", "rgb-4-zone", "rgb-5-zone"]


class EditorWindow(QMainWindow):
    def __init__(self, ctrl: Controller) -> None:
        super().__init__()
        self.ctrl = ctrl
        self.store = ctrl.store
        self.layout_ = ctrl.layout
        self.setWindowTitle("Custom Keyboard Lights")
        self.resize(1400, 820)
        self.profile: Profile | None = None
        self.layer_idx: int | None = None  # index into profile.layers
        self._save_timer = QTimer(self, singleShot=True, interval=120)
        self._save_timer.timeout.connect(self._commit)

        central = QWidget()
        root = QVBoxLayout(central)
        root.addLayout(self._build_top_bar())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_lighting_tab(), "Lighting")
        self.tabs.addTab(self._build_rules_tab(), "Per-app profiles")
        self.tabs.addTab(self._build_settings_tab(), "Settings")
        root.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.preview_timer = QTimer(self, interval=33)
        self.preview_timer.timeout.connect(lambda: self.kb.set_colors(self.ctrl.engine.preview()))
        self.preview_timer.start()
        ctrl.statusChanged.connect(self._on_status)
        ctrl.activeProfileChanged.connect(self._on_active)
        ctrl.profilesChanged.connect(self._on_profiles_reloaded)
        ctrl.pausedChanged.connect(self._on_paused)
        self._on_status(ctrl.client.connected, "Connected to SteelSeries GG" if ctrl.client.connected else "Connecting…")
        self._on_active(ctrl.active or "—")
        self.reload_profiles(self.ctrl.active or self.store.settings.default_profile)

    # ================================================================== top bar
    def _build_top_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentTextChanged.connect(self.select_profile)
        bar.addWidget(self.profile_combo)
        for text, slot in (("New", self.new_profile), ("Duplicate", self.duplicate_profile),
                           ("Rename", self.rename_profile), ("Delete", self.delete_profile)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        self.default_btn = QPushButton("Set as default")
        self.default_btn.setToolTip("Used when no per-app rule matches the focused app")
        self.default_btn.clicked.connect(self.make_default)
        bar.addWidget(self.default_btn)
        bar.addStretch(1)
        bar.addWidget(QLabel("Master brightness:"))
        self.master = FloatSlider(0, 100, 5, round(self.store.settings.master_brightness * 100))
        self.master.spin.setSuffix(" %")
        self.master.setFixedWidth(240)
        self.master.setToolTip("Dims every profile at once (also in the tray menu)")
        self.master.valueChanged.connect(lambda v: self.ctrl.set_master_brightness(v / 100.0))
        self.ctrl.masterBrightnessChanged.connect(lambda lv: self.master._set(round(lv * 100)))
        bar.addWidget(self.master)
        bar.addSpacing(12)
        self.active_label = QLabel()
        bar.addWidget(self.active_label)
        self.status_label = QLabel()
        bar.addWidget(self.status_label)
        self.pause_box = QCheckBox("Pause (give lights back to GG)")
        self.pause_box.toggled.connect(self.ctrl.set_paused)
        bar.addWidget(self.pause_box)
        return bar

    def _on_status(self, connected: bool, msg: str) -> None:
        color = "#2e7d32" if connected else "#c62828"
        self.status_label.setText(f"<span style='color:{color}'>●</span> {msg}")

    def _on_active(self, name: str) -> None:
        self.active_label.setText(f"Live: <b>{name}</b>   ")

    # ================================================================== lighting tab
    def _build_lighting_tab(self) -> QWidget:
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        self.kb = KeyboardView(self.layout_)
        self.kb.keysToggled.connect(self.on_keys_toggled)
        self.kb.keysPainted.connect(self.on_keys_painted)
        lv.addWidget(self.kb, 1)

        tools = QHBoxLayout()
        self.mode_select = QRadioButton("Select keys")
        self.mode_paint = QRadioButton("Paint")
        self.mode_select.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.mode_select)
        grp.addButton(self.mode_paint)
        self.mode_select.toggled.connect(self._mode_changed)
        tools.addWidget(self.mode_select)
        tools.addWidget(self.mode_paint)
        self.brush = ColorButton("#ff0000")
        self.brush.colorChanged.connect(lambda c: setattr(self.kb, "brush", c))
        tools.addWidget(QLabel("Brush:"))
        tools.addWidget(self.brush)
        tools.addSpacing(16)
        tools.addWidget(QLabel("Quick select:"))
        for name, ids in QUICK_SETS.items():
            b = QToolButton()
            b.setText(name)
            b.clicked.connect(lambda _=False, ids=ids: self.quick_select(ids))
            tools.addWidget(b)
        for name, slot in (("All", self.select_all), ("None", self.select_none), ("Invert", self.select_invert)):
            b = QToolButton()
            b.setText(name)
            b.clicked.connect(slot)
            tools.addWidget(b)
        tools.addStretch(1)
        lv.addLayout(tools)
        self.hint = QLabel()
        self.hint.setStyleSheet("color:gray")
        lv.addWidget(self.hint)
        split.addWidget(left)

        right = QWidget()
        right.setMinimumWidth(380)
        rv = QVBoxLayout(right)

        prof_box = QGroupBox("Profile options")
        pf = QFormLayout(prof_box)
        self.kb_brightness = FloatSlider(0, 100, 5, 100)
        self.kb_brightness.spin.setSuffix(" %")
        self.kb_brightness.valueChanged.connect(lambda v: self._set_level("keyboard_brightness", v))
        pf.addRow("Keyboard brightness", self.kb_brightness)
        self.mouse_brightness = FloatSlider(0, 100, 5, 100)
        self.mouse_brightness.spin.setSuffix(" %")
        self.mouse_brightness.setToolTip("0 % turns the mouse LEDs off and stops sending it lighting updates "
                                         "(saves battery)")
        self.mouse_brightness.valueChanged.connect(lambda v: self._set_level("mouse_brightness", v))
        pf.addRow("Mouse brightness", self.mouse_brightness)
        self.reactive_box = QCheckBox("Listen to key presses (reactive effects)")
        self.reactive_box.setToolTip("Turn off for games whose anti-cheat dislikes keyboard hooks")
        self.reactive_box.toggled.connect(self._set_reactive)
        pf.addRow(self.reactive_box)
        rv.addWidget(prof_box)

        layers_box = QGroupBox("Layers (top of list = drawn on top)")
        lb = QVBoxLayout(layers_box)
        self.layer_list = QListWidget()
        self.layer_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.layer_list.model().rowsMoved.connect(self._layers_reordered)
        self.layer_list.currentRowChanged.connect(self._layer_selected)
        self.layer_list.itemChanged.connect(self._layer_item_changed)
        lb.addWidget(self.layer_list)
        lbtn = QHBoxLayout()
        add = QToolButton()
        add.setText("Add layer ▾")
        add.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(add)
        cats: dict[str, QMenu] = {}
        for eid, cls in EFFECTS.items():
            sub = cats.get(cls.category) or menu.addMenu(cls.category)
            cats[cls.category] = sub
            act = QAction(cls.name, sub)
            act.triggered.connect(lambda _=False, eid=eid: self.add_layer(eid))
            sub.addAction(act)
        add.setMenu(menu)
        lbtn.addWidget(add)
        for text, slot in (("Duplicate", self.duplicate_layer), ("Remove", self.remove_layer),
                           ("▲", lambda: self.move_layer(+1)), ("▼", lambda: self.move_layer(-1))):
            b = QToolButton()
            b.setText(text)
            b.clicked.connect(slot)
            lbtn.addWidget(b)
        lbtn.addStretch(1)
        lb.addLayout(lbtn)
        rv.addWidget(layers_box, 1)

        self.layer_box = QGroupBox("Layer")
        lf = QFormLayout(self.layer_box)
        self.layer_name = QLineEdit()
        self.layer_name.editingFinished.connect(self._layer_name_changed)
        lf.addRow("Name", self.layer_name)
        self.layer_blend = QComboBox()
        self.layer_blend.addItems(BLEND_MODES)
        self.layer_blend.currentTextChanged.connect(lambda v: self._layer_set("blend", v))
        lf.addRow("Blend", self.layer_blend)
        self.layer_opacity = FloatSlider(0.0, 1.0, 0.05, 1.0)
        self.layer_opacity.valueChanged.connect(lambda v: self._layer_set("opacity", v))
        lf.addRow("Opacity", self.layer_opacity)
        self.layer_scope = QComboBox()
        self.layer_scope.addItems(["All keys + mouse", "Selected keys only"])
        self.layer_scope.currentIndexChanged.connect(self._scope_changed)
        lf.addRow("Applies to", self.layer_scope)
        rv.addWidget(self.layer_box)

        self.params_box = QGroupBox("Effect settings")
        pv = QVBoxLayout(self.params_box)
        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        pv.addWidget(self.params_scroll)
        rv.addWidget(self.params_box, 1)

        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        return split

    # ================================================================== rules tab
    def _build_rules_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.auto_box = QCheckBox("Switch profile automatically based on the focused application")
        self.auto_box.setChecked(self.store.settings.auto_switch)
        self.auto_box.toggled.connect(self.ctrl.set_auto_switch)
        v.addWidget(self.auto_box)
        self.rules_table = QTableWidget(0, 2)
        self.rules_table.setHorizontalHeaderLabels(["Application (.exe)", "Profile"])
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rules_table.itemChanged.connect(self._rules_edited)
        v.addWidget(self.rules_table, 1)
        row = QHBoxLayout()
        self.running_combo = QComboBox()
        self.running_combo.setEditable(True)
        self.running_combo.setMinimumWidth(260)
        self.running_combo.lineEdit().setPlaceholderText("game.exe")
        refresh = QPushButton("↻ running apps")
        refresh.clicked.connect(self._refresh_running)
        add = QPushButton("Add rule")
        add.clicked.connect(self._add_rule)
        rem = QPushButton("Remove selected")
        rem.clicked.connect(self._remove_rule)
        for x in (self.running_combo, refresh, add, rem):
            row.addWidget(x)
        row.addStretch(1)
        v.addLayout(row)
        self.fg_label = QLabel()
        self.fg_label.setStyleSheet("color:gray")
        v.addWidget(self.fg_label)
        t = QTimer(self, interval=1000)
        t.timeout.connect(lambda: self.fg_label.setText(
            f"Last focused app: {self.ctrl.foreground or '—'}   •   live profile: {self.ctrl.active}"))
        t.start()
        self._refresh_running()
        self._load_rules()
        return w

    def _refresh_running(self) -> None:
        names = set()
        for p in psutil.process_iter(["name"]):
            n = p.info.get("name") or ""
            if n.lower().endswith(".exe"):
                names.add(n)
        cur = self.running_combo.currentText()
        self.running_combo.clear()
        self.running_combo.addItems(sorted(names, key=str.lower))
        self.running_combo.setEditText(cur)

    def _load_rules(self) -> None:
        self.rules_table.blockSignals(True)
        self.rules_table.setRowCount(0)
        for rule in self.store.settings.rules:
            self._append_rule_row(rule)
        self.rules_table.blockSignals(False)

    def _append_rule_row(self, rule: AppRule) -> None:
        r = self.rules_table.rowCount()
        self.rules_table.insertRow(r)
        self.rules_table.setItem(r, 0, QTableWidgetItem(rule.exe))
        combo = QComboBox()
        combo.addItems(list(self.store.profiles))
        combo.setCurrentText(rule.profile)
        combo.currentTextChanged.connect(lambda _t: self._rules_edited())
        self.rules_table.setCellWidget(r, 1, combo)

    def _rules_edited(self, *_):
        rules = []
        for r in range(self.rules_table.rowCount()):
            item = self.rules_table.item(r, 0)
            combo = self.rules_table.cellWidget(r, 1)
            if item and item.text().strip() and combo:
                rules.append(AppRule(item.text().strip(), combo.currentText()))
        self.store.settings.rules = rules
        self.store.save_settings()
        self.ctrl.tick()

    def _add_rule(self) -> None:
        exe = self.running_combo.currentText().strip()
        if not exe:
            return
        if not exe.lower().endswith(".exe"):
            exe += ".exe"
        self.rules_table.blockSignals(True)
        self._append_rule_row(AppRule(exe, self.profile.name if self.profile else self.store.settings.default_profile))
        self.rules_table.blockSignals(False)
        self._rules_edited()

    def _remove_rule(self) -> None:
        rows = sorted({i.row() for i in self.rules_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.rules_table.removeRow(r)
        self._rules_edited()

    # ================================================================== settings tab
    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        fps = QSpinBox()
        fps.setRange(5, 60)
        fps.setValue(self.store.settings.fps)
        fps.setToolTip("GG accepts roughly 25 frames/s; higher values just drop frames")
        fps.valueChanged.connect(self.ctrl.set_fps)
        f.addRow("Frames per second", fps)
        mouse = QComboBox()
        mouse.addItems(MOUSE_DEVICE_TYPES)
        mouse.setCurrentText(self.store.settings.mouse_device_type)
        mouse.currentTextChanged.connect(self.ctrl.set_mouse_device_type)
        f.addRow("Mouse GameSense device type", mouse)
        mfps = QSpinBox()
        mfps.setRange(1, 30)
        mfps.setValue(round(self.store.settings.mouse_fps))
        mfps.setToolTip("Maximum lighting updates per second sent to the wireless mouse. Lower values save "
                        "battery on animated effects. Static colors are sent only when they change.")
        mfps.valueChanged.connect(self.ctrl.set_mouse_fps)
        f.addRow("Mouse update rate (per second)", mfps)
        auto = QCheckBox("Start with Windows (runs in the tray)")
        auto.setChecked(autostart_enabled())
        auto.toggled.connect(self._toggle_autostart)
        f.addRow(auto)
        cal_row = QHBoxLayout()
        self.cal_label = QLabel()
        cal = QPushButton("Calibrate keyboard…")
        cal.clicked.connect(self.calibrate)
        reset = QPushButton("Reset calibration")
        reset.clicked.connect(self.reset_calibration)
        cal_row.addWidget(self.cal_label)
        cal_row.addWidget(cal)
        cal_row.addWidget(reset)
        cal_row.addStretch(1)
        f.addRow("Key mapping", cal_row)
        self._update_cal_label()
        folder = QPushButton("Open profiles folder")
        folder.clicked.connect(lambda: os.startfile(str(self.store.dir)))
        f.addRow(folder)
        info = QLabel(
            "<p>Lighting is sent to <b>SteelSeries GG</b> through its official local GameSense API. "
            "Keep GG running in the background: it still handles your key bindings, macros, actuation "
            "and onboard profiles.</p>"
            "<p>If nothing lights up, open GG → <i>Engine</i> → <i>Apps</i> and make sure "
            "<b>Custom Keyboard Lights</b> is enabled.</p>"
            "<p>The key listener used for reactive effects only <i>observes</i> key presses to "
            "light them up. It never blocks or changes input. Turn it off per profile if a game's anti-cheat "
            "objects.</p>"
        )
        info.setWordWrap(True)
        f.addRow(info)
        return w

    def _toggle_autostart(self, on: bool) -> None:
        try:
            set_autostart(on)
        except OSError as exc:
            QMessageBox.warning(self, "Start with Windows", str(exc))

    def _update_cal_label(self) -> None:
        self.cal_label.setText("calibrated ✔" if self.layout_.calibrated else "default (approximate) mapping")

    def calibrate(self) -> None:
        if not self.ctrl.client.connected:
            QMessageBox.warning(self, "Calibration", "SteelSeries GG is not connected yet.")
            return
        CalibrationDialog(self.ctrl, self).exec()
        self._update_cal_label()

    def reset_calibration(self) -> None:
        self.layout_.reset_calibration()
        self._update_cal_label()

    # ================================================================== profiles
    def _on_profiles_reloaded(self) -> None:
        """Profiles were re-read from disk (CLI import): drop stale objects, keep the selection."""
        self._save_timer.stop()
        self.reload_profiles(self.profile.name if self.profile else None)

    def _on_paused(self, paused: bool) -> None:
        self.pause_box.blockSignals(True)
        self.pause_box.setChecked(paused)
        self.pause_box.blockSignals(False)

    def reload_profiles(self, select: str | None = None) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        names = list(self.store.profiles)
        for n in names:
            label = n + ("  (default)" if n == self.store.settings.default_profile else "")
            self.profile_combo.addItem(label, n)
        idx = names.index(select) if select in names else 0
        self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)
        self.select_profile()
        self._load_rules()

    def select_profile(self, *_):
        name = self.profile_combo.currentData()
        if not name:
            return
        self.profile = self.store.profiles[name]
        self.ctrl.editor_profile = name
        self.ctrl.tick()
        self.kb_brightness._set(round(self.profile.keyboard_brightness * 100))
        self.mouse_brightness._set(round(self.profile.mouse_brightness * 100))
        self.reactive_box.blockSignals(True)
        self.reactive_box.setChecked(self.profile.reactive)
        self.reactive_box.blockSignals(False)
        self._fill_layers(select=len(self.profile.layers) - 1)

    def _ask_name(self, title: str, default: str) -> str | None:
        name, ok = QInputDialog.getText(self, title, "Profile name:", text=default)
        name = name.strip()
        if not ok or not name:
            return None
        if name in self.store.profiles and name != default:
            QMessageBox.warning(self, title, f"A profile called '{name}' already exists.")
            return None
        return name

    def new_profile(self) -> None:
        name = self._ask_name("New profile", "New profile")
        if name:
            self.store.save_profile(Profile(name, [LayerConfig("solid", {"color": "#202030"}, name="Base")]))
            self.reload_profiles(name)

    def duplicate_profile(self) -> None:
        if not self.profile:
            return
        name = self._ask_name("Duplicate profile", self.profile.name + " copy")
        if name:
            p = copy.deepcopy(self.profile)
            p.name = name
            self.store.save_profile(p)
            self.reload_profiles(name)

    def rename_profile(self) -> None:
        if not self.profile:
            return
        old = self.profile.name
        name = self._ask_name("Rename profile", old)
        if name and name != old:
            self.profile.name = name
            self.store.save_profile(self.profile, old_name=old)
            if self.ctrl.active == old:
                self.ctrl.active = None
            self.reload_profiles(name)

    def delete_profile(self) -> None:
        if not self.profile or len(self.store.profiles) <= 1:
            return
        if QMessageBox.question(self, "Delete profile", f"Delete '{self.profile.name}'? "
                                "Per-app rules using it are removed too.") != QMessageBox.Yes:
            return
        self.store.delete_profile(self.profile.name)
        self.reload_profiles()

    def make_default(self) -> None:
        if self.profile:
            self.ctrl.set_default_profile(self.profile.name)
            self.reload_profiles(self.profile.name)

    def _set_level(self, attr: str, percent: float) -> None:
        if self.profile:
            setattr(self.profile, attr, percent / 100.0)
            if self.profile.name == self.ctrl.active:  # instant feedback while dragging
                self.ctrl.engine.set_levels(keyboard=self.profile.keyboard_brightness,
                                            mouse=self.profile.mouse_brightness)
            self._changed()

    def _set_reactive(self, on: bool) -> None:
        if self.profile:
            self.profile.reactive = on
            self._changed()

    # ================================================================== layers
    def _row_to_idx(self, row: int) -> int:
        return len(self.profile.layers) - 1 - row  # list shows top layer first

    def _fill_layers(self, select: int | None = None) -> None:
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        for cfg in reversed(self.profile.layers):
            it = QListWidgetItem(cfg.display_name())
            it.setData(Qt.UserRole, id(cfg))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Checked if cfg.enabled else Qt.Unchecked)
            cls = EFFECTS.get(cfg.effect)
            scope = "all" if cfg.keys is None else f"{len(cfg.keys)} keys"
            it.setToolTip(f"{cls.name if cls else cfg.effect} • {cfg.blend} • {int(cfg.opacity * 100)}% • {scope}")
            self.layer_list.addItem(it)
        self.layer_list.blockSignals(False)
        if self.profile.layers:
            idx = select if select is not None and 0 <= select < len(self.profile.layers) else len(self.profile.layers) - 1
            self.layer_list.setCurrentRow(self._row_to_idx(idx))
        else:
            self._layer_selected(-1)

    def _layer_selected(self, row: int) -> None:
        if not self.profile or row < 0 or row >= len(self.profile.layers):
            self.layer_idx = None
            self.layer_box.setEnabled(False)
            self.params_scroll.setWidget(QWidget())
            self.kb.set_selection(set(), False)
            self._update_hint()
            return
        self.layer_idx = self._row_to_idx(row)
        cfg = self.profile.layers[self.layer_idx]
        self.layer_box.setEnabled(True)
        for w in (self.layer_name, self.layer_blend, self.layer_scope):
            w.blockSignals(True)
        self.layer_name.setText(cfg.name)
        self.layer_name.setPlaceholderText(EFFECTS[cfg.effect].name if cfg.effect in EFFECTS else cfg.effect)
        self.layer_blend.setCurrentText(cfg.blend)
        self.layer_opacity._set(cfg.opacity)
        self.layer_scope.setCurrentIndex(0 if cfg.keys is None else 1)
        for w in (self.layer_name, self.layer_blend, self.layer_scope):
            w.blockSignals(False)
        cls = EFFECTS.get(cfg.effect)
        if cls:
            form = ParamForm(cls.params, cfg.params)
            form.changed.connect(self._param_changed)
            self.params_box.setTitle(f"Effect settings — {cls.name}")
            self.params_scroll.setWidget(form)
        self.kb.set_selection(set(cfg.keys or []), cfg.keys is not None)
        self._update_hint()

    @property
    def layer(self) -> LayerConfig | None:
        if self.profile and self.layer_idx is not None and self.layer_idx < len(self.profile.layers):
            return self.profile.layers[self.layer_idx]
        return None

    def _update_hint(self) -> None:
        cfg = self.layer
        if self.mode_paint.isChecked():
            if cfg and cfg.effect == "paint":
                self.hint.setText("Paint: left-drag paints with the brush color, right-drag erases.")
            else:
                self.hint.setText("Painting needs a 'Per-key paint' layer: select one, or add it with Add layer → Ambient.")
        elif cfg and cfg.keys is not None:
            self.hint.setText(f"Click or drag over keys to add/remove them from this layer ({len(cfg.keys)} selected).")
        else:
            self.hint.setText("This layer applies to every key and the mouse. Set 'Applies to' → "
                              "'Selected keys only' to limit it.")

    def add_layer(self, eid: str) -> None:
        cfg = LayerConfig(eid, EFFECTS[eid].defaults())
        if self.kb.selected and self.layer and self.layer.keys is not None:
            cfg.keys = sorted(self.kb.selected)
        if eid in ("ripple", "key_fade", "starlight"):
            cfg.blend = "screen"
        pos = (self.layer_idx + 1) if self.layer_idx is not None else len(self.profile.layers)
        self.profile.layers.insert(pos, cfg)
        self._fill_layers(select=pos)
        if eid == "paint":
            self.mode_paint.setChecked(True)
        self._changed()

    def duplicate_layer(self) -> None:
        if self.layer:
            self.profile.layers.insert(self.layer_idx + 1, self.layer.clone())
            self._fill_layers(select=self.layer_idx + 1)
            self._changed()

    def remove_layer(self) -> None:
        if self.layer:
            idx = self.layer_idx
            self.profile.layers.pop(idx)
            self._fill_layers(select=min(idx, len(self.profile.layers) - 1))
            self._changed()

    def move_layer(self, delta: int) -> None:
        i = self.layer_idx
        if i is None:
            return
        j = i + delta
        if 0 <= j < len(self.profile.layers):
            L = self.profile.layers
            L[i], L[j] = L[j], L[i]
            self._fill_layers(select=j)
            self._changed()

    def _layers_reordered(self, *_):
        # rebuild order from list items (top first) using the layer object each item carries
        n = self.layer_list.count()
        by_id = {id(cfg): cfg for cfg in self.profile.layers}
        new_rows = [by_id.get(self.layer_list.item(r).data(Qt.UserRole)) for r in range(n)]
        if len(new_rows) == n and all(c is not None for c in new_rows):
            self.profile.layers = list(reversed(new_rows))
            self._changed()
        self.layer_idx = self._row_to_idx(self.layer_list.currentRow())

    def _layer_item_changed(self, item: QListWidgetItem) -> None:
        row = self.layer_list.row(item)
        idx = self._row_to_idx(row)
        if 0 <= idx < len(self.profile.layers):
            self.profile.layers[idx].enabled = item.checkState() == Qt.Checked
            self._changed()

    def _layer_name_changed(self) -> None:
        if self.layer:
            self.layer.name = self.layer_name.text().strip()
            it = self.layer_list.currentItem()
            if it:
                self.layer_list.blockSignals(True)
                it.setText(self.layer.display_name())
                self.layer_list.blockSignals(False)
            self._changed()

    def _layer_set(self, attr: str, value) -> None:
        if self.layer:
            setattr(self.layer, attr, value)
            self._changed()

    def _scope_changed(self, idx: int) -> None:
        cfg = self.layer
        if not cfg:
            return
        if idx == 0:
            cfg.keys = None
        elif cfg.keys is None:
            cfg.keys = sorted(self.kb.selected) if self.kb.selected else []
        self.kb.set_selection(set(cfg.keys or []), cfg.keys is not None)
        self._update_hint()
        self._changed()

    def _param_changed(self, key: str, value) -> None:
        if self.layer:
            self.layer.params[key] = value
            self._changed()

    # ================================================================== keyboard interactions
    def _mode_changed(self, *_):
        self.kb.mode = "paint" if self.mode_paint.isChecked() else "select"
        self._update_hint()

    def on_keys_toggled(self, ids: list, state: bool) -> None:
        cfg = self.layer
        if not cfg or cfg.keys is None:
            return
        keys = set(cfg.keys)
        keys.update(ids) if state else keys.difference_update(ids)
        cfg.keys = sorted(keys)
        self._update_hint()
        self._changed()

    def on_keys_painted(self, ids: list, color) -> None:
        cfg = self.layer
        if not cfg or cfg.effect != "paint":
            self._update_hint()
            return
        painted = dict(cfg.params.get("keys") or {})
        for kid in ids:
            if color is None:
                painted.pop(kid, None)
            else:
                painted[kid] = color
        cfg.params["keys"] = painted
        self._changed()

    def _set_layer_keys(self, ids: set[str]) -> None:
        cfg = self.layer
        if not cfg:
            return
        if cfg.keys is None:
            self.layer_scope.setCurrentIndex(1)  # switches to selected-keys mode
        cfg.keys = sorted(i for i in ids if i in self.layout_.by_id)
        self.kb.set_selection(set(cfg.keys), True)
        self._update_hint()
        self._changed()

    def quick_select(self, ids: list[str]) -> None:
        cfg = self.layer
        if not cfg:
            return
        if self.mode_paint.isChecked() and cfg.effect == "paint":
            self.on_keys_painted(ids, self.brush.color())
            return
        current = set(cfg.keys or [])
        self._set_layer_keys(current | set(ids))

    def select_all(self) -> None:
        self._set_layer_keys({l.id for l in self.layout_.leds})

    def select_none(self) -> None:
        self._set_layer_keys(set())

    def select_invert(self) -> None:
        cur = set(self.layer.keys or []) if self.layer else set()
        self._set_layer_keys({l.id for l in self.layout_.leds} - cur)

    # ================================================================== persistence
    def _changed(self) -> None:
        self._save_timer.start()

    def _commit(self) -> None:
        if self.profile:
            self.ctrl.profile_edited(self.profile.name)
            row = self.layer_list.currentRow()
            if 0 <= row < self.layer_list.count() and self.layer:
                cfg = self.layer
                scope = "all" if cfg.keys is None else f"{len(cfg.keys)} keys"
                self.layer_list.item(row).setToolTip(
                    f"{EFFECTS[cfg.effect].name} • {cfg.blend} • {int(cfg.opacity * 100)}% • {scope}")

    def closeEvent(self, ev) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._commit()
        self.ctrl.editor_profile = None
        self.ctrl.tick()
        ev.accept()
