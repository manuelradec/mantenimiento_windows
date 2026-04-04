# RADEC Maintenance Program — Pruebas de Integración
## Documento: PT-INT-001 | Versión: 1.0.0 | Fecha: 2026-04-04

---

## CONTROL DE VERSIONES

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2026-04-04 | Área TI RADEC | Versión inicial para piloto |

---

## ALCANCE

Este documento cubre las pruebas de integración del Programa de Mantenimiento RADEC, verificando la interacción correcta entre:

- Frontend (navegador) ↔ Backend (Flask/Waitress)
- UI de mantenimiento ↔ Estado de sesión en el servidor
- Rutas (Blueprints) ↔ Servicios internos ↔ Motor de comandos
- Módulo de reportes ↔ Datos de sesión e inventario
- Módulo Office (ruta) ↔ `office_tools.py` ↔ `ospp.vbs`
- EXE empaquetado ↔ Módulos internos en PyInstaller

---

## INTEGRACIÓN: UI ↔ SERVIDOR DE MANTENIMIENTO

---

### PT-INT-001 — Inicio de sesión de mantenimiento desde UI crea sesión en servidor

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-001 |
| **Categoría** | UI ↔ Backend |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que el clic en "Iniciar Mantenimiento Lógico" en la UI envía correctamente la petición POST a `/maintenance/api/start` y que el servidor retorna un `session_id` válido que la UI utiliza para el polling. |

**Pasos:**
1. Abrir DevTools → Network.
2. Navegar a `/maintenance/` y hacer clic en "Iniciar Mantenimiento Lógico".
3. Observar la petición POST a `/maintenance/api/start`.
4. Verificar la respuesta JSON.
5. Observar las peticiones GET periódicas a `/maintenance/api/status/<session_id>`.

**Resultado esperado:**
- POST a `/maintenance/api/start` retorna HTTP 200 con `{"status": "started", "session_id": "<8 chars>"}`.
- El `session_id` en la respuesta coincide con el usado en las peticiones de polling.
- Las peticiones de polling comienzan dentro de 2 segundos del inicio.

---

### PT-INT-002 — Actualización de UI refleja el estado real del servidor

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-002 |
| **Categoría** | UI ↔ Backend |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que cada ciclo de polling actualiza el estado visual de los pasos en la UI de forma correcta y consistente con el estado real en el servidor. |

**Pasos:**
1. Iniciar mantenimiento.
2. Durante la ejecución, hacer GET manual a `/maintenance/api/status/<session_id>` desde DevTools.
3. Comparar el `status` de cada step en la respuesta JSON con el estado visual en pantalla.

**Resultado esperado:**
- El estado de cada paso en la UI (`step-running`, `step-flash-success`, íconos) corresponde exactamente al `status` retornado por la API.
- La discrepancia máxima entre el estado real y el visual es el intervalo de polling (≤ 2 segundos).

---

### PT-INT-003 — Campo `started_at` del servidor alimenta el timer en la UI

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-003 |
| **Categoría** | UI ↔ Backend |
| **Prioridad** | Media |
| **Objetivo** | Verificar que el campo `started_at` (ISO timestamp) incluido en cada step del servidor es consumido correctamente por la UI para calcular y mostrar el tiempo transcurrido. |

**Pasos:**
1. Iniciar mantenimiento.
2. Cuando el Paso 1 esté en ejecución, verificar en DevTools la respuesta de polling y extraer el `started_at` del Paso 1.
3. Calcular manualmente el tiempo transcurrido desde `started_at` hasta el momento actual.
4. Comparar con el timer visible en pantalla (`En ejecución — MM:SS transcurrido...`).

**Resultado esperado:**
- El timer en pantalla muestra un valor dentro de ±2 segundos del tiempo real transcurrido calculado a partir de `started_at`.

---

### PT-INT-004 — Cancelación de UI llega al servidor y detiene la secuencia

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-004 |
| **Categoría** | UI ↔ Backend |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que la señal de cancelación enviada desde la UI (POST `/maintenance/api/cancel/<session_id>`) es recibida y procesada por el servidor, resultando en que los pasos no ejecutados se marcan como "cancelados". |

**Pasos:**
1. Iniciar mantenimiento.
2. Esperar a que el Paso 1 esté en ejecución.
3. Hacer clic en "Cancelar mantenimiento" y confirmar.
4. Observar la petición POST a `/maintenance/api/cancel/<session_id>` en DevTools.
5. Esperar a que el servidor procese la cancelación.
6. Verificar el estado final de los pasos en la API y en la UI.

**Resultado esperado:**
- POST a `/maintenance/api/cancel/<session_id>` retorna HTTP 200 con `{"status": "cancelling"}`.
- El servidor procesa la cancelación después de que el paso actual concluye.
- Los pasos no ejecutados tienen `status: "cancelled"` en la respuesta de polling.
- La UI muestra correctamente los pasos cancelados con ícono 🚫.

---

## INTEGRACIÓN: RUTAS ↔ SERVICIOS ↔ COMMAND_RUNNER

---

### PT-INT-010 — Ruta de mantenimiento → _step_defrag → defrag C: /O

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-010 |
| **Categoría** | Route ↔ Service ↔ Command |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que la ejecución del Paso 4 (defrag) invoca correctamente `run_cmd(['defrag', 'C:', '/O'])` con los parámetros correctos y que el resultado se mapea correctamente al estado del paso. |

**Método:**
- Ejecutar la secuencia de mantenimiento con Administrador.
- Verificar en el log de la aplicación que existe una entrada correspondiente a `defrag C: /O`.
- Verificar que el paso muestra estado "Completado" después de la ejecución.

**Resultado esperado:**
- El log contiene una entrada de comando `defrag` con operación `Optimize disk C:`.
- El Paso 4 muestra estado "Completado" con mensaje que menciona "TRIM en SSD" o "desfragmentación en HDD".
- No hay entradas de "Command blocked by allowlist" para este comando.

---

### PT-INT-011 — Ruta de mantenimiento → _step_ccleaner → servicios de limpieza

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-011 |
| **Categoría** | Route ↔ Service ↔ Command |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que el Paso 2 invoca correctamente los cinco servicios de limpieza (`clean_user_temp`, `clean_windows_temp`, `clean_prefetch`, `clean_inet_cache`, `flush_dns_cache`) y que el resultado consolida correctamente los MB liberados. |

**Método:**
- Ejecutar el mantenimiento.
- Verificar que el Paso 2 muestra en el resultado inline los MB liberados totales.
- Verificar que el campo `space_freed_mb` en la respuesta de la API contiene un valor numérico >= 0.

**Resultado esperado:**
- `space_freed_mb` en la sesión del Paso 2 es un número real (puede ser 0 si no había temporales).
- El mensaje del Paso 2 menciona el número de operaciones ejecutadas (debe ser 5).

---

### PT-INT-012 — Propagación de campos estructurados en sesión de mantenimiento

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-012 |
| **Categoría** | Route ↔ State |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que los campos estructurados retornados por los handlers de pasos (`findings`, `errors`, `warnings`, `admin_skipped`, `recommended_actions`, `space_freed_mb`) se propagan correctamente al objeto de sesión y son accesibles via la API de estado. |

**Pasos:**
1. Ejecutar el mantenimiento con Administrador en un equipo con al menos un hallazgo (ej: actualizaciones pendientes, reinicio pendiente o servicio detenido).
2. Hacer GET a `/maintenance/api/status/<session_id>` después de que el Paso 1 complete.
3. Verificar la estructura del step `malwarebytes` en la respuesta.

**Resultado esperado:**
- La respuesta incluye `findings` como array de objetos con campos `title`, `severity`, `evidence`, `recommended_action`.
- La respuesta incluye `recommended_actions` como array de strings.
- Si no se ejecutó con Administrador, `admin_skipped` incluye "DISM /CheckHealth" y "SFC /scannow".

---

## INTEGRACIÓN: MÓDULO OFFICE

---

### PT-INT-020 — Ruta /office/api/info → office_tools.get_installation_info → registro

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-020 |
| **Categoría** | Route ↔ Service |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que la ruta `/office/api/info` invoca correctamente `get_installation_info()` y retorna datos del registro de Windows. |

**Pasos:**
1. Con Office instalado, hacer GET a `http://127.0.0.1:5000/office/api/info`.
2. Verificar la estructura y contenido de la respuesta JSON.

**Resultado esperado:**
- La respuesta incluye `installed: true`, `product_name`, `version`, `platform`, `ospp_path`.
- La respuesta NO incluye claves de producto ni datos de licencia (eso requiere /dstatus).

---

### PT-INT-021 — Ruta /office/api/inspect → office_tools.inspect_license → ospp.vbs /dstatus

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-021 |
| **Categoría** | Route ↔ Service ↔ cscript |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que la ruta `/office/api/inspect` ejecuta correctamente `cscript ospp.vbs /dstatus` y retorna el estado de licencia parseado. |

**Precondiciones:**
- Office instalado. Aplicación con Administrador.

**Pasos:**
1. Hacer POST a `http://127.0.0.1:5000/office/api/inspect` con headers CSRF correctos.
2. Verificar la respuesta JSON.

**Resultado esperado:**
- `status: "success"`.
- `parsed` incluye `product_name`, `license_status`, `partial_key`, `product_id`.
- `raw_output` contiene la salida completa de ospp.vbs.
- `message` es un resumen legible del estado.

---

### PT-INT-022 — Ruta /office/api/activate → office_tools.activate_with_key → ospp.vbs /inpkey + /act

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-022 |
| **Categoría** | Route ↔ Service ↔ cscript |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar que la ruta `/office/api/activate` ejecuta la secuencia completa de `/inpkey` y `/act`, y que la clave no aparece en ningún punto de la respuesta ni del log. |

**Precondiciones:**
- Office instalado. Administrador. Clave válida disponible.

**Pasos:**
1. Hacer POST a `/office/api/activate` con body `{"key": "XXXXX-XXXXX-XXXXX-XXXXX-YYYYY"}`.
2. Verificar la respuesta JSON.
3. Verificar el log de la aplicación.

**Resultado esperado:**
- `masked_key` en la respuesta muestra `XXXXX-XXXXX-XXXXX-XXXXX-YYYYY`.
- La clave completa NO aparece en `masked_key`, `inpkey_output`, `act_output`, ni en el log.
- Si la activación fue exitosa: `status: "success"`.

---

## INTEGRACIÓN: REPORTES ↔ DATOS DE SESIÓN E INVENTARIO

---

### PT-INT-030 — Reporte HTML incluye datos completos de sesión e inventario

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-030 |
| **Categoría** | Reportes ↔ Sesión ↔ Inventario |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que `generate_full_report(session)` utiliza correctamente los datos de la sesión de mantenimiento y los datos de inventario del sistema para generar un reporte HTML completo. |

**Pasos:**
1. Completar una sesión de mantenimiento.
2. Generar el reporte (POST a `/maintenance/api/report/<session_id>`).
3. Abrir el HTML generado.
4. Verificar que el reporte contiene datos del equipo, resultados de los 9 pasos, y hallazgos.

**Resultado esperado:**
- El hostname en el reporte coincide con el hostname real del equipo.
- Los resultados de cada paso en el reporte coinciden con los mostrados en pantalla.
- Los hallazgos de seguridad (findings) del Paso 1/3 están incluidos en el reporte.
- Los MB liberados por el Paso 2 están incluidos.
- La fecha/hora del mantenimiento es correcta.

---

### PT-INT-031 — Datos de inventario en el reporte son consistentes con el módulo de inventario

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-031 |
| **Categoría** | Reportes ↔ Inventario |
| **Prioridad** | Media |
| **Objetivo** | Verificar que los datos del equipo en el reporte de mantenimiento son consistentes con los mostrados en el módulo de inventario del sistema. |

**Pasos:**
1. Abrir el módulo de inventario y anotar: hostname, modelo, serie, RAM, procesador.
2. Completar un mantenimiento y generar el reporte.
3. Comparar los datos del equipo en el reporte con los anotados en el paso 1.

**Resultado esperado:**
- Los valores coinciden entre el módulo de inventario y el reporte (ambos leen del mismo origen: WMI/registro).

---

## INTEGRACIÓN: EXE EMPAQUETADO ↔ MÓDULOS INTERNOS

---

### PT-INT-040 — EXE empaquetado ejecuta mantenimiento completo

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-040 |
| **Categoría** | EXE ↔ Módulos internos |
| **Prioridad** | Crítica |
| **Objetivo** | Verificar end-to-end que el EXE empaquetado puede ejecutar la secuencia completa de mantenimiento en un equipo donde no existe el entorno de desarrollo Python. |

**Precondiciones:**
- Equipo sin Python instalado.
- `CleanCPU.exe` disponible.

**Pasos:**
1. Copiar `CleanCPU.exe` al equipo sin Python.
2. Ejecutar como Administrador.
3. Ejecutar la secuencia completa de mantenimiento.
4. Generar el reporte HTML.
5. Verificar que todo funciona sin errores de módulo o importación.

**Resultado esperado:**
- La secuencia completa de 9 pasos se ejecuta correctamente.
- El reporte HTML se genera en `C:\ProgramData\CleanCPU\reports\`.
- No hay errores de `ModuleNotFoundError`, `ImportError`, ni rutas de archivo no encontradas.

**Estado:** Pendiente de validación en piloto (prueba de aceptación crítica).

---

### PT-INT-041 — EXE empaquetado accede a rutas de datos (credentials, templates_data)

| Campo | Detalle |
|-------|---------|
| **ID** | PT-INT-041 |
| **Categoría** | EXE ↔ Datos empaquetados |
| **Prioridad** | Alta |
| **Objetivo** | Verificar que los archivos de datos (plantilla Excel, credenciales Google) empaquetados en `datas` de PyInstaller son accesibles correctamente en tiempo de ejecución. |

**Pasos:**
1. Con el EXE en un equipo sin el directorio fuente, intentar generar el reporte Excel FO-TI-19.
2. Verificar en el log si hay errores de ruta de plantilla.

**Resultado esperado:**
- El reporte Excel se genera correctamente (confirma que `templates_data` está empaquetado y accesible via `sys._MEIPASS`).
- No hay `FileNotFoundError` ni `TemplateNotFound` en el log.

---

*Fin de Pruebas de Integración — RADEC Maintenance Program v3.0.0*
*Documento: PT-INT-001 | Área TI RADEC | 2026-04-04*
