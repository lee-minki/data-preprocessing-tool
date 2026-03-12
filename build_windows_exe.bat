@echo off
setlocal

cd /d %~dp0

if not exist .venv\Scripts\python.exe (
    echo [ERROR] .venv\Scripts\python.exe not found
    echo Create the virtual environment first.
    exit /b 1
)

echo [1/3] Installing build dependencies...
.venv\Scripts\python.exe -m pip install -r build_requirements.txt
if errorlevel 1 exit /b 1

echo [2/3] Building Windows EXE...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DataPreprocessor_windows.spec
if errorlevel 1 exit /b 1

echo [3/3] Build complete.
echo Output: dist\DataPreprocessor_v1.7.0.exe
endlocal
