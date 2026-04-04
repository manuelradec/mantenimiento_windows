# RADEC Maintenance Program — Casos de Prueba Funcionales
## Documento: CPF-MNT-001 | Versión: 1.0.0 | Fecha: 2026-04-04

---

## CONTROL DE VERSIONES

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2026-04-04 | Área TI RADEC | Versión inicial para piloto |

---

## CONVENCIONES

| Prioridad | Significado |
|-----------|-------------|
| Alta | Funcionalidad crítica. Falla bloquea el uso de la aplicación. |
| Media | Funcionalidad importante. Falla impacta una función específica. |
| Baja | Funcionalidad complementaria. Falla no bloquea operación principal. |

| Tipo | Descripción |
|------|-------------|
| Funcional positivo | Verifica comportamiento correcto con datos/condiciones válidas |
| Funcional negativo | Verifica comportamiento correcto con datos/condiciones inválidas o edge cases |
| Límite | Verifica comportamiento en los límites del dominio de entrada |

---

## MÓDULO: INICIO Y ENTORNO GENERAL

---

### CPF-MNT-001 — Inicio con privilegios de Administrador

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-001 |
| **Módulo** | MNT — Sistema General |
| **Caso de uso relacionado** | CU-MNT-001 |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que la aplicación inicia correctamente cuando se ejecuta con privilegios de Administrador y muestra el estado de elevación correcto en el panel. |

**Precondiciones:**
- `CleanCPU.exe` disponible en el equipo.
- Puerto 5000 libre en `127.0.0.1`.
- Usuario con contraseña de Administrador local.

**Datos de entrada:**
- Acción: clic derecho → "Ejecutar como administrador" → confirmación UAC.

**Pasos de ejecución:**
1. Hacer clic derecho sobre `CleanCPU.exe` y seleccionar "Ejecutar como administrador".
2. Confirmar el cuadro UAC.
3. Esperar hasta 20 segundos.
4. Verificar que el navegador abre `http://127.0.0.1:5000`.
5. Verificar el indicador de elevación en el panel principal.

**Resultado esperado:**
- El navegador muestra la interfaz de la aplicación en `http://127.0.0.1:5000`.
- El indicador de elevación muestra "Administrador: Sí" (o equivalente).
- El hostname del equipo es visible en el panel.
- No hay mensajes de error en la pantalla de inicio.

**Criterios de validación:**
- El indicador de elevación debe indicar modo Administrador.
- El panel principal debe cargarse sin errores de consola del navegador.

**Notas / Evidencia:**
- Pendiente de validación en piloto.

---

### CPF-MNT-002 — Inicio sin privilegios de Administrador

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-002 |
| **Módulo** | MNT — Sistema General |
| **Prioridad** | Alta |
| **Tipo** | Funcional negativo |
| **Objetivo** | Verificar que la aplicación inicia sin errores y comunica correctamente el estado de no-elevación cuando se ejecuta sin privilegios de Administrador. |

**Precondiciones:**
- `CleanCPU.exe` disponible. Puerto 5000 libre.

**Pasos de ejecución:**
1. Ejecutar `CleanCPU.exe` con doble clic (sin "Ejecutar como administrador").
2. Si el UAC aparece, DENEGAR la elevación o ejecutar desde cuenta estándar.
3. Esperar a que el navegador abra.
4. Verificar el indicador de elevación.

**Resultado esperado:**
- La aplicación inicia correctamente (sin errores críticos).
- El indicador muestra "Administrador: No" (o equivalente).
- La aplicación no se cierra ni produce pantalla de error fatal.

**Criterios de validación:**
- La aplicación debe ser funcional aunque sin privilegios.
- No debe producir excepción no controlada visible al usuario.

---

### CPF-MNT-003 — Puerto 5000 ocupado al iniciar

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-003 |
| **Módulo** | MNT — Sistema General |
| **Prioridad** | Alta |
| **Tipo** | Funcional negativo |
| **Objetivo** | Verificar el comportamiento cuando el puerto 5000 está ocupado por otro proceso al intentar iniciar la aplicación. |

**Precondiciones:**
- Existe otro proceso escuchando en `127.0.0.1:5000` (puede simularse con `python -m http.server 5000`).

**Pasos de ejecución:**
1. Iniciar un proceso que ocupe el puerto 5000.
2. Ejecutar `CleanCPU.exe` como Administrador.
3. Observar el comportamiento.

**Resultado esperado:**
- El servidor no inicia o reporta error de binding.
- El navegador no abre la interfaz de la aplicación.
- No produce error fatal silencioso (el técnico debe poder identificar el problema).

**Criterios de validación:**
- Pendiente de validación en piloto: verificar si el EXE muestra mensaje de error o simplemente no abre el navegador.

---

## MÓDULO: MANTENIMIENTO LÓGICO

---

### CPF-MNT-010 — Secuencia completa de mantenimiento con Administrador

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-010 |
| **Módulo** | MNT — Mantenimiento Lógico |
| **Caso de uso relacionado** | CU-MNT-002 al CU-MNT-010 |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que la secuencia de nueve pasos se ejecuta completamente en un equipo con privilegios de Administrador, con los estados esperados por paso. |

**Precondiciones:**
- Aplicación iniciada como Administrador.
- Windows 10/11 x64.
- Espacio libre en C: > 1 GB.

**Datos de entrada:**
- Clic en "Iniciar Mantenimiento Lógico".

**Pasos de ejecución:**
1. Navegar a "Mantenimiento Lógico".
2. Verificar que los 9 pasos se muestran en estado "Pendiente".
3. Hacer clic en "Iniciar Mantenimiento Lógico".
4. Observar la ejecución de cada paso hasta la finalización.
5. Verificar el estado final de cada paso.
6. Verificar que la tarjeta de resumen aparece al finalizar.

**Resultado esperado:**

| Paso | Estado esperado |
|------|----------------|
| 1. Auditoría de Seguridad | Completado |
| 2. Limpieza Interna | Completado |
| 3. Salud y Reparación | Completado |
| 4. Optimización de disco | Completado |
| 5. Archivos temporales adicionales | **Omitido** (comportamiento esperado) |
| 6. Limpieza de disco | Completado |
| 7. Escaneo SFC adicional | **Omitido** (comportamiento esperado) |
| 8. Windows Update | Completado |
| 9. Lenovo Update | Completado u Omitido (según equipo) |

**Criterios de validación:**
- Los pasos 5 y 7 deben aparecer como "Omitido", no como "Fallido".
- Ningún paso debe quedar en estado "En ejecución" después de la finalización.
- La tarjeta de resumen debe mostrar el número correcto de pasos completados/omitidos.

---

### CPF-MNT-011 — Secuencia con operaciones que requieren Administrador omitidas

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-011 |
| **Módulo** | MNT — Mantenimiento Lógico |
| **Prioridad** | Alta |
| **Tipo** | Funcional negativo |
| **Objetivo** | Verificar que los pasos que requieren Administrador se omiten con mensaje honesto cuando la aplicación no está elevada. |

**Precondiciones:**
- Aplicación iniciada SIN privilegios de Administrador.

**Pasos de ejecución:**
1. Iniciar mantenimiento sin elevación.
2. Observar los pasos 4 (defrag), 6 (cleanmgr), 8 (UsoClient), y las sub-operaciones DISM/SFC en los pasos 1 y 3.

**Resultado esperado:**
- Los pasos 4, 6, 8 muestran estado "Omitido" con mensaje que incluye "se requiere ejecutar como Administrador".
- Los pasos 1 y 3 se completan pero con `admin_skipped` incluyendo "DISM /CheckHealth" y "SFC /scannow".
- Ningún paso muestra "Completado" falsamente para una operación que no se ejecutó.

**Criterios de validación:**
- Los mensajes de omisión deben mencionar explícitamente "Administrador".
- No debe haber pasos con estado "Completado" para operaciones que requirieron admin y no se ejecutaron.

---

### CPF-MNT-012 — Indicadores de progreso en ejecución

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-012 |
| **Módulo** | MNT — UI |
| **Prioridad** | Media |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que los indicadores de estado en pantalla funcionan correctamente: fila azul para paso activo, barra animada, contador de tiempo, desplazamiento automático. |

**Pasos de ejecución:**
1. Iniciar mantenimiento con Administrador.
2. Durante la ejecución del Paso 1 (que puede tomar varios minutos): verificar que la fila del Paso 1 tiene fondo azul.
3. Verificar que la barra de progreso animada es visible dentro del paso.
4. Verificar que el contador "En ejecución — MM:SS transcurrido..." avanza cada 2 segundos aproximadamente.
5. Verificar que la pantalla se desplaza automáticamente al paso activo cuando cambia de paso.

**Resultado esperado:**
- Solo el paso actualmente en ejecución tiene fondo azul.
- La barra animada es visible y animada.
- El contador muestra el tiempo transcurrido desde el inicio del paso.
- La pantalla se centra automáticamente en el paso activo al cambiar de paso.

---

### CPF-MNT-013 — Resultado inline de paso completado

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-013 |
| **Módulo** | MNT — UI |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el resultado de un paso completado aparece directamente en la fila del paso, sin requerir desplazamiento a la consola inferior. |

**Pasos de ejecución:**
1. Ejecutar el mantenimiento completo.
2. Al finalizar el Paso 2 (Limpieza Interna), verificar que el mensaje de resultado es visible en la fila del Paso 2 sin mover el scroll.
3. Verificar que el mensaje incluye la cantidad de MB liberados.
4. Verificar que el fondo del mensaje es verde (completado).

**Resultado esperado:**
- El mensaje de resultado es visible en la fila del paso.
- El fondo del mensaje es verde para estado "completado".
- Los MB liberados (si > 0) aparecen como insignia.
- La consola inferior NO es el único lugar donde aparece el resultado.

---

### CPF-MNT-014 — Cancelación del mantenimiento

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-014 |
| **Módulo** | MNT — Mantenimiento Lógico |
| **Caso de uso relacionado** | CU-MNT-011 |
| **Prioridad** | Media |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el mantenimiento puede cancelarse durante la ejecución y que los pasos restantes se marcan correctamente. |

**Pasos de ejecución:**
1. Iniciar mantenimiento con Administrador.
2. Esperar a que el Paso 1 esté en ejecución.
3. Hacer clic en "Cancelar mantenimiento".
4. Verificar que aparece el cuadro de confirmación.
5. Confirmar la cancelación.
6. Observar el estado final de los pasos.

**Resultado esperado:**
- El cuadro de confirmación aparece antes de cancelar.
- El paso en ejecución concluye su ciclo natural.
- Los pasos no ejecutados muestran estado "Cancelado" con mensaje "Cancelado por el usuario."
- El botón "Generar Reporte" permanece disponible.

---

### CPF-MNT-015 — Generación de reporte después del mantenimiento

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-015 |
| **Módulo** | RPT — Reportes |
| **Caso de uso relacionado** | CU-RPT-001 |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el reporte HTML local se genera correctamente después de una sesión de mantenimiento completada. |

**Precondiciones:**
- Sesión de mantenimiento completada (CPF-MNT-010 exitoso).

**Pasos de ejecución:**
1. Hacer clic en "Generar Reporte" en la tarjeta de resumen.
2. Esperar a que la generación concluya.
3. Verificar el mensaje de resultado en la consola de salida.
4. Navegar a `C:\ProgramData\CleanCPU\reports\` y verificar que existe el archivo HTML.
5. Abrir el archivo HTML y verificar su contenido.

**Resultado esperado:**
- El archivo HTML existe en el directorio de reportes.
- El reporte contiene el hostname, fecha, nombre del técnico (si aplica), resultados de cada paso, e inventario del sistema.
- El estado de cada paso en el reporte coincide con lo mostrado en pantalla durante la ejecución.

**Criterios de validación:**
- El reporte HTML debe poder abrirse en cualquier navegador sin errores.
- Los datos de inventario deben estar presentes.

---

### CPF-MNT-016 — Re-ejecución del mantenimiento en la misma sesión

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-MNT-016 |
| **Módulo** | MNT — Mantenimiento Lógico |
| **Prioridad** | Media |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el botón "Ejecutar de nuevo" permite iniciar una nueva sesión de mantenimiento correctamente después de una sesión completada. |

**Pasos de ejecución:**
1. Completar una sesión de mantenimiento (CPF-MNT-010).
2. Hacer clic en "Ejecutar de nuevo" en la tarjeta de resumen.
3. Verificar que todos los pasos vuelven al estado "Pendiente".
4. Iniciar el mantenimiento nuevamente.
5. Verificar que la nueva sesión tiene un nuevo ID de sesión.

**Resultado esperado:**
- Todos los pasos se resetean a "Pendiente".
- Los resultados de la sesión anterior no interfieren con la nueva sesión.
- El contador de progreso global se reinicia a 0%.

---

## MÓDULO: AUDITORÍA DE SEGURIDAD

---

### CPF-SGA-001 — Detección de reinicio pendiente

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-SGA-001 |
| **Módulo** | SGA — Auditoría de Seguridad |
| **Prioridad** | Media |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el Paso 1 detecta correctamente cuando existe una clave de reinicio pendiente en el registro. |

**Precondiciones:**
- Equipo con reinicio pendiente (verificable con `Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'`).

**Pasos de ejecución:**
1. Iniciar mantenimiento en equipo con reinicio pendiente.
2. Esperar a que el Paso 1 complete.
3. Verificar el hallazgo correspondiente en el resultado inline del Paso 1.

**Resultado esperado:**
- El Paso 1 incluye un hallazgo de severidad "warning" con título "Reinicio del sistema pendiente".
- La acción recomendada es "Reiniciar el equipo para completar actualizaciones o cambios pendientes."

---

### CPF-SGA-002 — Detección de espacio crítico en disco

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-SGA-002 |
| **Módulo** | SGA — Auditoría de Seguridad |
| **Prioridad** | Alta |
| **Tipo** | Límite |
| **Objetivo** | Verificar que el Paso 1 clasifica correctamente el espacio en disco: crítico (< 5 GB), advertencia (< 15 GB), normal (>= 15 GB). |

**Casos:**

| Caso | Espacio libre en C: | Severidad esperada |
|------|--------------------|--------------------|
| A | < 5 GB | critical |
| B | Entre 5 GB y 14.9 GB | warning |
| C | >= 15 GB | info |

**Pasos de ejecución:**
- Para cada caso: verificar el espacio disponible en el disco del equipo de prueba, ejecutar el mantenimiento, y verificar el hallazgo de espacio en disco en el Paso 1.

---

### CPF-SGA-003 — Servicios críticos detenidos

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-SGA-003 |
| **Módulo** | SGA — Auditoría de Seguridad |
| **Prioridad** | Media |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el Paso 1 detecta cuando un servicio crítico está detenido. |

**Precondiciones:**
- Equipo donde uno de los servicios monitoreados está detenido (puede simularse deteniendo `Dnscache` en un ambiente de prueba controlado).

**Resultado esperado:**
- Hallazgo de severidad "warning" con el nombre del servicio detenido.
- Acción recomendada con instrucción de revisión del servicio.

---

## MÓDULO: INVENTARIO DEL SISTEMA

---

### CPF-INV-001 — Captura completa de inventario

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-INV-001 |
| **Módulo** | INV — Inventario |
| **Caso de uso relacionado** | CU-INV-001 |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el módulo de inventario captura correctamente todos los campos esperados del equipo. |

**Pasos de ejecución:**
1. Abrir la sección de Inventario / Diagnósticos.
2. Esperar a que los datos carguen.
3. Verificar cada campo contra los datos reales del equipo.

**Datos a validar:**

| Campo | Fuente de verdad para validación |
|-------|----------------------------------|
| Hostname | `$env:COMPUTERNAME` en PowerShell |
| Fabricante | `(Get-WmiObject Win32_ComputerSystem).Manufacturer` |
| Modelo | `(Get-WmiObject Win32_ComputerSystem).Model` |
| Número de serie | `(Get-WmiObject Win32_BIOS).SerialNumber` |
| RAM total | `(Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory` convertido a GB |
| IP activa | `Get-NetIPAddress -AddressFamily IPv4` (no loopback) |
| Versión de Windows | `winver` o `(Get-WmiObject Win32_OperatingSystem).Caption` |

**Resultado esperado:**
- Todos los campos muestran datos reales del equipo (no "N/A" ni vacíos, salvo para hardware no presente como WiFi en equipos sin adaptador WiFi).

---

### CPF-INV-002 — Campo "N/A" para hardware no presente

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-INV-002 |
| **Módulo** | INV |
| **Prioridad** | Baja |
| **Tipo** | Funcional negativo |
| **Objetivo** | Verificar que los campos de hardware no presente (ej: MAC WiFi en equipo sin adaptador WiFi) se muestran como "N/A" en lugar de error. |

**Precondiciones:**
- Equipo de escritorio sin adaptador WiFi.

**Resultado esperado:**
- El campo MAC WiFi muestra "N/A" o equivalente.
- No se produce error ni excepción en el inventario.

---

## MÓDULO: LICENCIA OFFICE

---

### CPF-OFC-001 — Detección de Office instalado

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-OFC-001 |
| **Módulo** | OFC — Licencia Office |
| **Caso de uso relacionado** | CU-OFC-001 |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el módulo detecta correctamente la instalación de Office y muestra los detalles correctos. |

**Precondiciones:**
- Microsoft Office instalado en el equipo (versión 2016 o superior).

**Pasos de ejecución:**
1. Navegar al módulo "Licencia Office".
2. Esperar la carga automática de información.
3. Verificar los datos mostrados contra lo conocido del equipo.

**Resultado esperado:**
- Se muestra el nombre del producto, versión, plataforma y canal de Office.
- El campo "ospp.vbs" muestra una ruta válida y existente.
- No se muestra "Microsoft Office no detectado en este equipo."

---

### CPF-OFC-002 — Inspección de licencia con Administrador

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-OFC-002 |
| **Módulo** | OFC |
| **Caso de uso relacionado** | CU-OFC-002 |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que la inspección de licencia retorna el estado correcto cuando se ejecuta con Administrador y Office activado. |

**Precondiciones:**
- Aplicación con Administrador. Office instalado y activado.

**Pasos de ejecución:**
1. Hacer clic en "Inspeccionar licencia".
2. Esperar el resultado.

**Resultado esperado:**
- Estado: "Office activado: [nombre del producto]".
- Se muestra el estado de licencia, últimos 5 caracteres y Product ID.
- La salida bruta de ospp.vbs está disponible en el bloque expandible.

---

### CPF-OFC-003 — Inspección de licencia sin Administrador

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-OFC-003 |
| **Módulo** | OFC |
| **Prioridad** | Alta |
| **Tipo** | Funcional negativo |
| **Objetivo** | Verificar que la inspección de licencia informa honestamente la falta de permisos de Administrador. |

**Precondiciones:**
- Aplicación ejecutada SIN Administrador.

**Resultado esperado:**
- Se muestra: "Se requieren permisos de Administrador para inspeccionar la licencia de Office."
- No se muestra ningún estado de licencia falso.

---

### CPF-OFC-004 — Activación de Office con clave válida

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-OFC-004 |
| **Módulo** | OFC |
| **Caso de uso relacionado** | CU-OFC-003 |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar el flujo completo de activación con una clave de producto válida para la edición de Office instalada. |

**Precondiciones:**
- Aplicación con Administrador. Office instalado. Clave de producto válida para la edición instalada. Conectividad a Internet.

**Datos de entrada:**
- Clave de producto: clave válida XXXXX-XXXXX-XXXXX-XXXXX-XXXXX proporcionada por el canal de licenciamiento RADEC.

**Pasos de ejecución:**
1. Ingresar la clave en el campo de texto.
2. Hacer clic en "Activar Office".
3. Esperar el resultado (puede tomar hasta 60 segundos para la activación en línea).
4. Verificar el mensaje de resultado.
5. Verificar que el campo de clave está vacío después de la operación.
6. Ejecutar "Inspeccionar licencia" para confirmar la activación.

**Resultado esperado:**
- Mensaje: "Office activado correctamente con clave XXXXX-XXXXX-XXXXX-XXXXX-YYYYY." (últimos 5 enmascarados con los reales).
- El campo de clave está vacío.
- La inspección de licencia posterior confirma estado "Licensed".

---

### CPF-OFC-005 — Rechazo de clave con formato inválido

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-OFC-005 |
| **Módulo** | OFC |
| **Prioridad** | Alta |
| **Tipo** | Funcional negativo |
| **Objetivo** | Verificar que una clave con formato incorrecto es rechazada antes de ser enviada a ospp.vbs. |

**Datos de entrada (casos de prueba):**

| Caso | Entrada | Descripción |
|------|---------|-------------|
| A | `AAAAA-BBBBB-CCCCC-DDDDD` | Solo 20 caracteres (falta un grupo) |
| B | `AAAAA-BBBBB-CCCCC-DDDDD-EEEEEEXTRA` | Más de 25 caracteres |
| C | `ABC12-DEF34-GHI56-JKL78-MNO9!` | Carácter especial (!) |
| D | ` ` (solo espacios) | Entrada vacía |

**Resultado esperado (todos los casos):**
- Mensaje de error: "Ingrese una clave completa de 25 caracteres." o "Formato de clave inválido."
- No se invoca ospp.vbs para ninguno de estos casos.
- La clave no aparece en logs.

---

### CPF-OFC-006 — Enmascaramiento de clave en resultados

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-OFC-006 |
| **Módulo** | OFC |
| **Prioridad** | Alta |
| **Tipo** | Funcional negativo / Seguridad |
| **Objetivo** | Verificar que la clave de producto nunca es visible en pantalla, logs ni resultados de la aplicación. |

**Precondiciones:**
- Clave de producto disponible para prueba.

**Pasos de ejecución:**
1. Activar Office con una clave conocida (CPF-OFC-004).
2. Verificar el mensaje de resultado en pantalla.
3. Abrir el archivo de log `C:\ProgramData\CleanCPU\logs\app.log`.
4. Buscar en el log la clave ingresada.

**Resultado esperado:**
- En pantalla: solo aparecen los últimos 5 caracteres de la clave (`XXXXX-XXXXX-XXXXX-XXXXX-YYYYY`).
- En el log: la cadena `/inpkey:` aparece como `/inpkey:***` o similar. La clave completa NO debe aparecer en ninguna entrada del log.

---

### CPF-OFC-007 — Detección de Office no instalado

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-OFC-007 |
| **Módulo** | OFC |
| **Prioridad** | Media |
| **Tipo** | Funcional negativo |
| **Objetivo** | Verificar el comportamiento del módulo en un equipo sin Microsoft Office instalado. |

**Precondiciones:**
- Equipo sin Microsoft Office instalado. `ospp.vbs` no presente en las rutas estándar.

**Resultado esperado:**
- La detección automática muestra: "Microsoft Office no detectado en este equipo."
- El botón "Inspeccionar licencia" no falla; muestra el mensaje correspondiente a `ospp_not_found`.
- El módulo no genera excepciones ni pantalla de error.

---

### CPF-OFC-008 — Formateo automático de la clave al escribir

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-OFC-008 |
| **Módulo** | OFC — UI |
| **Prioridad** | Baja |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el campo de clave de producto formatea automáticamente los guiones al escribir. |

**Pasos de ejecución:**
1. Hacer clic en el campo de ingreso de clave.
2. Escribir 25 caracteres alfanuméricos sin guiones: `AAAAABBBBBCCCCCDDDDDEEEEE`

**Resultado esperado:**
- El campo muestra automáticamente: `AAAAA-BBBBB-CCCCC-DDDDD-EEEEE`
- Los guiones se insertan en las posiciones correctas (5-5-5-5-5).

---

## MÓDULO: REPORTES

---

### CPF-RPT-001 — Contenido del reporte HTML

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-RPT-001 |
| **Módulo** | RPT — Reportes |
| **Prioridad** | Alta |
| **Tipo** | Funcional positivo |
| **Objetivo** | Verificar que el reporte HTML contiene todos los campos requeridos para la documentación de servicio RADEC. |

**Precondiciones:**
- Sesión de mantenimiento completada.

**Pasos de ejecución:**
1. Generar el reporte HTML (CPF-MNT-015).
2. Abrir el archivo HTML en el navegador.
3. Verificar la presencia de los campos listados.

**Campos a verificar:**

| Campo | Presente en reporte | Coincide con datos del equipo |
|-------|---------------------|-------------------------------|
| Hostname del equipo | | |
| Fabricante y modelo | | |
| Número de serie | | |
| Versión de Windows | | |
| Procesador | | |
| RAM | | |
| Resultado de cada uno de los 9 pasos | | |
| Fecha y hora del mantenimiento | | |
| Total de MB liberados (Paso 2) | | |
| Hallazgos de seguridad (Paso 1/3) | | |
| Acciones recomendadas consolidadas | | |

---

### CPF-RPT-002 — Generación cuando Google Sheets no disponible

| Campo | Detalle |
|-------|---------|
| **ID** | CPF-RPT-002 |
| **Módulo** | RPT |
| **Prioridad** | Media |
| **Tipo** | Funcional negativo |
| **Objetivo** | Verificar que el reporte local se genera correctamente aunque Google Sheets no esté disponible. |

**Precondiciones:**
- Sin conectividad a Internet o credenciales de Google Sheets no configuradas.

**Resultado esperado:**
- El reporte HTML local se genera correctamente.
- Google Sheets aparece como "Omitido" con motivo claro en la consola de salida.
- No se genera excepción ni error crítico en la aplicación.

---

*Fin de Casos de Prueba Funcionales — RADEC Maintenance Program v3.0.0*
*Documento: CPF-MNT-001 | Área TI RADEC | 2026-04-04*
