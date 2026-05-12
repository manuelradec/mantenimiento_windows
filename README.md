# CleanCPU v3.0.0 — RADEC AUTOPARTES

Herramienta profesional de mantenimiento lógico para Windows 10/11.
Aplicación web local basada en Flask con arquitectura de gobernanza completa,
empaquetable como `.exe` para distribución interna en sucursales RADEC.

> **Tema oscuro corporativo RADEC** | **Interfaz 100% en español (LATAM)** | **287 tests automatizados**

---

## Índice

1. [Qué hace esta herramienta](#qué-hace-esta-herramienta)
2. [Requisitos del sistema](#requisitos-del-sistema)
3. [Instalación y primera ejecución](#instalación-y-primera-ejecución)
4. [Cómo ejecutar la aplicación](#cómo-ejecutar-la-aplicación)
5. [Generar el .exe para distribución](#generar-el-exe-para-distribución)
6. [Distribución en sucursales](#distribución-en-sucursales)
7. [Reportes RADEC (FO-TI-19 / FO-TI-20)](#reportes-radec-fo-ti-19--fo-ti-20)
8. [Detección de mejoras de hardware](#detección-de-mejoras-de-hardware)
9. [Configuración avanzada](#configuración-avanzada)
10. [Arquitectura](#arquitectura)
11. [Estructura del proyecto](#estructura-del-proyecto)
12. [CI/CD y desarrollo](#cicd-y-desarrollo)
13. [Solución de problemas](#solución-de-problemas)

---

## Qué hace esta herramienta

Unifica en una sola interfaz web local todas las tareas de mantenimiento técnico de Windows
y genera reportes profesionales con el formato oficial RADEC.

| Sección | Funcionalidad |
|---|---|
| **Panel principal** | Vista general del sistema: CPU, RAM, disco, uptime, equipo, sucursal |
| **Diagnósticos** | RAM, discos, SMART, TRIM, temperatura, procesos, servicios, drivers, red, programas de inicio, acceso remoto |
| **Limpieza** | Temp de usuario y sistema, papelera, caché DNS, caché de internet, SoftwareDistribution, cleanmgr, DISM ComponentCleanup, ReTrim SSD, desfragmentar HDD, duplicados |
| **Reparación** | SFC /scannow, DISM CheckHealth/ScanHealth/RestoreHealth, CHKDSK, WinSAT, diagnóstico de memoria |
| **Red** | Flush DNS, release/renew IP, reset TCP/IP, Winsock, autotuning, test de conectividad, sesiones SMB, proxy, carpetas compartidas |
| **Windows Update** | Escanear, descargar, instalar actualizaciones, hard reset de Windows Update, sincronizar hora |
| **Energía** | Planes de energía, reporte de batería, hibernación, contadores de procesador |
| **Controladores** | Listar drivers, dispositivos con problemas, drivers de terceros, drivers de video, errores en Event Log |
| **Seguridad** | Estado de Defender, escaneo rápido/completo, actualizar firmas, Smart App Control, detección de antivirus de terceros |
| **Mantenimiento Lógico** | Secuencia automatizada de 8 pasos (ejecutables completos o uno a uno desde el dashboard): Auditoría de seguridad, Limpieza interna, Salud del sistema (DISM CheckHealth + SFC), Desfragmentación, Limpieza extendida de disco, Reparación profunda (DISM RestoreHealth), Windows Update, Lenovo Update. Audit trail por paso en SQLite + diálogo de recomendaciones post-ejecución con countdown 30s. |
| **Reinicio Programado** | Programar reinicio único o recurrente (Una vez, Diario, Semanal, Mensual) vía Tareas Programadas de Windows |
| **Reportes RADEC** | Generación de **FO-TI-19** (Hoja de Servicio) y **FO-TI-20** (Bitácora) en HTML imprimible |
| **Registros** | Visor en tiempo real del log rotativo con filtros por nivel y búsqueda |
| **Avanzado** | Puntos de restauración, diagnósticos de display/DWM/GPU |

---

## Requisitos del sistema

### Para el equipo de desarrollo (donde compilas el .exe)

- **Python** 3.10 o superior (recomendado 3.11)
- **Sistema operativo**: Windows 10 (21H2+) o Windows 11 (22H2+)
- **Git** instalado
- **VS Code** (recomendado) o cualquier editor de código
- **~500 MB** de espacio libre para el entorno virtual + dependencias

### Para los equipos destino (donde se ejecuta el .exe)

- **Sistema operativo**: Windows 10 (cualquier versión) o Windows 11
- **Permisos**: Cuenta de administrador (UAC se solicita automáticamente)
- **Espacio**: ~50 MB libres en disco
- **NO se necesita instalar** Python, Flask, ni ninguna dependencia adicional

---

## Instalación y primera ejecución

### Paso 1: Clonar el repositorio

Abre PowerShell, CMD o la terminal de VS Code y ejecuta:

```bash
git clone https://github.com/manuelradec/mantenimiento_windows.git
cd mantenimiento_windows
```

### Paso 2: Abrir en VS Code (opcional pero recomendado)

```bash
code .
```

O bien: `Archivo` → `Abrir Carpeta...` → selecciona la carpeta `mantenimiento_windows`.

### Paso 3: Crear el entorno virtual de Python

En la terminal integrada (`Ctrl + ñ` en VS Code):

```powershell
python -m venv venv
```

Esto crea una carpeta `venv\` con una instalación aislada de Python.

### Paso 4: Activar el entorno virtual

**En PowerShell (predeterminado en VS Code):**

```powershell
.\venv\Scripts\Activate.ps1
```

> Si PowerShell bloquea el script con un error de política de ejecución, ejecuta esto una sola vez:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

**En CMD:**

```cmd
venv\Scripts\activate.bat
```

**En Git Bash:**

```bash
source venv/Scripts/activate
```

Cuando esté activado verás `(venv)` al inicio del prompt. VS Code generalmente detecta el venv
automáticamente y te pregunta si quieres usarlo como intérprete; acepta.

### Paso 5: Instalar las dependencias

```bash
pip install -r requirements.txt          # Dependencias de producción
pip install -r requirements-dev.txt      # + dependencias de desarrollo (tests, lint)
```

### Paso 6: Verificar la instalación

```bash
python -m pytest tests/ -v
```

Deberías ver **287 tests passed** al final.

---

## Cómo ejecutar la aplicación

### Modo desarrollo (recomendado durante codificación)

```bash
python server.py --dev
```

- Arranca el servidor de Flask en modo debug
- Mensajes detallados en consola
- Abre el navegador automáticamente en `http://127.0.0.1:5000`
- **No** usa Waitress; usa el servidor de desarrollo de Flask

### Modo producción (recomendado para uso normal)

```bash
python server.py
```

- Arranca con **Waitress** (WSGI thread-safe, listo para producción)
- Mensajes mínimos en consola
- Abre el navegador automáticamente

### Opciones de línea de comandos

```bash
python server.py --dev              # Modo desarrollo (Flask debug server)
python server.py --port 8080        # Cambiar puerto (default: 5000)
python server.py --no-browser       # No abrir el navegador automáticamente
python server.py --help             # Ver todas las opciones
```

### Atajos de uso

| Acción | Cómo |
|---|---|
| Detener la aplicación | `Ctrl + C` en la consola, o cerrar la ventana |
| Acceder desde el navegador | `http://127.0.0.1:5000` |
| Cambiar de modo de operación | Botón en el sidebar (DIAGNÓSTICO / MANTENIMIENTO SEGURO / AVANZADO / EXPERTO) |
| Ver registros | Menú lateral → **Registros** |
| Cancelar tarea en ejecución | Botón "Cancelar" en la barra inferior |

### Ejecutar tests y verificar calidad de código

```bash
python -m pytest tests/ -v                                # Tests (287 tests)
python -m pytest tests/ -v --cov=core --cov=services      # Tests + cobertura
flake8 core/ services/ routes/ app.py config.py           # Linting
mypy core/                                                 # Type checking
```

---

## Generar el .exe para distribución

### Opción A: Script automático (recomendado)

1. Doble clic en **`build.bat`**
2. Espera 1-3 minutos
3. El ejecutable queda en `dist\CleanCPU.exe`

El script hace todo automáticamente:
- Verifica que Python esté instalado
- Crea el entorno virtual si no existe
- Instala las dependencias de build (`requirements-build.txt`)
- Limpia builds anteriores
- Genera el `.exe` con PyInstaller (modo `--onefile --windowed`)

### Opción B: Build manual

```bash
# Activar entorno virtual
.\venv\Scripts\Activate.ps1

# Instalar dependencias de build
pip install -r requirements-build.txt

# Construir el ejecutable
pyinstaller mantenimiento_windows.spec --noconfirm
```

El resultado queda en `dist\CleanCPU.exe`.

### Verificar el build

Tras un build exitoso verás algo así:

```
============================================================
  BUILD SUCCESSFUL
============================================================

  Output: dist\CleanCPU.exe
  Size: ~22 MB
============================================================
```

Pruébalo localmente:

```bash
.\dist\CleanCPU.exe
```

### Configuración del build (mantenimiento_windows.spec)

| Opción | Valor | Razón |
|---|---|---|
| `console=False` | Sin ventana de consola | Experiencia limpia para el usuario final |
| `uac_admin=True` | Solicita UAC al iniciar | Acciones requieren admin |
| `--onefile` | Un solo archivo `.exe` | Fácil distribución |
| `datas` | Incluye `templates/`, `static/`, `credentials/`, `templates_data/` | Flask necesita estos en runtime |
| `hiddenimports` | Lista todos los módulos `services/`, `routes/`, `core/` | PyInstaller no detecta imports dinámicos |

---

## Distribución en sucursales

Solo se entrega **un archivo**: `CleanCPU.exe`

| Concepto | Detalle |
|---|---|
| **Archivo** | `CleanCPU.exe` (~20-25 MB) |
| **Requisitos del PC destino** | Windows 10 u 11, nada más |
| **NO necesita instalar** | Python, pip, Flask, ni ninguna otra dependencia |
| **Permisos** | El .exe pide elevación de administrador (UAC) automáticamente |
| **Conexión a Internet** | No es requerida; solo opcional para Google Sheets y carpeta de red |

### Qué pasa cuando el usuario ejecuta el .exe

1. Windows muestra el diálogo UAC pidiendo permisos de administrador → Aceptar
2. La aplicación se inicia en segundo plano (sin ventana de consola)
3. El navegador se abre automáticamente con la interfaz en `http://127.0.0.1:5000`
4. El usuario realiza el mantenimiento desde el navegador
5. Para cerrar: cerrar la pestaña del navegador y luego cerrar el proceso `CleanCPU.exe`
   desde el Administrador de Tareas (o esperar a que termine solo)

### Dónde se guardan los datos

| Tipo | Ubicación |
|---|---|
| Base de datos SQLite (auditoría, jobs, snapshots) | `C:\ProgramData\CleanCPU\cleancpu.db` |
| Logs rotativos de la aplicación | `C:\ProgramData\CleanCPU\logs\cleancpu.log` |
| Log de eventos JSONL (governance) | `C:\ProgramData\CleanCPU\logs\events.jsonl` |
| Reportes exportados (HTML / FO-TI-19 / FO-TI-20 / Excel) | `C:\ProgramData\CleanCPU\reports\` |

> Si `C:\ProgramData\` no tiene permisos de escritura, la aplicación crea automáticamente
> un fallback en la carpeta del propio `.exe`.

---

## Reportes RADEC (FO-TI-19 / FO-TI-20)

CleanCPU genera reportes oficiales en el formato corporativo RADEC AUTOPARTES, listos para
imprimir o exportar a PDF desde el navegador.

### FO-TI-19 — Hoja de Servicio Mantenimiento de Equipo de Cómputo

Reporte detallado por equipo, con todos los campos del formato oficial:

- Encabezado con logo RADEC, código `FO-TI-19`, fecha de emisión
- Sucursal, Fecha de Solicitud
- Nombre del solicitante (detectado automáticamente del usuario logueado en Windows)
- Dirección, Teléfono, Correo electrónico (del Active Directory si está disponible)
- **Datos del equipo**: descripción, marca, modelo, número de serie
- **Datos del monitor**: marca, modelo, número de serie (vía WmiMonitorID)
- **Procesador, Velocidad**: detectado vía `Win32_Processor`
- **Capacidad de RAM** con tipo (DDR4/DDR5) y velocidad
- **Capacidad de HD** con tipo (SSD/HDD/NVMe)
- **Sistema operativo** completo (ej. "Windows 11 Pro 25H2")
- **Unidades** (CD-ROM, DVD-ROM, USB, Micro SD — detectadas automáticamente)
- Tipo de Servicio (Revisión / Preventivo / Correctivo)
- Comentarios sobre la falla
- Observaciones estado físico
- **Firma del solicitante y de quien recibe** (espacios designados)
- **Actividades realizadas**
- **Observaciones del técnico**
- **Sección de Mejoras de Hardware** (ver siguiente sección)

#### Cómo generarlo

1. Menú lateral → **Reportes**
2. Llenar campos: **Sucursal** (ej. "CN PUEBLA") y **Nombre del Técnico**
3. Sección "FO-TI-19 — Hoja de Servicio" → botón **Descargar HTML**
4. Se descarga `FO-TI-19_HOSTNAME_FECHA.html`
5. Abrirlo en el navegador → botón **Imprimir / Guardar PDF**

### FO-TI-20 — Bitácora de Mantenimiento de Equipo de Cómputo

Tabla resumen de mantenimientos realizados en una sucursal, con columnas:

| # | Fecha | Usuario | Equipo | Reporte Final | Firma |
|---|---|---|---|---|---|

#### Cómo generarlo

1. Menú lateral → **Reportes**
2. Llenar campo **Sucursal**
3. En la sección "Entradas para Bitácora FO-TI-20" agregar una fila por equipo:
   - Fecha
   - Nombre del usuario
   - Modelo del equipo
   - Reporte final (por defecto "MANTENIMIENTO PREVENTIVO")
4. Botón **+ Agregar entrada** para más equipos
5. Sección "FO-TI-20 — Bitácora" → botón **Descargar HTML**
6. Imprimir o guardar como PDF desde el navegador

### Otros formatos de reporte

Además de FO-TI-19/20, también puedes exportar:

- **HTML** — Reporte completo de la sesión con tabla de acciones, estado, errores
- **TXT** — Texto plano para copiar/pegar en tickets
- **JSON** — Bundle estructurado con session_id, hostname, audit_log, snapshots, jobs, event_viewer
- **Excel FO-TI-19** — Versión `.xlsx` editable (vía openpyxl)

---

## Detección de mejoras de hardware

CleanCPU **escanea el hardware del equipo** y detecta automáticamente oportunidades de upgrade.
Esta información se incluye en la sección "MEJORAS DE HARDWARE DETECTADAS" del FO-TI-19 y en
la pestaña **Reportes** del navegador.

### Qué detecta

| Componente | Qué se detecta |
|---|---|
| **RAM** | Slots totales vs. ocupados, slots vacíos disponibles, capacidad actual vs. máxima soportada, tipo (DDR3/DDR4/DDR5), velocidad |
| **Almacenamiento** | Discos HDD (mecánicos) que pueden actualizarse a SSD/NVMe; discos SSD SATA que pueden migrarse a NVMe |
| **Slots M.2 / NVMe** | Slots M.2 totales en la placa base, slots disponibles para expansión, discos NVMe instalados |
| **Estado SMART** | Salud de cada disco (`Healthy`, `Warning`, `Unhealthy`) |

### Cómo usarlo

1. Menú lateral → **Reportes**
2. Sección "Mejoras de Hardware Detectadas" → botón **Escanear Mejoras**
3. Se muestran tarjetas con:
   - RAM: barra de progreso de capacidad usada/máxima, módulos instalados por slot
   - Almacenamiento: lista de discos con tipo, tamaño, salud SMART
   - Slots M.2: total / disponibles / instalados
   - Recomendaciones automáticas

La información también queda **embebida en el FO-TI-19** cuando se descarga, así el técnico
de campo puede entregar al usuario un reporte con sugerencias de upgrade documentadas.

### Ejemplo de recomendaciones generadas

- _"RAM: 2 slot(s) disponible(s). Actualmente 8 GB de 32 GB max. Puede agregar módulos DDR4-3200 para mejorar rendimiento."_
- _"ALMACENAMIENTO: Se detectó disco duro mecánico (HDD). Se recomienda actualizar a SSD/NVMe para mejorar significativamente los tiempos de arranque y rendimiento general."_
- _"NVMe M.2: 1 slot(s) M.2 disponible(s). Puede instalar un disco NVMe adicional para más almacenamiento de alto rendimiento."_

---

## Configuración avanzada

### Integración con Google Sheets (opcional)

Para que los mantenimientos se registren automáticamente en la hoja corporativa:

1. Crear un Service Account en Google Cloud Console
2. Descargar el archivo JSON de credenciales
3. Renombrarlo a `service_account.json`
4. Copiarlo a la carpeta `credentials/` antes de hacer el build

```
mantenimiento_windows/
└── credentials/
    └── service_account.json   ← Tu archivo de credenciales
```

5. Compartir la hoja de cálculo con el email del Service Account
6. El ID de la hoja está en `services/maintenance_report.py:21` (`GOOGLE_SHEET_ID`)

Si no se configura, la integración se omite silenciosamente sin afectar la generación de reportes locales.

### Carpeta de red compartida

Los reportes se copian automáticamente a:

```
\\192.168.122.215\soporte CLJ\Mantenimiento Anual\YYYY-MM-DD\
```

Definido en `services/maintenance_report.py:22` (`NETWORK_SHARE_BASE`).

Si la red no está disponible, los reportes solo se guardan localmente sin error.

### Variables de entorno

| Variable | Descripción | Default |
|---|---|---|
| `FLASK_SECRET_KEY` | Llave secreta para sesiones Flask | `'cleancpu-local-key'` |
| `PROGRAMDATA` | Ruta base para datos persistentes | `C:\ProgramData` |

### Modo de operación

| Modo | Permite | Bloquea |
|---|---|---|
| `DIAGNOSTIC` | Solo lectura | Toda mutación |
| `SAFE_MAINTENANCE` (default) | SAFE_READONLY, SAFE_MUTATION | DISRUPTIVE, RISKY, DESTRUCTIVE |
| `ADVANCED` | + DISRUPTIVE, RISKY (con confirmación) | DESTRUCTIVE |
| `EXPERT` | Todo (con confirmación para destructivas) | Nada |

Cambia el modo desde el botón de la barra lateral inferior (mostrado como badge).

---

## Arquitectura

### Flujo de una acción mutante

```
Ruta (POST) ──> execute_governed_action()
                  │
                  ├── 1. Registry lookup (action_registry)
                  ├── 2. Verificación de aplicabilidad (plataforma/hardware)
                  ├── 3. Snapshot pre-ejecución (disco, RAM, CPU)
                  ├── 4. Verificación de política (modo + clase de riesgo)
                  ├── 5. Encolar job (job_runner + locking)
                  ├── 6. Ejecución del handler (función de servicio)
                  ├── 7. Snapshot post-ejecución
                  ├── 8. Adjuntar info de rollback
                  ├── 9. Persistir en SQLite (audit + snapshots)
                  └── 10. Log de evento JSONL
```

**Ninguna ruta mutante ejecuta lógica directamente** — toda acción pasa por
`execute_governed_action()` que garantiza registro, política, auditoría y snapshots.

### Clasificación de riesgo

| Clase | Ejemplo | Confirmación |
|---|---|---|
| `SAFE_READONLY` | Diagnósticos, listar drivers | No |
| `SAFE_MUTATION` | Limpiar temp, flush DNS | No |
| `DISRUPTIVE` | Reset Winsock, SFC | Sí |
| `RISKY` | CHKDSK, hard reset WU | Sí |
| `DESTRUCTIVE` | Eliminar perfil, DISM RestoreHealth | Sí + token |

### Seguridad

- **Solo localhost** (`127.0.0.1`) — no expone ningún puerto a la red
- **CSRF tokens** en cada POST/PUT/DELETE/PATCH vía `X-CSRF-Token`
- **Validación de Host header** — rechaza requests con Host distinto a localhost
- **Validación de Origin/Referer** — bloquea si faltan ambos headers
- **Cookies de sesión** endurecidas: `HttpOnly`, `SameSite=Strict`, nombre `cleancpu_session`
- **CSP** con `default-src 'self'`, `form-action 'self'`, `frame-ancestors 'none'`
- **Allowlist de comandos** granular por ejecutable con subcomandos y argumentos denegados
- **Sanitización de argumentos** — bloquea `;`, `|`, backticks, `..`, saltos de línea
- **Subprocess con encoding utf-8** y `errors='replace'` para evitar UnicodeDecodeError

### Sistema de logging

- **RotatingFileHandler** — `cleancpu.log` rota a los 10 MB, mantiene 5 backups
- **Visor en la web** (`/logs`) con auto-refresh cada 5s, filtros por nivel y búsqueda
- **JSONL events** — auditoría estructurada para sistemas externos (SIEM, etc.)
- **SQLite audit** — tabla `audit_log` con índices para queries rápidos

---

## Estructura del proyecto

```
mantenimiento_windows/
├── app.py                          # Factory Flask + endpoints API + RotatingFileHandler
├── config.py                       # Configuración centralizada (paths, timeouts, cookies)
├── server.py                       # Servidor producción (Waitress) / dev mode
├── build.bat                       # Script de build automático
├── mantenimiento_windows.spec      # Configuración PyInstaller (console=False, uac_admin=True)
├── requirements.txt                # Dependencias producción
├── requirements-dev.txt            # Dependencias desarrollo (test, lint, types)
├── requirements-build.txt          # Dependencias build (PyInstaller)
├── .flake8                         # Configuración linting
├── README.md                       # Este archivo
├── VALIDATION_PLAN.md              # Plan de validación Windows
│
├── core/                           # Capa de gobernanza y seguridad
│   ├── governance.py               # execute_governed_action() — puente central
│   ├── action_registry.py          # Catálogo de ~70 acciones con clasificación de riesgo
│   ├── policy_engine.py            # Motor de políticas (4 modos operativos)
│   ├── job_runner.py               # Ejecución en background con ThreadPoolExecutor
│   ├── persistence.py              # SQLite: audit, jobs, sessions, snapshots, event_viewer
│   ├── snapshots.py                # Snapshots action-aware antes/después
│   └── security.py                 # CSRF, Origin, Host, cookies, CSP, headers
│
├── services/                       # Capa de servicios (lógica de negocio)
│   ├── command_runner.py           # Ejecución segura con allowlist granular
│   ├── permissions.py              # Validación de admin
│   ├── system_info.py              # Diagnósticos + detección de mejoras de hardware
│   ├── cleanup.py                  # Limpieza y optimización
│   ├── repair.py                   # Reparación del SO
│   ├── network_tools.py            # Herramientas de red
│   ├── windows_update.py           # Windows Update (con traducción de error codes)
│   ├── power_tools.py              # Energía y rendimiento
│   ├── graphics_tools.py           # Gráficos y display
│   ├── antivirus_tools.py          # Seguridad y antivirus
│   ├── restore_tools.py            # Puntos de restauración
│   ├── smart_app_control.py        # Smart App Control de Windows 11
│   ├── drivers.py                  # Diagnóstico de drivers
│   ├── event_viewer.py             # Recopilación Event Viewer (PowerShell JSON)
│   ├── reports.py                  # Logs y reportes legacy
│   └── maintenance_report.py       # Generación FO-TI-19, FO-TI-20, Google Sheets, red
│
├── routes/                         # Blueprints Flask (todas gobernadas)
│   ├── dashboard.py                # Solo lectura
│   ├── diagnostics.py              # Solo lectura (16+ endpoints)
│   ├── cleanup.py                  # 14 endpoints gobernados
│   ├── repair.py                   # 10 endpoints gobernados
│   ├── network.py                  # 10 endpoints gobernados
│   ├── update.py                   # 6 endpoints gobernados
│   ├── power.py                    # 5 endpoints gobernados
│   ├── security.py                 # 4 endpoints gobernados
│   ├── advanced.py                 # 1 endpoint gobernado
│   ├── drivers.py                  # Solo lectura
│   ├── reports.py                  # Exports: HTML/TXT/JSON + FO-TI-19/20 + hardware upgrades
│   ├── maintenance.py              # Mantenimiento Lógico (8 pasos secuenciales + single-step + audit)
│   ├── scheduled_restart.py        # CRUD de Tareas Programadas de Windows
│   └── logs.py                     # Visor en tiempo real del log rotativo
│
├── templates/                      # Plantillas Jinja2 (HTML)
│   ├── base.html                   # Layout con sidebar, search bar, job status bar
│   ├── dashboard.html              # Panel principal
│   ├── reports.html                # FO-TI-19/20 + escaneo de mejoras
│   ├── maintenance.html            # UI del mantenimiento lógico 8-pasos (con botón ▶ por paso)
│   ├── scheduled_restart.html      # Form de programación de reinicio
│   ├── logs.html                   # Visor de logs con filtros
│   └── *.html                      # Una plantilla por sección
│
├── static/
│   ├── css/style.css               # Tema oscuro RADEC corporativo
│   └── js/app.js                   # Frontend: CSRF, búsqueda global, modales, rollback
│
├── credentials/                    # Google Service Account JSON (gitignored)
│   └── .gitkeep
│
├── templates_data/                 # Plantillas Excel para FO-TI-19 (opcional)
│   └── .gitkeep
│
├── tests/                          # 287 tests (240 hist. + 23 scheduled_restart + 16 maintenance + 8 reports)
│   ├── conftest.py                 # Fixture autouse: aísla DB en tmp_path, resetea thread-local conn
│   ├── test_routes.py              # Rutas, CSRF, Origin, Host, headers, endpoints gobernados
│   ├── test_governance.py          # Comandos, sanitización, rollback, registry, policy, DB
│   ├── test_policy_engine.py       # Policy engine, registry, persistence
│   ├── test_hardening.py           # Seguridad y hardening
│   ├── test_snapshots.py           # Snapshots before/after
│   ├── test_smart_app_control.py   # Smart App Control
│   ├── test_maintenance.py         # 8 pasos, single-step (400/409/happy), audit trail (T-03)
│   ├── test_scheduled_restart.py   # Governance, audit trail SQLite, rollback (T-02)
│   └── test_reports.py             # Export xlsx histórico, filtros date/hostname (T-04)
│
└── .github/workflows/ci.yml       # CI: flake8 + pytest + mypy (Python 3.10/3.11/3.12)
```

---

## CI/CD y desarrollo

El repositorio incluye un workflow de GitHub Actions (`.github/workflows/ci.yml`) que ejecuta
automáticamente en cada push y PR:

1. **Lint** — `flake8` sobre `core/`, `services/`, `routes/`, `app.py`, `config.py`
2. **Tests** — `pytest` con cobertura sobre `core/`, `services/`, `routes/`
3. **Type check** — `mypy` sobre módulos core

Matrix: Python 3.10, 3.11, 3.12.

### Comandos útiles para desarrollo

```bash
# Activar venv y entrar al proyecto
.\venv\Scripts\Activate.ps1

# Lint
flake8 core/ services/ routes/ app.py config.py --max-line-length=120

# Tests con cobertura
python -m pytest tests/ -v --cov=core --cov=services --cov=routes

# Type check
mypy core/

# Limpiar caché
Remove-Item -Recurse -Force __pycache__, .pytest_cache, build, dist -ErrorAction SilentlyContinue

# Ver logs en vivo (mientras corre la app)
Get-Content -Wait -Tail 50 "$env:PROGRAMDATA\CleanCPU\logs\cleancpu.log"
```

---

## Solución de problemas

### "PowerShell no puede ejecutar scripts"

Ejecuta una sola vez en PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### El puerto 5000 ya está en uso

Otro programa ya ocupa el puerto. Usa otro:

```bash
python server.py --port 8080
```

### El .exe no abre o se cierra inmediatamente

Revisa el log:

```
C:\ProgramData\CleanCPU\logs\cleancpu.log
```

Causas comunes:
- Falta dar permisos de administrador (UAC denegado)
- Antivirus bloqueando el `.exe` → agregar excepción
- Carpeta `C:\ProgramData\CleanCPU\` con permisos restrictivos

### "Bibliotecas de Google no instaladas" al generar reporte

Es informativo, no es error. Si quieres usar Google Sheets:

```bash
pip install gspread google-auth
```

Si no, se omite y se generan el resto de reportes normalmente.

### El reporte no se copia a la carpeta de red

- Verifica que estés conectado a la VPN/red corporativa
- Verifica acceso manual: `\\192.168.122.215\soporte CLJ\Mantenimiento Anual`
- Si no se puede, el reporte solo se guarda localmente sin error

### Tests fallan con `ModuleNotFoundError`

Olvidaste activar el venv:

```powershell
.\venv\Scripts\Activate.ps1
```

### El PyInstaller falla con "module not found"

Agrega el módulo a `hiddenimports` en `mantenimiento_windows.spec`:

```python
hiddenimports = [
    ...,
    'tu.modulo.faltante',
]
```

### El CSS desaparece en el .exe empaquetado

Verifica que `mantenimiento_windows.spec` tenga:

```python
datas = [
    (templates_dir, 'templates'),
    (static_dir, 'static'),
    ...
]
```

---

## Licencia y soporte

Uso interno de **RADEC AUTOPARTES**. Para soporte técnico, contactar al equipo de TI de RADEC.

**Versión actual**: 3.0.0 — Spring 2026
