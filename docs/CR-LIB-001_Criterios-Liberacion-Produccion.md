# RADEC Maintenance Program — Criterios de Liberación a Producción
## Documento: CR-LIB-001 | Versión: 1.0.0 | Fecha: 2026-04-04

---

## CONTROL DE VERSIONES

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2026-04-04 | Área TI RADEC | Versión inicial — criterios para piloto y producción |

---

## 1. PROPÓSITO

Este documento define los criterios formales de liberación del Programa de Mantenimiento RADEC (CleanCPU v3.0.0) para su despliegue progresivo en el parque tecnológico de RADEC (más de 2,800 endpoints), comenzando con el piloto en un grupo controlado de equipos.

El proceso de liberación se divide en dos etapas:
1. **Aprobación de piloto:** Autoriza el despliegue en el grupo piloto inicial (mínimo 5 equipos de diferentes modelos y configuraciones).
2. **Aprobación de producción:** Autoriza el despliegue masivo en el parque completo de RADEC.

---

## 2. CLASIFICACIÓN DE CRITERIOS

| Clasificación | Definición |
|---------------|-----------|
| **Crítico** | Su incumplimiento impide la liberación. No hay excepciones. |
| **Importante** | Su incumplimiento requiere análisis de riesgo y aprobación explícita del Coordinador TI para liberar con observación documentada. |
| **Recomendado** | Su incumplimiento genera una observación en el expediente de liberación, pero no bloquea la liberación. Debe planificarse su resolución en la siguiente versión. |

---

## 3. CRITERIOS PARA APROBACIÓN DE PILOTO

### 3.1 Criterios Críticos (Piloto)

---

**CL-001 — El EXE empaquetado arranca correctamente en Windows 10 y Windows 11**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-001 |
| **Clasificación** | Crítico |
| **Módulo** | Sistema general / EXE |
| **Criterio** | `CleanCPU.exe` arranca sin errores, inicia el servidor Waitress, y abre el navegador automáticamente en al menos dos equipos: uno con Windows 10 (1903+) y uno con Windows 11. |
| **Evidencia requerida** | Captura de pantalla del panel principal cargado en W10 y W11. |
| **Prueba relacionada** | PT-TEC-001, PT-TEC-022 |
| **Estado** | Pendiente de validación en piloto |

---

**CL-002 — Secuencia completa de 9 pasos ejecuta sin falla fatal con Administrador**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-002 |
| **Clasificación** | Crítico |
| **Módulo** | MNT |
| **Criterio** | En un equipo con privilegios de Administrador, los 9 pasos de la secuencia de mantenimiento ejecutan hasta finalización. Los pasos 5 y 7 aparecen como "Omitido" (comportamiento esperado). Ningún paso queda colgado indefinidamente. |
| **Evidencia requerida** | Captura del resumen de mantenimiento con los 9 pasos y sus estados. |
| **Prueba relacionada** | CPF-MNT-010 |
| **Estado** | Pendiente de validación en piloto |

---

**CL-003 — Pasos admin-required reportan "Omitido" (no "Completado") sin elevación**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-003 |
| **Clasificación** | Crítico |
| **Módulo** | MNT |
| **Criterio** | Sin privilegios de Administrador, los pasos 4 (defrag), 6 (cleanmgr) y 8 (UsoClient) se marcan como "Omitido" con mensaje que menciona Administrador. Ninguno muestra "Completado" falsamente. |
| **Evidencia requerida** | Captura de los estados de pasos en ejecución sin Admin. Log de la sesión. |
| **Prueba relacionada** | CPF-MNT-011, PT-SEG-001 |
| **Estado** | Pendiente de validación en piloto |

---

**CL-004 — Clave de producto Office no aparece en logs ni en respuestas API**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-004 |
| **Clasificación** | Crítico |
| **Módulo** | OFC |
| **Criterio** | Después de activar Office con una clave de prueba, la clave completa no aparece en: (a) el archivo de log `app.log`, (b) la respuesta JSON de `/office/api/activate`, (c) el reporte generado. Solo los últimos 5 caracteres son visibles en el resultado. |
| **Evidencia requerida** | Log de activación. Captura de la respuesta JSON inspeccionada en DevTools. |
| **Prueba relacionada** | PT-SEG-010, PT-SEG-011, CPF-OFC-006 |
| **Estado** | Pendiente de validación en piloto |

---

**CL-005 — Allowlist bloquea comandos peligrosos antes de ejecutarse**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-005 |
| **Clasificación** | Crítico |
| **Módulo** | EJE — Command Runner |
| **Criterio** | Al intentar invocar comandos no permitidos (ej: `cmd /c del`, `format`, `reg delete`, `defrag C: /x`), la allowlist los bloquea antes de que el proceso del sistema operativo sea invocado. |
| **Evidencia requerida** | Prueba unitaria de PT-TEC-011 con resultado PASS. Log mostrando "blocked by allowlist". |
| **Prueba relacionada** | PT-TEC-011, PT-SEG-030, PT-SEG-031 |
| **Estado** | Validado (lógica revisada en código) — confirmación en piloto pendiente |

---

**CL-006 — Servidor accesible solo desde localhost**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-006 |
| **Clasificación** | Crítico |
| **Módulo** | Sistema general |
| **Criterio** | El servidor Waitress escucha en `127.0.0.1:5000`. Un equipo externo en la misma red no puede acceder a la interfaz de la aplicación. |
| **Evidencia requerida** | Salida de `netstat -an | findstr 5000` mostrando solo `127.0.0.1`. Captura del intento fallido de acceso externo. |
| **Prueba relacionada** | PT-RED-001 |
| **Estado** | Pendiente de validación en piloto |

---

**CL-007 — Reporte HTML local generado correctamente**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-007 |
| **Clasificación** | Crítico |
| **Módulo** | RPT |
| **Criterio** | Después de completar un mantenimiento, el botón "Generar Reporte" produce un archivo HTML en `C:\ProgramData\CleanCPU\reports\` que contiene el hostname, los resultados de los 9 pasos, y los datos de inventario del equipo. |
| **Evidencia requerida** | Ruta del archivo generado. Captura del reporte HTML abierto en navegador. |
| **Prueba relacionada** | CPF-MNT-015, PT-INT-030 |
| **Estado** | Pendiente de validación en piloto |

---

**CL-008 — UAC solicita elevación automáticamente al ejecutar el EXE**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-008 |
| **Clasificación** | Crítico |
| **Módulo** | EXE / UAC |
| **Criterio** | Al ejecutar `CleanCPU.exe` con doble clic, Windows presenta automáticamente el cuadro de diálogo UAC de solicitud de elevación (confirma que `uac_admin=True` está activo). |
| **Evidencia requerida** | Captura del cuadro UAC al ejecutar el EXE. |
| **Prueba relacionada** | PT-TEC-021 |
| **Estado** | Pendiente de validación en piloto |

---

**CL-009 — No hay errores de módulo (ImportError/ModuleNotFoundError) en EXE empaquetado**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-009 |
| **Clasificación** | Crítico |
| **Módulo** | EXE / PyInstaller |
| **Criterio** | El EXE empaquetado ejecuta todos los módulos de la aplicación en un equipo sin Python instalado, sin generar `ImportError` ni `ModuleNotFoundError`. |
| **Evidencia requerida** | Log de la aplicación sin errores de importación. Secuencia de mantenimiento completa en equipo sin Python. |
| **Prueba relacionada** | PT-INT-040 |
| **Estado** | Pendiente de validación en piloto |

---

### 3.2 Criterios Importantes (Piloto)

---

**CL-010 — Datos de inventario completos y correctos**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-010 |
| **Clasificación** | Importante |
| **Criterio** | El módulo de inventario muestra datos correctos y completos en al menos el 90% de los campos (hostname, modelo, serie, RAM, procesador, IP) en los equipos del piloto. Los campos de hardware no presente muestran "N/A" (no errores). |
| **Prueba relacionada** | CPF-INV-001, CPF-INV-002 |

---

**CL-011 — Módulo Office funcional en equipos con Office 365/M365**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-011 |
| **Clasificación** | Importante |
| **Criterio** | En equipos con Office 365/M365 ClickToRun, el módulo Office detecta la instalación, localiza `ospp.vbs`, y la inspección de licencia retorna el estado correcto. |
| **Prueba relacionada** | CPF-OFC-001, CPF-OFC-002 |

---

**CL-012 — Activación Office con clave válida exitosa**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-012 |
| **Clasificación** | Importante |
| **Criterio** | La activación de Office con una clave de producto válida para la edición instalada completa el proceso de `/inpkey` + `/act` exitosamente en al menos un equipo del piloto. |
| **Prueba relacionada** | CPF-OFC-004, PT-INT-022 |

---

**CL-013 — Pasos 5 y 7 se omiten con mensaje correcto (sin confusión)**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-013 |
| **Clasificación** | Importante |
| **Criterio** | Los pasos 5 (temp_cleanup) y 7 (sfc) muestran estado "Omitido" con el mensaje correcto explicando la razón. Los técnicos del piloto entienden que esto es comportamiento esperado (verificar mediante entrevista post-piloto). |
| **Prueba relacionada** | CPF-MNT-010 |

---

**CL-014 — Reporte FO-TI-19 o Excel generado sin errores**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-014 |
| **Clasificación** | Importante |
| **Criterio** | Al menos uno de los formatos de reporte formal (FO-TI-19 o Excel FO-TI-19) se genera correctamente en los equipos del piloto. |
| **Prueba relacionada** | CPF-MNT-015 |

---

**CL-015 — Indicadores de progreso funcionan correctamente en UI**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-015 |
| **Clasificación** | Importante |
| **Criterio** | Durante la ejecución del mantenimiento: (a) el paso activo muestra fondo azul, (b) la barra animada es visible, (c) el contador de tiempo transcurrido se actualiza, (d) el resultado inline aparece sin scroll al bottom. |
| **Prueba relacionada** | CPF-MNT-012, CPF-MNT-013 |

---

### 3.3 Criterios Recomendados (Piloto)

---

**CL-016 — Google Sheets actualizado correctamente**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-016 |
| **Clasificación** | Recomendado |
| **Criterio** | Si las credenciales de Google Sheets están configuradas y hay conectividad, el registro se actualiza correctamente en la hoja compartida de RADEC. |

---

**CL-017 — Carpeta de red accesible y reporte copiado**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-017 |
| **Clasificación** | Recomendado |
| **Criterio** | Si la ruta de red de RADEC está configurada y accesible, el reporte se copia exitosamente a la carpeta de red. |

---

**CL-018 — cleanmgr /sagerun:1 efectivo en equipos con /sageset:1 preconfigurado**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-018 |
| **Clasificación** | Recomendado |
| **Criterio** | En equipos del piloto donde el perfil `/sageset:1` ha sido previamente configurado, el Paso 6 (cleanmgr) libera espacio visible. |

---

**CL-019 — Paso Lenovo Update funciona en equipos Lenovo del piloto**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-019 |
| **Clasificación** | Recomendado |
| **Criterio** | En equipos Lenovo con Lenovo Vantage instalado, el Paso 9 lanza la aplicación de Lenovo correctamente. |

---

## 4. CRITERIOS PARA APROBACIÓN DE PRODUCCIÓN

Los criterios de producción requieren que los criterios de piloto hayan sido aprobados Y que el piloto haya sido completado satisfactoriamente.

### 4.1 Criterios Críticos (Producción)

---

**CL-020 — Piloto completado en mínimo 5 equipos representativos**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-020 |
| **Clasificación** | Crítico |
| **Criterio** | El piloto fue ejecutado en un mínimo de 5 equipos que representen la diversidad del parque RADEC: al menos 2 modelos de fabricantes distintos, al menos 1 equipo con Windows 10 y 1 con Windows 11, al menos 1 equipo con Office y 1 sin Office. |
| **Evidencia requerida** | Acta de piloto con inventario de equipos usados, resultados por equipo, y observaciones de los técnicos. |

---

**CL-021 — Ningún hallazgo crítico de seguridad sin resolver**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-021 |
| **Clasificación** | Crítico |
| **Criterio** | No existe ningún hallazgo de seguridad abierto de severidad crítica del documento PT-SEG-001. Los criterios CL-004, CL-005, CL-006 deben estar validados como PASS. |
| **Evidencia requerida** | Resultados de PT-SEG-001 con todos los ítems críticos en estado PASS o N/A. |

---

**CL-022 — Tasa de éxito del mantenimiento ≥ 80% en el piloto**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-022 |
| **Clasificación** | Crítico |
| **Criterio** | En los equipos del piloto, al menos el 80% de los pasos ejecutados (excluyendo los deliberadamente omitidos 5 y 7) terminan en estado "Completado". |
| **Evidencia requerida** | Tabla consolidada de resultados del piloto por paso y por equipo. |

---

**CL-023 — Ningún fallo fatal del EXE (crash, excepción no controlada visible al usuario)**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-023 |
| **Clasificación** | Crítico |
| **Criterio** | Durante el piloto, el EXE no presentó ningún crash irrecuperable, pantalla de error de Python no manejada, o pérdida de estado de sesión de mantenimiento que dejara al técnico sin resultado. |
| **Evidencia requerida** | Logs de los equipos del piloto. Reporte de incidencias del piloto. |

---

**CL-024 — Los reportes generados son aceptados como documentación formal FO-TI-19**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-024 |
| **Clasificación** | Crítico |
| **Criterio** | El Coordinador TI revisó los reportes FO-TI-19 y Excel generados durante el piloto y los acepta como documentación válida para los expedientes de servicio de RADEC. |
| **Evidencia requerida** | Revisión y visto bueno del Coordinador TI sobre los reportes del piloto. |

---

**CL-025 — Antivirus corporativo no interfiere con el EXE en el parque RADEC**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-025 |
| **Clasificación** | Crítico |
| **Criterio** | El antivirus corporativo desplegado en los equipos del piloto no bloquea `CleanCPU.exe` ni cuarentena los archivos generados por la aplicación. Si hay bloqueo, la exclusión está configurada antes del despliegue masivo. |
| **Evidencia requerida** | Evidencia de que el EXE se ejecutó sin interferencia del antivirus en los equipos del piloto. Documentación de la exclusión si fue necesaria. |

---

### 4.2 Criterios Importantes (Producción)

---

**CL-026 — Tiempo de ejecución aceptable en equipos del parque**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-026 |
| **Clasificación** | Importante |
| **Criterio** | El tiempo de ejecución de la secuencia completa de mantenimiento es aceptable para la operación del técnico: no supera 30 minutos en ningún equipo del piloto con hardware representativo del parque. |
| **Referencia técnica** | SFC puede tomar hasta 15 minutos en HDD lentos; esto es aceptable. |

---

**CL-027 — Técnicos del piloto comprenden el flujo sin capacitación extensa**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-027 |
| **Clasificación** | Importante |
| **Criterio** | Los técnicos que usaron la herramienta durante el piloto pueden operar la aplicación de forma autónoma con solo el Manual de Usuario como referencia. |
| **Evidencia requerida** | Encuesta de usabilidad de los técnicos del piloto (pendiente de validación en piloto). |

---

**CL-028 — Inventario del sistema cubre los modelos del parque RADEC**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-028 |
| **Clasificación** | Importante |
| **Criterio** | El módulo de inventario captura datos completos en los fabricantes y modelos representativos del parque RADEC (Dell, Lenovo, HP, u otros según inventario). |

---

**CL-029 — Estrategia de distribución del EXE definida y aprobada**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-029 |
| **Clasificación** | Importante |
| **Criterio** | El Coordinador TI ha definido y aprobado el canal de distribución de `CleanCPU.exe` para el despliegue masivo (carpeta de red compartida, correo electrónico, repositorio interno, u otro mecanismo). El canal garantiza que los técnicos reciben el EXE correcto (hash verificado). |

---

### 4.3 Criterios Recomendados (Producción)

---

**CL-030 — Procedimiento de actualización del EXE documentado**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-030 |
| **Clasificación** | Recomendado |
| **Criterio** | Existe un procedimiento documentado para actualizar `CleanCPU.exe` en el parque cuando se libere una nueva versión. |

---

**CL-031 — Procedimiento de soporte de primer nivel para el técnico**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-031 |
| **Clasificación** | Recomendado |
| **Criterio** | El Área TI cuenta con un procedimiento de soporte de primer nivel para resolver los problemas más comunes de la herramienta (puerto ocupado, antivirus, falta de Admin, cleanmgr sin sageset), basado en la Guía de Errores del Manual de Usuario. |

---

**CL-032 — Proceso para Lenovo Update estandarizado en equipos Lenovo del parque**

| Campo | Detalle |
|-------|---------|
| **ID** | CL-032 |
| **Clasificación** | Recomendado |
| **Criterio** | Para los equipos Lenovo del parque que forman parte del mantenimiento, existe un proceso definido para que el técnico complete la verificación de Lenovo Vantage después de que la herramienta lo lanza. |

---

## 5. CONDICIONES DE NO-LIBERACIÓN

Las siguientes condiciones implican rechazo automático de la liberación (piloto o producción) sin necesidad de análisis de riesgo:

| Condición de NO-GO | Justificación |
|-------------------|---------------|
| La clave de producto Office aparece en los logs | Violación de seguridad crítica de datos sensibles |
| Un paso admin-only reporta "Completado" sin haberse ejecutado | Reporte de servicio falso; implica documentación incorrecta en RADEC |
| El servidor es accesible desde equipos externos de la red | Exposición de la interfaz de administración a la red corporativa |
| El EXE activa Office mediante un mecanismo no oficial | Violación de términos de licencia Microsoft; riesgo legal para RADEC |
| La allowlist no bloquea `cmd /c del` u operaciones destructivas análogas | Riesgo de daño masivo en equipos del parque |
| El EXE falla en arrancar en Windows 10 o Windows 11 x64 | El parque objetivo no es soportado |
| El reporte FO-TI-19 no es aceptado como documentación formal | La herramienta no cumple su función principal de documentación RADEC |

---

## 6. EVIDENCIA MÍNIMA REQUERIDA PARA APROBACIÓN DE PILOTO

| # | Evidencia | Formato |
|---|-----------|---------|
| 1 | Capturas de pantalla del EXE funcionando en W10 y W11 | PNG/JPG |
| 2 | Captura de secuencia de mantenimiento completa (9 pasos) | PNG/JPG |
| 3 | Log `app.log` de al menos una sesión de mantenimiento | Archivo de texto |
| 4 | Extracto del log verificando ausencia de claves de producto | Documento de análisis |
| 5 | Captura de estado de pasos sin Admin (pasos omitidos visibles) | PNG/JPG |
| 6 | Archivo de reporte HTML generado | Archivo HTML |
| 7 | Resultado de `netstat` mostrando binding solo en 127.0.0.1 | Captura o texto |
| 8 | Lista de equipos del piloto con modelos, OS, y resultados | Tabla Excel o documento |

---

## 7. PROCESO DE APROBACIÓN

### 7.1 Aprobación de Piloto

| Paso | Responsable | Acción |
|------|-------------|--------|
| 1 | Técnico TI líder del piloto | Ejecutar la aplicación en los equipos del piloto y recopilar evidencias |
| 2 | Técnico TI líder del piloto | Completar la tabla de criterios con estado PASS/FAIL/N/A y evidencias |
| 3 | Coordinador TI | Revisar las evidencias y el cumplimiento de los criterios críticos |
| 4 | Coordinador TI | Emitir la aprobación de piloto (firmada) o documentar los criterios fallidos con plan de remediación |

### 7.2 Aprobación de Producción

| Paso | Responsable | Acción |
|------|-------------|--------|
| 1 | Técnicos del piloto | Completar el piloto con mínimo 5 equipos; documentar hallazgos |
| 2 | Técnico TI líder | Consolidar el acta de piloto con todos los resultados |
| 3 | Coordinador TI | Revisar el acta del piloto y verificar criterios CL-020 al CL-025 |
| 4 | Coordinador TI | Definir el canal de distribución masiva (CL-029) |
| 5 | Coordinador TI | Emitir la aprobación de producción (firmada) con el alcance del despliegue masivo |

---

## 8. REGISTRO DE APROBACIÓN

### 8.1 Aprobación de Piloto

| Campo | Valor |
|-------|-------|
| **Versión aprobada** | CleanCPU v3.0.0 |
| **Fecha de revisión** | Pendiente |
| **Criterios críticos evaluados** | CL-001 al CL-009 |
| **Criterios críticos aprobados** | ___ / 9 |
| **Criterios importantes evaluados** | CL-010 al CL-015 |
| **Criterios importantes aprobados** | ___ / 6 |
| **Observaciones** | |
| **Decisión** | ☐ Aprobado para piloto   ·   ☐ Aprobado con observaciones   ·   ☐ Rechazado |
| **Nombre del aprobador** | |
| **Firma y fecha** | |

---

### 8.2 Aprobación de Producción

| Campo | Valor |
|-------|-------|
| **Versión aprobada** | CleanCPU v3.0.0 |
| **Fecha del piloto** | Pendiente |
| **Equipos en piloto** | |
| **Tasa de éxito del mantenimiento en piloto** | % |
| **Incidencias abiertas** | |
| **Criterios críticos de producción** | CL-020 al CL-025 |
| **Criterios críticos aprobados** | ___ / 6 |
| **Canal de distribución aprobado** | |
| **Observaciones para producción** | |
| **Decisión** | ☐ Aprobado para despliegue masivo   ·   ☐ Aprobado por fases   ·   ☐ Rechazado |
| **Nombre del aprobador** | |
| **Firma y fecha** | |

---

## 9. PLAN DE DESPLIEGUE POR FASES (REFERENCIA)

En caso de aprobación parcial o gradual, se sugiere el siguiente esquema de fases:

| Fase | Alcance | Criterios previos requeridos |
|------|---------|------------------------------|
| Fase 0 — Piloto | 5 equipos representativos | CL-001 al CL-009 aprobados |
| Fase 1 — Área piloto | 50–100 equipos del área TI interno | CL-020 al CL-025 aprobados |
| Fase 2 — Área operativa prioritaria | Área(s) de mayor criticidad del parque | Resultados de Fase 1 documentados |
| Fase 3 — Despliegue completo | 2,800+ endpoints RADEC | Resultados de Fase 2 documentados, sin condiciones de NO-GO activas |

---

*Fin de Criterios de Liberación a Producción — RADEC Maintenance Program v3.0.0*
*Documento: CR-LIB-001 | Área TI RADEC | 2026-04-04*
