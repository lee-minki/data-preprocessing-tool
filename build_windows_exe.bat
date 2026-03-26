@echo off
setlocal

cd /d %~dp0

for /f %%i in ('powershell -NoProfile -Command "(Select-String -Path version.py -Pattern '__version__\s*=\s*\"([^\"]+)\"').Matches[0].Groups[1].Value"') do set VERSION=%%i

if "%VERSION%"=="" (
    echo [ERROR] Failed to read version from version.py
    exit /b 1
)

if not exist .venv\Scripts\python.exe (
    echo [ERROR] .venv\Scripts\python.exe not found
    echo Create the virtual environment first.
    exit /b 1
)

echo [1/4] Installing runtime dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [2/4] Installing build dependencies...
.venv\Scripts\python.exe -m pip install -r build_requirements.txt
if errorlevel 1 exit /b 1

echo [3/4] Building Windows EXE...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DataPreprocessor_windows.spec
if errorlevel 1 exit /b 1

echo [4/4] Build complete.
echo Output: dist\DataPreprocessor_v%VERSION%.exe
endlocal
