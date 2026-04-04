# RADEC Maintenance Program — Validación de Seguridad y Permisos
## Documento: PT-SEG-001 | Versión: 1.0.0 | Fecha: 2026-04-04

---

## CONTROL DE VERSIONES

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2026-04-04 | Área TI RADEC | Versión inicial para piloto |

---

## ALCANCE

Este documento cubre la validación de los controles de seguridad y gestión de privilegios implementados en el Programa de Mantenimiento RADEC:

1. Gestión honesta de privilegios de Administrador
2. Seguridad del manejo de claves de producto Office
3. Mecanismos de activación soportados y no soportados
4. Allowlist de comandos del sistema y protección contra ejecución peligrosa
5. Protección contra inyección de comandos
6. Seguridad de la interfaz web (CSRF, cookies, origin)
7. Comportamiento de los logs (qué se registra y qué no)
8. Seguridad de la ejecución local

---

## SECCIÓN 1: GESTIÓN HONESTA DE PRIVILEGIOS

---

### PT-SEG-001 — Operaciones admin-only marcadas como omitidas, no como completadas

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-001 |
| **Categoría** | Privilegios / Honestidad de reportes |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que ninguna operación que requiere permisos de Administrador reporta "Completado" cuando la aplicación no está elevada. |

**Criterio fundamental:**
La aplicación debe ser honesta. Una operación no ejecutada por falta de privilegios NO debe reportarse como exitosa. Este principio protege al técnico de creer que el mantenimiento fue completo cuando en realidad fue parcial.

**Pasos:**
1. Ejecutar la aplicación SIN Administrador.
2. Completar la secuencia de mantenimiento.
3. Verificar el estado de los pasos 4 (defrag), 6 (cleanmgr) y 8 (UsoClient).
4. Verificar el estado de las sub-operaciones DISM y SFC en los pasos 1 y 3.
5. Generar el reporte y verificar que refleja los pasos omitidos.

**Verificaciones específicas:**

| Operación | Estado esperado sin Admin | Estado NO aceptado |
|-----------|--------------------------|-------------------|
| `defrag C: /O` | "Omitido" con mensaje de Admin | "Completado" |
| `cleanmgr /sagerun:1` | "Omitido" con mensaje de Admin | "Completado" |
| `UsoClient StartScan` | "Omitido" con mensaje de Admin | "Completado" |
| DISM /CheckHealth | En `admin_skipped` del Paso 1/3 | Reportado como ejecutado |
| SFC /scannow | En `admin_skipped` del Paso 1/3 | Reportado como ejecutado |

**Resultado esperado:**
- Todas las operaciones admin-only muestran estado "Omitido" con mensaje explícito que menciona Administrador.
- El reporte generado incluye los pasos omitidos con su razón.
- Ningún paso finge haberse ejecutado exitosamente sin haberlo hecho.

---

### PT-SEG-002 — Mensaje de omisión incluye instrucción de remediación

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-002 |
| **Categoría** | Privilegios / UX de seguridad |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que los mensajes de omisión por falta de Admin incluyen la instrucción "Ejecutar como administrador" para guiar al técnico. |

**Resultado esperado:**
- El mensaje de omisión contiene texto como "Abra la aplicación con clic derecho → Ejecutar como administrador."
- El técnico puede actuar sobre el mensaje sin consultar documentación adicional.

---

### PT-SEG-003 — REQUIRES_ADMIN no se trata como error de sistema

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-003 |
| **Categoría** | Privilegios / Clasificación de estados |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que `CommandStatus.REQUIRES_ADMIN` se clasifica correctamente como estado de omisión esperado, no como error técnico. |

**Verificación:**
- `result.is_error` devuelve `False` cuando `result.status == CommandStatus.REQUIRES_ADMIN`.
- Solo `CommandStatus.ERROR` y `CommandStatus.TIMEOUT` son `is_error == True`.

**Justificación:**
Si `REQUIRES_ADMIN` fuera tratado como error, los pasos de mantenimiento reportarían "Fallido" en lugar de "Omitido" en equipos sin elevación, produciendo reportes de servicio incorrectos y alarmas falsas.

---

## SECCIÓN 2: SEGURIDAD DE CLAVES DE PRODUCTO OFFICE

---

### PT-SEG-010 — Clave de producto nunca visible en logs

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-010 |
| **Categoría** | Seguridad / Datos sensibles |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que la clave de producto Office ingresada por el técnico no aparece en ninguna entrada del log de la aplicación. |

**Pasos:**
1. Borrar o archivar el log actual: `C:\ProgramData\CleanCPU\logs\app.log`.
2. Activar Office con una clave conocida (ej: `AAAAA-BBBBB-CCCCC-DDDDD-EEEEE`).
3. Abrir el log inmediatamente después.
4. Buscar la cadena `AAAAA` o `AAAAA-BBBBB` en el log.

**Resultado esperado:**
- La clave completa `AAAAA-BBBBB-CCCCC-DDDDD-EEEEE` NO aparece en ninguna línea del log.
- Las entradas relacionadas con la activación muestran `ospp.vbs /inpkey:***` o similar.
- El campo `description` del comando registrado en el log es `ospp.vbs /inpkey:***`.

---

### PT-SEG-011 — Clave de producto nunca retornada en respuesta de API

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-011 |
| **Categoría** | Seguridad / API |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que la respuesta JSON de `/office/api/activate` contiene solo la clave enmascarada (últimos 5 caracteres) y nunca la clave completa. |

**Pasos:**
1. Activar Office con clave `AAAAA-BBBBB-CCCCC-DDDDD-EEEEE`.
2. Inspeccionar la respuesta JSON en DevTools → Network.

**Verificaciones en la respuesta:**

| Campo | Valor esperado | Valor NO aceptado |
|-------|---------------|------------------|
| `masked_key` | `XXXXX-XXXXX-XXXXX-XXXXX-EEEEE` | La clave completa |
| `inpkey_output` | Salida de ospp.vbs (no contiene la clave) | La clave completa |
| `act_output` | Salida de ospp.vbs (no contiene la clave) | La clave completa |
| `message` | Mensaje enmascarado | La clave completa |

---

### PT-SEG-012 — Campo de ingreso limpiado inmediatamente al enviar

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-012 |
| **Categoría** | Seguridad / UI |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que el campo de ingreso de la clave se limpia inmediatamente después de enviar la solicitud de activación, antes incluso de recibir la respuesta del servidor. |

**Pasos:**
1. Ingresar una clave en el campo de texto.
2. Hacer clic en "Activar Office".
3. Verificar inmediatamente el campo de texto antes de que la respuesta llegue.

**Resultado esperado:**
- El campo de texto se vacía inmediatamente después de hacer clic (antes de la respuesta del servidor).
- La clave no permanece visible mientras se espera la respuesta.

---

### PT-SEG-013 — Variable de clave sobreescrita en memoria del servidor

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-013 |
| **Categoría** | Seguridad / Memoria |
| **Prioridad** | Alta |
| **Objetivo** | Verificar en el código fuente que la variable que contiene la clave de producto es sobreescrita en memoria inmediatamente después de que el subproceso inicia. |

**Verificación de código (revisión estática):**

En `services/office_tools.py`, función `activate_with_key`:
```python
inpkey_result = _run_ospp(ospp_path, f'/inpkey:{key}', timeout=60)
key = None  # noqa: F841 — intentional memory clear
```

**Resultado esperado:**
- La línea `key = None` existe en el código fuente inmediatamente después del `_run_ospp` con `/inpkey`.
- No hay más referencias a la variable `key` después de esta línea.

---

## SECCIÓN 3: MECANISMOS DE ACTIVACIÓN

---

### PT-SEG-020 — Solo ospp.vbs es usado para activación Office

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-020 |
| **Categoría** | Seguridad / Activación |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que la aplicación utiliza exclusivamente `cscript ospp.vbs` (herramienta oficial de Microsoft) para activar Office, y que no existe ningún código de activación alternativo. |

**Verificación de código (revisión estática):**

En `services/office_tools.py`:
- La función `activate_with_key` invoca solo `_run_ospp(ospp_path, f'/inpkey:{key}')` y `_run_ospp(ospp_path, '/act')`.
- No hay llamadas a KMS no autorizados, activadores de terceros, ni scripts de rearm.

En `ALLOWED_COMMANDS['cscript']`:
- Los patrones permitidos solo cubren `/dstatus`, `/act`, `/inpkey:<clave-válida>` y slmgr.vbs.
- `/rearm` no está en la allowlist de ospp.vbs.

**Resultado esperado:**
- No existe código de activación alternativo al mecanismo oficial `ospp.vbs`.
- La allowlist de `cscript` bloquea cualquier flag de ospp.vbs no explícitamente permitido.

---

### PT-SEG-021 — /rearm bloqueado por allowlist

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-021 |
| **Categoría** | Seguridad / Activación |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que `ospp.vbs /rearm` (extensión del período de gracia) está bloqueado por la allowlist y no puede ser ejecutado. |

**Método:**
- Intentar invocar `run_cmd(['cscript', '//nologo', '<ruta_ospp.vbs>', '/rearm'], ...)`.
- Verificar que el comando es bloqueado por la validación de allowlist.

**Resultado esperado:**
- La llamada falla con error de allowlist (el patrón `r'^//nologo\s+.*\\ospp\.vbs\s+/(?:dstatus|act)$'` no incluye `/rearm`).
- El comando nunca se ejecuta en el sistema operativo.

---

## SECCIÓN 4: ALLOWLIST Y PROTECCIÓN CONTRA EJECUCIÓN PELIGROSA

---

### PT-SEG-030 — Comandos no permitidos son bloqueados antes de ejecutarse

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-030 |
| **Categoría** | Allowlist / Seguridad de comandos |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que el motor de comandos no ejecuta ningún comando que no esté en `ALLOWED_COMMANDS`. |

**Casos representativos de comandos bloqueados:**

| Comando intentado | Motivo de bloqueo |
|------------------|-------------------|
| `cmd /c del /f /q C:\Windows\*` | `cmd` no está en allowlist |
| `reg delete HKLM\...` | `reg` no está en allowlist |
| `format C:` | `format` no está en allowlist |
| `net user Administrator password123` | `net user` está en `denied_first_arg` |
| `netsh firewall ...` | `firewall` está en `denied_args` de netsh |
| `pnputil /delete-driver oem1.inf` | `/delete-driver` está en `denied_args` de pnputil |
| `defrag C: /x` | `/x` está en `denied_args` de defrag |
| `sc delete <servicio>` | `delete` está en `denied_args` de sc |
| `taskkill /fi "..."` | `/fi` está en `denied_args` de taskkill |

**Resultado esperado (todos los casos):**
- El comando retorna error de allowlist inmediatamente.
- El proceso del sistema operativo NO es invocado.
- La entrada de log contiene el bloqueo, no la ejecución.

---

### PT-SEG-031 — Subcomandos no permitidos de comandos en allowlist son bloqueados

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-031 |
| **Categoría** | Allowlist / Subcomandos |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que incluso cuando el comando base está en la allowlist, los subcomandos no permitidos son bloqueados. |

**Casos:**

| Comando | Subcomando intentado | ¿Bloqueado? |
|---------|---------------------|-------------|
| `sfc` | `/deleteallfiles` | Sí |
| `dism` | `/Apply-Image` | Sí |
| `chkdsk` | `/b` | Sí |
| `ipconfig` | `/registerdns` | Sí |

---

### PT-SEG-032 — Inyección de comandos mediante caracteres especiales

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-032 |
| **Categoría** | Seguridad / Inyección |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que los patrones `DANGEROUS_PATTERNS` detectan y bloquean intentos de inyección de comandos mediante caracteres especiales en los argumentos. |

**Patrones a verificar en `command_runner.py`:**
- `&`, `;`, `|`, `$(`, `` ` ``, saltos de línea (`\n`, `\r`), `>`, `<`, `%`

**Método:**
- Para cada carácter peligroso, intentar pasarlo como argumento en una llamada a `run_cmd`.
- Verificar que la validación de `DANGEROUS_PATTERNS` lo detecta antes de ejecutar el subproceso.

**Resultado esperado:**
- Todos los argumentos con caracteres de inyección son bloqueados.
- El `CommandResult` retorna error de validación con descripción del patrón detectado.
- Ningún subproceso es invocado.

---

### PT-SEG-033 — Ejecución como lista de argumentos (sin shell expansion)

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-033 |
| **Categoría** | Seguridad / Shell |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que los comandos de la secuencia de mantenimiento se ejecutan como listas de argumentos (no como cadenas con shell=True), eliminando el riesgo de shell expansion. |

**Verificación en código fuente:**
- Todos los comandos en `_step_*` que usan `run_cmd` con una lista (ej: `['sfc', '/scannow']`, `['defrag', 'C:', '/O']`) deben ejecutarse sin `shell=True`.
- Solo los comandos con `shell=True` explícito (como `start "" "..."` en Lenovo Update) están justificados por el uso de `start` (builtin del shell CMD).

---

## SECCIÓN 5: SEGURIDAD DE LA INTERFAZ WEB

---

### PT-SEG-040 — Protección CSRF en rutas POST

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-040 |
| **Categoría** | Seguridad Web / CSRF |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que las rutas POST (inicio de mantenimiento, cancelación, inspección de licencia, activación) están protegidas contra ataques CSRF. |

**Método:**
- Intentar hacer POST a `/maintenance/api/start` sin el header CSRF requerido (simulando una petición cruzada).
- Verificar que la petición es rechazada.

**Resultado esperado:**
- Las peticiones POST sin el token CSRF son rechazadas con HTTP 400 o 403.
- La función `init_security(app)` en `app.py` está activa y configura la validación CSRF.

---

### PT-SEG-041 — Cookie de sesión con atributos de seguridad

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-041 |
| **Categoría** | Seguridad Web / Cookies |
| **Prioridad** | Media |
| **Objetivo** | Verificar que la cookie de sesión tiene los atributos de seguridad correctos según la configuración en `Config`. |

**Configuración esperada en `Config`:**
```python
SESSION_COOKIE_HTTPONLY = True      # No accesible via JavaScript
SESSION_COOKIE_SAMESITE = 'Strict'  # No enviada en peticiones cross-site
SESSION_COOKIE_SECURE = False       # HTTP localhost (correcto)
SESSION_COOKIE_NAME = 'cleancpu_session'
PERMANENT_SESSION_LIFETIME = 28800  # 8 horas
```

**Verificación:**
- Abrir DevTools → Application → Cookies.
- Verificar los atributos de la cookie `cleancpu_session`.

**Resultado esperado:**
- `HttpOnly: true`
- `SameSite: Strict`
- `Secure: false` (correcto para HTTP localhost)
- Tiempo de expiración: 8 horas desde el inicio de sesión.

---

### PT-SEG-042 — Validación de Origin en peticiones

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-042 |
| **Categoría** | Seguridad Web / Origin |
| **Prioridad** | Media |
| **Objetivo** | Verificar que el middleware de seguridad rechaza peticiones con Origin diferente al esperado (`http://127.0.0.1:5000`). |

**Método:**
- Hacer una petición POST con header `Origin: http://malicious-site.com`.
- Verificar que la petición es rechazada por el middleware `init_security`.

**Resultado esperado:**
- La petición con Origin externo es rechazada con HTTP 403.

---

## SECCIÓN 6: COMPORTAMIENTO DE LOGS

---

### PT-SEG-050 — Qué se registra y qué no en los logs

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-050 |
| **Categoría** | Logs / Auditoría |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que el log de la aplicación registra las acciones del técnico de forma auditoriable, sin incluir datos sensibles. |

**Lo que DEBE aparecer en el log:**

| Evento | Ejemplo de entrada esperada |
|--------|----------------------------|
| Inicio de la aplicación | `CleanCPU v3.0.0 starting...` |
| Ejecución de cada comando | `[INFO] command_runner: [<id>] defrag C: /O` |
| Resultado de cada comando | Estado, duración, código de retorno |
| Error en un paso | Descripción del error con ID de operación |
| Inicio de sesión de mantenimiento | Session ID, timestamp |
| Activación Office (enmascarada) | `ospp.vbs /inpkey:***` |

**Lo que NO debe aparecer en el log:**

| Dato sensible | Razón |
|---------------|-------|
| Clave de producto completa | Dato confidencial de licenciamiento |
| Contraseñas | Si aplica en futuras funcionalidades |
| Tokens de sesión completos | Dato de autenticación |

---

### PT-SEG-051 — Log escribe solo en archivo local (sin stdout/network)

| Campo | Detalle |
|-------|---------|
| **ID** | PT-SEG-051 |
| **Categoría** | Logs / Privacidad |
| **Prioridad** | Media |
| **Objetivo** | Verificar que los logs de la aplicación se escriben únicamente en el archivo local, no en stdout, no en servicios de logging remotos, y no en consola (EXE empaquetado sin consola). |

**Verificación en `app.py`:**
- `RotatingFileHandler` es el único handler configurado en el root logger.
- No hay `StreamHandler` ni handlers de servicios remotos.
- La consola de Werkzeug está suprimida (`logging.getLogger('werkzeug').setLevel(logging.WARNING)`).

---

## RESUMEN DE CONTROLES DE SEGURIDAD IMPLEMENTADOS

| Control | Estado | Referencia |
|---------|--------|-----------|
| Clave de producto enmascarada en logs | Implementado | `_run_ospp` → `safe_desc` |
| Clave sobreescrita en memoria post-subproceso | Implementado | `key = None` en `activate_with_key` |
| Campo de ingreso limpiado en UI post-envío | Implementado | `keyInput.value = ''` en `activateOffice()` |
| Solo ospp.vbs para activación (no activadores no oficiales) | Implementado | `activate_with_key` |
| Allowlist de comandos del sistema | Implementado | `ALLOWED_COMMANDS` en `command_runner.py` |
| Bloqueo de inyección de comandos | Implementado | `DANGEROUS_PATTERNS` |
| Admin-required honesto (no false positive) | Implementado | `REQUIRES_ADMIN` no es `is_error` |
| Servidor solo en localhost | Implementado | `HOST = '127.0.0.1'` |
| CSRF en rutas POST | Implementado | `init_security(app)` |
| Cookies HttpOnly + SameSite=Strict | Implementado | `Config` |
| Logs solo en archivo local | Implementado | `RotatingFileHandler` únicamente |

---

*Fin de Validación de Seguridad y Permisos — RADEC Maintenance Program v3.0.0*
*Documento: PT-SEG-001 | Área TI RADEC | 2026-04-04*
