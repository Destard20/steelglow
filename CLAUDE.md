# Custom Keyboard Lights

Python (PySide6) tray app that drives SteelSeries Apex 9 TKL + Aerox 9 lighting through the
GameSense API of SteelSeries GG. GG must stay running; it keeps keybinds/macros. See README.md.

- Run things with the venv: `.venv\Scripts\python -m …` (package is installed editable from `src/`).
- Tests: `.venv\Scripts\python -m pytest`.

## Light profiles
- To create or change a lighting profile, use the **`/light-profile` skill**
  (`.claude/skills/light-profile/`). It interviews the user, previews live on the hardware and loops on
  feedback.
- Profile source files live in `profile_library/*.json` (committed). The app's live store is
  `%APPDATA%\CustomKeyboardLights\profiles\`; `ckl profile import` copies library files into it.
- Always-current reference for effects/params/key ids/groups: `python -m ckl profile schema`.
- Authoring CLI (`python -m ckl profile …`): `validate`, `render --out x.png`, `import [--replace]`,
  `preview NAME|--file F`, `end-preview`, `set-default`, `bind EXE NAME`, `list`, `status`, `delete`.
  App control: `python -m ckl app start|stop|restart|status`.

## Code map
- `src/ckl/engine/effects/` – one class per effect; subclasses of `Effect` with an `id` auto-register
  (new module = new effect, picked up by editor, schema and tests).
- `src/ckl/engine/layer.py` – layers + compositor (blend modes, opacity, key masks).
- `src/ckl/layout/` – key layout (`apex9_tkl.py`), `@group` definitions (`groups.py`), grid mapping.
- `src/ckl/profiles/` – profile/settings store, `validate.py`, per-app rules.
- `src/ckl/ui/` – controller (profile selection, preview, IPC commands), tray, editor.
- `src/ckl/ipc.py` + `src/ckl/cli.py` – CLI ↔ running app (JSON lines over a local socket).
