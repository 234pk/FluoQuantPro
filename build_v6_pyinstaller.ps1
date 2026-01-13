# FluoQuant Pro 1.1 Build Script (PyInstaller)

$VERSION = "1.1.0.0"
$ICON = "resources\icon.ico"
$APP_NAME = "FluoQuantPro"

Write-Host "--- Starting FluoQuant Pro $VERSION Build Process (PyInstaller) ---" -ForegroundColor Cyan

# 1. Clean previous builds
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# 2. Execute PyInstaller Build
& 'C:\Users\16500\AppData\Local\Programs\Python\Python312\python.exe' -m PyInstaller `
    --onefile `
    --windowed `
    --icon=$ICON `
    --name=$APP_NAME `
    --add-data "src/resources;src/resources" `
    --collect-all matplotlib `
    --noconfirm `
    main.py

Write-Host "--- Build Complete! Output available in dist/ ---" -ForegroundColor Green
