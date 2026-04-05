# RADEC Maintenance Program — Manual de Usuario
## Documento: MAN-MNT-001 | Versión: 1.0.0 | Fecha: 2026-04-04

---

## CONTROL DE VERSIONES

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2026-04-04 | Área TI RADEC | Versión inicial para piloto |

---

## ÍNDICE

1. Resumen ejecutivo
2. Objetivo del sistema
3. Alcance
4. Usuarios y roles
5. Descripción general del sistema
6. Arquitectura técnica (nivel operativo)
7. Requisitos previos de operación
8. Instalación y puesta en marcha
9. Módulos del sistema
10. Flujo de mantenimiento lógico
11. Módulo de licencia Microsoft Office
12. Generación de reportes
13. Notas operativas y advertencias
14. Guía de errores comunes
15. Buenas prácticas del técnico

---

## 1. RESUMEN EJECUTIVO

El Programa de Mantenimiento RADEC (nombre técnico interno: **CleanCPU v3.0.0**) es una herramienta de soporte técnico de escritorio diseñada para estandarizar, automatizar y documentar el mantenimiento preventivo lógico en los equipos de cómputo del parque tecnológico de RADEC, conformado por más de 2,800 endpoints activos bajo administración del Área de Tecnologías de la Información.

La aplicación encapsula en un ejecutable único de Windows (`CleanCPU.exe`) la ejecución secuencial de nueve (9) acciones de mantenimiento preventivo, la generación de reportes de servicio formales en los formatos corporativos de RADEC (FO-TI-19, HTML, Excel), la captura de inventario técnico del equipo, y el módulo de inspección y activación de licencias Microsoft Office.

La herramienta está orientada exclusivamente a técnicos y analistas de soporte del Área TI de RADEC. No requiere instalación, no modifica el registro de Windows para su propia operación, y se distribuye como un único ejecutable autoelevado (UAC) que integra todos sus módulos y dependencias de forma autocontenida.

---

## 2. OBJETIVO DEL SISTEMA

Proveer al personal técnico del Área TI de RADEC una plataforma unificada, segura y auditoriable para:

1. Ejecutar la secuencia estándar de mantenimiento preventivo lógico en equipos Windows 10/11 de forma estandarizada y reproducible.
2. Generar reportes de servicio técnico formales (FO-TI-19) y registros de actividades en los formatos aceptados por el proceso de Gestión TI de RADEC.
3. Capturar el inventario técnico actualizado del equipo intervenido (hardware, OS, red, Office).
4. Inspeccionar y, cuando sea autorizado, activar licencias de Microsoft Office mediante mecanismos oficiales de Microsoft.
5. Documentar hallazgos, advertencias y acciones recomendadas de forma auditoriable para su consulta posterior.

---

## 3. ALCANCE

**Incluido en el alcance:**
- Equipos de escritorio y portátiles con sistema operativo Windows 10 (versión 1903 o superior) y Windows 11, bajo administración del Área TI de RADEC.
- Ejecución por técnicos del Área TI de RADEC con credenciales de Administrador local en el equipo intervenido.
- Mantenimiento preventivo lógico (no físico): limpieza de archivos temporales, verificación de integridad del sistema, optimización de disco, verificación de actualizaciones.
- Generación de reportes de servicio en formatos FO-TI-19, HTML y Excel.
- Inspección y activación de licencias Microsoft Office 2016/2019/2021/2024/M365 instaladas mediante ClickToRun o MSI/Volumen.

**Excluido del alcance:**
- Mantenimiento físico de hardware.
- Instalación de software de terceros durante el mantenimiento.
- Modificación de políticas de dominio o Active Directory.
- Soporte para sistemas operativos distintos de Windows 10/11 (Windows Server, macOS, Linux).
- Activación de productos Microsoft distintos de Office (Windows, Visio autónomo, Project autónomo).

---

## 4. USUARIOS Y ROLES

| Rol | Descripción | Nivel de acceso |
|-----|-------------|-----------------|
| Técnico TI de campo | Técnico del Área TI que realiza el mantenimiento preventivo en sitio | Operación completa de todos los módulos |
| Analista TI senior | Analista que coordina intervenciones y revisa resultados | Operación completa + revisión de logs |
| Coordinador TI | Revisa reportes generados y métricas del servicio | Lectura de reportes; sin ejecución de acciones |

**Perfil mínimo requerido del técnico:** Conocimiento operativo de Windows (identificación de errores, manejo de permisos de Administrador), comprensión básica de mantenimiento preventivo de equipos, y familiaridad con el proceso FO-TI-19 de RADEC.

---

## 5. DESCRIPCIÓN GENERAL DEL SISTEMA

El Programa de Mantenimiento RADEC es una aplicación de escritorio para Windows que opera como servidor web local (`http://127.0.0.1:5000`) con interfaz de usuario en el navegador web predeterminado del equipo. Este modelo permite que la interfaz sea moderna, accesible y mantenible, sin requerir frameworks de interfaz gráfica adicionales ni instalación de dependencias en el equipo del usuario.

**Flujo de operación general:**

1. El técnico ejecuta `CleanCPU.exe` como Administrador.
2. Windows solicita elevación UAC. El técnico confirma.
3. La aplicación inicia el servidor web local en `http://127.0.0.1:5000`.
4. El navegador predeterminado se abre automáticamente con la interfaz de la aplicación.
5. El técnico navega a los módulos requeridos y ejecuta las acciones pertinentes.
6. Al cerrar la ventana del EXE, el servidor termina y la sesión finaliza.

**Estructura modular del sistema:**

| Módulo | Ruta interna | Función principal |
|--------|-------------|-------------------|
| Panel principal | `/` | Estado general del equipo; acceso a todos los módulos |
| Mantenimiento Lógico | `/maintenance` | Secuencia de 9 pasos de mantenimiento preventivo |
| Inventario del Sistema | `/diagnostics` | Captura de datos técnicos del equipo |
| Licencia Office | `/office` | Inspección y activación de Microsoft Office |
| Reportes | `/reports` | Generación de reportes de servicio |
| Red | `/network` | Diagnóstico y reparación de red |
| Energía | `/power` | Configuración y diagnóstico de energía |
| Controladores | `/drivers` | Gestión de controladores de dispositivos |
| Actualizaciones | `/update` | Verificación de Windows Update |
| Reparación | `/repair` | Herramientas avanzadas de reparación |
| Seguridad | `/security` | Revisión de configuración de seguridad |
| Logs | `/logs` | Registro de actividad de la aplicación |

---

## 6. ARQUITECTURA TÉCNICA (NIVEL OPERATIVO)

La aplicación está construida sobre Python con el framework Flask, empaquetada con PyInstaller como ejecutable único autocontenido. El servidor de producción es Waitress (WSGI), escuchando exclusivamente en `127.0.0.1:5000` (sin exposición a la red).

```
[CleanCPU.exe]  ←  PyInstaller (Python + Flask + Waitress, autocontenido)
       │
       ├── Servidor Waitress  (http://127.0.0.1:5000)
       │       │
       │       ├── Flask Blueprints (rutas por módulo)
       │       │     ├── /maintenance  → Mantenimiento Lógico
       │       │     ├── /office       → Licencia Office
       │       │     ├── /diagnostics  → Inventario / Diagnósticos
       │       │     └── /reports, /network, /power, /drivers, ...
       │       │
       │       └── Servicios internos
       │             ├── command_runner     → Capa de ejecución segura de comandos
       │             ├── security_audit     → Auditoría de seguridad interna
       │             ├── cleanup            → Limpieza nativa de archivos temporales
       │             ├── system_inventory   → Inventario del equipo
       │             ├── office_tools       → Inspección y activación de Office
       │             └── maintenance_report → Generación de reportes
       │
       └── Navegador web del equipo  (cliente de la interfaz de usuario)
```

**Almacenamiento local:**

| Recurso | Ruta primaria | Ruta alternativa |
|---------|--------------|-----------------|
| Logs de aplicación | `C:\ProgramData\CleanCPU\logs\app.log` | `<directorio EXE>\logs\` |
| Reportes de servicio | `C:\ProgramData\CleanCPU\reports\` | `<directorio EXE>\reports\` |
| Credenciales Google | `<directorio EXE>\credentials\` | No aplica |

Los logs tienen rotación automática (10 MB por archivo, máximo 5 respaldos).

**Seguridad de ejecución:**
- Todos los comandos del sistema pasan obligatoriamente por una capa de validación con lista de comandos permitidos (allowlist). Comandos fuera de la lista son bloqueados antes de ejecutarse.
- Las sesiones de mantenimiento se almacenan en memoria durante la sesión activa únicamente; no se persisten entre reinicios del EXE.
- Los datos sensibles (claves de producto Office) nunca se registran en logs ni en reportes.
- La interfaz web es accesible únicamente desde `127.0.0.1` (localhost); no se expone en la red local.

---

## 7. REQUISITOS PREVIOS DE OPERACIÓN

| Requisito | Detalle |
|-----------|---------|
| Sistema operativo | Windows 10 (versión 1903 o superior) o Windows 11 |
| Arquitectura | x64 |
| Privilegios de ejecución | Administrador local en el equipo intervenido |
| Navegador web | Cualquier navegador instalado (Edge, Chrome, Firefox). Edge incluido por defecto en W10/W11. |
| Conectividad de red | No requerida para operación local. Requerida para activación de Office en línea y generación de reportes en Google Sheets o carpeta de red. |
| PowerShell | Windows PowerShell 5.1+ (preinstalado en W10/W11). PowerShell 7+ también compatible. |
| Microsoft Office (módulo Office) | Microsoft Office 2016/2019/2021/2024/M365. `ospp.vbs` debe estar accesible en rutas estándar. |
| Antivirus corporativo | Si el antivirus bloquea el EXE, solicitarlo al Coordinador TI para agregar la ruta a exclusiones. |
| Puerto disponible | Puerto TCP 5000 libre en `127.0.0.1`. Si está ocupado, la aplicación no iniciará. |

---

## 8. INSTALACIÓN Y PUESTA EN MARCHA

La aplicación no requiere instalación formal. El técnico recibe `CleanCPU.exe` a través del canal de distribución autorizado por el Área TI de RADEC.

### 8.1 Procedimiento de inicio

1. Copiar `CleanCPU.exe` al escritorio o a cualquier ruta local del equipo intervenido.
2. Hacer clic derecho sobre `CleanCPU.exe` → **Ejecutar como administrador**.
3. Confirmar el cuadro de diálogo UAC con credenciales de administrador local.
4. Esperar de 5 a 15 segundos mientras la aplicación inicia el servidor interno.
5. El navegador predeterminado se abrirá automáticamente en `http://127.0.0.1:5000`.

> **Nota:** Si el navegador no se abre automáticamente, abrir manualmente `http://127.0.0.1:5000`.

> **Nota:** Si se ejecuta sin privilegios de Administrador, la aplicación indicará el estado de elevación en el panel. Las acciones que requieren administrador serán omitidas con mensaje explicativo; no provocarán errores críticos.

### 8.2 Verificación del inicio correcto

Al abrir el navegador, el técnico debe verificar:
- Que la barra de navegación muestre `http://127.0.0.1:5000`.
- Que el indicador de elevación en el panel principal muestre **Administrador: Sí**.
- Que el nombre del equipo (hostname) sea visible en el panel.

### 8.3 Finalización de la sesión

Cerrar la ventana del ejecutable `CleanCPU.exe` termina el servidor web. El navegador puede quedar abierto, pero perderá la conexión. Los reportes ya generados permanecen en disco.

---

## 9. MÓDULOS DEL SISTEMA

### 9.1 Panel Principal (Dashboard)

Muestra al técnico el estado inmediato del equipo: hostname, usuario activo, estado de elevación (Administrador / Usuario estándar), versión y build de Windows, y acceso rápido a todos los módulos de la aplicación.

### 9.2 Mantenimiento Lógico

Módulo central de la aplicación. Ejecuta la secuencia estándar de nueve (9) pasos de mantenimiento preventivo de forma secuencial y controlada. El técnico observa en tiempo real el avance de cada paso, el resultado al concluir, y puede cancelar el proceso en cualquier momento. Ver sección 10 para el detalle completo.

### 9.3 Inventario del Sistema

Captura y presenta datos técnicos del equipo:

| Campo | Descripción |
|-------|-------------|
| Hostname | Nombre del equipo en la red |
| Usuario | Usuario activo en sesión |
| Fabricante | Fabricante del equipo (WMI) |
| Modelo | Modelo del equipo |
| Número de serie | Serial del BIOS |
| UUID | Identificador único universal del hardware |
| Dominio / Grupo de trabajo | Pertenencia de red del equipo |
| SO | Nombre, versión, build y arquitectura del sistema operativo |
| Procesador | Nombre completo del procesador |
| RAM | Capacidad total y tipo/velocidad (DDR3/DDR4/DDR5) |
| Discos | Nombre amigable, tipo de medio (SSD/HDD), capacidad |
| IP | Dirección IPv4 activa (no loopback) |
| MAC Ethernet | Dirección MAC del adaptador Ethernet |
| MAC WiFi | Dirección MAC del adaptador WiFi |
| Microsoft Office | Producto, versión, plataforma, canal, tipo de instalación |

### 9.4 Licencia Microsoft Office

Permite al técnico detectar, inspeccionar y activar licencias de Microsoft Office. Ver sección 11.

### 9.5 Reportes

Genera reportes de servicio de una sesión de mantenimiento completada. Ver sección 12.

### 9.6 Módulos de soporte adicional

| Módulo | Función |
|--------|---------|
| Red | Diagnóstico de conectividad, reset de DNS, Winsock |
| Energía | Consulta y ajuste de esquemas de energía, reporte de batería |
| Controladores | Enumeración de controladores de dispositivos |
| Actualizaciones | Verificación y gestión de Windows Update |
| Reparación | Reparación avanzada: SFC, DISM RestoreHealth, servicios de Windows Update |
| Seguridad | Revisión de configuración de seguridad del sistema |
| Diagnósticos | Información técnica detallada del sistema |
| Logs | Visualización del registro de actividad de la aplicación |

---

## 10. FLUJO DE MANTENIMIENTO LÓGICO

### 10.1 Preparación antes de iniciar

El técnico debe verificar los siguientes puntos antes de hacer clic en "Iniciar Mantenimiento Lógico":

1. La aplicación está ejecutándose como Administrador (verificar indicador en el panel).
2. El equipo no está siendo utilizado activamente por el usuario final.
3. El disco C: tiene al menos 10% de espacio libre.
4. No hay actualizaciones de Windows en proceso activo.
5. No hay escaneos de antivirus en curso (pueden interferir con SFC).

### 10.2 Secuencia de los nueve pasos

| # | ID | Nombre del paso | Función |
|---|----|-----------------|---------|
| 1 | malwarebytes | Auditoría de Seguridad | Inspección interna de indicadores de seguridad y salud del sistema: reinicio pendiente, espacio en disco, servicios críticos (WinDefend, EventLog, wuauserv, Dhcp, Dnscache, LanmanWorkstation, mpssvc), DISM /CheckHealth, SFC /scannow, actualizaciones pendientes via COM, programas de inicio |
| 2 | ccleaner | Limpieza Interna del Sistema | Limpieza nativa: TEMP del usuario (%TEMP%), Windows\Temp, Prefetch, caché de Internet (INetCache), caché DNS (ipconfig /flushdns) |
| 3 | advancedsystemcare | Salud y Reparación del Sistema | DISM /CheckHealth, SFC /scannow, verificación de servicios críticos, reinicio pendiente, actualizaciones pendientes (COM), espacio en disco, programas de inicio |
| 4 | defrag | Optimización de disco | `defrag C: /O` — TRIM automático en SSD, desfragmentación en HDD. Windows selecciona la operación según el tipo de unidad de forma automática. Requiere Administrador. |
| 5 | temp_cleanup | Archivos temporales adicionales | **Omitido automáticamente.** Ya ejecutado en el Paso 2. No produce duplicación. |
| 6 | disk_cleanup | Limpieza de disco del sistema | `cleanmgr /sagerun:1` — limpieza avanzada de disco de Windows. Requiere Administrador. |
| 7 | sfc | Escaneo SFC adicional | **Omitido automáticamente.** Ya ejecutado en el Paso 3. No produce duplicación. |
| 8 | windows_update | Verificación de Windows Update | `UsoClient StartScan` — solicita escaneo de actualizaciones a Windows Update en segundo plano. Requiere Administrador. |
| 9 | lenovo_update | Verificación Lenovo Update | Lanza Lenovo Vantage (`Lenovo.Vantage.exe`) o Lenovo System Update (`tvsu.exe`) si está instalado. Omitido en equipos no Lenovo o sin Lenovo Vantage. |

> **Comportamiento de los pasos 5 y 7:** La omisión de estos pasos es deliberada y correcta. La limpieza de temporales se ejecuta en el Paso 2 y SFC se ejecuta en el Paso 3. Ejecutarlos nuevamente en la misma sesión no aportaría valor y duplicaría el tiempo de ejecución (SFC puede tomar hasta 15 minutos por ejecución). El técnico no debe interpretar estos pasos omitidos como fallas del sistema.

### 10.3 Estados posibles por paso

| Estado | Descripción | Icono en pantalla |
|--------|-------------|-------------------|
| Pendiente | El paso aún no ha sido ejecutado en esta sesión | ⏳ (gris) |
| En ejecución | El paso está siendo procesado activamente | 🔄 (azul, animado) |
| Completado | El paso finalizó sin errores críticos | ✅ (verde) |
| Omitido | El paso fue deliberadamente saltado (no es un error) | ⚠️ (naranja) |
| Fallido | El paso terminó con error de ejecución | ❌ (rojo) |
| Cancelado | El técnico canceló el mantenimiento antes de que el paso ejecutara | 🚫 (gris) |

### 10.4 Indicadores de progreso en pantalla

**Durante la ejecución de un paso:**
- La fila del paso activo se resalta con **fondo azul** y borde izquierdo azul.
- Se muestra una **barra de progreso animada** (indeterminada, azul-verde) dentro del paso.
- Un **contador de tiempo** indica los minutos y segundos transcurridos en el paso activo: `En ejecución — MM:SS transcurrido...`
- La pantalla se desplaza automáticamente para mantener el paso activo centrado en el viewport.

**Al finalizar un paso:**
- La fila destella brevemente en verde (completado) o rojo (fallido).
- El resultado del paso aparece directamente debajo del nombre, con:
  - Mensaje principal en color verde, rojo u naranja según el estado.
  - Insignias resumen: MB liberados, hallazgos críticos, advertencias, acciones recomendadas.
  - Panel de detalle expandible con errores individuales, advertencias y acciones recomendadas específicas.

**Barra de progreso global:**
- Muestra el porcentaje de avance general (pasos terminados / total de pasos).
- Incluye el contador de tiempo global de la sesión.
- Indica el número de pasos completados, omitidos y fallidos.

### 10.5 Cancelación del mantenimiento

El técnico puede cancelar el mantenimiento en cualquier momento haciendo clic en **"Cancelar mantenimiento"** en la barra superior. El sistema solicita confirmación antes de proceder. Los pasos en ejecución al momento de la cancelación concluirán su ciclo actual antes de detenerse; los pasos restantes quedarán en estado "Cancelado".

### 10.6 Resumen final y generación de reporte

Al completar todos los pasos, la aplicación muestra una tarjeta de resumen con:
- Cantidad de pasos completados, omitidos y fallidos.
- Tiempo total de ejecución de la sesión.
- Botón **"Generar Reporte"** para generar los reportes de servicio formales.
- Botón **"Ejecutar de nuevo"** para iniciar una nueva sesión de mantenimiento.

---

## 11. MÓDULO DE LICENCIA MICROSOFT OFFICE

### 11.1 Detección de instalación de Office

Al abrir el módulo, la aplicación consulta automáticamente el registro de Windows para detectar Microsoft Office. Esta operación **no requiere permisos de Administrador** y muestra:

| Campo | Descripción |
|-------|-------------|
| Producto | Nombre del producto Office detectado |
| Versión | Versión numérica de Office |
| Plataforma | x86 o x64 |
| Canal | Current, MonthlyEnterprise, SemiAnnual (ClickToRun) o MSI/Volumen |
| Release IDs | IDs de producto ClickToRun instalados |
| ospp.vbs | Ruta al archivo ospp.vbs (herramienta oficial de activación de Microsoft) |

### 11.2 Inspección del estado de licencia

El botón **"Inspeccionar licencia"** ejecuta `cscript ospp.vbs /dstatus` para obtener el estado de activación actual de Office. Esta operación **requiere permisos de Administrador**.

Resultado mostrado:

| Campo | Descripción |
|-------|-------------|
| Nombre del producto | Nombre completo del producto licenciado |
| Estado de licencia | Activado / Período de gracia / Sin licencia |
| Últimos 5 caracteres | Últimos 5 caracteres de la clave actualmente instalada |
| Product ID | Identificador del producto |
| Gracia restante | Días restantes de período de gracia (si aplica) |

### 11.3 Activación con clave de producto

**Procedimiento:**

1. Ingresar la clave de producto legítima en el campo de texto (formato: `XXXXX-XXXXX-XXXXX-XXXXX-XXXXX`, 25 caracteres alfanuméricos). El campo formatea automáticamente los guiones al escribir.
2. Hacer clic en **"Activar Office"**.
3. La aplicación ejecuta en secuencia:
   - `cscript ospp.vbs /inpkey:<clave>` — instala la clave en el almacén de licencias de Office.
   - `cscript ospp.vbs /act` — activa Office contra los servidores de Microsoft.
4. El resultado se muestra en pantalla indicando si la activación fue exitosa, si la clave fue rechazada, o si se requieren acciones adicionales.

**Seguridad de la clave de producto:**
- La clave **nunca se almacena** en logs ni reportes.
- Solo los **últimos 5 caracteres** son retenidos en el resultado para referencia del técnico.
- La variable que contiene la clave en memoria es sobreescrita en cuanto el subproceso inicia.
- El campo de ingreso es de tipo `password` (los caracteres no se muestran en pantalla).
- El campo se limpia automáticamente una vez enviada la solicitud al servidor.

### 11.4 Escenarios manejados por el módulo

| Escenario | Comportamiento de la aplicación |
|-----------|--------------------------------|
| Office no instalado | Informa: "Microsoft Office no detectado en este equipo." |
| ospp.vbs no encontrado | Informa: "No se encontró ospp.vbs. Office puede no estar instalado o estar en una ruta no estándar." |
| No hay permisos de Administrador | Informa: "Se requieren permisos de Administrador para inspeccionar/activar la licencia de Office." |
| Clave con formato inválido | Informa: "Formato de clave inválido. El formato debe ser XXXXX-XXXXX-XXXXX-XXXXX-XXXXX." |
| Clave no compatible con la edición | Informa el error reportado por ospp.vbs. No falla silenciosamente. |
| Activación exitosa | Informa: "Office activado correctamente con clave XXXXX-XXXXX-XXXXX-XXXXX-XXXXX." (clave enmascarada) |
| Activación fallida | Informa el error de activación reportado por ospp.vbs con código de error si está disponible. |

**Ediciones de Office soportadas por el módulo:**

| Versión | ClickToRun | MSI/Volumen |
|---------|-----------|-------------|
| Office 2016 | ✓ | ✓ |
| Office 2019 | ✓ | ✓ |
| Office 2021 | ✓ | ✓ |
| Office 2024 | ✓ | Pendiente de validación en piloto |
| Microsoft 365 | ✓ | N/A |

---

## 12. GENERACIÓN DE REPORTES

Después de completar una sesión de mantenimiento, el técnico hace clic en **"Generar Reporte"** en la tarjeta de resumen. La aplicación genera todos los formatos disponibles y muestra el resultado de cada uno.

### 12.1 Formatos generados

| Formato | Descripción | Destino |
|---------|-------------|---------|
| HTML local | Reporte visual completo con todos los hallazgos, resultados, inventario e historial de comandos | `C:\ProgramData\CleanCPU\reports\` |
| FO-TI-19 | Hoja de Servicio oficial RADEC (formato corporativo) | `C:\ProgramData\CleanCPU\reports\` |
| Excel FO-TI-19 | Versión Excel del formulario FO-TI-19 | `C:\ProgramData\CleanCPU\reports\` |
| Google Sheets | Registro en la hoja compartida corporativa RADEC | Hoja de cálculo Google configurada (requiere conectividad y credenciales) |
| Carpeta de red | Copia del reporte en ruta de red RADEC | Ruta de red compartida configurada (requiere conectividad) |

### 12.2 Contenido del reporte

Cada reporte incluye:

- **Identificación del equipo:** hostname, usuario, fabricante, modelo, número de serie, UUID, dominio/grupo de trabajo.
- **Datos del sistema operativo:** nombre, versión, build, arquitectura.
- **Hardware:** procesador, RAM, discos.
- **Red:** IP activa, MAC Ethernet, MAC WiFi.
- **Microsoft Office:** producto, versión, plataforma, canal.
- **Datos del técnico y fecha/hora de intervención.**
- **Resultado por paso:** estado, mensaje, hallazgos, errores, advertencias, acciones ejecutadas.
- **Hallazgos de seguridad:** por severidad (crítico, advertencia, informativo).
- **Acciones recomendadas pendientes:** lista consolidada de acciones que el técnico debe realizar manualmente.
- **Resumen ejecutivo:** pasos completados, omitidos, fallidos; tiempo total.

---

## 13. NOTAS OPERATIVAS Y ADVERTENCIAS

**Nota 1 — Administrador requerido para la mayoría de acciones:**
Las acciones DISM /CheckHealth, SFC /scannow, `defrag /O`, `cleanmgr` y Windows Update (`UsoClient`) requieren permisos de Administrador. Si la aplicación no está elevada, estas acciones se marcarán como omitidas con mensaje explicativo. No se reportarán como fallos del sistema; el técnico recibirá instrucción de cuáles acciones requieren re-ejecución como Administrador.

**Nota 2 — cleanmgr y el perfil /sageset:1:**
La limpieza avanzada de disco (`cleanmgr /sagerun:1`) requiere que el perfil de categorías haya sido configurado previamente con `cleanmgr /sageset:1` en el equipo específico. En equipos nuevos o recién formateados donde este perfil no existe, cleanmgr puede ejecutarse sin limpiar archivos. El técnico debe ejecutar `cleanmgr /sageset:1` manualmente en esos equipos la primera vez.

**Nota 3 — Lenovo Update no aplica a todos los equipos:**
El Paso 9 aplica únicamente a equipos Lenovo con Lenovo Vantage (`Lenovo.Vantage.exe`) o Lenovo System Update (`tvsu.exe`) instalado en las rutas estándar. En equipos de otras marcas o en equipos Lenovo sin estas herramientas, el paso se omite automáticamente. Esto es comportamiento esperado.

**Nota 4 — Windows Update (UsoClient StartScan):**
El comando inicia un escaneo de actualizaciones en segundo plano en el servicio de Windows Update. El resultado del escaneo no se retorna en tiempo real. El técnico debe verificar manualmente el estado de las actualizaciones en Configuración → Windows Update para confirmar si existen actualizaciones pendientes.

**Nota 5 — Tiempo de ejecución variable:**
La secuencia completa puede tomar entre 5 y 25 minutos según el estado y velocidad del equipo. SFC /scannow (Paso 3) es el paso más lento y puede tomar hasta 15 minutos en equipos con discos mecánicos (HDD) o con archivos del sistema dañados. DISM /CheckHealth (también en Paso 3) puede tomar hasta 2 minutos adicionales. El técnico debe esperar con paciencia la finalización de estos pasos.

**Nota 6 — No interrumpir durante la ejecución:**
No cerrar la ventana del EXE ni el navegador durante la ejecución del mantenimiento. Si se interrumpe abruptamente, los pasos en curso pueden quedar en estado indeterminado. Usar siempre el botón de cancelación formal si se requiere detener el proceso.

**Nota 7 — Antivirus corporativo:**
Algunos antivirus corporativos pueden detectar el EXE como sospechoso al analizar su contenido de heurística. Si esto ocurre, el Coordinador TI debe agregar la ruta completa de `CleanCPU.exe` a la lista de exclusiones del antivirus, y verificar que el hash del EXE corresponde al distribuido por el canal oficial de RADEC.

**Nota 8 — Sesión única por instancia:**
La aplicación soporta una sesión de mantenimiento activa a la vez. No ejecutar múltiples instancias del EXE en el mismo equipo simultáneamente.

---

## 14. GUÍA DE ERRORES COMUNES

| Síntoma observado | Causa probable | Acción recomendada |
|-------------------|----------------|-------------------|
| Pasos 4, 6, 8 se muestran como "Omitidos" con mensaje de Administrador | Aplicación ejecutada sin privilegios de Administrador | Cerrar la aplicación; reabrir con "Clic derecho → Ejecutar como administrador" |
| Pasos 1 y 3 muestran "Completado" pero DISM /CheckHealth y SFC /scannow no se ejecutaron | Sin Administrador, estas sub-operaciones se omiten internamente; el paso completa pero las anota en `admin_skipped` | Misma acción: reabrir como Administrador para que DISM y SFC se ejecuten |
| El navegador no se abre automáticamente al iniciar | Comportamiento del navegador predeterminado o demora en inicio del servidor | Abrir manualmente `http://127.0.0.1:5000` después de 15 segundos |
| "El sitio no está disponible" en el navegador | El servidor no inició o el puerto 5000 está ocupado | Verificar en el Administrador de tareas que `CleanCPU.exe` está en ejecución. Si el puerto está ocupado, identificar el proceso conflictivo. |
| "ospp.vbs no encontrado" en módulo Office | Office no instalado o instalado en ruta no estándar | Verificar la instalación de Office; revisar rutas estándar manualmente |
| Error de red al generar reporte Google Sheets | Sin conectividad a Internet o credenciales no configuradas | Verificar conectividad; revisar que el archivo de credenciales existe en `credentials/` |
| cleanmgr ejecuta pero no libera espacio visible | Perfil `/sageset:1` no configurado en el equipo | Ejecutar `cleanmgr /sageset:1` desde línea de comandos elevada; seleccionar las categorías deseadas; volver a ejecutar `cleanmgr /sagerun:1` |
| SFC reporta "infracciones de integridad detectadas y NO reparadas" | Corrupción del sistema que SFC no puede resolver por sí solo | Ejecutar `DISM /Online /Cleanup-Image /RestoreHealth` con Administrador, luego repetir `sfc /scannow` |
| Paso Lenovo Update "omitido" en equipo Lenovo | Lenovo Vantage no está instalado en las rutas estándar esperadas | Instalar Lenovo Vantage desde el sitio oficial de soporte de Lenovo |
| La activación de Office falla con código de error | Clave incompatible con la edición instalada, o problema de conectividad con servidores Microsoft | Verificar que la clave corresponde a la edición exacta de Office instalada; verificar conectividad |

---

## 15. BUENAS PRÁCTICAS DEL TÉCNICO

1. **Verificar el estado de Administrador antes de iniciar.** El panel principal muestra claramente si la aplicación está elevada. Iniciar el mantenimiento sin permisos de Administrador resultará en múltiples pasos omitidos.

2. **Documentar siempre el resultado.** Generar el reporte al finalizar cada intervención, incluso si hubo pasos con error o pasos omitidos. El reporte queda como evidencia de la intervención para el proceso FO-TI-19.

3. **Leer los resultados inline de cada paso.** Los mensajes de resultado de cada paso pueden indicar acciones manuales pendientes (por ejemplo: "Se recomienda reiniciar el equipo", "Ejecutar DISM /RestoreHealth"). Estas acciones no las ejecuta automáticamente la aplicación.

4. **No forzar el cierre durante la ejecución.** Siempre usar el botón formal de cancelación si se requiere detener el proceso.

5. **Registrar el estado del equipo antes de la intervención.** Si el usuario reportó problemas específicos antes del mantenimiento, documentarlos en el formulario FO-TI-19 para correlacionar con los hallazgos de la herramienta.

6. **No ingresar claves de Office no autorizadas.** Las claves de producto deben ser proporcionadas exclusivamente por el canal oficial de licenciamiento de RADEC. No usar claves genéricas, de prueba, ni provenientes de fuentes no verificadas.

7. **Reportar fallas repetidas al Coordinador TI.** Si un paso específico falla de forma consistente en múltiples equipos del mismo modelo o área, documentarlo y reportarlo para análisis de causa raíz.

8. **Verificar la resolución de advertencias críticas.** Si el Paso 1 (Auditoría de Seguridad) reporta hallazgos críticos (espacio en disco < 5 GB, servicios críticos detenidos), resolverlos antes o inmediatamente después del mantenimiento, según el procedimiento de escalación del Área TI.

---

*Fin del Manual de Usuario — RADEC Maintenance Program v3.0.0*
*Documento: MAN-MNT-001 | Área TI RADEC | 2026-04-04*
