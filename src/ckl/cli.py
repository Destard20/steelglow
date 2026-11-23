"""Command-line tools for authoring profiles (used by the /light-profile skill) and app control.

    python -m ckl profile schema                 effects, params, key ids, groups, file format
    python -m ckl profile validate FILE...       check profile JSON
    python -m ckl profile render FILE --out PNG  offscreen picture of the profile over time
    python -m ckl profile import FILE... [--replace]
    python -m ckl profile preview NAME | --file FILE   show it live on the hardware now
    python -m ckl profile end-preview
    python -m ckl profile set-default NAME
    python -m ckl profile bind EXE NAME | unbind EXE
    python -m ckl profile list | status | delete NAME | export NAME [--out FILE]
    python -m ckl app start [--editor] | stop | restart | status
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

FRAME_DT = 1 / 30


# ---------------------------------------------------------------------- helpers
def _load_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"error: can't read {path}: {exc.strerror or exc}")
    except ValueError as exc:
        raise SystemExit(f"error: {path} is not valid JSON: {exc}")


def _expand_files(patterns: list[str]) -> list[str]:
    """Expand wildcards ourselves (Windows shells don't)."""
    import glob

    out = []
    for pat in patterns:
        matches = sorted(glob.glob(pat)) if any(c in pat for c in "*?[") else [pat]
        if not matches:
            raise SystemExit(f"error: no files match {pat}")
        out.extend(matches)
    return out


def _print_issues(path: str, issues) -> bool:
    from .profiles.validate import errors

    if not issues:
        print(f"OK      {path}")
        return True
    for i in issues:
        print(f"{i}   ({path})")
    return not errors(issues)


def _store():
    from .profiles import ProfileStore

    return ProfileStore()


def _notify_reload(quiet: bool = False) -> None:
    from . import ipc

    if ipc.is_running():
        if ipc.send({"cmd": "reload"}) is None and not quiet:
            print("note: the running app did not answer (older version?). Run: python -m ckl app restart")


def _pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def _app_pids() -> list[int]:
    import psutil

    me = os.getpid()
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
        except (psutil.Error, OSError):
            continue
        if p.info["pid"] == me or "-m" not in cmd:
            continue
        i = cmd.index("-m")
        rest = cmd[i + 1:]
        if rest and rest[0] == "ckl" and not (len(rest) > 1 and rest[1] in ("profile", "app")):
            pids.append(p.info["pid"])
    return pids


def app_start(editor: bool = False, wait: float = 15.0) -> dict | None:
    from . import ipc

    if ipc.is_running():
        return ipc.send({"cmd": "status"})
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([_pythonw(), "-m", "ckl"] + (["--editor"] if editor else []),
                     creationflags=flags, close_fds=True)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(0.4)
        st = ipc.send({"cmd": "status"}, timeout_ms=800)
        if st is not None:
            # give GameSense a moment to connect
            while not st.get("connected") and time.monotonic() < deadline:
                time.sleep(0.4)
                st = ipc.send({"cmd": "status"}, timeout_ms=800) or st
            return st
    return None


def app_stop() -> bool:
    import psutil

    from . import ipc

    if ipc.is_running():
        ipc.send({"cmd": "quit"}, timeout_ms=1500)
    deadline = time.monotonic() + 5
    while _app_pids() and time.monotonic() < deadline:
        time.sleep(0.3)
    for pid in _app_pids():  # older versions without the quit command
        try:
            psutil.Process(pid).terminate()
        except psutil.Error:
            pass
    time.sleep(0.5)
    return not _app_pids()


def ensure_app() -> dict:
    """Make sure an up-to-date app instance is running and answering. Returns its status."""
    from . import ipc

    if ipc.is_running():
        st = ipc.send({"cmd": "status"})
        if st is not None:
            return st
        print("The running app is an older version that can't take commands; restarting it…")
        app_stop()
    st = app_start()
    if st is None:
        raise SystemExit("error: could not start the app (see %APPDATA%\\CustomKeyboardLights\\ckl.log)")
    return st


def _print_status(st: dict) -> None:
    gg = "connected" if st.get("connected") else f"NOT connected ({st.get('gg_error') or 'waiting'})"
    print(f"app:         running{' (PAUSED)' if st.get('paused') else ''}")
    print(f"GG:          {gg}")
    print(f"live:        {st.get('active')}{'  [preview]' if st.get('preview') else ''}")
    print(f"default:     {st.get('default')}")
    print(f"calibrated:  {st.get('calibrated')}")
    print(f"profiles:    {', '.join(st.get('profiles', []))}")


# ---------------------------------------------------------------------- schema
def cmd_schema(args) -> int:
    from .engine.effects import EFFECTS
    from .engine.layer import BLEND_MODES
    from .layout import get_layout
    from .layout.groups import DYNAMIC_GROUPS, STATIC_GROUPS
    from .profiles.validate import CATEGORIES

    layout = get_layout()
    effects = {
        eid: {
            "name": cls.name,
            "category": cls.category,
            "reactive": cls.reactive,
            "description": cls.description,
            "params": [
                {k: v for k, v in {"key": p.key, "label": p.label, "kind": p.kind, "default": p.default,
                                   "min": p.min, "max": p.max, "choices": p.choices or None}.items()
                 if v is not None}
                for p in cls.params
            ],
        }
        for eid, cls in EFFECTS.items()
    }
    rows = {f"row{r}": [l.id for l in layout.keyboard if l.row == r] for r in range(6)}
    rows["mouse"] = [l.id for l in layout.mouse]
    labels = {l.id: l.label for l in layout.leds}
    data = {
        "effects": effects,
        "blend_modes": BLEND_MODES,
        "categories": CATEGORIES,
        "key_groups": {**{f"@{k}": v for k, v in STATIC_GROUPS.items()},
                       **{f"@{k}": "(dynamic)" for k in DYNAMIC_GROUPS}},
        "keys_by_row": rows,
        "key_labels": labels,
    }
    if args.json:
        print(json.dumps(data, indent=1, ensure_ascii=False))
        return 0
    print("EFFECTS  (layer.effect = id; params not given use the default)")
    for eid, e in effects.items():
        flag = " · reactive (needs key presses)" if e["reactive"] else ""
        print(f"\n  {eid}  — {e['name']} [{e['category']}]{flag}")
        if e["description"]:
            print(f"      {e['description']}")
        for p in e["params"]:
            rng = f"  range {p['min']}..{p['max']}" if "min" in p else ""
            ch = f"  one of {p['choices']}" if "choices" in p else ""
            print(f"      {p['key']}: {p['kind']} = {json.dumps(p['default'])}{rng}{ch}   ({p['label']})")
    print(f"\nBLEND MODES: {', '.join(BLEND_MODES)}")
    print("  normal=replace · add=brighten (sum) · screen=soft brighten · multiply=tint/darken · max=brightest wins")
    print("\nKEY GROUPS (use in layer.keys and in paint params.keys):")
    for g, members in data["key_groups"].items():
        print(f"  {g}: {' '.join(members) if isinstance(members, list) else members}")
    print("\nKEY IDS by row (label in parentheses where it differs; Italian ISO legends):")
    for r, ids in rows.items():
        print(f"  {r}: " + " ".join(f"{i}({labels[i]})" if labels[i] and labels[i].lower() != i else i for i in ids))
    print("\nPROFILE FILE FORMAT:")
    print(json.dumps({
        "name": "Example", "description": "one line", "category": "vibe", "tags": ["calm"],
        "keyboard_brightness": 1.0, "mouse_brightness": 0.6, "reactive": True,
        "layers": [
            {"name": "Base", "effect": "gradient", "params": {"colors": ["#120024", "#3a0060"]}},
            {"name": "Highlights", "effect": "paint", "params": {"keys": {"@wasd": "#ff2050", "space": "#ffb000"}}},
            {"name": "Typing", "effect": "ripple", "blend": "screen", "opacity": 0.8, "keys": ["@keyboard"]},
        ]}, indent=1))
    print("Layers draw bottom (first) to top (last). keys: null/omitted = every key + mouse.")
    return 0


# ---------------------------------------------------------------------- validate / render
def cmd_validate(args) -> int:
    from .profiles.validate import validate

    ok = True
    for f in _expand_files(args.files):
        ok &= _print_issues(f, validate(_load_json(f)))
    return 0 if ok else 1


def render_frames(data: dict, times: list[float], press: list[str], caps: bool = False, cpu: float = 0.45):
    """Simulate the profile and return [(t, colors_u8)] at the requested times."""
    import numpy as np

    from .engine.effects import RenderContext
    from .engine.layer import Layer, composite, to_u8
    from .layout import get_layout
    from .profiles import Profile

    layout = get_layout()
    prof = Profile.from_dict(data)
    layers = [Layer(cfg, layout) for cfg in prof.layers]
    is_mouse = np.array([l.device == "mouse" for l in layout.leds])
    levels = np.where(is_mouse, prof.mouse_brightness, prof.keyboard_brightness).astype(np.float32)[:, None]
    press_ids = [k for k in layout.expand(press) if k in layout.by_id]
    schedule = {round(0.1 + i * 0.12, 3): layout.by_id[k].index for i, k in enumerate(press_ids)}
    out, t, want = [], 0.0, sorted(times)
    end = want[-1] + 1e-6
    while t <= end:
        presses = [(idx, t) for pt, idx in schedule.items() if t - FRAME_DT < pt <= t] if prof.reactive else []
        ctx = RenderContext(t=t, dt=FRAME_DT, layout=layout, presses=presses, held=set(),
                            locks={"caps": caps, "scroll": False, "num": False}, cpu=cpu)
        frame = to_u8(composite(layers, ctx), levels)
        while want and t >= want[0] - FRAME_DT / 2:
            out.append((want.pop(0), frame.copy()))
        t += FRAME_DT
    return out


def cmd_render(args) -> int:
    from .profiles.validate import errors, validate

    data = _load_json(args.file)
    issues = validate(data)
    if errors(issues):
        _print_issues(args.file, issues)
        return 1
    # Native platform (has fonts); the widget is only grabbed, never shown.
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPalette
    from PySide6.QtWidgets import QApplication

    from .layout import get_layout
    from .ui.keyboard_view import KeyboardView

    app = QApplication.instance() or QApplication([])  # noqa: F841
    times = [float(x) for x in args.times.split(",")]
    press = [p.strip() for p in args.press.split(",") if p.strip()] if args.press is not None else None
    if press is None:
        reactive = any(l.get("effect") in ("ripple", "key_fade", "heatmap") for l in data.get("layers", []))
        press = ["f", "j", "space", "w"] if reactive else []
    frames = render_frames(data, times, press, caps=args.caps)
    view = KeyboardView(get_layout())
    pal = view.palette()
    pal.setColor(QPalette.Window, QColor(24, 24, 28))
    view.setPalette(pal)
    w, h, header = 1100, 330, 26
    img = QImage(w, (h + header) * len(frames) + 34, QImage.Format_RGB32)
    img.fill(QColor(24, 24, 28))
    p = QPainter(img)
    f = QFont()
    f.setPixelSize(15)
    p.setFont(f)
    p.setPen(QColor(235, 235, 240))
    title = f"{data.get('name')} — {data.get('description', '')}"
    p.drawText(12, 22, title[:140])
    for i, (t, colors) in enumerate(frames):
        y = 34 + i * (h + header)
        p.setPen(QColor(170, 170, 180))
        extra = f"   simulated presses: {' '.join(press)}" if press and i == 0 else ""
        p.drawText(12, y + 18, f"t = {t:.2f}s{extra}")
        view.resize(w, h)
        view.set_colors(colors)
        p.drawPixmap(0, y + header, view.grab())
    p.end()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    for i in issues:
        print(i)
    print(f"rendered {len(frames)} frames -> {out}")
    return 0


# ---------------------------------------------------------------------- store ops
def cmd_import(args) -> int:
    from .profiles import Profile
    from .profiles.validate import errors, validate

    store = _store()
    imported = []
    for f in _expand_files(args.files):
        data = _load_json(f)
        issues = validate(data)
        if not _print_issues(f, issues):
            return 1
        name = data["name"]
        if name in store.profiles and not args.replace:
            print(f"error: a profile named {name!r} already exists (use --replace)")
            return 1
        store.save_profile(Profile.from_dict(data))
        imported.append(name)
    print(f"imported: {', '.join(imported)}")
    if not args.no_reload:
        _notify_reload()
    return 0


def cmd_preview(args) -> int:
    from . import ipc

    name = args.name
    if args.file:
        rc = cmd_import(argparse.Namespace(files=[args.file], replace=True, no_reload=True))
        if rc:
            return rc
        name = _load_json(args.file)["name"]
    if not name:
        raise SystemExit("error: give a profile NAME or --file FILE")
    st = ensure_app()
    store = _store()
    needed = {l.effect for l in store.profiles[name].layers} if name in store.profiles else set()
    missing = needed - set(st.get("effects", []))
    if missing:
        print(f"The running app doesn't know {sorted(missing)} yet (new code); restarting it…")
        app_stop()
        if app_start() is None:
            raise SystemExit("error: could not restart the app")
    st = ipc.send({"cmd": "preview", "name": name})
    if not st or not st.get("ok"):
        print(f"error: {st.get('error') if st else 'no answer from the app'}")
        return 1
    _print_status(st)
    if not st.get("connected"):
        print("warning: GG is not connected, so the hardware won't show it yet")
    return 0


def cmd_end_preview(args) -> int:
    from . import ipc

    if not ipc.is_running():
        print("app not running")
        return 0
    st = ipc.send({"cmd": "end_preview"})
    if st:
        _print_status(st)
    return 0


def cmd_set_default(args) -> int:
    store = _store()
    if args.name not in store.profiles:
        raise SystemExit(f"error: no profile named {args.name!r}")
    store.settings.default_profile = args.name
    store.save_settings()
    _notify_reload()
    print(f"default profile: {args.name}")
    return 0


def cmd_bind(args) -> int:
    from .profiles import AppRule

    store = _store()
    if args.name not in store.profiles:
        raise SystemExit(f"error: no profile named {args.name!r}")
    exe = args.exe if args.exe.lower().endswith(".exe") else args.exe + ".exe"
    store.settings.rules = [r for r in store.settings.rules if r.exe.lower() != exe.lower()]
    store.settings.rules.append(AppRule(exe, args.name))
    store.settings.auto_switch = True
    store.save_settings()
    _notify_reload()
    print(f"{exe} -> {args.name} (auto-switch on)")
    return 0


def cmd_unbind(args) -> int:
    store = _store()
    before = len(store.settings.rules)
    store.settings.rules = [r for r in store.settings.rules if r.exe.lower() != args.exe.lower()]
    store.save_settings()
    _notify_reload()
    print("removed" if len(store.settings.rules) < before else "no such rule")
    return 0


def cmd_list(args) -> int:
    store = _store()
    rules: dict[str, list[str]] = {}
    for r in store.settings.rules:
        rules.setdefault(r.profile, []).append(r.exe)
    for name, p in store.profiles.items():
        mark = " (default)" if name == store.settings.default_profile else ""
        bound = f"  ← {', '.join(rules[name])}" if name in rules else ""
        print(f"{name}{mark}  [{p.category}] {len(p.layers)} layers{bound}")
        if p.description:
            print(f"    {p.description}")
    return 0


def cmd_status(args) -> int:
    from . import ipc

    if ipc.is_running():
        st = ipc.send({"cmd": "status"})
        if st is None:
            print("app: running, but an older version that doesn't answer commands -> python -m ckl app restart")
            return 1
        _print_status(st)
        return 0
    from .gamesense import GameSenseUnavailable, read_address

    try:
        gg = f"GameSense at {read_address()}"
    except GameSenseUnavailable as exc:
        gg = str(exc)
    print("app:         not running (preview/app start will launch it)")
    print(f"GG:          {gg}")
    print(f"profiles:    {', '.join(_store().profiles)}")
    return 0


def cmd_delete(args) -> int:
    store = _store()
    if args.name not in store.profiles:
        raise SystemExit(f"error: no profile named {args.name!r}")
    if len(store.profiles) <= 1:
        raise SystemExit("error: can't delete the last profile")
    store.delete_profile(args.name)
    _notify_reload()
    print(f"deleted {args.name}")
    return 0


def cmd_export(args) -> int:
    store = _store()
    if args.name not in store.profiles:
        raise SystemExit(f"error: no profile named {args.name!r}")
    text = json.dumps(store.profiles[args.name].to_dict(), indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


# ---------------------------------------------------------------------- app
def cmd_app(args) -> int:
    if args.action == "start":
        st = app_start(editor=args.editor)
        if st is None:
            print("error: app did not start")
            return 1
        _print_status(st)
    elif args.action == "stop":
        print("stopped" if app_stop() else "warning: some app processes are still running")
    elif args.action == "restart":
        app_stop()
        st = app_start(editor=args.editor)
        if st is None:
            print("error: app did not start")
            return 1
        _print_status(st)
    else:
        return cmd_status(args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m ckl", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    top = ap.add_subparsers(dest="group", required=True)

    prof = top.add_parser("profile", help="profile authoring tools").add_subparsers(dest="cmd", required=True)
    s = prof.add_parser("schema", help="effects, params, key ids, groups, file format")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_schema)
    s = prof.add_parser("validate")
    s.add_argument("files", nargs="+")
    s.set_defaults(func=cmd_validate)
    s = prof.add_parser("render", help="offscreen PNG of the profile at a few moments in time")
    s.add_argument("file")
    s.add_argument("--out", required=True)
    s.add_argument("--times", default="0,0.7,1.4", help="comma-separated seconds")
    s.add_argument("--press", default=None, help="comma-separated key ids/@groups to simulate pressing")
    s.add_argument("--caps", action="store_true", help="simulate Caps Lock on")
    s.set_defaults(func=cmd_render)
    s = prof.add_parser("import")
    s.add_argument("files", nargs="+")
    s.add_argument("--replace", action="store_true")
    s.add_argument("--no-reload", action="store_true")
    s.set_defaults(func=cmd_import)
    s = prof.add_parser("preview", help="show a profile live on the hardware (starts the app if needed)")
    s.add_argument("name", nargs="?")
    s.add_argument("--file", help="import this file (replacing) and preview it")
    s.set_defaults(func=cmd_preview)
    prof.add_parser("end-preview").set_defaults(func=cmd_end_preview)
    s = prof.add_parser("set-default")
    s.add_argument("name")
    s.set_defaults(func=cmd_set_default)
    s = prof.add_parser("bind", help="auto-switch to NAME when EXE has focus")
    s.add_argument("exe")
    s.add_argument("name")
    s.set_defaults(func=cmd_bind)
    s = prof.add_parser("unbind")
    s.add_argument("exe")
    s.set_defaults(func=cmd_unbind)
    prof.add_parser("list").set_defaults(func=cmd_list)
    prof.add_parser("status").set_defaults(func=cmd_status)
    s = prof.add_parser("delete")
    s.add_argument("name")
    s.set_defaults(func=cmd_delete)
    s = prof.add_parser("export")
    s.add_argument("name")
    s.add_argument("--out")
    s.set_defaults(func=cmd_export)

    app = top.add_parser("app", help="control the tray app")
    app.add_argument("action", choices=["start", "stop", "restart", "status"])
    app.add_argument("--editor", action="store_true")
    app.set_defaults(func=cmd_app)
    return ap


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)
