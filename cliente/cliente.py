"""Cliente TCP sin Blockchain ni acceso a la clave privada del servidor."""
import socket
from comunicacion import enviar_json, recibir_json


class Cliente:
    def __init__(self, host='127.0.0.1', puerto=5000, timeout=300):
        self.host = host
        self.puerto = puerto
        self.timeout = timeout

    def solicitar(self, operacion, datos=None):
        # Una conexión por solicitud simplifica el protocolo inicial y permite
        # que el hilo de minado y la interfaz usen el mismo cliente sin mezclar bytes.
        with socket.create_connection((self.host, self.puerto), self.timeout) as conexion:
            with conexion.makefile('rwb') as flujo:
                enviar_json(flujo, {'operacion': operacion, 'datos': datos or {}})
                respuesta = recibir_json(flujo)
        if respuesta.get('ok') is not True:
            raise ValueError(respuesta.get('error', 'Respuesta inválida del servidor.'))
        return respuesta['resultado']
