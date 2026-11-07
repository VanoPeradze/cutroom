# CUTROOM Desktop window for Windows

Run `START CUTROOM DESKTOP.cmd` from the main CUTROOM folder. It opens a separate application window using the already installed Google Chrome runtime, with the existing local Python/FFmpeg engine. No browser tab, download, dependency installation, or project conversion is required.

In a downloaded beta, run the normal `START CUTROOM.bat` once to complete setup. Then open `App/START CUTROOM DESKTOP.cmd` for the Chrome desktop window. The desktop launcher itself never installs dependencies.

This is a desktop shell, not a native rewrite or a signed standalone installer. The normal `run_windows.bat` remains available.

## Data and safety

- The same folder's `config.json`, projects, media, exports and installed runtime stay in place.
- The launcher verifies both the running engine's version and its data-folder identity. It will not silently attach to another installed CUTROOM copy.
- The desktop window has a dedicated Chrome profile, separate from normal Chrome and from any earlier Edge test profile. It never falls back to Edge. Browser-local interface preferences and source marks from Chrome are not automatically migrated. Saved projects and editing decisions are unchanged.
- Closing the window does not terminate the engine or interrupt an export. Opening Desktop again reconnects to that engine. For this first desktop shell, close the engine before replacing application files; automatic shutdown, a tray controller and signed installation are not implemented yet.
- Startup failures appear in a CUTROOM dialog. Engine output is recorded in `data/logs/desktop-engine.log`.
- The launcher refuses remote addresses and does not change Windows execution policy, firewall rules or security settings.

Validate prerequisites without opening the app:

` .venv\Scripts\python.exe scripts\desktop_windows.py --check `

Before a public desktop release, validate window close/reopen, export after close, startup failure recovery, multiple installed folders, Hebrew paths, monitor scaling, media dialogs and project recovery on physical Windows machines. macOS packaging and a bundled runtime remain separate work.
