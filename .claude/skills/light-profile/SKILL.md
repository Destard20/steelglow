---
name: light-profile
description: Design a new RGB lighting profile for the user's SteelSeries Apex 9 TKL keyboard and Aerox 9 mouse (or change an existing one). Interviews the user about what it is for (vibe/mood, a game, a task, other), builds the profile, shows it live on the hardware, and loops on their feedback until they approve. Use when the user asks for a new light/lighting/RGB profile, theme, color scheme for a game, or wants to tweak one.
---

# Light profile designer

You design lighting profiles for Custom Keyboard Lights and iterate **with the hardware showing the
result live**. The user judges by looking at their keyboard, so every draft must be previewed and then
followed by a question.

All commands run from the repo root in PowerShell. Abbreviation used below:
`ckl` = `.venv\Scripts\python -m ckl`

## 0. Setup (silently, in parallel)
- `ckl profile status`: is the app running, is GG connected? "older version" → run `ckl app restart`.
  GG not connected → tell the user to start SteelSeries GG; you can still design meanwhile.
- `ckl profile schema`: the authoritative list of effects, params, ranges, key ids, `@groups`. Never
  guess param names; use this output.
- `ckl profile list` and the files in `profile_library/`: existing profiles. If the user wants to
  change one, start from its library file (or `ckl profile export NAME --out profile_library/<slug>.json`).
- Read `design-guide.md` (next to this file) before designing.

## 1. Interview (AskUserQuestion)
Ask **one round first**: what kind of profile.
- Header "Kind": **Vibe / mood**, **Game**, **Task / activity**, **Other**. If the user's request
  already makes the kind obvious, skip this and say what you assumed.

Then one follow-up round (up to 4 questions together) tailored to the kind. Prefer concrete options
with a recommended first option, and let "Other" catch free text:
- **Vibe**: mood or theme (e.g. Synthwave night, Cozy fireplace, Ocean calm, Cyberpunk neon, Forest),
  and the palette direction if they care.
- **Game**: which game. Then, in a **separate step**, propose that game's default keybinds grouped by
  role (movement, core abilities, items/potions/consumables, utility/UI, communication) as a short
  list with the key ids you'd highlight, and ask them to confirm or correct it (option "Looks right" vs
  "I'll correct it" in Other). They may have rebinds, and the Aerox 9 side buttons send keys
  (e.g. Q, 2, 3, E, 5, 6, R, 8, 9 in their PoE2 config), so trust what they say over defaults.
- **Task**: what activity (coding, writing, streaming, reading/night use, music, video calls…).
- **Every kind**, in the same round where it fits:
  - Animation energy: Calm/static · Gentle motion · Energetic.
  - React to typing? Ripples · Key glow/fade · Heatmap · None.
  - Mouse: Match the keyboard · Dim (≈30–50 %) · Off (saves battery). The user cares about mouse
    battery, so mention that dim/off helps.

Don't over-interview: two rounds normally, three at most (the game key confirmation counts as one).

## 2. Design
- Follow `design-guide.md`: base layer → role/highlight layers → reactive overlay → indicators on top.
- Write the profile to `profile_library/<kebab-slug>.json` with `name` (Title Case, unique unless
  replacing), one-line `description`, `category` (vibe|game|task|other), `tags`, brightness values,
  `reactive`, `layers`. Use `@groups` for readability.
- **If no existing effect can produce the look** (e.g. fire, rain, matrix, aurora), write a new
  effect: create `src/ckl/engine/effects/<name>.py` following the template in `design-guide.md`.
  It auto-registers. Run `.venv\Scripts\python -m pytest -q`; the suite renders every registered effect.
  Then re-run `ckl profile schema` to confirm its params. Tell the user you added an effect.

## 3. Self-check before showing
1. `ckl profile validate profile_library/<slug>.json`: fix every ERROR; read the WARNINGs (e.g. an
   opaque full layer hiding everything below is usually a mistake).
2. `ckl profile render profile_library/<slug>.json --out <scratchpad>\<slug>.png [--press <keys>]`
   then **Read the PNG**. Check that highlights are readable, colors match the intent, nothing is
   accidentally black or washed out, and reactive layers do something (pass `--press` with keys the user will
   actually use, e.g. `@wasd,space`). Fix and re-render if needed. Put the PNG in the session scratchpad,
   not the repo.

## 4. Show it live and ask
1. `ckl profile preview --file profile_library/<slug>.json`: imports (replacing a same-named profile)
   and forces it live on keyboard + mouse, overriding per-app switching, even while this chat window
   has focus. It starts the tray app if needed.
2. Tell the user in one or two sentences what they should be seeing (layers, what to press to try
   the reactive part, what happens on Caps Lock if relevant).
3. AskUserQuestion, header "Verdict": "It's live on your keyboard now. How is it?"
   - **Keep it** — approve as is
   - **Tweak it** — keep the idea, change details (they describe in Other / next message)
   - **Different direction** — rethink colors/concept
   - **Discard** — drop it
   If they pick Tweak or Different direction without details, ask what to change (free-form is
   fine). Apply the change to the same library file, then repeat **3 → 4** (validate, render, preview,
   ask). Keep each iteration small and say what you changed.

## 5. Finish
- **Keep it** → AskUserQuestion, header "Use it": what should happen now:
  - **Just save it**: stays available in the tray/editor.
  - **Make it the default**: `ckl profile set-default "<Name>"`.
  - **Auto-switch for an app**: for games, look up the running exe (`Get-Process | Select-Object
    ProcessName,Path`, filter plausible names) or ask the user. Then run `ckl profile bind <game.exe> "<Name>"`.
  Then `ckl profile end-preview` so normal switching resumes (if they made it default it stays visible).
  Offer to commit `profile_library/<slug>.json` (and any new effect + tests) to git. Don't commit
  unasked.
- **Discard** → `ckl profile end-preview`, `ckl profile delete "<Name>"` (only if it was created in this
  session, never delete a pre-existing profile without asking), and delete the library file you created.
- If the user stops answering or changes topic, run `ckl profile end-preview` before moving on so their
  per-app switching isn't stuck on the preview.

## Rules
- Never finish a draft without previewing it live **and** asking for the verdict.
- Don't edit `%APPDATA%` files by hand; go through `ckl profile import/preview`.
- Don't change GG settings or other profiles unless asked.
- Keep chat output short; the hardware is the preview.
