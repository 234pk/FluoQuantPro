
$source_root = "F:\ubuntu\IF_analyzer\FluoQuantPro"
$dest_dirs = @(
    "F:\ubuntu\IF_analyzer\FluoQuantPro\macversion",
    "F:\ubuntu\IF_analyzer\FluoQuantPro\FluoQuantPro_Mac_Version"
)

$files_to_sync = @(
    "src\core\roi_model.py",
    "src\core\data_model.py",
    "src\core\project_model.py",
    "src\core\analysis.py",
    "src\gui\canvas_view.py",
    "src\gui\filmstrip_view.py",
    "src\gui\tools.py",
    "src\core\performance_monitor.py",
    "src\core\cache_manager.py",
    "main.py"
)

foreach ($dest_root in $dest_dirs) {
    if (-not (Test-Path $dest_root)) {
        Write-Host "Skipping non-existent directory: $dest_root"
        continue
    }
    
    Write-Host "Syncing to $dest_root..."
    
    foreach ($file in $files_to_sync) {
        $src = Join-Path $source_root $file
        $dest = Join-Path $dest_root $file
        
        # Create directory if it doesn't exist
        $dest_dir = Split-Path $dest -Parent
        if (-not (Test-Path $dest_dir)) {
            New-Item -ItemType Directory -Path $dest_dir -Force | Out-Null
        }

        if (Test-Path $src) {
            Write-Host "  Copying $file"
            Copy-Item -Path $src -Destination $dest -Force
        } else {
            Write-Host "  Warning: Source file $src not found"
        }
    }
}
