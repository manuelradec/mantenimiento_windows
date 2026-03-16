# CleanCPU v3.0.0

Herramienta profesional de mantenimiento logico para Windows 10/11.
Aplicacion web local basada en Flask con arquitectura de gobernanza completa, empaquetable como `.exe` para distribucion interna.

---

## Que hace esta herramienta

Unifica en una sola interfaz web local todas las tareas de mantenimiento tecnico de Windows:

| Seccion | Funcionalidad |
|---|---|
| **Dashboard** | Vista general del sistema: CPU, RAM, disco, uptime |
| **Diagnosticos** | RAM, discos, SMART, TRIM, temperatura, procesos, servicios, drivers, red, programas de inicio, acceso remoto |
| **Limpieza** | Temp de usuario y sistema, papelera, cache DNS, cache de internet, SoftwareDistribution, cleanmgr, DISM ComponentCleanup, ReTrim SSD, desfragmentar HDD, duplicados |
| **Reparacion** | SFC /scannow, DISM CheckHealth/ScanHealth/RestoreHealth, CHKDSK, WinSAT, diagnostico de memoria |
| **Red** | Flush DNS, release/renew IP, reset TCP/IP, Winsock, autotuning, test de conectividad, sesiones SMB, proxy, carpetas compartidas |
| **Windows Update** | Escanear, descargar, instalar actualizaciones, hard reset de Windows Update, sincronizar hora |
| **Energia** | Planes de energia, reporte de bateria, hibernacion, contadores de procesador |
| **Drivers** | Listar drivers, dispositivos con problemas, drivers de terceros, drivers de video, errores en Event Log |
| **Seguridad** | Estado de Defender, escaneo rapido/completo, actualizar firmas, carga de CPU de escaneo, deteccion de antivirus de terceros |
| **Reportes** | Reportes incident-grade desde SQLite: HTML/TXT/JSON con resumen ejecutivo, snapshots, Event Viewer |
| **Avanzado** | Puntos de restauracion, diagnosticos de display/DWM/GPU, Panel Self Refresh |

---

## Requisitos

- **Python** 3.10 o superior
- **Sistema operativo**: Windows 10 (21H2+) o Windows 11 (22H2+)
- **Permisos**: Administrador recomendado (requerido para la mayoria de operaciones)
- **Editor recomendado**: Visual Studio Code

---

## Clonar el repositorio e iniciar en VS Code

### 1. Clonar con Git

Abre una terminal (PowerShell, CMD o la terminal integrada de VS Code) y ejecuta:

```bash
git clone https://github.com/manuelradec/mantenimiento_windows.git
cd mantenimiento_windows
```

### 2. Abrir en VS Code

Desde la misma terminal:

```bash
code .
```

O bien: abre VS Code > `File` > `Open Folder...` > selecciona la carpeta `mantenimiento_windows`.

### 3. Crear entorno virtual

Abre la terminal integrada de VS Code (`Ctrl+`` `) y ejecuta:

```bash
python -m venv venv
```

**Activar el entorno:**

```bash
# PowerShell (default en VS Code)
.\venv\Scripts\Activate.ps1

# CMD
venv\Scripts\activate.bat

# Git Bash
source venv/Scripts/activate
```

> VS Code puede detectar el venv automaticamente. Si aparece un popup preguntando si deseas seleccionarlo como interprete, acepta.

### 4. Instalar dependencias

```bash
# Dependencias de produccion
pip install -r requirements.txt

# Dependencias de desarrollo (tests, linting, types)
pip install -r requirements-dev.txt
```

### 5. Ejecutar en modo desarrollo

```bash
python server.py --dev
```

Se abre automaticamente en `http://127.0.0.1:5000`.

Para modo produccion (Waitress WSGI server):

```bash
python server.py
```

### 6. Ejecutar tests

```bash
python -m pytest tests/ -v
```

### 7. Ejecutar linting

```bash
flake8 core/ services/ routes/ app.py config.py
```

---

## Crear el .exe para distribucion

### Opcion A: Script automatico (recomendado)

1. Doble clic en **`build.bat`**
2. Espera 1-3 minutos
3. El ejecutable queda en `dist\CleanCPU.exe`

El script automaticamente:
- Verifica que Python este instalado
- Crea un entorno virtual si no existe
- Instala las dependencias de build (`requirements-build.txt`)
- Limpia builds anteriores
- Genera el `.exe` con PyInstaller

### Opcion B: Build manual

```bash
# Activar entorno virtual
.\venv\Scripts\Activate.ps1

# Instalar dependencias de build
pip install -r requirements-build.txt

# Construir el ejecutable
pyinstaller mantenimiento_windows.spec --noconfirm
```

El resultado esta en `dist\CleanCPU.exe`.

### Verificar el build

Tras el build exitoso, la terminal muestra:

```
============================================================
  BUILD SUCCESSFUL
============================================================

  Output: dist\CleanCPU.exe
  Size: XXXXX bytes
============================================================
```

Puedes probar el ejecutable localmente:

```bash
.\dist\CleanCPU.exe
```

---

## Distribuir a los usuarios

Solo se entrega **un archivo**: `CleanCPU.exe`

| Concepto | Detalle |
|---|---|
| **Archivo** | `CleanCPU.exe` (~15-25 MB) |
| **Requisitos del PC destino** | Windows 10 o 11, nada mas |
| **NO necesita instalar** | Python, pip, Flask, ni ninguna otra dependencia |
| **Permisos** | El .exe pide elevacion de administrador (UAC) automaticamente |

### Que pasa cuando el usuario ejecuta el .exe

1. Windows muestra el dialogo UAC pidiendo permisos de administrador
2. Se abre una ventana de consola mostrando:
   ```
   ============================================================
     CleanCPU v3.0.0
     Running at: http://127.0.0.1:5000
     Admin: True
     Mode: safe_maintenance
   ============================================================
   ```
3. El navegador se abre automaticamente con la interfaz
4. La consola debe permanecer abierta mientras se usa la herramienta
5. Para cerrar: cerrar la ventana de consola o Ctrl+C

### Donde se guardan los datos

| Tipo | Ubicacion |
|---|---|
| Base de datos SQLite | `C:\ProgramData\CleanCPU\cleancpu.db` |
| Logs de aplicacion | `C:\ProgramData\CleanCPU\logs\` |
| Log de eventos JSONL | `C:\ProgramData\CleanCPU\logs\events.jsonl` |
| Reportes exportados | `C:\ProgramData\CleanCPU\reports\` |

---

## Arquitectura v3.0.0

### Flujo de una accion mutante

```
Route (POST) ──> execute_governed_action()
                    │
                    ├── 1. Registry lookup (action_registry)
                    ├── 2. Applicability check (platform/hardware)
                    ├── 3. Before-snapshot (disk, RAM, CPU)
                    ├── 4. Policy check (mode + risk class)
                    ├── 5. Job submission (job_runner + locking)
                    ├── 6. Handler execution (service function)
                    ├── 7. After-snapshot
                    ├── 8. Rollback info attachment
                    ├── 9. SQLite persistence (audit + snapshots)
                    └── 10. JSONL event log
```

**Ninguna ruta mutante ejecuta logica directamente** — toda accion pasa por `execute_governed_action()` que garantiza registro, politica, auditoria y snapshots.

### Motor de politicas

| Modo | Permite | Bloquea |
|---|---|---|
| `DIAGNOSTIC` | Solo lectura | Toda mutacion |
| `SAFE_MAINTENANCE` | SAFE_READONLY, SAFE_MUTATION | DISRUPTIVE, RISKY, DESTRUCTIVE |
| `ADVANCED` | + DISRUPTIVE, RISKY (con confirmacion) | DESTRUCTIVE |
| `EXPERT` | Todo (con confirmacion para destructivas) | Nada |

### Clasificacion de riesgo

| Clase | Ejemplo | Confirmacion |
|---|---|---|
| `SAFE_READONLY` | Diagnosticos, listar drivers | No |
| `SAFE_MUTATION` | Limpiar temp, flush DNS | No |
| `DISRUPTIVE` | Reset Winsock, SFC | Si |
| `RISKY` | CHKDSK, hard reset WU | Si |
| `DESTRUCTIVE` | Eliminar perfil, DISM RestoreHealth | Si + token |

### Seguridad

- **Solo localhost** (`127.0.0.1`) — no expone ningun puerto a la red
- **CSRF tokens** en cada POST/PUT/DELETE/PATCH via `X-CSRF-Token`
- **Validacion de Host header** — rechaza requests con Host distinto a localhost
- **Validacion de Origin/Referer** — bloquea si faltan ambos headers
- **Session cookies** hardened: `HttpOnly`, `SameSite=Strict`, nombre `cleancpu_session`
- **CSP** con `default-src 'self'`, `form-action 'self'`, `frame-ancestors 'none'`
- **Allowlist de comandos** granular por ejecutable con subcomandos y argumentos denegados
- **Sanitizacion de argumentos** — bloquea `;`, `|`, `` ` ``, `..`, saltos de linea

---

## Estructura del proyecto

```
mantenimiento_windows/
├── app.py                          # Factory Flask + API endpoints
├── config.py                       # Configuracion centralizada
├── server.py                       # Servidor produccion (Waitress)
├── build.bat                       # Script de build automatico
├── mantenimiento_windows.spec      # Configuracion PyInstaller
├── requirements.txt                # Dependencias produccion
├── requirements-dev.txt            # Dependencias desarrollo (test, lint)
├── requirements-build.txt          # Dependencias build (PyInstaller)
├── .flake8                         # Configuracion linting
├── VALIDATION_PLAN.md              # Plan de validacion Windows
│
├── core/                           # Capa de gobernanza y seguridad
│   ├── governance.py               # execute_governed_action() - puente central
│   ├── action_registry.py          # Catalogo de ~70 acciones con clasificacion de riesgo
│   ├── policy_engine.py            # Motor de politicas (4 modos operativos)
│   ├── job_runner.py               # Ejecucion en background con ThreadPoolExecutor
│   ├── persistence.py              # SQLite: audit, jobs, sessions, snapshots, event_viewer
│   └── security.py                 # CSRF, Origin, Host, cookies, CSP, headers
│
├── services/                       # Capa de servicios (logica de negocio)
│   ├── command_runner.py           # Ejecucion segura con allowlist granular
│   ├── permissions.py              # Validacion de admin
│   ├── system_info.py              # Diagnosticos del sistema
│   ├── cleanup.py                  # Limpieza y optimizacion
│   ├── repair.py                   # Reparacion del SO
│   ├── network_tools.py            # Herramientas de red
│   ├── windows_update.py           # Windows Update
│   ├── power_tools.py              # Energia y rendimiento
│   ├── graphics_tools.py           # Graficos y display
│   ├── antivirus_tools.py          # Seguridad y antivirus
│   ├── restore_tools.py            # Puntos de restauracion
│   ├── drivers.py                  # Diagnostico de drivers
│   ├── event_viewer.py             # Recopilacion Event Viewer (PowerShell JSON)
│   └── reports.py                  # Logs y reportes legacy
│
├── routes/                         # Blueprints Flask (todas gobernadas)
│   ├── dashboard.py                # Solo lectura
│   ├── diagnostics.py              # Solo lectura
│   ├── cleanup.py                  # 14 endpoints gobernados
│   ├── repair.py                   # 10 endpoints gobernados
│   ├── network.py                  # 10 endpoints gobernados
│   ├── update.py                   # 6 endpoints gobernados
│   ├── power.py                    # 5 endpoints gobernados
│   ├── security.py                 # 4 endpoints gobernados
│   ├── advanced.py                 # 1 endpoint gobernado
│   ├── drivers.py                  # Solo lectura
│   └── reports.py                  # SQLite-first, incident-grade
│
├── templates/                      # Plantillas Jinja2 (HTML)
│   ├── base.html                   # Layout con sidebar, job status bar, cancel button
│   └── *.html                      # Una plantilla por seccion
│
├── static/
│   ├── css/style.css               # Estilos CSS
│   └── js/app.js                   # Frontend: CSRF, confirmacion, cancelacion, rollback
│
├── tests/                          # 102 tests
│   ├── test_routes.py              # Rutas, CSRF, Origin, Host, headers, endpoints gobernados
│   ├── test_governance.py          # Comandos, sanitizacion, rollback, registry, policy, DB
│   └── test_policy_engine.py       # Policy engine, registry, persistence
│
└── .github/workflows/ci.yml       # CI: flake8 + pytest + mypy (Python 3.10/3.11/3.12)
```

---

## Notas tecnicas para el build

- `console=True` en el `.spec`: la consola permanece abierta para mostrar la URL del servidor. Si se cierra la consola, la aplicacion se detiene.
- `uac_admin=True` en el `.spec`: Windows solicita elevacion UAC automaticamente.
- `use_reloader=False` en `app.py`: el reloader de Flask no es compatible con ejecutables empaquetados por PyInstaller.
- Los templates y archivos estaticos se incluyen via `datas` en el `.spec` porque Flask los lee desde disco en tiempo de ejecucion.
- Los modulos Python (`services/`, `routes/`, `core/`) se incluyen via `hiddenimports` para que PyInstaller los compile e integre correctamente.
- La base de datos SQLite se crea automaticamente en el primer arranque.

---

## CI/CD

El repositorio incluye un workflow de GitHub Actions (`.github/workflows/ci.yml`) que ejecuta en cada push y PR:

1. **Lint** — `flake8` sobre `core/`, `services/`, `routes/`, `app.py`, `config.py`
2. **Tests** — `pytest` con cobertura sobre `core/`, `services/`, `routes/`
3. **Type check** — `mypy` sobre modulos core

Matrix: Python 3.10, 3.11, 3.12.
