param(
    [string]$PythonExe = "py",
    [string]$ExeName = "SimpleMapperRuntime"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EntryPoint = Join-Path $ProjectRoot "PyGUI\main.py"
$BuildDir = Join-Path $ProjectRoot "build"
$DistDir = $ProjectRoot
$SpecPath = Join-Path $ProjectRoot "$ExeName.spec"

Write-Host "Project root: $ProjectRoot"
Write-Host "Entry point : $EntryPoint"

if (-not (Test-Path $EntryPoint)) {
    throw "Entry point not found: $EntryPoint"
}

if (Test-Path $BuildDir) {
    Remove-Item -LiteralPath $BuildDir -Recurse -Force
}

$ExePath = Join-Path $ProjectRoot "$ExeName.exe"
if (Test-Path $ExePath) {
    try {
        Remove-Item -LiteralPath $ExePath -Force
    }
    catch {
        throw "Close $ExeName.exe before rebuilding."
    }
}

& $PythonExe -3 -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $ExeName `
    --distpath $DistDir `
    --workpath $BuildDir `
    --specpath $ProjectRoot `
    --paths $ProjectRoot `
    --paths (Join-Path $ProjectRoot "PyGUI") `
    $EntryPoint

if (Test-Path $BuildDir) {
    Remove-Item -LiteralPath $BuildDir -Recurse -Force
}

if (Test-Path $SpecPath) {
    Remove-Item -LiteralPath $SpecPath -Force
}

Write-Host ""
Write-Host "Build complete: $ExePath"
