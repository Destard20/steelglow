# SteelGlow

Layered, reactive, per-app RGB lighting for the **SteelSeries Apex 9 TKL** and **Aerox 9 Wireless**,
inspired by Cooler Master MasterPlus.

Lighting goes through SteelSeries' official local **GameSense** API, so **SteelSeries GG keeps running
in the background** and still handles key bindings, macros, actuation points and onboard profiles.
This app only takes over the LEDs. Pause it, or quit it, and GG's own lighting comes back.

> SteelGlow is an independent hobby project. It is not affiliated with or endorsed by SteelSeries.
> SteelSeries, GG, GameSense, Apex and Aerox are trademarks of their owners.

## Features
- **Layer stack** per profile: each layer has an effect, a blend mode (normal, add, multiply,
  screen, max), opacity, and a scope (every key plus the mouse, or a chosen set of keys).
- **Effects**
  - Ambient: solid, per-key paint, gradient, wave (rainbow or custom colors, 6 directions),
    spectrum cycle, breathing, starlight
  - Reactive: ripple, key fade, typing heatmap
  - Indicators: Caps/Scroll/Num Lock, CPU-load bar
- **Per-app profiles**: switch profile automatically when a given `.exe` has focus.
- **Tray app** with profile switcher, pause, start-with-Windows and a live preview editor.
  *Start with Windows* puts a **SteelGlow** shortcut in your Startup folder, so it shows up by name
  in Task Manager → Startup apps and Settings → Apps → Startup, where you can also turn it off.
- **Calibration wizard** that learns exactly which key each GameSense grid cell lights.

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
```

## Run
```powershell
.\.venv\Scripts\pythonw -m ckl --editor
```
`pythonw -m ckl` starts in the tray only. Double-click the tray icon to open the editor. A second
launch just brings up the running instance's editor.

First run: if nothing lights up, open **GG → Engine → Apps** and enable *SteelGlow*.
Then use **Settings → Calibrate keyboard…** once for exact per-key mapping.

## Designing profiles with Claude
Run **`/light-profile`** in Claude Code. It asks what the profile is for (a vibe, a game, a task…),
builds it, shows it live on the keyboard and mouse, and keeps adjusting it until you approve. Profiles
it creates are saved in `profile_library/`.

The same tools are available by hand:
```powershell
.\.venv\Scripts\python -m ckl profile schema                          # effects, params, key ids, @groups
.\.venv\Scripts\python -m ckl profile preview --file profile_library\gaming.json
.\.venv\Scripts\python -m ckl profile end-preview
```
Other commands: `validate`, `render --out x.png`, `import`, `set-default`, `bind game.exe NAME`,
`list`, `status`, `delete`. Use `python -m ckl app start|stop|restart` to control the app.

## Where things are stored
`%USERPROFILE%\.steelglow\`: `profiles\*.json`, `settings.json`,
`calibration_apex9_tkl.json`, `ckl.log`.

## Tests / tools
```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\smoke.py
```
`smoke.py` shows red, then green, then a rainbow on the keyboard and mouse, then hands the lights
back to GG.

## Notes
- GG accepts about 25 frames per second, so the engine always sends the newest frame and drops the rest.
- Reactive effects use a read-only low-level keyboard hook. It never blocks or changes input. Untick
  *Listen to key presses* on a profile if a game's anti-cheat objects.
- **Mouse stays dark?** In GG, open the Aerox 9 page and turn **High-Efficiency Mode off**. While it is
  on, it blocks all lighting, including this app's. The Aerox 9 works with the default `rgb-3-zone`
  device type; other device types are only for different mice.
- GG's own mouse battery settings still apply on top of this app. *Illumination Smart Mode* turns the
  LEDs off while the mouse moves, and *Illumination Dim Timer* dims them when idle. To save battery from
  this app instead, set *Mouse brightness* to 0 % on a profile: the mouse then gets almost no lighting
  updates.

## License
MIT, see [LICENSE](LICENSE).
