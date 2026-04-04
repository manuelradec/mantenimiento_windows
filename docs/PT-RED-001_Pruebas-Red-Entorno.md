# RADEC Maintenance Program — Pruebas de Red y Entorno
## Documento: PT-RED-001 | Versión: 1.0.0 | Fecha: 2026-04-04

---

## CONTROL DE VERSIONES

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2026-04-04 | Área TI RADEC | Versión inicial para piloto |

---

## ALCANCE

Este documento cubre la validación del entorno de red y sistema operativo necesario para la operación correcta del Programa de Mantenimiento RADEC, incluyendo:

- Restricción de acceso al servidor local (localhost-only)
- Puerto y binding del servidor
- Dependencias del entorno Windows (PowerShell, WMI, herramientas del sistema)
- Comportamiento sin conectividad (operación offline)
- Comportamiento con conectividad (reportes remotos, activación Office)
- Dependencias del entorno Office (ospp.vbs)
- Prerrequisitos del equipo para operación completa del técnico

---

## VALIDACIONES DE SERVIDOR LOCAL

---

### PT-RED-001 — Servidor escucha exclusivamente en localhost

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-001 |
| **Categoría** | Seguridad de red / Binding |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que el servidor Waitress escucha únicamente en `127.0.0.1:5000` y no es accesible desde otros equipos de la red. |

**Precondiciones:**
- `CleanCPU.exe` iniciado en el equipo A (HOST).
- Equipo B en la misma red local.

**Pasos:**
1. Desde el Equipo A, verificar con `netstat -an | findstr 5000` que el servidor está en `127.0.0.1:5000`.
2. Desde el Equipo B, intentar acceder a `http://<IP del Equipo A>:5000/`.
3. Desde el Equipo A, acceder a `http://127.0.0.1:5000/`.

**Resultado esperado:**
- `netstat` muestra `127.0.0.1:5000` (no `0.0.0.0:5000`).
- El acceso desde el Equipo B resulta en timeout o rechazo de conexión.
- El acceso desde `127.0.0.1` en el Equipo A funciona correctamente.

**Justificación:**
- El servidor está configurado con `HOST = '127.0.0.1'` en `Config`. Ningún técnico externo ni equipo de la red puede acceder a la interfaz de otro equipo en mantenimiento.

---

### PT-RED-002 — Puerto 5000 disponible como prerequisito

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-002 |
| **Categoría** | Entorno / Puerto |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que el técnico puede identificar si el puerto 5000 está ocupado antes de ejecutar la aplicación, y que la aplicación no falla silenciosamente en ese caso. |

**Precondiciones:**
- Otro proceso ocupa el puerto 5000 (verificable con `netstat -an | findstr 5000`).

**Pasos:**
1. Confirmar que el puerto 5000 está ocupado.
2. Intentar iniciar `CleanCPU.exe`.
3. Observar el comportamiento de la aplicación.

**Resultado esperado:**
- El servidor no inicia.
- El navegador no se abre o muestra error de conexión.
- El log de la aplicación contiene un error de binding ("`[Errno 10048]` Only one usage of each socket address" o equivalente).

**Acción recomendada documentada:**
- El técnico debe ejecutar `netstat -an | findstr 5000` para identificar el proceso conflictivo y cerrarlo antes de reiniciar la aplicación.

---

### PT-RED-003 — Acceso solo via HTTP (no HTTPS) en localhost

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-003 |
| **Categoría** | Protocolo |
| **Prioridad** | Baja |
| **Objetivo** | Confirmar que el servidor opera en HTTP plano sobre localhost (no HTTPS) y que esto es aceptable para la operación local. |

**Pasos:**
1. Intentar acceder a `https://127.0.0.1:5000/`.
2. Verificar la configuración `SESSION_COOKIE_SECURE = False` en `Config`.

**Resultado esperado:**
- El acceso via HTTPS falla (no hay certificado SSL configurado).
- El acceso via HTTP funciona correctamente.
- Las cookies de sesión tienen `HttpOnly` y `SameSite=Strict` pero no `Secure` (correcto para HTTP localhost).

**Justificación:**
- La aplicación opera exclusivamente en localhost. HTTPS en localhost requeriría certificados autofirmados que generarían advertencias en el navegador y aumentarían la complejidad operativa sin beneficio de seguridad adicional (no hay tráfico de red externo).

---

## VALIDACIONES DE DEPENDENCIAS DEL ENTORNO WINDOWS

---

### PT-RED-010 — Disponibilidad de PowerShell 5.1+

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-010 |
| **Categoría** | Entorno Windows / PowerShell |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que PowerShell 5.1 (preinstalado en Windows 10/11) es accesible desde la aplicación y puede ejecutar los scripts utilizados en la secuencia de mantenimiento. |

**Pasos:**
1. Ejecutar la aplicación en un equipo estándar Windows 10/11.
2. Iniciar el mantenimiento.
3. Verificar en el log que las operaciones de PowerShell (paso 1: servicios, actualizaciones, reinicio pendiente) ejecutan sin error de `powershell.exe not found` o `execution policy`.

**Resultado esperado:**
- PowerShell se invoca correctamente con `-ExecutionPolicy Bypass -NonInteractive`.
- Las consultas WMI/CIM retornan datos del equipo.
- No hay errores de política de ejecución bloqueando los scripts.

---

### PT-RED-011 — WMI accesible para inventario

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-011 |
| **Categoría** | Entorno Windows / WMI |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que el servicio WMI (`winmgmt`) está activo y accesible para las consultas de inventario del sistema. |

**Pasos:**
1. Verificar que el servicio WMI está activo: `Get-Service winmgmt`.
2. Navegar al módulo de inventario y verificar que todos los campos se poblan.

**Resultado esperado:**
- El módulo de inventario muestra datos reales (no "N/A" en fabricante, modelo, serie, procesador).
- No hay errores de "Access is denied" ni "WMI query failed" en el log.

---

### PT-RED-012 — Herramientas del sistema disponibles en PATH

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-012 |
| **Categoría** | Entorno Windows / PATH |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que todas las herramientas del sistema operativo utilizadas en el mantenimiento están disponibles en el PATH del sistema. |

**Herramientas a verificar:**

| Herramienta | Ruta típica en Windows 10/11 | Comando de verificación |
|-------------|------------------------------|------------------------|
| `sfc.exe` | `C:\Windows\System32` | `where sfc` |
| `dism.exe` | `C:\Windows\System32` | `where dism` |
| `defrag.exe` | `C:\Windows\System32` | `where defrag` |
| `cleanmgr.exe` | `C:\Windows\System32` | `where cleanmgr` |
| `ipconfig.exe` | `C:\Windows\System32` | `where ipconfig` |
| `UsoClient.exe` | `C:\Windows\System32` | `where UsoClient` |
| `cscript.exe` | `C:\Windows\System32` | `where cscript` |
| `powershell.exe` | `C:\Windows\System32\WindowsPowerShell\v1.0` | `where powershell` |

**Resultado esperado:**
- Todas las herramientas están en el PATH del sistema (instalación estándar de Windows 10/11).
- La aplicación puede invocarlas sin especificar ruta absoluta.

---

### PT-RED-013 — Directorio de logs escribible

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-013 |
| **Categoría** | Entorno / Permisos de escritura |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que la aplicación puede crear y escribir el archivo de log, ya sea en la ruta primaria (`C:\ProgramData\CleanCPU\logs\`) o en la ruta alternativa local. |

**Caso A — Aplicación con Administrador:**
- Ruta primaria debe ser escribible.
- Verificar que `C:\ProgramData\CleanCPU\logs\app.log` existe y tiene entradas después de iniciar la aplicación.

**Caso B — Aplicación sin Administrador:**
- `C:\ProgramData\` puede no ser escribible para usuarios estándar.
- Verificar que la aplicación crea el log en la ruta alternativa (`<directorio EXE>\logs\`).
- Verificar que la aplicación no falla por error de creación del log.

**Resultado esperado (ambos casos):**
- La aplicación inicia y opera correctamente independientemente de si puede escribir en `C:\ProgramData\`.
- Existe al menos un archivo de log con entradas.

---

### PT-RED-014 — Directorio de reportes escribible

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-014 |
| **Categoría** | Entorno / Permisos de escritura |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que el directorio de reportes es escribible y la aplicación puede crear archivos de reporte. |

**Pasos:**
1. Completar un mantenimiento y generar el reporte.
2. Verificar que el archivo HTML existe en `C:\ProgramData\CleanCPU\reports\`.
3. Verificar el tamaño del archivo (debe ser > 0 bytes).

**Resultado esperado:**
- El reporte HTML se crea correctamente.
- El archivo tiene contenido (> 0 bytes).

---

## VALIDACIONES DE OPERACIÓN OFFLINE

---

### PT-RED-020 — Operación completa de mantenimiento sin conectividad

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-020 |
| **Categoría** | Conectividad / Offline |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que la secuencia completa de mantenimiento y la generación del reporte HTML local funcionan correctamente en un equipo sin conectividad a Internet. |

**Precondiciones:**
- Equipo sin conectividad a Internet o con cable desconectado.

**Pasos:**
1. Deshabilitar el adaptador de red del equipo.
2. Ejecutar la secuencia completa de mantenimiento.
3. Generar el reporte HTML local.

**Resultado esperado:**
- Los 9 pasos se ejecutan correctamente (el mantenimiento es operación local).
- El reporte HTML se genera sin errores relacionados con red.
- Los destinos remotos (Google Sheets, carpeta de red) se reportan como "Omitidos/Error" pero no bloquean la generación del reporte local.

---

### PT-RED-021 — Activación de Office sin conectividad

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-021 |
| **Categoría** | Conectividad / Office |
| **Prioridad** | Media |
| **Objetivo** | Verificar el comportamiento de la activación de Office cuando no hay conectividad para contactar los servidores de Microsoft. |

**Precondiciones:**
- Office instalado. Equipo sin conectividad a Internet.

**Pasos:**
1. Intentar activar Office con una clave válida sin conectividad.
2. Observar el resultado.

**Resultado esperado:**
- ospp.vbs retorna un código de error de activación (ej: `0x8004FE33` o similar).
- La aplicación muestra el error específico de ospp.vbs con el código.
- La aplicación NO reporta "activación exitosa" falsamente.
- El técnico recibe instrucción de verificar conectividad.

**Estado:** Pendiente de validación en piloto.

---

## VALIDACIONES DEL ENTORNO OFFICE

---

### PT-RED-030 — ospp.vbs en ruta estándar de Office 2016–2024

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-030 |
| **Categoría** | Entorno / Office |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que la aplicación localiza correctamente `ospp.vbs` en las rutas estándar para las versiones de Office en uso en RADEC. |

**Rutas verificadas:**

| Ruta | Aplicable a |
|------|------------|
| `C:\Program Files\Microsoft Office\Office16\ospp.vbs` | Office 2016/2019/2021/M365 x64 |
| `C:\Program Files (x86)\Microsoft Office\Office16\ospp.vbs` | Office 2016/2019/2021/M365 x86 |
| `C:\Program Files\Microsoft Office\Office15\ospp.vbs` | Office 2013 x64 |
| `C:\Program Files (x86)\Microsoft Office\Office15\ospp.vbs` | Office 2013 x86 |

**Pasos:**
1. En cada tipo de equipo con las versiones de Office listadas, abrir el módulo Office.
2. Verificar que el campo "ospp.vbs" muestra la ruta correcta (no vacío).

**Resultado esperado:**
- `ospp.vbs` es detectado en la ruta correcta para cada versión de Office.
- El módulo no reporta "ospp.vbs no encontrado" para Office instalado en rutas estándar.

---

### PT-RED-031 — Office en ruta no estándar (instalación personalizada)

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-031 |
| **Categoría** | Entorno / Office |
| **Prioridad** | Media |
| **Objetivo** | Verificar el comportamiento cuando Office está instalado en una ruta no estándar (instalación personalizada que no sigue las rutas predefinidas en la allowlist de ospp). |

**Precondiciones:**
- Office instalado en ruta personalizada (ej: `D:\Office\Office16\ospp.vbs`).

**Resultado esperado:**
- La detección via registro puede encontrar el producto pero `ospp.vbs` puede no estar en las rutas predefinidas.
- La aplicación muestra: "No se encontró ospp.vbs. Office puede no estar instalado o estar en una ruta no estándar."
- El técnico recibe instrucción clara; no hay error fatal.

**Estado:** Pendiente de validación en piloto. Se recomienda ampliar `_OSPP_SEARCH_PATHS` si se identifican rutas adicionales en el parque de RADEC.

---

## PRERREQUISITOS DEL EQUIPO PARA OPERACIÓN COMPLETA

---

### PT-RED-040 — Checklist de prerrequisitos del equipo técnico

| Campo | Detalle |
|-------|---------|
| **ID** | PT-RED-040 |
| **Categoría** | Entorno / Prerrequisitos |
| **Prioridad** | Alta |
| **Objetivo** | Validar que un equipo representativo del parque RADEC cumple todos los prerrequisitos para operación completa de la herramienta. |

**Checklist de verificación:**

| # | Prerrequisito | Verificación | Estado |
|---|--------------|-------------|--------|
| 1 | Windows 10 (1903+) o Windows 11 x64 | `winver` o `systeminfo` | Pendiente |
| 2 | PowerShell 5.1+ disponible | `Get-Host \| Select-Object Version` | Pendiente |
| 3 | WMI activo (`winmgmt`) | `Get-Service winmgmt` | Pendiente |
| 4 | Puerto 5000 libre | `netstat -an \| findstr 5000` | Pendiente |
| 5 | `C:\ProgramData\` escribible (con Admin) | `icacls C:\ProgramData` | Pendiente |
| 6 | `sfc.exe` disponible | `where sfc` | Pendiente |
| 7 | `dism.exe` disponible | `where dism` | Pendiente |
| 8 | `defrag.exe` disponible | `where defrag` | Pendiente |
| 9 | `cscript.exe` disponible | `where cscript` | Pendiente |
| 10 | Antivirus no bloquea `CleanCPU.exe` | Inspección visual al ejecutar | Pendiente |
| 11 | UAC no deshabilitado o configurable | `reg query HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System /v EnableLUA` | Pendiente |
| 12 | Navegador web instalado (Edge, Chrome, Firefox) | Verificación visual | Pendiente |

**Estado general:** Pendiente de validación en piloto en un mínimo de 3 equipos representativos del parque de RADEC.

---

*Fin de Pruebas de Red y Entorno — RADEC Maintenance Program v3.0.0*
*Documento: PT-RED-001 | Área TI RADEC | 2026-04-04*
