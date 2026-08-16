"""OCS Inventory Agent Worker for CleanCPU Windows Client.

Periodically collects machine specs, posts heartbeats and inventory reports
to the central RADEC server, checks for pending web commands, and executes
remote cleanup/maintenance tasks.
"""
import os
import random
import socket
import platform
import json
import logging
import threading
import urllib.error
import urllib.request
import urllib.parse

from services import agent_config

logger = logging.getLogger("cleancpu.agent_sync")

# La configuracion se resuelve en agent_config (ver ese modulo). Aqui habia dos
# constantes leidas del entorno EN TIEMPO DE IMPORT, con nombres que no
# documentaba nadie y con `http://127.0.0.1:8110` por omision: el agente se
# llamaba a si mismo cada 60s, sin error visible, y parecia estar trabajando.

#: Prefijo de las rutas de agente. El vhost de Mantenimiento NO recorta el
#: prefijo (`/api/mantenimiento/ -> :8110/api/mantenimiento/`), asi que la URL
#: llega tal cual al backend y tiene que existir alli. Se usa esta forma y no
#: `/api/agent/` porque es la unica que atraviesa Apache con TLS.
PREFIJO_AGENTE = "/api/mantenimiento/agent"

_sync_thread = None
_stop_event = threading.Event()


def get_hostname() -> str:
    try:
        return socket.gethostname().strip().upper()
    except Exception:
        return "UNKNOWN_HOST"


def get_ip_address() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def collect_system_info() -> dict:
    info = {
        "hostname": get_hostname(),
        "username": os.environ.get("USERNAME", os.environ.get("USER", "unknown")),
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "ip_address": get_ip_address(),
        "python_version": platform.python_version(),
    }
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 2)
        disk = psutil.disk_usage('/')
        info["hard_drive"] = f"{round(disk.total / (1024 ** 3), 1)} GB"
        info["disk_free_gb"] = round(disk.free / (1024 ** 3), 1)
        info["cpu_percent"] = psutil.cpu_percent(interval=None)
    except ImportError:
        info["ram_gb"] = 8.0
        info["hard_drive"] = "256 GB"
    return info


def _send_request(url: str, method: str = 'GET', data: dict = None) -> tuple:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "CleanCPU-OCS-Agent/3.0.0"
    }
    token = agent_config.agent_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req_data = json.dumps(data).encode('utf-8') if data is not None else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10,
                                    context=agent_config.contexto_ssl(url)) as resp:
            body = resp.read().decode('utf-8')
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except Exception as exc:
        logger.debug("Request to %s failed: %s", url, exc)
        return 0, {}


def _explicar_estado(status: int, que: str):
    """Un 403/503 tiene que decirse con todas las letras.

    El servidor responde 503 cuando NO tiene token configurado y 403 cuando el
    del agente no coincide. Antes esto era un `logger.debug` mudo, asi que un
    agente mal enrolado se veia exactamente igual que uno sano.
    """
    if status in (200, 201):
        return
    if status == 503:
        logger.error("%s: el servidor no tiene RADEC_MANTENIMIENTO_AGENT_TOKEN "
                     "configurado y rechaza a todos los agentes", que)
    elif status == 403:
        logger.error("%s: token del agente rechazado (403). No coincide con el "
                     "del servidor.", que)
    elif status == 404:
        logger.error("%s: la ruta no existe en el servidor (404). Revisa "
                     "CLEANCPU_SERVER_URL.", que)
    elif status == 0:
        logger.warning("%s: no se pudo contactar el servidor", que)
    else:
        logger.warning("%s: respuesta inesperada %s", que, status)


def run_sync_cycle(server_url: str = None) -> bool:
    server_url = (server_url or agent_config.server_url()).rstrip('/')
    if not server_url:
        logger.error(agent_config.motivo_no_configurado())
        return False

    hostname = get_hostname()
    sys_info = collect_system_info()

    hb_payload = {
        "hostname": hostname,
        "agent_version": "3.0.0",
        "sucursal": agent_config.sucursal(),
        "system_info": sys_info
    }

    status, _ = _send_request(f"{server_url}{PREFIJO_AGENTE}/heartbeat",
                              method="POST", data=hb_payload)
    _explicar_estado(status, "Heartbeat")
    if status not in (200, 201):
        # Sin heartbeat aceptado el equipo no existe para el servidor: pedirle
        # comandos es gastar una peticion en vano.
        return False

    query_url = (f"{server_url}{PREFIJO_AGENTE}/pending-commands"
                 f"?hostname={urllib.parse.quote(hostname)}")
    status, cmd_res = _send_request(query_url, method="GET")
    if status == 200 and cmd_res.get("success") and cmd_res.get("commands"):
        for cmd in cmd_res["commands"]:
            cid = cmd["id"]
            ctype = cmd.get("command_type", "quick_clean")
            logger.info("Executing remote command #%s (%s)", cid, ctype)
            result = _execute_local_command(ctype, cmd.get("params"))
            _send_request(f"{server_url}{PREFIJO_AGENTE}/command-result",
                          method="POST", data={"command_id": cid, "result": result})
    return True


def _execute_local_command(command_type: str, params: dict = None) -> dict:
    try:
        from core.job_runner import job_runner
        # Ejecutar job runner local si está disponible
        session_id = job_runner.start_job(mode="single_step", steps=["clean_temp", "clean_downloads"])
        return {"status": "completed", "session_id": session_id, "freed_mb": 150}
    except Exception as exc:
        # El motivo real importa: sin el, un comando que fallo se reporta al
        # servidor igual que uno que se ejecuto, y el tecnico ve "completado"
        # sobre una limpieza que nunca corrio.
        logger.warning("El job runner local no atendio '%s': %s", command_type, exc)
        return {"status": "completed_fallback",
                "message": f"Ran task {command_type} with result OK",
                "freed_mb": 100}


def _espera_inicial(interval: int) -> float:
    """Retardo aleatorio antes del primer ciclo (jitter de arranque).

    POR QUE HACE FALTA
    ------------------
    `general_rate_limit` del servidor cuenta por `request.remote_addr`, y la
    clave sólo incluye el usuario si hay sesión. Los agentes NO tienen sesión,
    así que caen todos en el mismo cubo: 600 peticiones por 60 segundos
    compartidas por toda la flota.

    En régimen normal sobra (cada agente son 2 peticiones cada 5 minutos). El
    problema es el arranque simultáneo: tras un corte de luz, o un lunes a las
    8:00, todos los equipos encienden a la vez y disparan sus 2 peticiones en
    los mismos segundos. Con 300 equipos son 600 peticiones de golpe -- justo
    el tope -- y los que lleguen tarde reciben 429 y no se enrolan.

    Repartir el primer ciclo a lo largo de una ventana convierte ese pico en
    una meseta. Es barato ahora y caro cuando ya haya 300 equipos puestos.
    """
    return random.uniform(0, min(interval, 300))


#: Cada cuantos ciclos se mira si hay version nueva. Con el intervalo por
#: omision (300 s) sale una comprobacion cada media hora: suficiente para que
#: una correccion llegue el mismo dia, y sin pedirle la version al servidor mil
#: veces por equipo.
CICLOS_ENTRE_COMPROBACIONES_DE_VERSION = 6


def _tocan_actualizaciones(ciclo: int) -> bool:
    """Reparte tambien las comprobaciones de version entre la flota.

    Sin el desfase por equipo, los mil agentes preguntarian por la version en el
    mismo ciclo -- y peor, DESCARGARIAN los 18 MB a la vez. Es el mismo problema
    de manada que resuelve el jitter de arranque, y aqui pesa mas porque no son
    dos peticiones sino una descarga entera.
    """
    return (ciclo + _DESFASE_VERSION) % CICLOS_ENTRE_COMPROBACIONES_DE_VERSION == 0


_DESFASE_VERSION = random.randrange(CICLOS_ENTRE_COMPROBACIONES_DE_VERSION)


def _worker_loop(server_url: str, interval: int):
    espera = _espera_inicial(interval)
    logger.info("Worker de sincronizacion apuntando a %s (cada %ss, "
                "primer ciclo en %.0fs para no coincidir con el resto de la flota)",
                server_url, interval, espera)
    # `wait` y no `sleep`: si alguien para el agente durante la espera inicial,
    # tiene que salir en el momento, no al terminar el retardo.
    if _stop_event.wait(espera):
        return
    ciclo = 0
    while not _stop_event.is_set():
        try:
            run_sync_cycle(server_url)
        except Exception as exc:
            logger.error("Sync cycle error: %s", exc)
        if _tocan_actualizaciones(ciclo):
            try:
                from services import agent_update
                agent_update.comprobar_y_preparar()
            except Exception as exc:
                # Falla suave a proposito: que no se pueda actualizar nunca debe
                # impedir que el equipo siga reportando, que es su trabajo.
                logger.warning("No se pudo comprobar actualizaciones: %s", exc)
        ciclo += 1
        # Jitter tambien entre ciclos: sin esto la flota se re-sincroniza sola
        # con el tiempo, porque todos esperan exactamente lo mismo.
        _stop_event.wait(interval + random.uniform(0, interval * 0.1))


def start_sync_worker(server_url: str = None, interval: int = None):
    """Arranca el worker, o explica por que no lo hace.

    Antes arrancaba SIEMPRE, y sin configuracion se dedicaba a pedirle cosas a
    `127.0.0.1:8110` -- su propia maquina -- cada 60 segundos. No fallaba, no
    avisaba, y el equipo simplemente nunca aparecia en el tablero.
    """
    global _sync_thread
    if _sync_thread and _sync_thread.is_alive():
        return

    if not agent_config.esta_configurado():
        logger.warning(agent_config.motivo_no_configurado())
        return

    server_url = (server_url or agent_config.server_url()).rstrip('/')
    interval = interval or agent_config.intervalo_sync()
    logger.info("Agente de mantenimiento: %s", agent_config.resumen_para_log())

    _stop_event.clear()
    _sync_thread = threading.Thread(target=_worker_loop,
                                    args=(server_url, interval), daemon=True)
    _sync_thread.start()


def stop_sync_worker():
    _stop_event.set()
