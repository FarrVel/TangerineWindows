$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
$script = Join-Path $root "run_tangerine.pyw"
$ico = Join-Path $root "tangerine.ico"

# Buat file .ico dari logo prosedural
& (Join-Path $root ".venv\Scripts\python.exe") -c "import sys; sys.path.insert(0, r'$root'); from PySide6.QtWidgets import QApplication; app=QApplication([]); from tangerine.icons import logo_pixmap; logo_pixmap(256).save(r'$ico','ICO')" 2>$null

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs")
)
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Tangerine for Windows.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "`"$script`""
    $lnk.WorkingDirectory = $root
    $lnk.Description = "Konversi file instan offline (Drag + SHIFT)"
    if (Test-Path $ico) { $lnk.IconLocation = $ico }
    $lnk.Save()
}
Write-Host "  Shortcut dibuat di Desktop & Start Menu."
