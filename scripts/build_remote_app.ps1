param(
    [switch] $OneFile,
    [switch] $Clean,
    [switch] $SkipInstall,
    [switch] $RecreateVenv,
    [switch] $Lite
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $RepoRoot

if ($PSVersionTable.PSEdition -ne "Core" -or $PSVersionTable.PSVersion.Major -ne 7) {
    throw "ABORT(A0): build script requires PowerShell 7 Core. Run with pwsh."
}

$BuildVenv = Join-Path $RepoRoot ".venv_build"
if ($RecreateVenv -and (Test-Path -LiteralPath $BuildVenv)) {
    $resolvedBuildVenv = Resolve-Path -LiteralPath $BuildVenv
    if (-not $resolvedBuildVenv.Path.StartsWith($RepoRoot.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "ABORT(A11): refusing to remove build venv outside repo: $resolvedBuildVenv"
    }
    Write-Host "Removing build virtual environment: $BuildVenv"
    Remove-Item -LiteralPath $BuildVenv -Recurse -Force
}
$Python = Join-Path $BuildVenv "Scripts\python.exe"
$AppEntry = Join-Path $RepoRoot "run_windows_remote_app.py"
$AppName = if ($Lite) { "Deep-Live-Cam-Remote-Lite" } else { "Deep-Live-Cam-Remote" }
$IconPath = Join-Path $RepoRoot "windows_app\icon.ico"
$ThemePath = Join-Path $RepoRoot "windows_app\dark_theme.qss"

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "Creating build virtual environment: $BuildVenv"
    & py -3.11 -m venv $BuildVenv
    if ($LASTEXITCODE -ne 0) { throw "ABORT(A13): failed to create build venv ($LASTEXITCODE)" }
}

if (-not $SkipInstall) {
    Write-Host "Installing build requirements from requirements-build.txt"
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "ABORT(A13): pip upgrade failed ($LASTEXITCODE)" }
    & $Python -m pip install -r (Join-Path $RepoRoot "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "ABORT(A13): build requirements install failed ($LASTEXITCODE)" }
}

$modeArg = if ($OneFile) { "--onefile" } else { "--onedir" }
$cleanArgs = if ($Clean) { @("--clean") } else { @() }
$separator = ";"

$args = @(
    "-m", "PyInstaller",
    "--noconfirm",
    $modeArg,
    "--windowed",
    "--name", $AppName,
    "--distpath", (Join-Path $RepoRoot "dist"),
    "--workpath", (Join-Path $RepoRoot "build"),
    "--specpath", (Join-Path $RepoRoot "build"),
    "--add-data", "$ThemePath${separator}windows_app",
    "--add-data", "$IconPath${separator}windows_app",
    "--hidden-import", "PySide6.QtMultimedia",
    "--hidden-import", "PySide6.QtMultimediaWidgets",
    "--hidden-import", "websockets"
)

if ($Lite) {
    $args += @(
        "--exclude-module", "cv2",
        "--exclude-module", "numpy",
        "--exclude-module", "pyvirtualcam"
    )
} else {
    $args += @(
        "--hidden-import", "cv2",
        "--hidden-import", "numpy",
        "--hidden-import", "pyvirtualcam"
    )
}

if (Test-Path -LiteralPath $IconPath) {
    $args += @("--icon", $IconPath)
}

$args += $cleanArgs
$args += $AppEntry

if ($Lite) { Write-Host "Lite build: live webcam dependencies are excluded (cv2, numpy, pyvirtualcam)." }
Write-Host "Running PyInstaller ($modeArg) for $AppName"
& $Python @args
if ($LASTEXITCODE -ne 0) { throw "ABORT(A13): PyInstaller failed ($LASTEXITCODE)" }

Write-Host "Build output: $(Join-Path $RepoRoot 'dist')"

