@echo off
REM ============================================================
REM  Build script for CleanCPU
REM  Generates: dist\CleanCPU.exe
REM ============================================================

REM Always work from the directory where this .bat file lives
cd /d "%~dp0"

echo.
echo ============================================================
echo   CLEANCPU - Build Process
echo   Directory: %cd%
echo ============================================================
echo.

REM Step 1: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Download Python from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python found.

REM Step 2: Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

REM Step 3: Activate virtual environment
call venv\Scripts\activate.bat

REM Step 4: Install dependencies
echo [INFO] Installing dependencies...
pip install -r requirements-build.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

REM Step 5: Clean previous build
if exist "build" (
    echo [INFO] Cleaning previous build...
    rmdir /s /q build
)
if exist "dist" (
    rmdir /s /q dist
)

REM Step 6: Build the executable
echo.
echo [INFO] Building executable... (this takes 1-3 minutes)
echo.
pyinstaller mantenimiento_windows.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check the errors above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD SUCCESSFUL
echo ============================================================
echo.
echo   Output: dist\CleanCPU.exe
echo.
echo   To deploy:
echo   1. Copy dist\CleanCPU.exe to the target machine
echo   2. Run as Administrator (double-click, accept UAC)
echo   3. Browser opens automatically
echo.
echo ============================================================

REM Show file size
for %%I in (dist\CleanCPU.exe) do echo   Size: %%~zI bytes

echo.
pause
