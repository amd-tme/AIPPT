# Exporting Slides to Images

Several AIPPT features (e.g. `analyze`, `catalog --images-dir`) require
slide images exported as individual PNG files. On Windows with PowerPoint
installed, the included helper script automates this via COM automation.

## Prerequisites

- **Windows** with **Microsoft PowerPoint** installed (desktop version, not web).
- PowerShell 5.1+ (ships with Windows 10/11).

## Quick Start

### Using the CLI wrapper

```bash
# From the project root (Git Bash)
venv/Scripts/python.exe aippt.py export-images deck.pptx images/deck-name/
```

### Using PowerShell directly

```powershell
.\scripts\Export-SlidesToImages.ps1 -PptxPath deck.pptx -OutDir images\deck-name
```

### Custom resolution

```powershell
.\scripts\Export-SlidesToImages.ps1 -PptxPath deck.pptx -OutDir images\deck-name -Width 2560 -Height 1440
```

## Output

PowerPoint creates files named `Slide1.PNG`, `Slide2.PNG`, etc. in the output
directory. This naming convention is what `analyze` and `catalog` expect when
looking up slide images by position.

## Typical Workflow

```bash
# 1. Export slides as images
venv/Scripts/python.exe aippt.py export-images deck.pptx images/deck/

# 2. Catalog the deck with image paths
venv/Scripts/python.exe aippt.py catalog deck.pptx --images-dir images/deck/

# 3. Run AI analysis using the images
venv/Scripts/python.exe aippt.py analyze deck.pptx --mode feedback --images-dir images/deck/
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `New-Object: Cannot create COM object` | PowerPoint is not installed, or only the Store/web version is available. Install the desktop version. |
| Orphaned `POWERPNT.EXE` process | The script cleans up COM references in a `finally` block, but if it crashes hard, kill the process manually via Task Manager. |
| Images are blank or wrong size | Ensure the `.pptx` file is not corrupt. Try opening it in PowerPoint first. |
| Permission error on output dir | Run PowerShell as your normal user (not Admin) or check folder permissions. |
