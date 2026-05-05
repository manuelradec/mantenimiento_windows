---
name: build-exe
description: Compila CleanCPU a cleancpu.exe con PyInstaller, verifica que el binario exista y reporta tamaño. Si la compilación falla revisa hiddenimports en cleancpu.spec antes de tocar cualquier otra cosa.
---

# Build CleanCPU executable

Sigue estos pasos en orden y reporta cada uno al usuario:

1. **Compilar**: ejecuta `pyinstaller cleancpu.spec --clean --noconfirm`. Si el comando dura más de 2 minutos, mantenlo en foreground para ver errores.

2. **Verificar binario**: confirma que `dist/cleancpu.exe` exista. Si no existe, busca el último error de PyInstaller en stderr — típicamente `ModuleNotFoundError` que apunta a un `hiddenimports` faltante en `cleancpu.spec`.

3. **Reportar tamaño**: usa `Get-Item dist/cleancpu.exe | Select-Object Length` (PowerShell) o `ls -la dist/cleancpu.exe` (bash) y reporta el tamaño en MB.

4. **Si falla**:
   - **NO** modifiques nada del código de la app.
   - Lee `cleancpu.spec` y revisa el array `hiddenimports`.
   - Si el error apunta a un módulo que está en `requirements.txt` pero no en `hiddenimports`, propón añadirlo y espera confirmación del usuario antes de editar.
   - Si el error es un import circular o template/static faltante, revisa `datas` en el spec.

5. **Salida esperada**: una línea final con tamaño + ruta absoluta del binario, p.ej. `dist/cleancpu.exe — 38.2 MB`.

**No hacer**:
- No commitear `dist/` ni `build/` (están en .gitignore por design).
- No correr el .exe contra `C:\ProgramData\CleanCPU\` (es la instalación de producción).
