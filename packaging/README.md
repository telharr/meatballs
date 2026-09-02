# Packaging — PZ Control Panel

Build standalone Windows distribution (Sprint 6 / v3.17.0).

## Prerequisites

- Python 3.10+ with `panel/requirements.txt` installed
- [PyInstaller](https://pyinstaller.org): `python -m pip install pyinstaller`
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (Windows only, for `.exe` installer)

## Build standalone bundle

```bash
python packaging/build_exe.py --clean
```

Output: `dist/PZControlPanel/` containing `PZControlPanel.exe` (Windows) plus bundled `panel/static`, `tools`, etc.

Run locally:

```bash
cd dist/PZControlPanel
./PZControlPanel.exe    # Windows
```

## Build Windows installer

1. Complete PyInstaller step above.
2. Open Inno Setup → Compile `packaging/installer.iss`  
   Or CLI: `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss`
3. Installer output: `packaging/Output/PZControlPanel-3.17.0-setup.exe`

### Installer modes

| Radio option | `.env` |
|--------------|--------|
| Локальный сервер / Разработчик | `AUTH_LOCAL_BYPASS=true` |
| Клиент удалённого сервера | `AUTH_LOCAL_BYPASS=false` + host template |

Post-install runs `start_panel.bat` and opens http://127.0.0.1:8000/

## Gitignored artifacts

`dist/`, `build/`, `packaging/Output/`, `*.exe` — see root `.gitignore`.

## See also

- `docs/DEPLOYMENT.md` — scenarios A (local), B (VPS), C (Docker)
- `packaging/templates/` — `.env` templates (no secrets)
