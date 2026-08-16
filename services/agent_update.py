"""Auto-actualizacion del agente contra el servidor RADEC.

POR QUE HACE FALTA
------------------
El unico despliegue que habia era: copiar el .exe a la maquina y ejecutarlo.
Con 1 000 equipos, publicar una correccion significaba visitar 1 000 maquinas, o
no publicarla. En la practica lo segundo: la flota se queda con la version del
dia que se instalo.

QUE HACE, Y QUE NO
------------------
Compara la version local con la que publica el servidor. Si difiere, descarga el
ejecutable nuevo, **verifica su SHA-256 contra el que declara el manifiesto**, y
lo deja como `CleanCPU.exe.nuevo` junto a un script de reemplazo.

NO se reemplaza en caliente: Windows bloquea el ejecutable de un proceso vivo, y
ademas cortar un mantenimiento a la mitad para actualizarse seria peor que estar
desactualizado. El cambio lo aplica el script en el siguiente arranque, que lo
provoca la tarea programada.

EL HASH NO ES OPCIONAL
----------------------
Un canal que descarga un binario y lo ejecuta, sin verificar, es una puerta de
ejecucion remota en cada equipo de la flota. Si el hash no coincide, se descarta
la descarga y se avisa en el log; no hay modo "confiar de todas formas".
"""
import hashlib
import logging
import os
import sys
import tempfile
import urllib.request

from services import agent_config

logger = logging.getLogger('cleancpu.agent_update')

#: Tope de descarga. El agente ronda los 18 MB; 100 evita que un servidor
#: comprometido o un error de ruta llene el disco del equipo.
MAX_BYTES = 100 * 1024 * 1024


def _directorio_instalacion() -> str:
    """Donde vive el .exe. Con PyInstaller, junto a sys.executable."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _version_local() -> str:
    try:
        from config import Config
        return str(Config.APP_VERSION)
    except Exception:
        return '0.0.0'


def _pedir(ruta: str, binario: bool = False):
    """GET autenticado contra el servidor, con el mismo token que el resto."""
    base = agent_config.server_url()
    if not base:
        return None
    req = urllib.request.Request(
        base + ruta,
        headers={'Authorization': f'Bearer {agent_config.agent_token()}',
                 'User-Agent': 'CleanCPU-Updater/1.0'})
    try:
        with urllib.request.urlopen(
                req, timeout=120 if binario else 15,
                context=agent_config.contexto_ssl(base)) as resp:
            if binario:
                datos = resp.read(MAX_BYTES + 1)
                if len(datos) > MAX_BYTES:
                    logger.error('La descarga supera %s MB; se descarta', MAX_BYTES // 1024 // 1024)
                    return None
                return datos
            import json
            return json.loads(resp.read().decode('utf-8'))
    except Exception as exc:
        logger.debug('No se pudo consultar %s: %s', ruta, exc)
        return None


def _escribir_script_de_reemplazo(destino: str, nuevo: str) -> str:
    """Deja el .bat que sustituye el ejecutable en el siguiente arranque.

    Espera a que el proceso muera antes de copiar: si se lanza mientras el
    agente sigue vivo, el copy falla con el archivo en uso y el equipo se queda
    a medias -- con el .nuevo en disco y el viejo corriendo.
    """
    script = os.path.join(os.path.dirname(destino), 'aplicar_actualizacion.bat')
    contenido = f"""@echo off
REM Generado por services/agent_update.py. Lo lanza la tarea programada al
REM arrancar, ANTES del agente.
setlocal
set ORIGEN="{nuevo}"
set DESTINO="{destino}"

REM Hasta 30 s a que el proceso anterior termine de cerrar.
for /L %%i in (1,1,30) do (
    tasklist /FI "IMAGENAME eq CleanCPU.exe" 2>NUL | find /I "CleanCPU.exe" >NUL
    if errorlevel 1 goto :copiar
    timeout /t 1 /nobreak >NUL
)

:copiar
if not exist %ORIGEN% goto :fin
copy /Y %ORIGEN% %DESTINO% >NUL
if errorlevel 1 goto :fin
del /Q %ORIGEN%

:fin
endlocal
"""
    with open(script, 'w', encoding='ascii') as fh:
        fh.write(contenido)
    return script


def comprobar_y_preparar() -> bool:
    """Un ciclo de comprobacion. True si dejo una actualizacion lista.

    Falla suave siempre: que no se pueda actualizar NUNCA debe impedir que el
    agente siga reportando, que es su trabajo principal.
    """
    if not agent_config.esta_configurado():
        return False

    info = _pedir('/api/mantenimiento/agent/version')
    if not info or not info.get('disponible'):
        return False

    remota = str(info.get('version') or '')
    local = _version_local()
    if not remota or remota == local:
        return False

    esperado = str(info.get('sha256') or '').lower()
    if len(esperado) != 64:
        logger.error('El servidor ofrece %s sin un SHA-256 valido; no se actualiza', remota)
        return False

    logger.info('Version nueva del agente: %s (local %s). Descargando...', remota, local)
    datos = _pedir(info.get('url') or '/api/mantenimiento/agent/descargar', binario=True)
    if not datos:
        return False

    real = hashlib.sha256(datos).hexdigest()
    if real != esperado:
        # Esto no es un fallo de red: es un binario que no es el que el servidor
        # dice. Se descarta entero y se deja constancia.
        logger.error('HASH NO COINCIDE al descargar el agente %s. '
                     'Esperado %s, recibido %s. Descarga DESCARTADA.',
                     remota, esperado, real)
        return False

    destino = os.path.join(_directorio_instalacion(), 'CleanCPU.exe')
    nuevo = destino + '.nuevo'
    try:
        # Escritura atomica: a un temporal y luego rename. Si el equipo se apaga
        # a media descarga, no queda un .nuevo truncado que el .bat copiaria
        # como si fuera bueno.
        fd, temporal = tempfile.mkstemp(dir=os.path.dirname(destino), suffix='.parcial')
        with os.fdopen(fd, 'wb') as fh:
            fh.write(datos)
        os.replace(temporal, nuevo)
        script = _escribir_script_de_reemplazo(destino, nuevo)
    except OSError as exc:
        logger.error('No se pudo dejar preparada la actualizacion: %s', exc)
        return False

    logger.info('Agente %s listo para aplicarse en el siguiente arranque (%s)', remota, script)
    return True
