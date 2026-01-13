# FluoQuant Pro 1.1 Build Script (Nuitka)

$VERSION = "3.0"
$ICON = "resources\icon.ico"
$APP_NAME = "FluoQuantPro"

Write-Host "--- Starting FluoQuant Pro $VERSION Build Process ---" -ForegroundColor Cyan

# 1. Clean previous builds
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "$APP_NAME.build") { Remove-Item -Recurse -Force "$APP_NAME.build" }
if (Test-Path "$APP_NAME.dist") { Remove-Item -Recurse -Force "$APP_NAME.dist" }
if (Test-Path "$APP_NAME.onefile-build") { Remove-Item -Recurse -Force "$APP_NAME.onefile-build" }

# 2. Execute Nuitka Build
# Increase recursion limit to prevent Nuitka crash on complex modules
& 'C:\Users\16500\AppData\Local\Programs\Python\Python312\python.exe' -X recursionlimit=5000 -m nuitka `
    --standalone `
    --onefile `
    --mingw64 `
    --enable-plugin=pyside6 `
    --include-package=imagecodecs `
    --no-deployment-flag=self-execution `
    --include-package=tifffile `
    --include-package-data=matplotlib `
    --include-data-dir=src/resources=src/resources `
    --windows-icon-from-ico=$ICON `
    --windows-console-mode=disable `
    --file-version=$VERSION `
    --product-version=$VERSION `
    --company-name="FluoQuant" `
    --product-name="FluoQuant Pro" `
    --file-description="Advanced Fluorescence Image Analysis Pro" `
    --copyright="Copyright 2026 FluoQuant" `
    --output-dir=dist `
    --lto=no `
    --assume-yes-for-downloads `
    --clean-cache=all `
    main.py

Write-Host "--- Build Complete! Output available in dist/ ---" -ForegroundColor Green
