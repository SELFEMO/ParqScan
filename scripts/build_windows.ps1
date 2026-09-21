$ErrorActionPreference = "Stop"

function Test-CondaPython {
    param([Parameter(Mandatory = $true)][string]$PythonExe)
    if (-not (Test-Path $PythonExe)) {
        return $true
    }
    & $PythonExe -c @"
import sys
from pathlib import Path

prefix = Path(sys.prefix)
executable = Path(sys.executable).as_posix().casefold()
is_conda = (prefix / 'conda-meta').exists() or 'conda' in executable or 'anaconda' in executable
raise SystemExit(1 if is_conda else 0)
"@ | Out-Null
    return $LASTEXITCODE -ne 0
}

function Test-VenvUsesConda {
    param([Parameter(Mandatory = $true)][string]$VenvPath)
    $cfg = Join-Path $VenvPath "pyvenv.cfg"
    if (Test-Path $cfg) {
        $content = Get-Content $cfg -Raw
        if ($content -match "(?i)anaconda|conda") {
            return $true
        }
    }
    return Test-Path (Join-Path $VenvPath "conda-meta")
}

function Resolve-BuildPython {
    $candidates = @()
    if ($env:PARQSCAN_BUILD_PYTHON) {
        $candidates += $env:PARQSCAN_BUILD_PYTHON
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @("3.12", "3.11", "3.10")) {
            $resolved = & py "-$version" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved) {
                $candidates += $resolved.Trim()
            }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += (Get-Command python).Source
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path $candidate)) {
            continue
        }
        if (-not (Test-CondaPython $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw @"
No non-Conda Python was found for release builds.

Install python.org Python 3.12, then rerun this script:
  winget install --id Python.Python.3.12 -e

Or set PARQSCAN_BUILD_PYTHON to the full path of python.exe.
"@
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$basePython = Resolve-BuildPython
$venvPath = Join-Path $root ".build-venv"
$python = Join-Path $venvPath "Scripts\python.exe"

if ((Test-Path $venvPath) -and (Test-VenvUsesConda $venvPath)) {
    Write-Host "Removing Conda-based .build-venv so it can be recreated with python.org Python."
    Remove-Item $venvPath -Recurse -Force
}

if (-not (Test-Path $python)) {
    & $basePython -m venv $venvPath
}

if (Test-CondaPython $python) {
    throw "The .build-venv was created from Conda Python. Delete .build-venv and install python.org Python 3.12."
}

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt pyinstaller
$env:PARQSCAN_STRICT_BUILD = "1"
& $python build.py --installer --skip-smoke-test
