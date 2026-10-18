"""Protocolo compartido: un documento JSON UTF-8 por línea de TCP.

TCP entrega bytes, no mensajes: readline reúne fragmentos hasta el delimitador.
El límite evita que una petición incompleta consuma memoria sin control.
"""
import json

MAX_MENSAJE = 4 * 1024 * 1024


def enviar_json(flujo, mensaje):
    contenido = json.dumps(mensaje, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'
    if len(contenido) > MAX_MENSAJE:
        raise ValueError('Mensaje demasiado grande.')
    flujo.write(contenido)
    flujo.flush()


def recibir_json(flujo):
    contenido = flujo.readline(MAX_MENSAJE + 1)
    if not contenido:
        raise ConnectionError('La conexión terminó sin respuesta.')
    if len(contenido) > MAX_MENSAJE or not contenido.endswith(b'\n'):
        raise ValueError('Mensaje demasiado grande o sin delimitador.')
    mensaje = json.loads(contenido.decode('utf-8'))
    if not isinstance(mensaje, dict):
        raise ValueError('El mensaje debe ser un objeto JSON.')
    return mensaje
