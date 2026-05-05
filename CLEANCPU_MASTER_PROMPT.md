# CleanCPU v3.0.0 — Master Prompt / Estado del Proyecto

> Última actualización: 2026-05-05
> Versión actual: 3.0.0
> Estado general: T-01 cerrada. T-05 sub-objetivo (14 fallos readonly DB) cerrado. T-05 amplio (smoke tests por blueprint) en curso.

---

## 0. Cómo usar este archivo

Este archivo es la **memoria viva del proyecto**. Cada sesión:
1. Claude lo lee al inicio para saber dónde estamos
2. Al final de la sesión, Claude lo actualiza marcando lo hecho y agregando hallazgos nuevos
3. Yo (Infra) lo reviso antes de cerrar y hago commit

Las **reglas duras del stack** NO van aquí, van en `CLAUDE.md`.

---

## 1. Tareas activas (en progreso)

### T-05 — Tests automatizados base (en curso, 2026-05-05)
- **Sub-objetivo cerrado**: 14 fallos `OperationalError: readonly database` resueltos en commit `65cbb17`. La suite va de 219 pass / 14 fail → **233 pass / 0 fail**. Ver sección 4 para detalle del fix (conftest.py + SessionStore.create en fixtures).
- **Sub-objetivo abierto**: smoke tests de cada blueprint (criterio de aceptación del backlog). Hay que inventariar `routes/*.py` vs cobertura actual e escribir tests faltantes.

---

## 2. Backlog priorizado

### [x] T-01 — Validar build limpio del .exe en máquina nueva — CERRADA 2026-05-05
- **Resolución**: bug encontrado y arreglado. Los reportes históricos de "estilos desaparecen después de 30+ min" no eran cuestión de tiempo idle — eran consecuencia del flujo de "mantenimiento lógico". `services/cleanup.py:_clean_directory()` borraba el directorio `_MEIxxxxxx\` activo de PyInstaller en `%TEMP%` durante el paso "Limpieza Interna del Sistema". Eso destruía templates/static/módulos en runtime → cualquier `render_template()` posterior daba `TemplateNotFound: <archivo>.html` → 500.
- **Fix primario** (`services/cleanup.py`): helpers `_get_pyinstaller_runtime_root()` + `_should_skip_pyinstaller_runtime()`. Skipea cualquier item `_MEI*` en %TEMP% o que esté dentro de `sys._MEIPASS`. Reporta count de skipped en details.
- **Fix complementario** (`server.py`): quitado `logging.basicConfig(...)` — añadía un StreamHandler a stderr (que va a NUL en `--windowed`) y bloqueaba que `app.py:create_app()` agregara el `RotatingFileHandler` real. Sin file handler, los tracebacks de 500 se perdían y `app.log` no se actualizaba en producción. Sin esto, T-01 era imposible de diagnosticar.
- **Validación**: smoke test post-fix completo. Lanzar `dist\CleanCPU.exe` → mantenimiento (9 pasos) → click cualquier módulo → 200 OK. Cerrar → relanzar → click módulo → 200 OK. Cero tracebacks en `app.log`. Forensia preservada en `C:\ProgramData\CleanCPU.backup-pre-bug-repro-20260504-223634\` y log con bug reproducido en `app.log.repro1-20260505-080052`.
- **No verificado**: prueba 60 min idle con navegación periódica. La hipótesis original era de tiempo, pero el bug que encontramos no es de tiempo. Si aparece otro síntoma de pérdida de CSS sin haber corrido mantenimiento, abrir tarea nueva.

### [ ] T-02 — Scheduled restart manager
- **Origen**: pendiente del backlog v3.0.0
- **Criterio de aceptación**: UI para programar reinicios + persistencia en SQLite + ejecución por scheduled task
- **Archivos**: `routes/restart.py` (nuevo), `templates/restart.html` (nuevo), `db.py`
- **Notas**: usar `schtasks` de Windows, no APScheduler dentro del proceso

### [ ] T-03 — Dashboard de mantenimiento de 9 pasos lógicos
- **Origen**: pendiente del backlog v3.0.0
- **Criterio de aceptación**: vista única que muestra los 9 pasos con estado (pendiente/corriendo/ok/error) y permite ejecutar uno o todos
- **Archivos**: `routes/dashboard.py`, `templates/dashboard.html`, `static/js/dashboard.js`

### [ ] T-04 — Reportes a Google Sheets / Excel
- **Origen**: pendiente del backlog v3.0.0
- **Criterio de aceptación**: exportación del histórico de mantenimientos a Sheets (vía API) y a `.xlsx` local
- **Archivos**: `services/reports.py` (nuevo)
- **Notas**: para Sheets, decidir si usamos Service Account o OAuth — pendiente

### [ ] T-05 — Tests automatizados base
- **Origen**: deuda técnica
- **Criterio de aceptación**: `pytest` corre y cubre al menos rutas + capa de DB
- **Archivos**: `tests/`
- **Notas**: empezar con smoke tests de cada blueprint

---

## 3. Decisiones técnicas tomadas

- **WSGI server**: Waitress (no Gunicorn — no soporta Windows nativo)
- **Empaquetado**: PyInstaller `--onefile --windowed`, NO `--onedir`
- **DB**: SQLite en `C:\ProgramData\CleanCPU\cleancpu.db` (NO en AppData del usuario, debe ser accesible para todos los users de la máquina)
- **Logs**: `C:\ProgramData\CleanCPU\logs\` con rotación 10 MB × 5 archivos
- **Encoding subprocess**: siempre `encoding='utf-8', errors='replace'` para evitar `UnicodeDecodeError` con cp1252
- **Privilegios**: la app corre como administrador (UAC manifest)
- **UI**: Flask + Jinja2 + Tailwind CSS, sin SPA framework
- **Idioma**: español en UI, comentarios y commits
- **Audit antes de empaquetar (2026-05-04)**: en sesión de T-01 hicimos pasada read-only de higiene. Razón: evitar empaquetar deuda conocida al .exe. Resultado en sección 4.
- **Cleanup nunca borra `_MEI*` (2026-05-05)**: `_clean_directory()` debe skipear cualquier item cuyo nombre empiece con `_MEI` (case insensitive) y cualquier path dentro de `sys._MEIPASS` cuando `sys.frozen` es True. Razón: PyInstaller --onefile extrae todo el runtime de la app (templates/, static/, módulos) a `%TEMP%\_MEIxxxxxx\`. Borrarlo destruye los recursos en runtime. Aplica a TODAS las rutas que pasan por `_clean_directory`, no sólo a `clean_user_temp`.
- **Logging en .exe production (2026-05-05)**: NO usar `logging.basicConfig` en `server.py`. Crea un StreamHandler a stderr (que va a NUL en `--windowed`) y bloquea que `app.py:create_app()` agregue el `RotatingFileHandler` real (su check `if not root_logger.handlers` queda en False). Sin file handler, tracebacks se pierden. Solo configurar niveles de loggers nominales (werkzeug, waitress) en server.py.

---

## 4. Hallazgos / bugs detectados (sin priorizar aún)

Bugs de T-01 (2026-05-05) — RESUELTOS:
- ~~`services/cleanup.py:_clean_directory` borraba `_MEIxxxxxx\` activo del .exe~~ → fix con helper `_should_skip_pyinstaller_runtime`.
- ~~`server.py` mataba el RotatingFileHandler de `app.log` con `logging.basicConfig`~~ → quitado, comentario in-code documenta por qué.

Audit higiene (2026-05-04) — RESUELTOS:
- ~~`core/governance.py:927-943` SQL crudo~~ → migrado a `SnapshotStore.save()` en `core/persistence.py`.
- ~~`app.py:218-224` prints sin logger~~ → banner mantiene `print` + duplica vía `app.logger.info`. Excepción documentada.
- ~~`tests/*` 8 imports + 1 variable no usados~~ → todos eliminados. Pyflakes limpio.
- ~~`legacy_tkinter_main.py` (Opción A)~~ → docstring de rol + try/except + variable removida.

Pendientes (no bloqueantes):

~~**14 tests con `OperationalError: readonly database` (deuda de testabilidad)**~~ — RESUELTO 2026-05-05 (commit `65cbb17`):
- `tests/conftest.py` (nuevo): autouse fixture `_isolate_db` redirige `Config.LOG_DIR`/`Config.REPORT_DIR` a `tmp_path` por test vía monkeypatch, y resetea `core.persistence._local.conn` antes/después. Resuelve 8 fallos.
- `tests/test_routes.py` y `tests/test_smart_app_control.py`: el fixture `app` ahora llama `SessionStore.create('test-session', ...)` después de `init_db()`. Resuelve 6 FK constraint failures que estaban enmascarados por el readonly DB. Sin esta sesión, cualquier endpoint gobernado fallaba con `IntegrityError: FOREIGN KEY constraint failed` porque `jobs.session_id REFERENCES sessions.session_id`.
- Resultado: 219 pass / 14 fail → **233 pass / 0 fail**.

**Estilo `pathlib` (NO tocar):**
- ~10 lugares (`config.py:50,61`, `services/cleanup.py:40,52,69,354`, `services/power_tools.py:91`, `core/snapshots.py:86,165,198,312`, `services/system_info.py:42`, `routes/maintenance.py:371`) usan `os.path.join` + literal `'C:\\Windows'` en vez de `pathlib.Path`. Funciona, refactor amplio fuera de scope.

**Disk Cleanup paso 6 hace timeout a 300s consistentemente:**
- Observado en ambas corridas de T-01 (08:18 y 07:42). El paso completa con WARNING pero el resto del flujo sigue. No bloquea, pero candidato a investigar si los timeouts son sintomáticos o esperados (cleanmgr puede tardar más en sistemas con mucho a limpiar).

**Sin hallazgos en producción:**
- subprocess centralizados en `core/job_runner.py:374` y `services/command_runner.py:283,421` están envueltos en try/except. OK.
- Pyflakes sobre `core/`, `routes/`, `services/`, `app.py`, `config.py`, `server.py`: limpio en imports.

---

## 5. Próximo paso concreto

**Continuar T-05 amplio**: smoke tests de cada blueprint. Hay que listar `routes/*.py`, cruzar con tests existentes (`test_routes.py`, `test_smart_app_control.py`, etc.) y escribir smoke tests para los blueprints sin cobertura. Cada test mínimo: `client.get('/<blueprint-prefix>/')` → 200 + verificar template renderiza.

Después de T-05 amplio cerrado:
- **T-02**: scheduled restart manager. Requiere persistencia nueva (con T-05 cerrado, agregar tests es directo).
- **T-03**: dashboard 9 pasos lógicos. Bloque grande de UI; ya existe `routes/maintenance.py` con la lógica, falta la vista unificada.

---

## 6. Histórico (resumen, no detalle)

- **2026-05-05 (cont.)**: T-05 sub-objetivo cerrado. Suite limpia: 233 pass / 0 fail. Fix vía `tests/conftest.py` (autouse fixture aislando DB en tmp_path + reset de thread-local conn) + `SessionStore.create` en fixtures de `test_routes.py` y `test_smart_app_control.py` para satisfacer FK constraint en `jobs.session_id`. Commit `65cbb17`.
- **2026-05-05**: T-01 cerrada. Build .exe ejecutado (12.13 MB), reproducción guiada del bug, traceback capturado (`TemplateNotFound: diagnostics.html`), root cause identificado (cleanup borraba `_MEIxxxxxx\`). Fix aplicado en `services/cleanup.py` (skip de `_MEI*` en %TEMP%) + fix complementario en `server.py` (quitar `logging.basicConfig` que bloqueaba el RotatingFileHandler). Smoke test post-fix: mantenimiento → click módulos → cerrar → relanzar → click módulos. Todo 200 OK. Bug primario y secundario resueltos.
- **2026-05-04**: Audit higiene previo a T-01 + fixes Dudas 1/2/3/4/5 cerradas. SQL de `governance.py` migrado a `SnapshotStore.save()`. `app.py` banner: print (UX) + `app.logger.info` (cumple §5). Tests: 8 imports + 1 variable no usados eliminados. `legacy_tkinter_main.py` (Opción A): docstring de rol + try/except en subprocess + variable no usada removida. Pyflakes limpio en todo el árbol. Descubiertos 14 fallos pre-existentes de tests por `OperationalError readonly db` (deuda de testabilidad, no bloqueante).
- **2026-03-19**: Sesión inicial de migración a v3.0.0. Bugs críticos identificados y arreglados (TemplateNotFound, UnicodeDecodeError, timeouts de NetAdapter, error JS de className).
- **2026-03-16**: Setup inicial de PyInstaller, primeros builds funcionales.