# CLAUDE.md — CleanCPU / Programa de Mantenimiento RADEC

## 1. Propósito del proyecto
CleanCPU es una aplicación interna de soporte técnico para RADEC orientada a Windows 10/11.
Su objetivo es ejecutar mantenimiento lógico, diagnóstico, reparación, captura de datos de servicio, generación de reportes y flujos de soporte técnico de forma controlada y auditable.

La aplicación está diseñada para:
- uso por técnicos de soporte
- operación en entorno empresarial
- despliegue progresivo tras pruebas piloto
- ejecución segura de acciones sobre Windows
- trazabilidad de acciones, resultados y reportes

Este proyecto NO es una app genérica de consumo.
Es una herramienta interna de soporte con prioridades de:
- seguridad
- compatibilidad Windows
- estabilidad operativa
- claridad para el técnico
- cambios incrementales y auditables

---

## 2. Stack técnico
- Backend: Flask
- Servidor WSGI: Waitress
- Frontend: HTML + JS + CSS
- Persistencia: SQLite
- Empaquetado: PyInstaller
- Plataforma objetivo: Windows 10/11
- Entorno local frecuente: WampServer/Apache reverse proxy
- Despliegue futuro considerado: AWS / reverse proxy / load balancer

---

## 3. Archivos clave
- `app.py`: arranque de Flask y registro principal
- `server.py`: arranque con Waitress / modo producción
- `config.py`: configuración general y variables de entorno
- `core/action_registry.py`: registro de acciones gobernadas
- `core/governance.py`: rollback, clasificación de riesgo y reglas de control
- `core/security.py`: validaciones de seguridad, host/origin/proxy
- `services/command_runner.py`: capa de ejecución controlada de comandos
- `services/maintenance_report.py`: generación de reportes FO-TI-19 / FO-TI-20
- `templates/base.html`: layout base compartido
- `static/js/app.js`: helpers globales del frontend
- `mantenimiento_windows.spec` o `cleancpu.spec`: PyInstaller
- `CLEANCPU_MASTER_PROMPT.md`: backlog / guía maestra si existe

---

## 4. Reglas operativas obligatorias
### 4.1 No rediseñar de más
- No rehacer toda la arquitectura.
- No mover módulos sin necesidad real.
- No introducir refactors amplios si el pedido es una corrección puntual.
- No mezclar varias fases en un solo cambio si el trabajo se puede separar.

### 4.2 Cambios quirúrgicos
- Preferir cambios pequeños, seguros y localizados.
- Mantener compatibilidad con comportamiento ya aprobado.
- Si una mejora requiere rediseño grande, primero reportarlo antes de implementarlo.

### 4.3 Seguridad y honestidad
- Nunca fingir que una función está completa si depende de validación real en Windows.
- Nunca marcar como “success” una acción que fue:
  - omitida
  - parcialmente aplicada
  - no soportada
  - bloqueada por permisos o entorno
- Si algo depende de:
  - edición de Windows
  - GPO
  - privilegios admin
  - DISM / CBS
  - Office MSI vs ClickToRun
  - servicios no presentes
  debe mostrarse explícitamente.

### 4.4 Nada inseguro o no soportado
- No implementar recuperación de claves completas de Office.
- No implementar activaciones no oficiales.
- No habilitar SMB1 silenciosamente.
- No usar métodos inseguros o hacks para licensing.
- No usar comandos arbitrarios fuera de allowlist / governance.

---

## 5. Convenciones de código
- Idioma de comentarios y mensajes técnicos: español, salvo que una librería o API requiera inglés.
- Logs: usar `logging`, no `print`.
- Rutas: usar `pathlib.Path` cuando aplique.
- Subprocesos: preferir la capa existente (`command_runner.py` o helpers ya definidos).
- No usar `os.system`.
- No usar `shell=True` salvo caso muy justificado y ya alineado con la arquitectura actual.
- No duplicar lógica si ya existe helper global reutilizable.
- Respetar separación entre:
  - rutas (`routes/`)
  - servicios (`services/`)
  - core (`core/`)
  - templates (`templates/`)
  - frontend global (`static/js/app.js`, `static/css/style.css`)

---

## 6. Gobernanza obligatoria
Toda acción mutante o riesgosa debe respetar el modelo actual del proyecto.

### Si agregas una acción nueva:
Debes revisar si requiere:
- registro en `core/action_registry.py`
- cobertura de rollback en `core/governance.py`
- validación en `services/command_runner.py`
- confirmación
- privilegios admin
- advertencia de reinicio
- advertencia de restore point
- restricción por modo (SAFE / ADVANCED / EXPERT)

### Nunca:
- bypassear gobernanza
- ejecutar acciones destructivas fuera del flujo previsto
- abrir huecos genéricos en allowlist solo para hacer “que funcione”

---

## 7. Reglas Windows específicas
Este proyecto es Windows-first. No usar supuestos POSIX.

### 7.1 Compatibilidad
- Todo debe pensarse para Windows 10/11.
- Ser explícito cuando algo pueda variar por:
  - versión
  - build
  - edición
  - idioma del sistema
  - instalación de Office
  - políticas de dominio

### 7.2 Office
- Usar solo rutas y herramientas oficiales/sostenibles.
- Distinguir MSI vs ClickToRun.
- La licencia solo puede mostrar:
  - product/edition
  - version
  - architecture
  - channel
  - activation status
  - partial key si la herramienta oficial la expone
- No mostrar ni inventar full product key.

### 7.3 Features opcionales
Ser cuidadoso con estados como:
- Enabled
- Disabled
- EnablePending
- DisabledWithPayloadRemoved
- NotPresent
- Unknown

### 7.4 Servicios, sharing y red
- No asumir que todos los servicios existen.
- Browser / Exploración de equipos puede no existir.
- NetBIOS / sharing / firewall pueden estar sujetos a GPO.
- Mostrar siempre estado real antes de permitir cambios.

### 7.5 Reinicios
- No forzar reinicios por defecto.
- Diferenciar claramente entre:
  - reinicio con aviso
  - reinicio forzado
- Mostrar uptime real cuando aplique.

---

## 8. UX obligatoria para técnicos
Esta aplicación la usan técnicos. La UX debe ser práctica, clara y operativa.

### Toda acción debe:
- mostrar resultado visible
- escribir a terminal/salida o área equivalente
- usar toast cuando corresponda
- evitar cierres silenciosos

### La interfaz debe:
- estar en español para el técnico
- ser clara en warnings
- no esconder limitaciones reales
- no depender solo de mensajes “bonitos”
- priorizar utilidad sobre cosmética

---

## 9. Reportes y formularios
Los reportes son parte crítica del producto.

### Reglas:
- No romper flujo FO-TI-19 / FO-TI-20
- Si agregas campos nuevos, revisar:
  - frontend de captura
  - parseo en rutas
  - persistencia temporal/sesión si aplica
  - generación del HTML/Excel/PDF correspondiente
- Si una pieza de información depende de otra fase, dejarlo explícito

### Ejemplos de dependencias importantes:
- licencia Office en reporte puede depender de inspección previa en sesión
- obsolescencia CPU no debe fingir certeza si el procesador es ambiguo
- tipo de disco puede requerir autodetección + override manual

---

## 10. Reverse proxy / despliegue
La app debe poder funcionar:
- localmente detrás de Apache/WampServer
- en futuro detrás de reverse proxy / load balancer en AWS

### Reglas:
- mantener `ALLOWED_HOSTS` flexible por env
- respetar `CLEANCPU_ALLOWED_HOSTS`, `CLEANCPU_ENV`, `CLEANCPU_HOST`, `CLEANCPU_PORT`
- soportar `ProxyFix` / `X-Forwarded-*` solo donde corresponda
- no romper operación local por cambios pensados para nube

---

## 11. Empaquetado
Cuando una tarea toca imports, módulos, archivos de datos o comportamiento de runtime:
- revisar impacto en `.spec`
- revisar hidden imports
- revisar `datas`
- no asumir que algo funciona igual empaquetado que en dev

No agregar dependencias sin:
- actualizar `requirements.txt`
- revisar `mantenimiento_windows.spec` / `cleancpu.spec`

---

## 12. Qué NO hacer
- No tocar migraciones o estructura de persistencia sin necesidad explícita.
- No introducir dependencias nuevas sin justificación real.
- No meter binarios, `dist/`, `build/`, o artefactos temporales al repo.
- No usar `eval`, `exec`, ni descarga dinámica de código.
- No abrir alcance innecesariamente.
- No reescribir templates completos si bastan cambios puntuales.
- No cambiar contratos JSON existentes sin revisar consumidores.
- No romper compatibilidad del frontend sin validar templates afectados.

---

## 13. Flujo esperado de trabajo
Cuando implementes algo:

### Antes de editar
Debes identificar:
1. archivos exactos a tocar
2. flujo backend afectado
3. flujo frontend afectado
4. impacto en governance/action_registry/rollback
5. riesgos y limitaciones del entorno

### Después de editar
Debes entregar:
1. resumen exacto de cambios
2. archivos modificados
3. comportamiento final
4. validaciones ejecutadas
5. blockers restantes
6. si está listo o no para review / PR

---

## 14. Validaciones mínimas obligatorias
Después de cambios relevantes:
- correr lint sobre archivos tocados
- correr tests relevantes
- validar imports si se tocaron módulos/rutas
- revisar que no se haya roto action_registry/governance
- revisar que el frontend no quede con funciones huérfanas o handlers rotos

Comandos frecuentes:
- Desarrollo local: `python app.py`
- Producción local / Waitress: revisar `server.py`
- Tests: `pytest tests/ -v`
- Lint: `ruff check .`
- Formato: `black .`

Si el proyecto realmente usa otra combinación de lint/build, respetar la configuración real actual del repo.

---

## 15. Formato de respuesta esperado de Claude
Cuando termines una tarea, responde con esta estructura:

### Resumen
- qué se hizo

### Archivos tocados
- lista exacta

### Cambios clave
- backend
- frontend
- gobernanza
- reportes
- seguridad
- despliegue

### Validación
- qué pruebas/lint se corrieron
- qué quedó pendiente de validar en máquina real

### Riesgos / limitaciones
- qué depende de entorno
- qué no se puede garantizar sin smoke test real

### Estado final
- listo para review
- listo para PR
- no listo todavía


## 16. Estado actual del producto
El proyecto ya contiene múltiples módulos funcionales y no debe tratarse como una aplicación vacía o prototipo temprano.

Existen o pueden existir implementaciones previas de:
- reportes
- Office
- networking
- startup management
- sharing / NetBIOS
- optional Windows features
- restart scheduling
- reverse proxy support

Antes de proponer una implementación nueva, revisar si ya existe una versión parcial o completa en el código actual y trabajar sobre ella en lugar de duplicarla.


## Build (.exe)
- Entry point: `server.py`
- Spec: `mantenimiento_windows.spec`
- Salida: `dist/CleanCPU.exe`
- Comando: `pyinstaller mantenimiento_windows.spec --clean --noconfirm`
- Script: `build.bat`
- Datos empaquetados: `templates/`, `static/`, `routes/`
- Flags críticos: `--onefile`, `--windowed`, `--name CleanCPU`
- Verificación post-build: arranca sin consola, abre http://127.0.0.1:5000, navegar todas las páginas, prueba de 30 min
- Logs runtime: `C:\ProgramData\CleanCPU\logs\` (NO empaquetar, se crean en runtime)


## Skills disponibles
- `/catchup` — usar al inicio de sesión solo si reanudas trabajo previo
- `/build-exe` — usar al cerrar tarea que toca runtime, después de tests verdes
- `/release` — usar solo para versiones distribuibles, desde main, no en ramas de feature

Si Infra olvida invocar uno cuando aplica, recuérdaselo antes de seguir.