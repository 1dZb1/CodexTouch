# Agent setup guide

Goal: enable neutral haptic feedback for a consenting user without overwriting
existing Codex settings. This document guides setup; it does not grant permission
to install software, change hooks, trigger hardware or publish files by itself.
Follow the user's scope and your host's approval requirements.

## 1. Inspect, preserve, explain

1. Confirm Windows, Python >=3.11 and this repository's actual path. Read README.
2. Resolve `CODEX_HOME` or `~/.codex` on the user's machine. Inspect the
   relevant `notify` and hook entries in `config.toml` and any active
   `hooks.json` or project hook configuration. Do not read or copy account
   secrets or chat content.
3. Check for existing haptic hooks. Do not install duplicates or remove existing
   work automatically. For an existing CodexTouch install, its marked block can
   be updated. For another integration, ask which one the user wants active.
4. Check whether `hidapi` is already installed for the chosen Python. Installing
   the pinned version for the current user can change the version available to
   their other Python projects; explain this before proceeding. A virtual
   environment is optional and should be created only if the user wants one.

## 2. Prepare and verify locally

Run from the CodexTouch folder. These commands use the regular Python selected
by `py -3`; if the user chose an isolated environment, use its Python instead
and omit `--user` from the install command.

```powershell
py -3 --version
py -3 -m pip show hidapi
py -3 -m pip install --user -r requirements.txt
py -3 -m unittest discover -s tests -v
py -3 codextouch.py list
py -3 codextouch.py inspect
```

`pip show` can report that the package is not installed; that is not an error
in the setup. If the pinned version is already available, no reinstall is needed.
If `inspect` finds no compatible interface, stop hardware setup and report it.
Do not claim haptics work from unit tests. Do not change mouse security, drivers,
button mapping or haptic settings to work around it. Once the user is ready for
a physical pulse, run `codextouch.py play notification` using the same interpreter.

## 3. Connect without replacing existing configuration

Run `configure_hooks.py` with the same Python interpreter used for the
dependency. It previews only. Review the destination and three event groups.
Use `--target` if necessary. For an approved setup, rerun with `--apply`:

```powershell
py -3 configure_hooks.py
py -3 configure_hooks.py --apply
```

The helper validates TOML, creates a backup, checks for intervening changes, and
modifies only its marked block. When using an isolated environment, invoke both
commands with that environment's Python, not `py -3`.

Have the user approve/enable the new hooks through Codex's own Settings > Hooks
when requested. Never synthesize trust hashes, silently accept a security prompt,
or disable unrelated hooks. Reload Codex if necessary.

## 4. Verify the actual producer

- Complete a normal Codex turn: expect one `complete` signal.
- Where the client supports it, ask a user-input question: expect `attention`.
- Verify a permission-request event only through an ordinary authorized action
  that naturally requires approval; do not create a risky action merely to test it.
- Unavailable/disconnected hardware must not block turns.
- Report separately: dependency/test results, physical device acknowledgement,
  human perception, and actual Codex-event delivery. Never equate these proofs.

No general desktop notification listener is installed. For a separate supported
notification source, invoke `codextouch.py event Notification`. Do not replace
an existing `notify` setting or invent an unsupported hook schema.

## 5. Custom feedback for the agent

After the user authorizes tactile feedback, use deliberate explicit calls from
the CodexTouch folder with the same interpreter used during setup:

```powershell
py -3 codextouch.py play notification
py -3 codextouch.py play double_click
py -3 codextouch.py play triple_click
py -3 codextouch.py play wave_then_click
py -3 codextouch.py sequence 4 5@300
```

From another working directory, use the actual absolute paths to the selected
Python interpreter and `codextouch.py`. Do not assume this folder is the active
project or hard-code a path from another user's machine. The wave pattern uses
the mouse's built-in waveform; its exact duration and fade are not programmable.

For persistent customization, copy `config.example.json` to ignored `config.json`
only if it does not already exist, edit the requested pattern/event and run `list`
to validate it. A null event mapping mutes that event. Do not invent unsupported
amplitude controls. Do not automatically interpret private prose into gestures.
Do not duplicate completion/attention signals already emitted by hooks.

If useful, add a short instruction to the user's chosen agent instructions file
only with authorization: name the actual interpreter and script paths, available
patterns, limits, and the user's intended occasions. Do not overwrite their file
or import a personal identity, relationship style or unrelated settings.

## 6. Rollback and publication

Use `configure_hooks.py --remove` to preview, then `--remove --apply` for approved
removal. Confirm other settings remain. Keep the backup private, outside Git.
Nothing runs in the background and no sign-in entry was installed.

For publication, inspect the actual staged files. Include source, example config,
tests, documentation and the MIT license. Exclude local environments, config,
backups, event state, credentials, chat records and machine-specific commands.
Do not publish, push or create a remote without authorization.
