# Stalcraft Waypoint Editor

<div align="center">

**🌐 Available in:**  
🇬🇧 **English** · [🇷🇺 Русский](README.ru.md)

</div>

<img wifth="128" height="128" alt="icon" src="https://github.com/HelloGames-ds/Stalcraft-Waypoint-Editor/blob/main/assets/app.ico" />

---

Desktop waypoint editor for **Stalcraft** with zone-based map loading, waypoint editing, image-to-marker parsing, and layer support.

---

## Screenshots

<img width="632" height="312" alt="Image" src="https://github.com/user-attachments/assets/1af8c97f-be9f-486a-af7c-c7478d5eebe4" />

<img width="1920" height="1017" alt="Image" src="https://github.com/user-attachments/assets/2f3c2438-d8b4-46f2-9606-9145e15e78a3" />

<img width="1920" height="1017" alt="Image" src="https://github.com/user-attachments/assets/3e49643e-7501-45d2-874e-248d64b5aca0" />

<img width="914" height="849" alt="Image" src="https://github.com/user-attachments/assets/29f151f7-c518-4ce6-8734-3dd3b859ea18" />

---

## Features

- Load map zones from `assets/maps/zone_pack_png`
- Enable only the regions you need instead of loading the whole map at once
- Load and save `waypoints.cfg`
- Create, move, delete, rename, recolor, and re-icon waypoints
- Parse images into waypoint markers(`Mask fill`/`Silhouette contour`/`Detail edges`)
- Preview generated markers before parsing
- Layer support with separate local layer storage
- Undo / Redo
- EXBO path configuration
- RU / EN interface
- Basic UI customization

---

## Requirements

- Windows
- Python `3.13` recommended

Install dependencies:

```powershell
py -3 -m pip install -r requirements.txt
```

---

## Run

### Option 1: Run the packaged `.exe`

- Open the repository `Releases` page
- Download `Stalcraft-Waypoint-Editor.exe` from the latest release assets
- Run the executable

### Option 2: Run from source

From the project root:

```powershell
py .\PyGUI\main.py
```

---

## First Launch

On first start the app asks for:

1. Interface language
2. Path to the `EXBO` folder

Expected folder example:

```text
C:\Users\<YourUser>\AppData\Roaming\EXBO
```

The app then looks for:

```text
<EXBO>\runtime\stalcraft\config\waypoints.cfg
```

Local runtime files created by the app are stored in:

```text
%APPDATA%\Stalcraft-Waypoint-Editor
```

This includes:

- `app_config.json`
- `settings.json`
- `ui_config.json`
- `layers.json`
- `backups/`
- `.cache/`

These files are user-local, are not stored next to the executable, and should usually stay out of the repository.

---

## Hotkeys

- `H` - hide / show sidebar
- `Delete` - delete selected waypoint(s) or loaded image
- `Ctrl+S` - save waypoints to cfg
- `Ctrl+Z` - undo
- `Ctrl+Y` - redo
- `Ctrl+Shift+Z` - redo

---

## Project Structure

- `PyGUI/main.py` - app entry point
- `PyGUI/desktop_app.py` - main application class
- `PyGUI/ui_mixin.py` - interface building and theming
- `PyGUI/image_mixin.py` - image parsing and preview logic
- `PyGUI/zone_mixin.py` - zone loading and reveal logic
- `PyGUI/layers_mixin.py` - layer system
- `PyGUI/i18n.py` - translations
- `simplemapper_core.py` - cfg IO, asset discovery, and map scanning
- `assets/maps/zone_pack_png` - zone PNG pack
- `assets/waypoint_icons` - waypoint icons
- `.github/workflows/build-exe.yml` - GitHub Actions workflow for Windows `.exe` builds
- `simplemapper_runtime.spec` - PyInstaller spec for one-file packaging

---

## Build EXE

The repository is configured to build a standalone Windows `.exe` through GitHub Actions.

- Push changes to `main`
- Open the latest `Build Windows EXE` workflow run in `Actions`
- Download the artifact containing `Stalcraft-Waypoint-Editor.exe`

---

## Credits

Special thanks to [TeamDima](https://github.com/DeTTK) for the original program.
