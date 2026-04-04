# RADEC Maintenance Program — Catálogo de Casos de Uso
## Documento: CCU-MNT-001 | Versión: 1.0.0 | Fecha: 2026-04-04

---

## CONTROL DE VERSIONES

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2026-04-04 | Área TI RADEC | Versión inicial para piloto |

---

## ÍNDICE DE CASOS DE USO

| ID | Módulo | Nombre |
|----|--------|--------|
| CU-MNT-001 | MNT | Inicio de la aplicación |
| CU-MNT-002 | MNT | Inicio del mantenimiento lógico |
| CU-MNT-003 | SGA | Ejecución de Auditoría de Seguridad (Paso 1) |
| CU-MNT-004 | LMP | Ejecución de Limpieza Interna del Sistema (Paso 2) |
| CU-MNT-005 | SRS | Ejecución de Salud y Reparación del Sistema (Paso 3) |
| CU-MNT-006 | OPT | Ejecución de Optimización de Disco (Paso 4) |
| CU-MNT-007 | MNT | Omisión de pasos duplicados (Pasos 5 y 7) |
| CU-MNT-008 | MNT | Ejecución de Limpieza de Disco del Sistema (Paso 6) |
| CU-MNT-009 | UPD | Ejecución de Verificación de Windows Update (Paso 8) |
| CU-MNT-010 | LNV | Ejecución de Verificación Lenovo Update (Paso 9) |
| CU-MNT-011 | MNT | Cancelación del mantenimiento en curso |
| CU-MNT-012 | MNT | Visualización de resultados inline por paso |
| CU-RPT-001 | RPT | Generación de reporte de mantenimiento |
| CU-INV-001 | INV | Consulta de inventario del sistema |
| CU-OFC-001 | OFC | Detección de instalación de Microsoft Office |
| CU-OFC-002 | OFC | Inspección del estado de licencia de Office |
| CU-OFC-003 | OFC | Activación de Office con clave de producto |
| CU-OFC-004 | OFC | Manejo de escenarios de Office no soportados |

---

## CU-MNT-001 — Inicio de la aplicación

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-001 |
| **Módulo** | MNT — Mantenimiento Lógico / Sistema General |
| **Objetivo** | Iniciar la aplicación CleanCPU en el equipo del usuario final, elevar privilegios mediante UAC y abrir la interfaz de usuario en el navegador predeterminado |
| **Actor principal** | Técnico TI de campo |
| **Actores secundarios** | Sistema operativo Windows (UAC), navegador web predeterminado del equipo, servidor Waitress interno |
| **Precondiciones** | El archivo `CleanCPU.exe` se encuentra disponible en el equipo. El equipo ejecuta Windows 10/11 x64. El puerto 5000 de localhost está libre. |
| **Disparador** | El técnico hace doble clic o usa "Ejecutar como administrador" sobre `CleanCPU.exe`. |

### Flujo principal

1. El técnico hace clic derecho sobre `CleanCPU.exe` y selecciona "Ejecutar como administrador".
2. Windows presenta el cuadro de diálogo UAC solicitando confirmación de elevación.
3. El técnico confirma la elevación con credenciales de administrador local.
4. El EXE inicia el servidor Waitress en `http://127.0.0.1:5000`.
5. Tras 5 a 15 segundos de inicialización, la aplicación abre automáticamente el navegador predeterminado en `http://127.0.0.1:5000`.
6. El panel principal muestra el hostname del equipo, el usuario activo, el estado de elevación ("Administrador: Sí") y los accesos a todos los módulos.

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-MNT-001-A | El técnico ejecuta el EXE sin "Ejecutar como administrador" (sin elevación) | La aplicación inicia normalmente pero el indicador de elevación muestra "Administrador: No". Las acciones que requieren administrador serán omitidas con mensaje explicativo durante el mantenimiento. |
| FA-MNT-001-B | El navegador no se abre automáticamente | El técnico abre manualmente `http://127.0.0.1:5000` en cualquier navegador. |

### Excepciones / Errores

| ID | Condición | Resultado |
|----|-----------|-----------|
| EX-MNT-001-A | Puerto 5000 ocupado por otro proceso | El servidor no puede iniciar. El navegador no abre. El técnico debe identificar y detener el proceso que ocupa el puerto, luego reiniciar el EXE. |
| EX-MNT-001-B | Antivirus bloquea el EXE | Windows muestra error de acceso denegado o el antivirus cuarentena el archivo. El Coordinador TI debe agregar `CleanCPU.exe` a las exclusiones del antivirus. |
| EX-MNT-001-C | Técnico deniega el cuadro UAC | El EXE no se ejecuta con elevación. Ver FA-MNT-001-A. |

### Postcondiciones

- El servidor Waitress está activo en `http://127.0.0.1:5000`.
- El navegador muestra la interfaz de la aplicación.
- El estado de elevación es visible en el panel principal.
- Los logs de la aplicación se escriben en `C:\ProgramData\CleanCPU\logs\app.log`.

### Reglas de negocio / técnicas

- RN-001: El EXE incluye la directiva `uac_admin=True` en el spec de PyInstaller. Windows solicitará elevación UAC automáticamente al lanzar el ejecutable.
- RN-002: El servidor escucha exclusivamente en `127.0.0.1` (localhost). No es accesible desde otros equipos de la red.
- RN-003: Si `C:\ProgramData\CleanCPU\logs\` no es escribible, los logs se redirigen a un directorio local alternativo. La aplicación no falla por problemas de log.

---

## CU-MNT-002 — Inicio del mantenimiento lógico

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-002 |
| **Módulo** | MNT — Mantenimiento Lógico |
| **Objetivo** | Iniciar la secuencia de nueve pasos de mantenimiento preventivo lógico para el equipo intervenido |
| **Actor principal** | Técnico TI de campo |
| **Actores secundarios** | Motor de ejecución (command_runner), hilo de ejecución en segundo plano |
| **Precondiciones** | La aplicación está iniciada (CU-MNT-001 completado). El técnico ha navegado a la sección "Mantenimiento Lógico". El equipo no tiene otro mantenimiento activo en curso. |
| **Disparador** | El técnico hace clic en el botón "Iniciar Mantenimiento Lógico". |

### Flujo principal

1. El técnico hace clic en "Iniciar Mantenimiento Lógico".
2. El servidor genera un identificador único de sesión de mantenimiento.
3. Los nueve pasos se inicializan en estado "Pendiente" en la pantalla.
4. La tarjeta de progreso global se muestra en la parte superior.
5. El botón "Iniciar" se reemplaza por "Cancelar mantenimiento".
6. El primer paso (Auditoría de Seguridad) cambia a estado "En ejecución".
7. La interfaz inicia el ciclo de polling (consulta al servidor cada 2 segundos) para actualizar el estado de los pasos.
8. Los pasos se ejecutan secuencialmente. Ver CU-MNT-003 al CU-MNT-010 para el detalle de cada paso.
9. Al completar todos los pasos, la sesión cambia a estado "completada".
10. La interfaz muestra la tarjeta de resumen con el botón "Generar Reporte".

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-MNT-002-A | El técnico cancela antes de que todos los pasos terminen | Ver CU-MNT-011 |
| FA-MNT-002-B | Un paso falla con error | El paso se marca como "Fallido"; los siguientes pasos continúan ejecutándose; el mantenimiento no se detiene por un fallo individual |

### Excepciones / Errores

| ID | Condición | Resultado |
|----|-----------|-----------|
| EX-MNT-002-A | Error de red entre navegador y servidor (pérdida de conexión) | El polling continúa intentando cada 2 segundos. La ejecución en segundo plano no se interrumpe. |
| EX-MNT-002-B | Excepción no controlada en un paso | El paso se registra como "Fallido" con el mensaje de la excepción. La secuencia continúa. |

### Postcondiciones

- Existe una sesión de mantenimiento con ID único.
- Todos los pasos tienen un estado final (completado, omitido, fallido o cancelado).
- La sesión está disponible para generación de reporte (CU-RPT-001).

### Reglas de negocio / técnicas

- RN-004: Los pasos 5 (temp_cleanup) y 7 (sfc) siempre se omiten con estado "skipped" sin ejecutar la operación de sistema correspondiente. Esto es intencional para evitar duplicación.
- RN-005: El mantenimiento se ejecuta en un hilo separado (daemon thread). La interfaz web no bloquea durante la ejecución.
- RN-006: Solo puede existir una sesión de mantenimiento activa simultáneamente por instancia de la aplicación.

---

## CU-MNT-003 — Ejecución de Auditoría de Seguridad (Paso 1)

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-003 |
| **Módulo** | SGA — Auditoría de Seguridad |
| **Objetivo** | Ejecutar la inspección interna de indicadores de seguridad y salud del sistema mediante herramientas nativas de Windows |
| **Actor principal** | Sistema (ejecución automática en secuencia) |
| **Actores secundarios** | PowerShell (servicios, actualizaciones, reinicio pendiente, inicio de sesión), DISM, SFC |
| **Precondiciones** | Sesión de mantenimiento activa. Este es el primer paso; se ejecuta inmediatamente al iniciar el mantenimiento. |
| **Disparador** | Inicio automático de secuencia de mantenimiento (CU-MNT-002). |

### Flujo principal

1. El paso cambia a estado "En ejecución".
2. La aplicación ejecuta en secuencia las siguientes inspecciones:
   - Verificación de reinicio pendiente (registro: RebootPending, RebootRequired, PendingFileRenameOperations).
   - Verificación de espacio libre en disco C: (umbral crítico: < 5 GB; advertencia: < 15 GB).
   - Verificación de servicios críticos detenidos (WinDefend, mpssvc, EventLog, wuauserv, Dhcp, Dnscache, LanmanWorkstation).
   - DISM /Online /Cleanup-Image /CheckHealth (requiere Administrador).
   - SFC /scannow (requiere Administrador; puede tomar hasta 15 minutos).
   - Listado de programas de inicio automático (Win32_StartupCommand, máximo 25 entradas).
   - Verificación de actualizaciones de Windows pendientes (COM: Microsoft.Update.Session).
3. Se construye la lista de hallazgos por severidad (crítico, advertencia, informativo).
4. El paso cambia a estado "Completado" con un mensaje resumen.
5. Los hallazgos individuales están disponibles para el reporte.

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-MNT-003-A | La aplicación no tiene permisos de Administrador | DISM y SFC se registran en `admin_skipped`. El paso continúa sin ellos y se reporta como completado con advertencia de herramientas omitidas. |
| FA-MNT-003-B | La consulta COM de Windows Update falla | La advertencia se registra pero el paso continúa. No se genera hallazgo de error crítico. |

### Excepciones / Errores

| ID | Condición | Resultado |
|----|-----------|-----------|
| EX-MNT-003-A | SFC no puede reparar archivos dañados | Hallazgo "warning": SFC encontró infracciones no reparadas. Acción recomendada: ejecutar DISM /RestoreHealth. |
| EX-MNT-003-B | DISM reporta imagen reparable | Hallazgo "warning": imagen marcada como reparable. Acción recomendada: DISM /RestoreHealth. |
| EX-MNT-003-C | Disco C: con menos de 5 GB libres | Hallazgo "critical": espacio en disco crítico. Acción recomendada: liberar espacio urgentemente. |

### Postcondiciones

- El paso tiene estado "completado".
- La lista `findings` contiene hallazgos con severidad y evidencia.
- La lista `recommended_actions` contiene acciones pendientes para el reporte.
- Los campos `admin_skipped`, `warnings`, `errors` están poblados según corresponda.

### Reglas de negocio / técnicas

- RN-007: El paso siempre retorna status "completed" (nunca "failed") independientemente de los hallazgos individuales; el estado "failed" solo ocurriría por una excepción no controlada a nivel de Python.
- RN-008: Las operaciones con `requires_admin=True` que fallan por falta de privilegios se registran en `admin_skipped`, no en `errors`.
- RN-009: SFC tiene timeout de 900 segundos (15 minutos). Si supera el límite, se registra como timeout.

---

## CU-MNT-004 — Ejecución de Limpieza Interna del Sistema (Paso 2)

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-004 |
| **Módulo** | LMP — Limpieza del Sistema |
| **Objetivo** | Limpiar archivos temporales, caché de Internet y caché DNS mediante rutinas nativas de la aplicación |
| **Actor principal** | Sistema (ejecución automática en secuencia) |
| **Actores secundarios** | Módulo de limpieza interno (`services/cleanup.py`), ipconfig (caché DNS) |
| **Precondiciones** | Paso 1 (CU-MNT-003) completado. |
| **Disparador** | Finalización del Paso 1. |

### Flujo principal

1. El paso ejecuta en secuencia:
   - Limpieza de TEMP del usuario (`%TEMP%`).
   - Limpieza de Windows\Temp (`C:\Windows\Temp`).
   - Limpieza de Prefetch (`C:\Windows\Prefetch`).
   - Limpieza de caché de Internet (INetCache: `%LOCALAPPDATA%\Microsoft\Windows\INetCache`).
   - Vaciado de caché DNS (`ipconfig /flushdns`).
2. Se contabiliza el espacio liberado en MB por cada operación.
3. El paso retorna el total de MB liberados y el resultado individual de cada operación.
4. El paso cambia a estado "Completado" con mensaje: "Limpieza completada: X MB liberados en 5 operaciones."

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-MNT-004-A | Una operación de limpieza falla (ej: archivos bloqueados por el sistema) | El error se registra en `errors`; las operaciones restantes continúan; el paso se completa con mensaje de advertencia sobre errores menores. |
| FA-MNT-004-B | No hay archivos temporales que eliminar en alguna carpeta | La operación reporta 0 MB liberados; no es un error. |

### Postcondiciones

- Los directorios de temporales están limpios o parcialmente limpios.
- `space_freed_mb` contiene el total de espacio liberado.
- Los pasos 5 (temp_cleanup) y 7 (sfc) de la secuencia quedan automáticamente marcados para omisión.

### Reglas de negocio / técnicas

- RN-010: Los archivos en uso por el sistema operativo no pueden eliminarse; esto se registra como error menor, no como fallo del paso.
- RN-011: La limpieza de Prefetch solo procede si la aplicación tiene permisos de escritura sobre `C:\Windows\Prefetch`.

---

## CU-MNT-005 — Ejecución de Salud y Reparación del Sistema (Paso 3)

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-005 |
| **Módulo** | SRS — Salud y Reparación del Sistema |
| **Objetivo** | Ejecutar DISM /CheckHealth, SFC /scannow, verificar servicios críticos, reinicio pendiente, actualizaciones y espacio en disco |
| **Actor principal** | Sistema (ejecución automática en secuencia) |
| **Actores secundarios** | DISM, SFC, PowerShell (servicios, actualizaciones, espacio), Windows Update Agent COM |
| **Precondiciones** | Paso 2 (CU-MNT-004) completado. Requiere Administrador para DISM y SFC. |
| **Disparador** | Finalización del Paso 2. |

### Flujo principal

Idéntico al Paso 1 (CU-MNT-003) en términos de operaciones ejecutadas. La secuencia en Paso 3 reproduce las mismas verificaciones con datos actualizados post-limpieza.

1. Reinicio pendiente (registro).
2. Espacio en disco C:.
3. Servicios críticos.
4. DISM /Online /Cleanup-Image /CheckHealth (requiere Admin).
5. SFC /scannow (requiere Admin; hasta 15 minutos).
6. Programas de inicio (Win32_StartupCommand).
7. Actualizaciones pendientes (COM).

### Postcondiciones

- Hallazgos actualizados post-limpieza del Paso 2.
- Si SFC reparó archivos en el Paso 1, en el Paso 3 debería reportar "sin infracciones".

### Reglas de negocio / técnicas

- RN-012: El Paso 3 ejecuta SFC nuevamente aunque ya se ejecutó en el Paso 1. Esto permite detectar si los archivos del sistema quedaron en buen estado después de las operaciones de limpieza.

---

## CU-MNT-006 — Ejecución de Optimización de Disco (Paso 4)

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-006 |
| **Módulo** | OPT — Optimización de Disco |
| **Objetivo** | Optimizar el disco C: mediante `defrag /O`, que ejecuta TRIM en SSD o desfragmentación en HDD según el tipo de unidad detectado por Windows |
| **Actor principal** | Sistema (ejecución automática en secuencia) |
| **Actores secundarios** | Comando `defrag` del sistema operativo Windows |
| **Precondiciones** | Paso 3 (CU-MNT-005) completado. Requiere Administrador. |
| **Disparador** | Finalización del Paso 3. |

### Flujo principal

1. La aplicación ejecuta `defrag C: /O` con `requires_admin=True` y timeout de 600 segundos.
2. Windows identifica automáticamente el tipo de unidad (SSD o HDD).
3. En SSD: ejecuta ReTrim (liberación de bloques no utilizados).
4. En HDD: ejecuta desfragmentación del disco.
5. El paso retorna estado "Completado" con mensaje confirmando la operación.

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-MNT-006-A | Sin permisos de Administrador | El paso retorna estado "Omitido" con mensaje indicando que se requiere ejecutar como Administrador. |

### Excepciones / Errores

| ID | Condición | Resultado |
|----|-----------|-----------|
| EX-MNT-006-A | defrag retorna código de error | El paso retorna estado "Fallido" con el mensaje de error de defrag. |
| EX-MNT-006-B | Timeout de 600 segundos superado | El paso retorna estado "Fallido" con indicación de timeout. |

### Reglas de negocio / técnicas

- RN-013: El flag `/O` es la operación unificada de optimización. No se utiliza `/L` (solo SSD) ni `/U /V` (solo HDD) para simplificar la lógica y evitar errores de detección del tipo de unidad.
- RN-014: `defrag /O` no está permitido para unidades que no sean el volumen del sistema en la allowlist actual. Solo se ejecuta sobre `C:`.

---

## CU-MNT-007 — Omisión de pasos duplicados (Pasos 5 y 7)

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-007 |
| **Módulo** | MNT — Mantenimiento Lógico |
| **Objetivo** | Documentar el comportamiento esperado de omisión automática de los pasos 5 y 7 que duplicarían operaciones ya ejecutadas en los pasos 2 y 3 respectivamente |
| **Actor principal** | Sistema (ejecución automática) |
| **Precondiciones** | Pasos 2 y 3 completados. |

### Flujo principal (Paso 5 — temp_cleanup)

1. El motor de mantenimiento invoca el manejador `_step_temp_cleanup()`.
2. El manejador retorna inmediatamente `status: 'skipped'` con mensaje: "TEMP, Windows\Temp y Prefetch ya fueron limpiados en 'Limpieza Interna del Sistema'. Omitido para evitar duplicación."
3. El paso se muestra en pantalla como "Omitido" (ícono ⚠️, color naranja).

### Flujo principal (Paso 7 — sfc)

1. El motor de mantenimiento invoca el manejador `_step_sfc()`.
2. El manejador retorna inmediatamente `status: 'skipped'` con mensaje: "SFC /scannow ya fue ejecutado en 'Salud y Reparación del Sistema'. Omitido para evitar duplicación."
3. El paso se muestra en pantalla como "Omitido".

### Reglas de negocio / técnicas

- RN-015: La omisión de estos pasos es una decisión de diseño intencional. No representa un error ni una deficiencia de la ejecución.
- RN-016: El técnico no debe interpretar el estado "Omitido" de los pasos 5 y 7 como un problema del equipo ni de la aplicación.

---

## CU-MNT-008 — Ejecución de Limpieza de Disco del Sistema (Paso 6)

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-008 |
| **Módulo** | MNT |
| **Objetivo** | Ejecutar la herramienta de Limpieza de Disco de Windows (`cleanmgr /sagerun:1`) para limpiar categorías de archivos del sistema previamente configuradas |
| **Actor principal** | Sistema (ejecución automática en secuencia) |
| **Actores secundarios** | `cleanmgr.exe` del sistema operativo |
| **Precondiciones** | Paso 5 (CU-MNT-007) completado. Requiere Administrador. Perfil `/sageset:1` configurado previamente en el equipo. |
| **Disparador** | Finalización del Paso 5. |

### Flujo principal

1. La aplicación ejecuta `cleanmgr /sagerun:1` con `requires_admin=True` y timeout de 300 segundos.
2. cleanmgr ejecuta la limpieza según las categorías configuradas en el perfil 1 del equipo.
3. El paso retorna estado "Completado" con mensaje y nota sobre la necesidad de que `/sageset:1` haya sido configurado.

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-MNT-008-A | Sin permisos de Administrador | Estado "Omitido" con instrucción de ejecutar como Administrador. |

### Excepciones / Errores

| ID | Condición | Resultado |
|----|-----------|-----------|
| EX-MNT-008-A | cleanmgr retorna error | Estado "Fallido" con el error reportado. |

### Reglas de negocio / técnicas

- RN-017: Si el perfil `/sageset:1` no ha sido configurado en el equipo, `cleanmgr /sagerun:1` puede ejecutar sin limpiar ningún archivo. El paso reportará "completado" igualmente, pero el técnico debe configurar el perfil manualmente la primera vez.

---

## CU-MNT-009 — Ejecución de Verificación de Windows Update (Paso 8)

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-009 |
| **Módulo** | UPD — Windows Update |
| **Objetivo** | Solicitar al servicio de Windows Update que ejecute un escaneo de actualizaciones disponibles |
| **Actor principal** | Sistema (ejecución automática en secuencia) |
| **Actores secundarios** | `UsoClient.exe`, PowerShell (versión de Windows) |
| **Precondiciones** | Paso 7 (CU-MNT-007) completado. Requiere Administrador. |
| **Disparador** | Finalización del Paso 7. |

### Flujo principal

1. La aplicación ejecuta `UsoClient StartScan` con `requires_admin=True` y timeout de 120 segundos.
2. La aplicación consulta la versión de Windows (`$env:OSVersion.Version`).
3. El escaneo se inicia en segundo plano en el servicio de Windows Update.
4. El paso retorna estado "Completado" con mensaje: "Escaneo de actualizaciones solicitado a Windows Update. Windows: X.X.X.X"

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-MNT-009-A | Sin permisos de Administrador | Estado "Omitido" con la versión de Windows y mensaje de que se requiere Administrador. |
| FA-MNT-009-B | UsoClient no disponible en el equipo (Windows muy antiguo o versión limitada) | Estado "Completado" con mensaje: "UsoClient no disponible en este equipo. Revise Windows Update manualmente." |

### Reglas de negocio / técnicas

- RN-018: `UsoClient StartScan` inicia el escaneo de forma asíncrona. La aplicación no espera el resultado del escaneo. El técnico debe verificar manualmente el estado en Configuración → Windows Update.
- RN-019: Si `UsoClient` retorna código de error distinto de "command not found", el paso se reporta como completado con aviso, no como fallido, ya que el escaneo pudo haber iniciado igualmente.

---

## CU-MNT-010 — Ejecución de Verificación Lenovo Update (Paso 9)

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-010 |
| **Módulo** | LNV — Lenovo Update |
| **Objetivo** | Lanzar Lenovo Vantage o Lenovo System Update para que el técnico verifique manualmente las actualizaciones de controladores Lenovo |
| **Actor principal** | Sistema (ejecución automática en secuencia) |
| **Actores secundarios** | `Lenovo.Vantage.exe` o `tvsu.exe` |
| **Precondiciones** | Paso 8 (CU-MNT-009) completado. |
| **Disparador** | Finalización del Paso 8. |

### Flujo principal

1. La aplicación verifica la existencia del ejecutable en las rutas estándar:
   - `C:\Program Files (x86)\Lenovo\VantageService\Lenovo.Vantage.exe`
   - `C:\Program Files\Lenovo\VantageService\Lenovo.Vantage.exe`
   - `C:\Program Files (x86)\Lenovo\System Update\tvsu.exe`
2. Si se encuentra el ejecutable, la aplicación lanza el proceso usando `start "" "<ruta>"`.
3. El paso retorna estado "Completado" con mensaje: "Lenovo Update iniciado. Verifique actualizaciones manualmente."

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-MNT-010-A | Ningún ejecutable de Lenovo encontrado | Estado "Omitido" con mensaje: "Lenovo Vantage/System Update no está instalado." |
| FA-MNT-010-B | El ejecutable existe pero el lanzamiento falla | Estado "Omitido" con mensaje: "No se pudo iniciar automáticamente — ábralo manualmente desde el Menú Inicio." |

### Reglas de negocio / técnicas

- RN-020: El paso no verifica el resultado de la ejecución de Lenovo Vantage. Solo confirma que el proceso fue lanzado correctamente. El técnico debe revisar manualmente la interfaz de Lenovo Vantage.
- RN-021: Si el lanzamiento falla, el estado es "skipped" (no "failed"), ya que no es responsabilidad de la aplicación gestionar Lenovo Vantage una vez lanzado.

---

## CU-MNT-011 — Cancelación del mantenimiento en curso

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-011 |
| **Módulo** | MNT — Mantenimiento Lógico |
| **Objetivo** | Permitir al técnico interrumpir el mantenimiento antes de que concluya, marcando los pasos restantes como cancelados |
| **Actor principal** | Técnico TI de campo |
| **Actores secundarios** | Motor de ejecución en segundo plano |
| **Precondiciones** | Una sesión de mantenimiento está en curso. |
| **Disparador** | El técnico hace clic en "Cancelar mantenimiento" y confirma el cuadro de diálogo. |

### Flujo principal

1. El técnico hace clic en "Cancelar mantenimiento".
2. La interfaz muestra un cuadro de confirmación: "¿Está seguro de que desea cancelar el mantenimiento? Los pasos restantes no se ejecutarán."
3. El técnico confirma.
4. El servidor registra la señal de cancelación en la sesión (`cancelled: true`).
5. Al finalizar el paso actualmente en ejecución, el motor verifica la señal de cancelación.
6. El paso actualmente en ejecución concluye normalmente (no se interrumpe a la mitad).
7. Los pasos restantes se marcan como "Cancelado" con mensaje: "Cancelado por el usuario."
8. La sesión cambia a estado "completada" (con pasos cancelados).
9. El botón "Generar Reporte" permanece disponible con los resultados parciales.

### Reglas de negocio / técnicas

- RN-022: El paso en ejecución al momento de la cancelación **no** es interrumpido abruptamente. Concluye su ciclo natural. Solo los pasos que aún no iniciaron se cancelan.
- RN-023: La cancelación del mantenimiento no revierte las acciones ya ejecutadas (no deshace la limpieza de temporales ni SFC).

---

## CU-MNT-012 — Visualización de resultados inline por paso

| Campo | Detalle |
|-------|---------|
| **ID** | CU-MNT-012 |
| **Módulo** | MNT — UI de Mantenimiento |
| **Objetivo** | Presentar al técnico el resultado de cada paso directamente en la fila del paso, sin necesidad de desplazarse a la consola inferior |
| **Actor principal** | Técnico TI de campo |
| **Precondiciones** | Una sesión de mantenimiento está en ejecución o ha finalizado. |
| **Disparador** | Un paso cambia a estado terminal (completado, omitido, fallido, cancelado) durante el polling. |

### Flujo principal

1. La interfaz detecta la transición de "en ejecución" a estado terminal para un paso.
2. La fila del paso destella en verde (completado) o rojo (fallido).
3. En la fila del paso, se muestra:
   - **Mensaje principal** (13px, fondo color-codificado): verde, rojo u naranja según el estado.
   - **Insignias resumen** (cuando aplica): MB liberados, hallazgos críticos, advertencias, acciones recomendadas.
   - **Panel de detalle** (cuando aplica): errores individuales, advertencias, acciones recomendadas específicas (máximo 3 de cada tipo; con indicación de "+ N más").
4. El técnico puede leer el resultado del paso sin desplazarse a ningún otro componente de la pantalla.
5. El tiempo de ejecución del paso se muestra en la esquina derecha de la fila.

### Reglas de negocio / técnicas

- RN-024: El panel de detalle muestra un máximo de 3 errores y 3 acciones recomendadas inline. Para el detalle completo, el técnico debe generar el reporte HTML.
- RN-025: El desplazamiento automático ocurre una vez por paso, cuando cambia a estado "en ejecución", y centra el paso activo en el viewport.

---

## CU-RPT-001 — Generación de reporte de mantenimiento

| Campo | Detalle |
|-------|---------|
| **ID** | CU-RPT-001 |
| **Módulo** | RPT — Reportes |
| **Objetivo** | Generar los reportes de servicio formales (FO-TI-19, HTML, Excel, Google Sheets, carpeta de red) a partir de los resultados de una sesión de mantenimiento completada |
| **Actor principal** | Técnico TI de campo |
| **Actores secundarios** | `services/maintenance_report.py`, API de Google Sheets (opcional), carpeta de red RADEC (opcional) |
| **Precondiciones** | Una sesión de mantenimiento ha finalizado (completada o con pasos cancelados). |
| **Disparador** | El técnico hace clic en "Generar Reporte" en la tarjeta de resumen. |

### Flujo principal

1. El técnico hace clic en "Generar Reporte".
2. La interfaz muestra "Generando reportes..." en la consola de salida.
3. El servidor invoca `generate_full_report(session)`.
4. Se generan en paralelo:
   - Reporte HTML local en `C:\ProgramData\CleanCPU\reports\`.
   - Formulario FO-TI-19 (formato RADEC).
   - Versión Excel del FO-TI-19.
   - Registro en Google Sheets (si credenciales y conectividad disponibles).
   - Copia en carpeta de red RADEC (si conectividad y ruta configurada).
5. La interfaz muestra el resultado de cada formato generado con la ruta del archivo local o el estado de los destinos remotos.

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-RPT-001-A | Google Sheets no disponible (sin conectividad o credenciales) | Se genera igual el reporte local; Google Sheets se reporta como "Omitido" con motivo. |
| FA-RPT-001-B | Carpeta de red no accesible | Se genera igual el reporte local; carpeta de red se reporta con el error específico. |

### Postcondiciones

- Al menos el reporte HTML local ha sido generado en `C:\ProgramData\CleanCPU\reports\`.
- El técnico dispone del formulario FO-TI-19 para entregar al Coordinador TI.

---

## CU-INV-001 — Consulta de inventario del sistema

| Campo | Detalle |
|-------|---------|
| **ID** | CU-INV-001 |
| **Módulo** | INV — Inventario del Sistema |
| **Objetivo** | Consultar y mostrar los datos técnicos actualizados del equipo intervenido |
| **Actor principal** | Técnico TI de campo |
| **Actores secundarios** | PowerShell (WMI/CIM), `services/system_inventory.py` |
| **Precondiciones** | La aplicación está iniciada. |
| **Disparador** | El técnico navega al módulo de Inventario / Diagnósticos. |

### Flujo principal

1. El técnico accede al módulo de Inventario.
2. La aplicación consulta WMI/CIM mediante PowerShell para obtener los datos del equipo.
3. Se presenta la información en pantalla: hostname, usuario, fabricante, modelo, serie, UUID, dominio, OS, procesador, RAM (con tipo DDR), discos, IP, MAC Ethernet, MAC WiFi, y datos de Office.
4. Los datos de inventario se incorporan automáticamente en los reportes de mantenimiento.

### Reglas de negocio / técnicas

- RN-026: Si un campo no puede obtenerse (WMI no responde, campo no disponible en el hardware), se reporta como "N/A" en lugar de generar un error.
- RN-027: El inventario es una captura en el momento de la consulta. No se actualiza automáticamente durante el mantenimiento.

---

## CU-OFC-001 — Detección de instalación de Microsoft Office

| Campo | Detalle |
|-------|---------|
| **ID** | CU-OFC-001 |
| **Módulo** | OFC — Licencia Microsoft Office |
| **Objetivo** | Detectar si Microsoft Office está instalado en el equipo y mostrar los detalles de la instalación |
| **Actor principal** | Técnico TI de campo (disparo automático al abrir el módulo) |
| **Actores secundarios** | Registro de Windows, `services/office_tools.py`, `services/system_inventory.py` |
| **Precondiciones** | La aplicación está iniciada. El técnico ha navegado al módulo "Licencia Office". |
| **Disparador** | Carga de la página del módulo Office (automático, sin interacción del técnico). |

### Flujo principal

1. Al cargar la página, la función `loadInfo()` consulta `/office/api/info`.
2. El servidor consulta el registro de Windows y las rutas de `ospp.vbs` sin requerir privilegios de Administrador.
3. Se muestran: nombre del producto, versión, plataforma, canal, Release IDs, y ruta de `ospp.vbs`.

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-OFC-001-A | Office no detectado en el registro pero `ospp.vbs` existe en una ruta estándar | Se muestra `installed: true` indicando detección parcial. |
| FA-OFC-001-B | Office no instalado ni `ospp.vbs` encontrado | Se muestra: "Microsoft Office no detectado en este equipo." |

---

## CU-OFC-002 — Inspección del estado de licencia de Office

| Campo | Detalle |
|-------|---------|
| **ID** | CU-OFC-002 |
| **Módulo** | OFC — Licencia Microsoft Office |
| **Objetivo** | Consultar el estado de activación actual de Microsoft Office mediante `cscript ospp.vbs /dstatus` |
| **Actor principal** | Técnico TI de campo |
| **Actores secundarios** | `cscript.exe`, `ospp.vbs`, `services/office_tools.py` |
| **Precondiciones** | Office instalado con `ospp.vbs` accesible. Requiere Administrador. |
| **Disparador** | El técnico hace clic en "Inspeccionar licencia". |

### Flujo principal

1. La interfaz deshabilita el botón y muestra "Inspeccionando...".
2. El servidor localiza `ospp.vbs` en las rutas estándar.
3. Ejecuta `cscript //nologo <ruta_ospp.vbs> /dstatus` con `requires_admin=True`.
4. Parsea la salida para extraer: nombre, estado de licencia, últimos 5 caracteres, Product ID, gracia restante.
5. Muestra el resultado estructurado en la pantalla.
6. La salida completa de ospp.vbs se muestra en un bloque de código expandible para diagnóstico.

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-OFC-002-A | Sin permisos de Administrador | Muestra: "Se requieren permisos de Administrador para inspeccionar la licencia de Office." |
| FA-OFC-002-B | ospp.vbs no encontrado | Muestra: "No se encontró ospp.vbs." |

---

## CU-OFC-003 — Activación de Office con clave de producto

| Campo | Detalle |
|-------|---------|
| **ID** | CU-OFC-003 |
| **Módulo** | OFC — Licencia Microsoft Office |
| **Objetivo** | Instalar una clave de producto válida y activar Microsoft Office mediante los mecanismos oficiales de Microsoft (`ospp.vbs`) |
| **Actor principal** | Técnico TI de campo |
| **Actores secundarios** | `cscript.exe`, `ospp.vbs /inpkey`, `ospp.vbs /act`, servidores de activación de Microsoft |
| **Precondiciones** | Office instalado. `ospp.vbs` accesible. Administrador disponible. Clave de producto legítima disponible. |
| **Disparador** | El técnico ingresa una clave de 25 caracteres y hace clic en "Activar Office". |

### Flujo principal

1. El técnico ingresa la clave en el campo de texto (el campo formatea guiones automáticamente).
2. La interfaz valida que la clave tenga 25 caracteres antes de enviar.
3. La interfaz deshabilita el botón y limpia el campo inmediatamente al enviar.
4. El servidor valida el formato de la clave con regex (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX).
5. El servidor ejecuta: `cscript //nologo <ospp.vbs> /inpkey:<clave>`.
6. Si la instalación de la clave es exitosa, ejecuta: `cscript //nologo <ospp.vbs> /act`.
7. La clave se sobreescribe en memoria inmediatamente después de iniciar el subproceso.
8. El resultado se muestra en pantalla con la clave enmascarada (XXXXX-XXXXX-XXXXX-XXXXX-YYYYY).

### Flujos alternativos

| ID | Condición | Acciones alternativas |
|----|-----------|----------------------|
| FA-OFC-003-A | La activación requiere conexión a Internet pero no hay conectividad | ospp.vbs retorna código de error de activación. Se muestra el error con el código específico. |

### Excepciones / Errores

| ID | Condición | Resultado en pantalla |
|----|-----------|----------------------|
| EX-OFC-003-A | Formato de clave inválido | "Formato de clave inválido. El formato debe ser XXXXX-XXXXX-XXXXX-XXXXX-XXXXX." |
| EX-OFC-003-B | Clave no compatible con la edición instalada | Error de ospp.vbs /inpkey con código de error específico de Microsoft. |
| EX-OFC-003-C | Instalación exitosa pero activación falla | "La clave fue instalada pero la activación falló. Detalle: <código de error de ospp.vbs>." |
| EX-OFC-003-D | Sin permisos de Administrador | "Se requieren permisos de Administrador para instalar la clave de producto." |

### Postcondiciones

- Si exitoso: Office queda activado con la nueva clave.
- La clave nunca es visible en logs, reportes ni en la pantalla (solo últimos 5 caracteres).
- El campo de ingreso de clave está vacío.

### Reglas de negocio / técnicas

- RN-028: La clave de producto se maneja en memoria solo el tiempo mínimo necesario para pasarla como argumento al subproceso. Inmediatamente después se sobreescribe con `None`.
- RN-029: La descripción del comando registrada en los logs es `ospp.vbs /inpkey:***` (con la clave enmascarada), nunca la clave real.
- RN-030: Solo se usa el mecanismo oficial de Microsoft (`ospp.vbs`). Ningún otro mecanismo de activación (KMS ilegal, MAK no autorizado, activadores de terceros) está implementado ni es invocado.

---

## CU-OFC-004 — Manejo de escenarios de Office no soportados

| Campo | Detalle |
|-------|---------|
| **ID** | CU-OFC-004 |
| **Módulo** | OFC — Licencia Microsoft Office |
| **Objetivo** | Informar al técnico de forma clara cuando el módulo de Office no puede operar por condiciones de entorno específicas |
| **Actor principal** | Sistema (detección automática) |
| **Precondiciones** | El técnico ha navegado al módulo Office o ha intentado ejecutar una operación. |

### Flujo principal (múltiples escenarios)

| Escenario | Condición detectada | Mensaje mostrado |
|-----------|--------------------|--------------------|
| Office no instalado | Registro y ospp.vbs ausentes | "Microsoft Office no detectado en este equipo." |
| ospp.vbs en ruta no estándar | Registro detecta Office pero ospp.vbs no está en ninguna ruta conocida | "No se encontró ospp.vbs. Office puede no estar instalado o estar en una ruta no estándar." |
| Sin permisos de Administrador | `requires_admin` retornado por command_runner | "Se requieren permisos de Administrador para inspeccionar/activar la licencia de Office." |
| Plataforma no soportada | Ejecución fuera de Windows | "Inspección/Activación de Office solo disponible en Windows." |
| Clave con formato inválido | Regex de formato no coincide | "Formato de clave inválido. El formato debe ser XXXXX-XXXXX-XXXXX-XXXXX-XXXXX." |

### Reglas de negocio / técnicas

- RN-031: El módulo nunca falla silenciosamente. Todo escenario no soportado genera un mensaje específico y descriptivo para el técnico.
- RN-032: El estado de la respuesta siempre es uno de: `success`, `requires_admin`, `ospp_not_found`, `office_not_found`, `invalid_key`, `inpkey_failed`, `activation_failed`, `error`, `not_applicable`. No se usan estados genéricos.

---

*Fin del Catálogo de Casos de Uso — RADEC Maintenance Program v3.0.0*
*Documento: CCU-MNT-001 | Área TI RADEC | 2026-04-04*
