"""Entry point.

    python -m ckl                 run the tray app
    python -m ckl --editor        run it and open the editor
    python -m ckl profile ...     profile authoring CLI (see ``ckl.cli``)
    python -m ckl app ...         start / stop / restart the tray app
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys

from .paths import data_dir


def _setup_logging(verbose: bool) -> None:
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(data_dir() / "ckl.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:  # pythonw has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("profile", "app"):
        from .cli import main as cli_main

        return cli_main(argv)
    return run_app(argv)


def run_app(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ckl", description="SteelGlow (subcommands: profile, app)")
    ap.add_argument("--editor", action="store_true", help="open the editor window on start")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    _setup_logging(args.verbose)

    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from . import ipc

    app = QApplication(sys.argv[:1])
    app.setApplicationName("SteelGlow")
    app.setQuitOnLastWindowClosed(False)

    # Single instance: a second launch just asks the first one to open its editor.
    if ipc.is_running():
        if ipc.send({"cmd": "show"}, timeout_ms=1500) is None:
            logging.getLogger(__name__).warning(
                "another (older) instance is running and did not answer; use `python -m ckl app restart`")
        return 0

    from .ui.controller import Controller
    from .ui.editor import EditorWindow
    from .ui.tray import Tray, make_icon

    app.setWindowIcon(make_icon())
    ctrl = Controller()
    ctrl.start()
    editor: dict[str, EditorWindow | None] = {"w": None}

    def open_editor() -> None:
        w = editor["w"]
        if w is None:
            w = EditorWindow(ctrl)
            editor["w"] = w
        w.show()
        w.raise_()
        w.activateWindow()

    server = ipc.IpcServer(lambda req: ctrl.handle_command(req, on_show=open_editor, on_quit=app.quit))  # noqa: F841

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(ctrl, open_editor)
        tray.show()
    if args.editor or tray is None:
        open_editor()
        if tray is None:
            app.setQuitOnLastWindowClosed(True)

    app.aboutToQuit.connect(ctrl.shutdown)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
