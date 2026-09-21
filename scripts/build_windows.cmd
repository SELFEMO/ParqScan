@echo off
setlocal

cd /d "%~dp0\.."

call conda activate py312
if errorlevel 1 (
    echo Failed to activate conda env py312.
    exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

python build.py --installer --skip-smoke-test
exit /b %errorlevel%
