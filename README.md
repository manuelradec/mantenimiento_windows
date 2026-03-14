# Mantenimiento Windows v2.0

Herramienta profesional de mantenimiento logico para Windows 10/11.
Aplicacion web local basada en Flask, empaquetable como `.exe` para distribucion interna.

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
| **Reportes** | Log de sesion, exportar a HTML/TXT/JSON |
| **Avanzado** | Puntos de restauracion, diagnosticos de display/DWM/GPU, Panel Self Refresh |

---

## Requisitos para desarrollo

- Python 3.10 o superior
- Windows 10/11 (las funciones de mantenimiento solo operan en Windows)
- Permisos de administrador (requerido para la mayoria de operaciones)

## Instalacion para desarrollo

```bash
git clone <url-del-repositorio>
cd mantenimiento_windows

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

## Ejecutar en modo desarrollo

```bash
python app.py
```

Se abre automaticamente en `http://127.0.0.1:5000`.

---

## Crear el .exe para distribucion

### Opcion A: Script automatico (recomendado)

1. Doble clic en **`build.bat`**
2. Espera 1-3 minutos
3. El ejecutable queda en `dist\MantenimientoWindows.exe`

El script crea el entorno virtual, instala dependencias y genera el `.exe` automaticamente.

### Opcion B: Manual

```bash
# Activar entorno virtual
venv\Scripts\activate

# Instalar PyInstaller si no lo tienes
pip install pyinstaller

# Construir
pyinstaller mantenimiento_windows.spec --noconfirm
```

El resultado esta en `dist\MantenimientoWindows.exe`.

---

## Distribuir a los usuarios

Solo se entrega **un archivo**: `MantenimientoWindows.exe`

| Concepto | Detalle |
|---|---|
| **Archivo** | `MantenimientoWindows.exe` (~15-25 MB) |
| **Requisitos del PC destino** | Windows 10 o 11, nada mas |
| **NO necesita instalar** | Python, pip, Flask, ni ninguna otra dependencia |
| **Permisos** | El .exe pide elevacion de administrador (UAC) automaticamente |

### Que pasa cuando el usuario ejecuta el .exe

1. Windows muestra el dialogo UAC pidiendo permisos de administrador
2. Se abre una ventana de consola mostrando:
   ```
   ============================================================
     Mantenimiento Windows v2.0.0
     Running at: http://127.0.0.1:5000
     Admin: True
     Logs: C:\ProgramData\MantenimientoWindows\logs
   ============================================================
   ```
3. El navegador se abre automaticamente con la interfaz
4. La consola debe permanecer abierta mientras se usa la herramienta
5. Para cerrar: cerrar la ventana de consola o Ctrl+C

### Donde se guardan los datos

| Tipo | Ubicacion |
|---|---|
| Logs de aplicacion | `C:\ProgramData\MantenimientoWindows\logs\` |
| Reportes exportados | `C:\ProgramData\MantenimientoWindows\reports\` |

---

## Estructura del proyecto

```
mantenimiento_windows/
├── app.py                          # Entrypoint Flask
├── config.py                       # Configuracion centralizada
├── requirements.txt                # Dependencias Python
├── build.bat                       # Script de build automatico
├── mantenimiento_windows.spec      # Configuracion PyInstaller
├── main.py                         # Legacy (Tkinter original)
│
├── services/                       # Capa de servicios (logica de negocio)
│   ├── command_runner.py           # Ejecucion segura de comandos
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
│   └── reports.py                  # Logs y reportes
│
├── routes/                         # Blueprints Flask (rutas HTTP)
│   ├── dashboard.py
│   ├── diagnostics.py
│   ├── cleanup.py
│   ├── repair.py
│   ├── network.py
│   ├── update.py
│   ├── power.py
│   ├── drivers.py
│   ├── security.py
│   ├── reports.py
│   └── advanced.py
│
├── templates/                      # Plantillas Jinja2 (HTML)
│   ├── base.html                   # Layout principal con sidebar
│   ├── dashboard.html
│   ├── diagnostics.html
│   ├── cleanup.html
│   ├── repair.html
│   ├── network.html
│   ├── update.html
│   ├── power.html
│   ├── drivers.html
│   ├── security.html
│   ├── reports.html
│   └── advanced.html
│
└── static/
    ├── css/style.css               # Estilos CSS
    └── js/app.js                   # JavaScript frontend
```

---

## Seguridad y diseno

- **Todas las acciones destructivas requieren confirmacion** del usuario antes de ejecutarse
- **Indicadores de riesgo** visibles en la interfaz (verde/amarillo/rojo)
- **Capa centralizada de ejecucion de comandos** (`command_runner.py`):
  - Timeouts configurables
  - Captura de stdout, stderr y codigo de retorno
  - Validacion de permisos de admin
  - Prevencion de inyeccion de shell
  - Resultados estructurados: `success`, `warning`, `error`, `not_applicable`, `timeout`, `requires_admin`
- **Logging completo** de cada accion ejecutada
- **Deteccion de hardware** antes de operaciones especificas (SSD vs HDD, Intel vs otro GPU)
- **Solo acceso local** (`127.0.0.1`) — no expone ningun puerto a la red

### Clasificacion de operaciones

| Nivel | Significado | Ejemplo |
|---|---|---|
| **Safe** | Sin riesgo, solo lectura o limpieza basica | Diagnosticos, flush DNS, limpiar temp |
| **Admin** | Requiere permisos de administrador | SFC, DISM, servicios |
| **Caution** | Puede causar desconexion temporal o cambios reversibles | Release IP, restart Explorer |
| **Danger** | Cambio significativo, requiere confirmacion explicita | Reset TCP/IP, hard reset WU, CHKDSK /f /r |

---

## Notas tecnicas para el build

- `console=True` en el `.spec`: la consola permanece abierta para mostrar la URL del servidor. Si se cierra la consola, la aplicacion se detiene.
- `uac_admin=True` en el `.spec`: Windows solicita elevacion UAC automaticamente.
- `use_reloader=False` en `app.py`: el reloader de Flask no es compatible con ejecutables empaquetados por PyInstaller.
- Los templates y archivos estaticos se incluyen via `datas` en el `.spec` porque Flask los lee desde disco en tiempo de ejecucion.
- Los modulos Python (`services/`, `routes/`) se incluyen via `hiddenimports` para que PyInstaller los compile e integre correctamente.
