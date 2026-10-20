from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from cliente.cliente import Cliente
from comunicacion import MAX_MENSAJE, enviar_json, recibir_json
from servidor.servidor import ServidorBlockchain


class PruebasComunicacion(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.servidor = ServidorBlockchain(('127.0.0.1', 0), 1, Path(temporal.name) / 'clave.key')
        self.addCleanup(self.servidor.server_close)
        self.hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.hilo.start()
        self.addCleanup(self.detener)
        self.cliente = Cliente(*self.servidor.server_address, timeout=10)

    def detener(self):
        self.servidor.shutdown()
        self.hilo.join(timeout=5)

    def agregar(self):
        return self.cliente.solicitar('AGREGAR_INCIDENTE', {
            'tipo': 'Phishing', 'descripcion': 'Correo extraño\nSegunda línea 🔐',
            'reportado_por': 'José', 'severidad': 'Alta'})

    def test_flujo_completo_tcp_json_y_detalles(self):
        self.assertEqual(len(self.cliente.solicitar('VER_CADENA')['cadena']), 1)
        self.assertIsNone(self.cliente.solicitar('VER_BLOQUE_PROPUESTO'))
        self.agregar()
        self.agregar()
        propuesto = self.cliente.solicitar('VER_BLOQUE_PROPUESTO')
        self.assertIsNone(propuesto['hash'])
        self.assertEqual(len(propuesto['transacciones']), 2)
        bloque = self.cliente.solicitar('MINAR_BLOQUE')
        cadena = self.cliente.solicitar('VER_CADENA')['cadena']
        self.assertEqual(cadena[1], bloque)
        self.assertEqual(bloque['hash_anterior'], cadena[0]['hash'])
        self.assertTrue(bloque['hash'].startswith('0'))
        self.assertIsNone(self.cliente.solicitar('VER_BLOQUE_PROPUESTO'))
        detalle = self.cliente.solicitar('VER_INCIDENTE', {'numero_bloque': 1, 'id_incidente': 1})
        self.assertEqual(detalle['reportado_por'], 'José')
        self.assertEqual(detalle['descripcion'], 'Correo extraño\nSegunda línea 🔐')
        # Alterar una copia del cliente no altera el servidor.
        bloque['transacciones'].clear()
        self.assertEqual(len(self.cliente.solicitar('VER_CADENA')['cadena'][1]['transacciones']), 2)

    def test_errores_y_cambio_de_dificultad(self):
        for operacion, datos in [('MINAR_BLOQUE', {}), ('DESCONOCIDA', {}),
                                 ('AGREGAR_INCIDENTE', {}),
                                 ('CAMBIAR_DIFICULTAD', {'dificultad': -1}),
                                 ('CAMBIAR_DIFICULTAD', {'dificultad': True})]:
            with self.assertRaises(ValueError):
                self.cliente.solicitar(operacion, datos)
        self.cliente.solicitar('CAMBIAR_DIFICULTAD', {'dificultad': 2})
        self.assertEqual(self.cliente.solicitar('VER_CADENA')['dificultad'], 2)

    def test_clientes_concurrentes(self):
        with ThreadPoolExecutor(max_workers=4) as grupo:
            incidentes = list(grupo.map(lambda _: self.agregar(), range(8)))
        self.assertEqual(len({i['id_incidente'] for i in incidentes}), 8)
        self.assertEqual(len(self.cliente.solicitar('VER_BLOQUE_PROPUESTO')['transacciones']), 8)

    def test_json_fragmentado_en_tcp(self):
        with socket.create_connection(self.servidor.server_address, timeout=10) as conexion:
            salida = io.BytesIO()
            enviar_json(salida, {'operacion': 'VER_CADENA'})
            contenido = salida.getvalue()
            for fragmento in contenido:
                conexion.sendall(bytes([fragmento]))
            with conexion.makefile('rb') as flujo:
                self.assertTrue(recibir_json(flujo)['ok'])

    def test_json_invalido_no_detiene_servidor(self):
        for contenido in (b'{invalido}\n', b'[]\n', b'\xff\n'):
            with socket.create_connection(self.servidor.server_address, timeout=10) as conexion:
                conexion.sendall(contenido)
                with conexion.makefile('rb') as flujo:
                    self.assertFalse(recibir_json(flujo)['ok'])
        self.assertEqual(len(self.cliente.solicitar('VER_CADENA')['cadena']), 1)

    def test_delimitacion_y_limite(self):
        flujo = io.BytesIO()
        enviar_json(flujo, {'texto': 'á\nβ'})
        enviar_json(flujo, {'numero': 2})
        flujo.seek(0)
        self.assertEqual(recibir_json(flujo), {'texto': 'á\nβ'})
        self.assertEqual(recibir_json(flujo), {'numero': 2})
        with self.assertRaises(ValueError):
            recibir_json(io.BytesIO(b'{}'))
        with self.assertRaises(ValueError):
            recibir_json(io.BytesIO(b'x' * (MAX_MENSAJE + 1)))


if __name__ == '__main__':
    unittest.main()
