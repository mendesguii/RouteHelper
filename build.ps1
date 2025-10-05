# Build script for RouteHelper on Windows (PowerShell)
# Usage examples:
#   pwsh ./build.ps1                 # Build Tk GUI (default) as onefile exe
#   pwsh ./build.ps1 -Target kivy    # Build Kivy GUI (experimental)
#   pwsh ./build.ps1 -Target cli     # Build CLI executable
#   pwsh ./build.ps1 -Clean          # Clean previous build artifacts and build
#
# Output binaries are placed under ./dist

param(
    [ValidateSet('tk','cli')]
    [string]$Target = 'tk',
    [switch]$Clean,
    [switch]$OneDir  # If set, produce a folder (onedir) instead of a single exe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Move to repo root (script location)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Resolve Python
$pythonCmd = 'python'
try {
    $null = & $pythonCmd --version
} catch {
    Write-Host 'python not found on PATH. Please install Python 3.10+ and ensure "python" is available.' -ForegroundColor Red
    exit 1
}

# Create/Use venv
$venvPython = Join-Path $ScriptDir '.venv/Scripts/python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host 'Creating virtual environment (.venv)...' -ForegroundColor Cyan
    & $pythonCmd -m venv .venv
}

# Upgrade pip and install deps
Write-Host 'Installing dependencies...' -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip wheel
& $venvPython -m pip install -r requirements.txt
& $venvPython -m pip install pyinstaller

<# Kivy no longer used #>

# Clean previous builds if requested
if ($Clean) {
    Write-Host 'Cleaning previous build artifacts...' -ForegroundColor Cyan
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
    Get-ChildItem -Filter '*.spec' | Remove-Item -Force -ErrorAction SilentlyContinue
}

# Choose entry point and flags
switch ($Target) {
    'tk'   { $entry = 'gui.py';  $name = 'RouteHelper';     $noConsole = '--noconsole' }
    'cli'  { $entry = 'main.py'; $name = 'routehelper-cli'; $noConsole = $null }
}

if (-not (Test-Path $entry)) {
    Write-Host "Entry script '$entry' not found. Aborting." -ForegroundColor Red
    exit 1
}

# Build args
$mode = if ($OneDir) { '--onedir' } else { '--onefile' }

# Ensure flights folder exists at runtime (created by app too, but we can include empty dir in dist on onedir)
if ($OneDir -and -not (Test-Path 'flights')) { New-Item -ItemType Directory -Path 'flights' | Out-Null }

$pyiArgs = @(
    'PyInstaller',
    '--noconfirm',
    $noConsole,
    $mode,
    '--name', $name,
    $entry
) | Where-Object { $_ -ne $null -and $_ -ne '' }

Write-Host "Building $Target -> $name..." -ForegroundColor Green
& $venvPython -m @pyiArgs

Write-Host "Done. Check the 'dist' folder for output." -ForegroundColor Green
