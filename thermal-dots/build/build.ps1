# Build a standalone Windows bundle with Nuitka.
#
#   .\build\build.ps1                 # standalone folder + tdots.exe
#   .\build\build.ps1 -OneFile        # single .exe (slower cold start)
#   .\build\build.ps1 -SkipInstall    # tooling already present
#
# Output: build\nuitka\tdots.dist\tdots.exe  (matches build\installer.iss)
#
# Console mode "attach": launched from a terminal the exe shares that console
# (so the CLI prints normally), launched from Explorer it opens no console at
# all (so the GUI is clean).

param(
    [switch]$OneFile,
    [string]$Python = ".venv\Scripts\python.exe",
    [switch]$SkipInstall,
    [ValidateSet("attach", "force", "disable", "hide")]
    [string]$ConsoleMode = "attach"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path $Python)) {
    throw "Python not found at $Python. Create the venv first (see README)."
}

# Windows PowerShell 5.1 turns any stderr line from a native command into a
# terminating error while $ErrorActionPreference is "Stop" - and both pip and
# uv write progress to stderr. Run them with the preference relaxed and judge
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
# clr_loader and the WebView2 loader itself.  Listing those packages explicitly
# *conflicts* with the plugin, so only our own package and its web assets are
# declared here.
#
# The entry script is build/launcher.py, not src/thermaldots/__main__.py:
# Nuitka treats the entry script as a top-level module, so a relative import
# ("from .cli import main") raises ImportError at start-up.  The launcher uses
# an absolute import - same as the "tdots" console script.
$arguments = @(
    "-m", "nuitka",
    $mode,
    "--windows-console-mode=$ConsoleMode",
    "--include-package=thermaldots",
    "--include-data-dir=src/thermaldots/ui/web=thermaldots/ui/web",
    "--assume-yes-for-downloads",
    "--output-dir=build/nuitka",
    "--output-folder-name=tdots.dist",
    "--output-filename=tdots.exe",
    "--company-name=thermal-dots",
    "--product-name=THERMAL//DOTS",
    "--file-version=1.0.0.0",
    "--product-version=1.0.0",
    "--nofollow-import-to=pytest,benchmarks,ruff,mypy",
    "build/launcher.py"
)

Write-Host "==> nuitka $mode (console: $ConsoleMode)" -ForegroundColor Cyan
Invoke-Native $Python $arguments

Write-Host ""
Write-Host "Done. Bundle in build\nuitka\" -ForegroundColor Green
Write-Host "Next: compile build\installer.iss with Inno Setup (optional)."
