@echo off
REM ============================================================
REM  Build script for Mantenimiento Windows
REM  Generates: dist\MantenimientoWindows.exe
REM ============================================================

echo.
echo ============================================================
echo   MANTENIMIENTO WINDOWS - Build Process
echo ============================================================
echo.

REM Step 1: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en PATH.
    echo Descarga Python desde https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python encontrado.

REM Step 2: Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [INFO] Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado.
) else (
    echo [OK] Entorno virtual ya existe.
)

REM Step 3: Activate virtual environment
call venv\Scripts\activate.bat

REM Step 4: Install dependencies
echo [INFO] Instalando dependencias...
pip install flask psutil pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] Fallo al instalar dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.

REM Step 5: Clean previous build
if exist "build" (
    echo [INFO] Limpiando build anterior...
    rmdir /s /q build
)
if exist "dist" (
    rmdir /s /q dist
)

REM Step 6: Build the executable
echo.
echo [INFO] Construyendo el ejecutable... (esto tarda 1-3 minutos)
echo.
pyinstaller mantenimiento_windows.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] La construccion fallo. Revisa los errores arriba.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD EXITOSO
echo ============================================================
echo.
echo   Archivo generado: dist\MantenimientoWindows.exe
echo.
echo   Para distribuir:
echo   1. Copia dist\MantenimientoWindows.exe al equipo destino
echo   2. Ejecuta como administrador (doble clic, acepta UAC)
echo   3. El navegador se abre automaticamente
echo.
echo ============================================================

REM Show file size
for %%I in (dist\MantenimientoWindows.exe) do echo   Tamano: %%~zI bytes (~%%~zI bytes)

echo.
pause
