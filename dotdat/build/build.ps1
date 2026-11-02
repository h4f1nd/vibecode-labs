# Build a standalone Windows bundle with Nuitka.
#
#   .\build\build.ps1                 # standalone folder + dotdat.exe
#   .\build\build.ps1 -OneFile        # single .exe (slower cold start)
#   .\build\build.ps1 -SkipInstall    # tooling already present
#
# Output: build\nuitka\dotdat.dist\dotdat.exe
#
# The exe uses the console subsystem so shells wait for CLI commands, pipes work
# and exit codes are reliable. build/launcher.py hides the console window for
# GUI-only launches from Explorer, where it is the sole console client.

param(
    [switch]$OneFile,
    [string]$Python = ".venv\Scripts\python.exe",
    [switch]$SkipInstall,
    [ValidateSet("attach", "force", "disable", "hide")]
    [string]$ConsoleMode = "force"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path $Python)) {
    throw "Python not found at $Python. Create the venv first (see README)."
}

# Windows PowerShell 5.1 turns any stderr line from a native command into a
# terminating error while $ErrorActionPreference is "Stop" - and both pip and uv
# write progress to stderr. Run them with the preference relaxed and judge
# success by the exit code instead.
function Invoke-Native {
    param(
        [string]$Exe,
        [string[]]$Arguments,
        [switch]$AllowFail
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Exe @Arguments | Out-Host
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0 -and -not $AllowFail) {
        throw "$Exe $($Arguments -join ' ') failed with exit code $code"
    }
    return $code
}

if (-not $SkipInstall) {
    Write-Host "==> installing build tooling" -ForegroundColor Cyan
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        # `uv venv` creates a venv without pip; uv can install into it anyway.
        Invoke-Native "uv" @("pip", "install", "--python", $Python, "--quiet", "nuitka", "ordered-set", "zstandard")
    }
    else {
        Invoke-Native $Python @("-m", "ensurepip", "--upgrade") -AllowFail | Out-Null
        Invoke-Native $Python @("-m", "pip", "install", "--quiet", "--upgrade", "nuitka", "ordered-set", "zstandard")
    }
}

$mode = if ($OneFile) { "--mode=onefile" } else { "--mode=standalone" }

# Nuitka 4.x has a built-in pywebview plugin: it pulls in webview, pythonnet,
# clr_loader and the WebView2 loader itself. Listing those packages explicitly
# conflicts with the plugin, so only our own package and its web assets are
# declared here.
$arguments = @(
    "-m", "nuitka",
    $mode,
    "--windows-console-mode=$ConsoleMode",
    "--include-package=dotdat",
    "--include-data-dir=src/dotdat/ui/web=dotdat/ui/web",
    "--assume-yes-for-downloads",
    "--output-dir=build/nuitka",
    "--output-folder-name=dotdat.dist",
    "--output-filename=dotdat.exe",
    "--company-name=dotdat",
    "--product-name=DOTDAT",
    "--file-version=0.1.0.0",
    "--product-version=0.1.0",
    "--nofollow-import-to=pytest,tests,benchmarks,ruff,mypy",
    "build/launcher.py"
)

Write-Host "==> nuitka $mode (console: $ConsoleMode)" -ForegroundColor Cyan
Invoke-Native $Python $arguments

Write-Host ""
Write-Host "Done. Bundle in build\nuitka\dotdat.dist" -ForegroundColor Green
Write-Host "Double-click dotdat.exe for the GUI, or run: dotdat.exe info <file.dat>"
