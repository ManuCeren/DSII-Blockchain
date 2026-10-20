"""JSON autenticado con Fernet, delimitado por línea sobre TCP (no TLS)."""
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

MAX_MENSAJE = 4 * 1024 * 1024
RAIZ = Path(__file__).resolve().parent


def clave_contexto(contexto='wallet'):
    if contexto not in ('wallet', 'nodos'):
        raise ValueError('Contexto de comunicación desconocido.')
    ruta = Path(os.environ.get('BLOCKCHAIN_' + contexto.upper() + '_KEY',
                               str(RAIZ / ('canal_' + contexto + '.key'))))
    return cargar_clave(ruta)


def cargar_clave(ruta, crear=True):
    ruta = Path(ruta)
    if not ruta.exists() and crear:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        # Publicar una clave completa de forma exclusiva, incluso entre procesos.
        import tempfile
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(dir=ruta.parent, delete=False) as f:
                temporal = Path(f.name)
                f.write(Fernet.generate_key())
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(temporal, ruta)
            except FileExistsError:
                pass
        finally:
            if temporal is not None:
                temporal.unlink(missing_ok=True)
    if not ruta.exists():
        raise ValueError('Falta la clave Fernet: ' + str(ruta))
    return Fernet(ruta.read_bytes())


def enviar_json(flujo, mensaje, *, contexto='wallet', cifrador=None):
    contenido = json.dumps(mensaje, ensure_ascii=False, allow_nan=False).encode('utf-8')
    token = (cifrador or clave_contexto(contexto)).encrypt(contenido)
    contenido = contexto.encode('ascii') + b':' + token + b'\n'
    if len(contenido) > MAX_MENSAJE:
        raise ValueError('Mensaje demasiado grande.')
    flujo.write(contenido)
    flujo.flush()


def recibir_json(flujo, *, contexto='wallet', cifrador=None):
    contenido = flujo.readline(MAX_MENSAJE + 1)
    if not contenido:
        raise ConnectionError('La conexión terminó sin respuesta.')
    if len(contenido) > MAX_MENSAJE or not contenido.endswith(b'\n'):
        raise ValueError('Mensaje demasiado grande o sin delimitador.')
    prefijo = contexto.encode('ascii') + b':'
    if not contenido.startswith(prefijo):
        raise ValueError('Contexto de comunicación inválido.')
    try:
        contenido = (cifrador or clave_contexto(contexto)).decrypt(contenido[len(prefijo):-1])
    except InvalidToken as error:
        raise ValueError('Mensaje cifrado no autenticado.') from error
    mensaje = json.loads(contenido.decode('utf-8'))
    if not isinstance(mensaje, dict):
        raise ValueError('El mensaje debe ser un objeto JSON.')
    return mensaje
