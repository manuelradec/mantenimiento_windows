# RADEC Maintenance Program — Pruebas Técnicas
## Documento: PT-TEC-001 | Versión: 1.0.0 | Fecha: 2026-04-04

---

## CONTROL DE VERSIONES

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2026-04-04 | Área TI RADEC | Versión inicial para piloto |

---

## ALCANCE

Este documento cubre las pruebas técnicas del Programa de Mantenimiento RADEC orientadas a verificar la integridad interna del sistema:

- Smoke tests del ejecutable
- Comportamiento del motor de ejecución de comandos (command_runner)
- Validación de la lista de comandos permitidos (allowlist)
- Manejo de privilegios y timeouts
- Integridad del empaquetado PyInstaller
- Seguridad del manejo de claves de producto
- Estabilidad del modelo polling / ejecución en segundo plano
- Generación e integridad de logs

---

## PRUEBAS DE SMOKE (ARRANQUE Y ESTABILIDAD BÁSICA)

---

### PT-TEC-001 — Smoke test: arranque del EXE empaquetado

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-001 |
| **Categoría** | Smoke / EXE packaging |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que el ejecutable `CleanCPU.exe` generado por PyInstaller arranca correctamente, inicia Waitress, y responde peticiones HTTP. |

**Precondiciones:**
- `CleanCPU.exe` construido desde `pyinstaller mantenimiento_windows.spec`.
- Puerto 5000 libre.

**Pasos:**
1. Ejecutar `CleanCPU.exe` como Administrador.
2. Esperar 20 segundos.
3. Abrir `http://127.0.0.1:5000` en el navegador.
4. Verificar que el panel principal responde.
5. Hacer GET a `http://127.0.0.1:5000/api/elevation`.

**Resultado esperado:**
- El servidor responde con HTTP 200 en todas las rutas base.
- `/api/elevation` retorna JSON con campo `is_admin`.
- La interfaz del panel principal se carga sin errores 404 en recursos estáticos (CSS, JS).

**Evidencia requerida:**
- Captura de pantalla del panel principal cargado.
- Captura de la respuesta de `/api/elevation`.

---

### PT-TEC-002 — Smoke test: módulos críticos importan sin error

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-002 |
| **Categoría** | Smoke / EXE packaging |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que todos los módulos de servicio y rutas definidos en `hiddenimports` del spec de PyInstaller están disponibles en el EXE empaquetado. |

**Pasos:**
1. Con la aplicación corriendo, hacer GET a las rutas de cada Blueprint:
   - `/maintenance/` → Mantenimiento Lógico
   - `/office/` → Licencia Office
   - `/diagnostics/` → Diagnósticos (Inventario)
   - `/reports/` → Reportes
   - `/network/` → Red
   - `/update/` → Actualizaciones

**Resultado esperado:**
- Todas las rutas responden HTTP 200.
- No se producen ImportError ni ModuleNotFoundError en ninguna ruta.

---

### PT-TEC-003 — Recursos estáticos y templates disponibles

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-003 |
| **Categoría** | Smoke / EXE packaging |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que los archivos de templates, CSS y JS se empaquetan correctamente y son accesibles desde el EXE. |

**Pasos:**
1. Abrir la interfaz de Mantenimiento Lógico: `http://127.0.0.1:5000/maintenance/`.
2. Abrir herramientas de desarrollo del navegador (F12) → pestaña Network.
3. Recargar la página y verificar que no hay recursos con código de error (404 o 500).

**Resultado esperado:**
- Todos los recursos (CSS, JS, fuentes) cargan con HTTP 200.
- No hay recursos de 404 en la consola de red del navegador.

---

## PRUEBAS DEL MOTOR DE COMANDOS (COMMAND_RUNNER)

---

### PT-TEC-010 — Validación de la allowlist: comando permitido

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-010 |
| **Categoría** | Command runner / Allowlist |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que un comando explícitamente permitido en `ALLOWED_COMMANDS` se ejecuta correctamente. |

**Caso de prueba:**
- Comando: `ipconfig /flushdns`
- Entrada al motor: `run_cmd(['ipconfig', '/flushdns'], description='Flush DNS')`

**Resultado esperado:**
- El comando se ejecuta sin error de allowlist.
- `CommandResult.status` es `SUCCESS` o `ERROR` (nunca "blocked_by_allowlist").

---

### PT-TEC-011 — Validación de la allowlist: comando bloqueado

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-011 |
| **Categoría** | Command runner / Allowlist |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que un comando no presente en `ALLOWED_COMMANDS` es bloqueado antes de ejecutarse. |

**Casos de prueba:**

| Caso | Comando intentado | Comportamiento esperado |
|------|------------------|-----------------------|
| A | `cmd /c del /f /s C:\Windows\*` | Bloqueado (cmd no está en allowlist) |
| B | `format C:` | Bloqueado (format no está en allowlist) |
| C | `reg delete HKLM\Software\...` | Bloqueado (reg no está en allowlist) |
| D | `sfc /deleteallfiles` | Bloqueado (`/deleteallfiles` no es subcomando permitido de sfc) |
| E | `defrag C: /x` | Bloqueado (`/x` está en `denied_args` de defrag) |
| F | `pnputil /delete-driver oem1.inf` | Bloqueado (`/delete-driver` está en `denied_args` de pnputil) |

**Resultado esperado (todos los casos):**
- El comando no se ejecuta en el sistema operativo.
- `CommandResult.status` es `ERROR` con mensaje indicando bloqueo por allowlist.
- No hay efecto colateral en el sistema.

---

### PT-TEC-012 — Validación de patrones ospp.vbs en allowlist (cscript)

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-012 |
| **Categoría** | Command runner / Allowlist |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que los tres patrones de allowlist para cscript/ospp.vbs permiten exactamente las operaciones correctas y bloquean variantes no autorizadas. |

**Patrones definidos:**
```python
r'^//nologo\s+.*\\ospp\.vbs\s+/(?:dstatus|act)$'
r'^//nologo\s+.*\\ospp\.vbs\s+/inpkey:[a-z0-9]{5}-[a-z0-9]{5}-[a-z0-9]{5}-[a-z0-9]{5}-[a-z0-9]{5}$'
```

**Casos de prueba:**

| Caso | Argumentos de cscript | Debe: Pasar / Bloquear |
|------|----------------------|----------------------|
| A | `//nologo C:\...\ospp.vbs /dstatus` | **Pasar** |
| B | `//nologo C:\...\ospp.vbs /act` | **Pasar** |
| C | `//nologo C:\...\ospp.vbs /inpkey:AAAAA-BBBBB-CCCCC-DDDDD-EEEEE` | **Pasar** |
| D | `//nologo C:\...\ospp.vbs /rearm` | **Bloquear** (`/rearm` no es dstatus ni act) |
| E | `//nologo C:\...\ospp.vbs /inpkey:AAAAA-BBBBB-CCCCC` | **Bloquear** (clave incompleta) |
| F | `//nologo C:\...\ospp.vbs /dstatus && del C:\Windows\*` | **Bloquear** (inyección de comando) |
| G | `//nologo C:\...\slmgr.vbs /xpr` | **Pasar** (slmgr.vbs tiene patrón separado) |

**Método de prueba:**
- Prueba unitaria sobre la función de validación de allowlist en `command_runner.py`.
- Verificar que `re.match(pattern, args_str, re.IGNORECASE)` produce el resultado esperado para cada caso.

---

### PT-TEC-013 — Manejo de timeout de comando

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-013 |
| **Categoría** | Command runner / Timeouts |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que el motor de comandos respeta el timeout configurado y retorna el estado TIMEOUT correctamente cuando un proceso excede el límite. |

**Método:**
- Invocar `run_cmd(['timeout', '/t', '120'], timeout=3, description='Test timeout')` donde el proceso tarda más que el timeout.

**Resultado esperado:**
- El proceso es terminado antes de los 120 segundos.
- `CommandResult.status` es `CommandStatus.TIMEOUT`.
- `CommandResult.is_error` es `True` (TIMEOUT está en `is_error`).

---

### PT-TEC-014 — REQUIRES_ADMIN no está incluido en is_error

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-014 |
| **Categoría** | Command runner / Lógica interna |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que `CommandStatus.REQUIRES_ADMIN` no es evaluado como `is_error=True`, ya que es un estado esperado y manejado explícitamente. |

**Método:**
- Simular una respuesta `CommandStatus.REQUIRES_ADMIN` (ejecutar operación admin sin elevación).
- Verificar: `result.is_error` == `False`.
- Verificar: `result.status == CommandStatus.REQUIRES_ADMIN` == `True`.

**Resultado esperado:**
- `is_error` es `False` para `REQUIRES_ADMIN`.
- `is_error` es `True` solo para `ERROR` y `TIMEOUT`.

**Justificación:**
- Si `REQUIRES_ADMIN` fuera `is_error`, los pasos de mantenimiento reportarían "falló" en lugar de "omitido" cuando la aplicación no está elevada. Esto produciría reportes con falsos negativos.

---

### PT-TEC-015 — Redacción de datos sensibles en logs

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-015 |
| **Categoría** | Command runner / Seguridad de logs |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que datos sensibles (claves de producto, contraseñas) no aparecen en el log de la aplicación. |

**Pasos:**
1. Ejecutar la activación de Office con una clave de prueba conocida (CPF-OFC-004).
2. Abrir `C:\ProgramData\CleanCPU\logs\app.log` después de la operación.
3. Buscar la clave completa en el archivo de log.

**Resultado esperado:**
- La clave completa NO aparece en ninguna línea del log.
- Las entradas de log relacionadas con `ospp.vbs /inpkey` muestran `***` o equivalente en lugar de la clave.

---

### PT-TEC-016 — Ejecución sin shell=True para comandos en lista

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-016 |
| **Categoría** | Command runner / Seguridad |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que los comandos pasados como lista (no como string) se ejecutan sin `shell=True`. |

**Método:**
- Verificar en el código fuente de `command_runner.py` que cuando el argumento `cmd` es una lista, `subprocess.run` se invoca con `shell=False` (o sin parámetro `shell`).
- Verificar que solo comandos en `SHELL_REQUIRED_COMMANDS` (`start`) pueden usar `shell=True`.

**Resultado esperado:**
- `shell=True` solo se usa cuando el comando es un string y pasa la validación de allowlist, o cuando el comando base está en `SHELL_REQUIRED_COMMANDS`.
- Los comandos de lista nunca usan `shell=True`.

---

### PT-TEC-017 — Inyección de comandos en argumentos bloqueada

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-017 |
| **Categoría** | Command runner / Seguridad |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que los patrones de inyección de comandos (`DANGEROUS_PATTERNS`) bloquean argumentos maliciosos. |

**Casos de prueba (argumentos que deben ser bloqueados):**

| Caso | Argumento malicioso | Patrón que debe detectar |
|------|--------------------|-----------------------|
| A | `sfc /scannow & del /f C:\Windows` | `&` separador de comando |
| B | `sfc /scannow; ipconfig` | `;` separador de comando |
| C | `sfc /scannow \| taskkill /F /IM explorer.exe` | `|` pipe |
| D | `sfc $(calc)` | Shell expansion `$()` |
| E | `sfc /scannow\n<comando_inyectado>` | Salto de línea |

**Resultado esperado:**
- Todos los casos son bloqueados por `DANGEROUS_PATTERNS` antes de ejecutarse.
- El `CommandResult` retorna error de validación.

---

### PT-TEC-018 — Rotación de logs

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-018 |
| **Categoría** | Logging |
| **Prioridad** | Baja |
| **Objetivo** | Verificar que el sistema de rotación de logs funciona correctamente (10 MB por archivo, 5 respaldos máximos). |

**Método:**
- Verificar la configuración del `RotatingFileHandler` en `app.py`: `maxBytes=10*1024*1024`, `backupCount=5`.
- Verificar en producción (después de múltiples sesiones de mantenimiento) que se generan respaldos `app.log.1`, `app.log.2`, etc.

**Resultado esperado:**
- El archivo `app.log` no supera 10 MB antes de rotar.
- Existen como máximo 5 archivos de respaldo.
- Los logs más antiguos se eliminan automáticamente al superar el límite.

---

## PRUEBAS DE INTEGRIDAD DEL EMPAQUETADO

---

### PT-TEC-020 — Templates y datos empaquetados accesibles

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-020 |
| **Categoría** | PyInstaller / Empaquetado |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que `sys._MEIPASS` resuelve correctamente las rutas de templates, static y templates_data en el EXE empaquetado. |

**Método:**
- Ejecutar el EXE en una máquina donde no existe el directorio fuente del proyecto (simula la ejecución real en equipos de técnicos).
- Verificar que las páginas HTML renderizan correctamente (implica que Jinja2 encontró los templates).
- Verificar que los archivos CSS/JS cargan (implica que la carpeta `static` está empaquetada).
- Intentar generar un reporte Excel (implica que `templates_data` con la plantilla Excel está empaquetada).

**Resultado esperado:**
- Todas las páginas renderizan sin error de template.
- Los recursos estáticos cargan correctamente.
- La generación de reporte Excel no falla por plantilla no encontrada.

---

### PT-TEC-021 — UAC elevation solicitada automáticamente

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-021 |
| **Categoría** | PyInstaller / UAC |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que Windows solicita automáticamente elevación UAC al ejecutar `CleanCPU.exe` por doble clic, sin que el técnico necesite "Ejecutar como administrador" explícitamente. |

**Método:**
- Ejecutar `CleanCPU.exe` con doble clic desde el Explorador de Windows (sin clic derecho → Ejecutar como administrador).
- Observar si Windows presenta el cuadro UAC de solicitud de elevación.

**Resultado esperado:**
- Windows presenta cuadro UAC automáticamente (confirma que `uac_admin=True` está activo en el EXE).
- Al confirmar UAC, la aplicación inicia con privilegios de Administrador.

**Nota:**
- Si el UAC está deshabilitado en el equipo (nivel 0), el EXE se ejecuta directamente como Administrador sin el cuadro. Esto es comportamiento esperado.

---

### PT-TEC-022 — Ejecución en Windows 10 y Windows 11

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-022 |
| **Categoría** | Compatibilidad |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que el EXE funciona correctamente tanto en Windows 10 (versión 1903+) como en Windows 11. |

**Pasos:**
1. Ejecutar PT-TEC-001, PT-TEC-002 y PT-TEC-003 en Windows 10.
2. Repetir en Windows 11.
3. Comparar resultados.

**Resultado esperado:**
- El EXE arranca y opera correctamente en ambas versiones.
- No hay errores de compatibilidad de API de Windows.

**Estado:** Pendiente de validación en piloto.

---

## PRUEBAS DEL MODELO DE POLLING

---

### PT-TEC-030 — Polling continúa en errores de red transitorios

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-030 |
| **Categoría** | Polling / Estabilidad |
| **Prioridad** | Media |
| **Objetivo** | Verificar que el cliente de polling no detiene el ciclo de actualización si hay un error de red puntual durante una petición de estado. |

**Método:**
- Iniciar mantenimiento.
- Simular un error de red transitorio (cerrar y abrir DevTools → Network → "offline" momentáneo en el navegador).
- Verificar que el polling se recupera automáticamente.

**Resultado esperado:**
- La interfaz puede mostrar brevemente un estado desactualizado.
- El polling se reanuda en el siguiente ciclo de 2 segundos.
- La ejecución en segundo plano no se ve afectada.
- No hay mensajes de error no manejados en la consola del navegador.

---

### PT-TEC-031 — Polling se detiene al completar la sesión

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-031 |
| **Categoría** | Polling / Estabilidad |
| **Prioridad** | Media |
| **Objetivo** | Verificar que el `setInterval` del polling se cancela correctamente cuando la sesión de mantenimiento alcanza estado "completed". |

**Método:**
- Abrir DevTools → pestaña Network.
- Completar una sesión de mantenimiento.
- Después de mostrar la tarjeta de resumen, observar si continúan peticiones a `/maintenance/api/status/<id>`.

**Resultado esperado:**
- Después de que la sesión llega a "completed", no hay más peticiones de polling al endpoint de estado.
- `clearInterval(maintenancePollInterval)` se ejecutó correctamente.

---

### PT-TEC-032 — Sesión en memoria no persiste entre reinicios del EXE

| Campo | Detalle |
|-------|---------|
| **ID** | PT-TEC-032 |
| **Categoría** | Estado / Memoria |
| **Prioridad** | Baja |
| **Objetivo** | Verificar que al reiniciar el EXE, las sesiones de mantenimiento previas no están disponibles. |

**Pasos:**
1. Completar una sesión de mantenimiento. Anotar el ID de sesión (ej: `abc123`).
2. Cerrar `CleanCPU.exe`.
3. Volver a ejecutar `CleanCPU.exe` como Administrador.
4. Hacer GET a `/maintenance/api/status/abc123`.

**Resultado esperado:**
- Respuesta HTTP 404 con `{"error": "Sesión no encontrada."}`.
- El histórico de sesiones no se persiste entre ejecuciones del EXE.

---

*Fin de Pruebas Técnicas — RADEC Maintenance Program v3.0.0*
*Documento: PT-TEC-001 | Área TI RADEC | 2026-04-04*
