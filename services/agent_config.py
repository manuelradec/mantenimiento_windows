"""Origen unico de la configuracion del agente (servidor, token, sucursal).

POR QUE EXISTE ESTE MODULO
--------------------------
Habia dos agentes conviviendo, cada uno leyendo variables distintas:

    services/agent_sync.py       RADEC_MANTENIMIENTO_SERVER / _AGENT_TOKEN / RADEC_SUCURSAL
    services/reporting_agent.py  CLEANCPU_SERVER_URL / CLEANCPU_AGENT_TOKEN / CLEANCPU_SUCURSAL

`.env.example` solo documenta las `CLEANCPU_*`. Es decir: quien configuraba el
agente siguiendo la documentacion alimentaba `reporting_agent` (reporte de
mantenimiento y un heartbeat al arrancar) y NO alimentaba el worker recurrente,
que se quedaba con su valor por omision `http://127.0.0.1:8110` -- la propia
maquina del usuario, donde no escucha nadie -- y sin token. El equipo no se
mantenia vivo en el tablero y no recogia comandos remotos.

Ademas no habia ningun cargador de `.env`: `python-dotenv` no esta en
requirements y nadie llamaba a `load_dotenv()`. Copiar `.env.example` a `.env`
no hacia absolutamente nada. En un .exe empaquetado que el tecnico abre con
doble clic, eso dejaba la configuracion sin ninguna via practica de entrega.

QUE HACE
--------
Resuelve la configuracion una sola vez, en este orden:

    1. variables de entorno del proceso        (gana: util para GPO / servicio)
    2. archivo `.env` junto al ejecutable       (via practica de despliegue)
    3. valores por omision                      (vacios, NO localhost)

y acepta los dos juegos de nombres para no romper instalaciones existentes:
`CLEANCPU_*` es el nombre preferido y `RADEC_MANTENIMIENTO_*` queda como alias.

No añade dependencias: el lector de `.env` son veinte lineas, mismo criterio
que `_load_dotenv_once()` de `_shared/infra_utils.py` en la plataforma.
"""
import logging
import os
import sys

logger = logging.getLogger('cleancpu.agent_config')

#: Nombre preferido -> alias heredados que se siguen aceptando.
_ALIAS = {
    'CLEANCPU_SERVER_URL': ('RADEC_MANTENIMIENTO_SERVER',),
    'CLEANCPU_AGENT_TOKEN': ('RADEC_MANTENIMIENTO_AGENT_TOKEN',),
    'CLEANCPU_SUCURSAL': ('RADEC_SUCURSAL',),
}

_env_archivo = {}
_cargado = False


def _directorio_base() -> str:
    """Carpeta donde vive el .exe (o el codigo, en desarrollo).

    Con PyInstaller `sys.executable` es el .exe y `__file__` apunta al
    directorio temporal de extraccion, que no le sirve a nadie para dejar un
    archivo de configuracion al lado.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rutas_env():
    """Donde se busca el .env, en orden de preferencia."""
    yield os.path.join(_directorio_base(), '.env')
    # Ubicacion de despliegue: la escribe el instalador y sobrevive a que
    # alguien reemplace el .exe.
    programdata = os.environ.get('PROGRAMDATA', r'C:\ProgramData')
    yield os.path.join(programdata, 'CleanCPU', 'agente.env')


def _cargar_env_archivo():
    global _cargado
    if _cargado:
        return
    _cargado = True
    for ruta in _rutas_env():
        if not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, encoding='utf-8-sig') as fh:
                for linea in fh:
                    linea = linea.strip()
                    if not linea or linea.startswith('#') or '=' not in linea:
                        continue
                    clave, _, valor = linea.partition('=')
                    clave = clave.strip()
                    valor = valor.strip().strip('"').strip("'")
                    # El primer archivo que define una clave manda.
                    _env_archivo.setdefault(clave, valor)
            logger.info('Configuracion de agente leida de %s', ruta)
        except OSError as exc:
            logger.warning('No se pudo leer %s: %s', ruta, exc)


def _valor(nombre: str, defecto: str = '') -> str:
    """Entorno del proceso primero, luego el archivo, luego el defecto."""
    _cargar_env_archivo()
    candidatos = (nombre,) + _ALIAS.get(nombre, ())
    for clave in candidatos:
        crudo = os.environ.get(clave, '').strip()
        if crudo:
            return crudo
    for clave in candidatos:
        crudo = _env_archivo.get(clave, '').strip()
        if crudo:
            return crudo
    return defecto


def server_url() -> str:
    """URL base del servidor RADEC, sin barra final. Vacia si no se configuro.

    Vacia y NO `http://127.0.0.1:8110`: ese valor por omision hacia que el
    agente se llamara a si mismo cada 60 segundos, sin error visible, dando la
    impresion de que estaba funcionando.
    """
    return _valor('CLEANCPU_SERVER_URL').rstrip('/')


def agent_token() -> str:
    return _valor('CLEANCPU_AGENT_TOKEN')


def sucursal() -> str:
    return _valor('CLEANCPU_SUCURSAL', 'SIN_ASIGNAR')


def intervalo_sync() -> int:
    """Segundos entre ciclos de sincronizacion."""
    try:
        segundos = int(_valor('CLEANCPU_SYNC_INTERVAL', '300'))
    except ValueError:
        return 300
    # Menos de 30s satura el servidor con cientos de equipos; mas de una hora
    # deja el tablero inservible.
    return max(30, min(segundos, 3600))


def tls_inseguro() -> bool:
    """¿Aceptar certificados que no validan? Por omision NO.

    Los dos agentes traian `check_hostname = False` y `verify_mode = CERT_NONE`
    fijos, con el comentario "certificados internos mkcert". Pero el servidor
    sirve un comodin `*.radec.com.mx` emitido por Sectigo -- publico y de
    confianza -- asi que esa permisividad no habilitaba nada y si costaba:

    `sistemas.radec.com.mx` tiene DNS dividido. Dentro resuelve a la IP de la
    LAN; FUERA resuelve a la IP publica de salida. Una laptop que sale de la
    sucursal, sin verificar el certificado, entrega hostname, usuario, IP,
    inventario de software Y EL TOKEN Bearer a lo que sea que conteste en ese
    puerto: un portal cautivo de hotel, un proxy transparente, o alguien
    haciendo MITM en el wifi. Validar el certificado corta eso solo, y como el
    certificado es publico no hay nada que configurar.

    La escotilla queda para nombres que un CA publico no puede emitir (los
    `.local` internos) o para apuntar a una IP. Se avisa en cada arranque
    porque desactivar esto en un equipo que sale de la empresa es serio.
    """
    return _valor('CLEANCPU_TLS_INSECURE').lower() in ('1', 'true', 'si', 'yes')


def contexto_ssl(url: str):
    """Contexto TLS para una URL. None si no es https."""
    import ssl

    if not url.lower().startswith('https'):
        return None
    ctx = ssl.create_default_context()
    if tls_inseguro():
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        logger.warning(
            'CLEANCPU_TLS_INSECURE activo: NO se valida el certificado de %s. '
            'En un equipo que sale de la empresa esto expone el token del '
            'agente a cualquiera que intercepte la conexion.', url)
    return ctx


def esta_configurado() -> bool:
    """Hace falta URL y token: el servidor rechaza sin token (503/403)."""
    return bool(server_url() and agent_token())


def motivo_no_configurado() -> str:
    """Texto para el log. Silencio no, que es justo lo que ocultaba el fallo."""
    faltan = []
    if not server_url():
        faltan.append('CLEANCPU_SERVER_URL')
    if not agent_token():
        faltan.append('CLEANCPU_AGENT_TOKEN')
    if not faltan:
        return ''
    return ('Agente sin configurar: falta ' + ' y '.join(faltan)
            + '. Define esas variables o deja un archivo .env junto al '
              'ejecutable (o en %PROGRAMDATA%\\CleanCPU\\agente.env). '
              'Sin eso el equipo NO aparece en el tablero de Mantenimiento.')


def resumen_para_log() -> str:
    """Nunca incluye el token, solo si esta presente."""
    return (f"servidor={server_url() or '(sin definir)'} "
            f"token={'definido' if agent_token() else '(sin definir)'} "
            f"sucursal={sucursal()} intervalo={intervalo_sync()}s")
