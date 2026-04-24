# SimpleMapper Runtime

Desktop map and waypoint editor for Stalcraft zone PNG packs.

## What it does

- Loads map zones from `assets/maps/zone_pack_png`
- Loads and saves `waypoints.cfg`
- Lets you select, move, delete, recolor, rename, and re-icon waypoints
- Parses images into waypoint markers
- Supports layers, undo/redo, EXBO path setup, and UI customization

## Project layout

- `PyGUI/main.py` - app entry point
- `PyGUI/desktop_app.py` - main app class
- `PyGUI/ui_mixin.py` - interface building and theming
- `PyGUI/image_mixin.py` - image parsing and preview logic
- `PyGUI/zone_mixin.py` - zone loading and animation
- `PyGUI/layers_mixin.py` - layer editor logic
- `simplemapper_core.py` - map scanning and waypoint cfg IO
- `assets/maps/zone_pack_png` - runtime zone pack
- `assets/waypoint_icons` - waypoint icons

## Requirements

- Python 3.13 recommended
- Windows

Install dependencies:

```powershell
py -3 -m pip install -r requirements.txt
```

## Run

From the project root:

```powershell
py .\PyGUI\main.py
```

## Build EXE

The project includes a build script that places the executable directly in the project root.

From the project root:

```powershell
.\build_exe.ps1
```

Or just double-click:

```text
build_exe.bat
```

Output file:

```text
SimpleMapperRuntime.exe
```

The EXE expects the project folders next to it, especially:

- `assets/`
- `PyGUI/` is not needed at runtime once built
- local config files like `app_config.json`, `ui_config.json`, and `layers.json` will appear near the EXE

## First launch

On first start the app asks for the `EXBO` folder.

Expected folder example:

```text
C:\Users\<YourUser>\AppData\Roaming\EXBO
```

The app then looks for:

```text
<EXBO>\runtime\stalcraft\config\waypoints.cfg
```

The selected EXBO path is stored in local `app_config.json`.

## Local generated files

These files are local-only and are ignored by git:

- `app_config.json`
- `ui_config.json`
- `layers.json`
- `waypoints.cfg`
- `backups/`
- `__pycache__/`
- `build/`
- `*.exe`

## Hotkeys

- `H` - hide/show sidebar
- `Delete` - delete selected markers or loaded image
- `Ctrl+S` - save markers to cfg
- `Ctrl+Z` - undo
- `Ctrl+Y` - redo
- `Ctrl+Shift+Z` - redo

## GitHub upload

1. Create an empty GitHub repository.
2. Open PowerShell in this folder.
3. Run:

```powershell
git init
git add .
git commit -m "Initial runtime release"
git branch -M main
git remote add origin https://github.com/<your-name>/<your-repo>.git
git push -u origin main
```

If Git asks for auth, sign in through Git Credential Manager or use GitHub Desktop.

## Notes

- This repo is prepared to avoid publishing personal runtime config files.
- If you want a shared default theme, create `ui_config.json` locally and tune it before release, then decide whether to keep it tracked or ignored.
