"""Cliente TCP sin Blockchain ni acceso a la clave privada del servidor."""
import argparse
import socket
from comunicacion import enviar_json, recibir_json


class Cliente:
    def __init__(self, host='127.0.0.1', puerto=7000, timeout=300, *, contexto="wallet", cifrador=None):
        self.contexto = contexto
        self.cifrador = cifrador
        self.host = host
        self.puerto = puerto
        self.timeout = timeout

    def solicitar(self, operacion, datos=None):
        # Una conexión por solicitud simplifica el protocolo inicial y permite
        # que el hilo de minado y la interfaz usen el mismo cliente sin mezclar bytes.
        with socket.create_connection((self.host, self.puerto), self.timeout) as conexion:
            with conexion.makefile('rwb') as flujo:
                enviar_json(flujo, {'operacion': operacion, 'datos': datos or {}}, contexto=self.contexto, cifrador=self.cifrador)
                respuesta = recibir_json(flujo, contexto=self.contexto, cifrador=self.cifrador)
        if respuesta.get('ok') is not True:
            raise ValueError(respuesta.get('error', 'Respuesta inválida del servidor.'))
        if 'resultado' not in respuesta:
            raise ValueError('Respuesta del servidor sin resultado.')
        return respuesta['resultado']


def puerto_cliente(texto):
    try:
        puerto = int(texto)
    except ValueError as error:
        raise argparse.ArgumentTypeError('El puerto debe ser un entero.') from error
    if not 1 <= puerto <= 65535:
        raise argparse.ArgumentTypeError('Puerto TCP fuera del rango 1–65535.')
    return puerto


def argumentos_cliente(parser):
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--puerto', type=puerto_cliente, default=7000)
    return parser
