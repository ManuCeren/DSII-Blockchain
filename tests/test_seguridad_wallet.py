"""Verificación del disco y de los bytes del canal Wallet TCP real."""
import io
import json
import socket
from unittest.mock import patch
from cryptography.fernet import Fernet
from cliente.cliente import Cliente
from comunicacion import enviar_json, recibir_json, clave_contexto
from servidor.persistencia import AlmacenCadena
from servidor.servidor import ServicioBlockchain
from tests.soporte import PruebaConNodos


class PruebasWalletSegura(PruebaConNodos):
    def test_archivos_hash_cifrados_inmutables_y_solo_confirmados(self):
        nodo = self.crear_nodo()
        almacen = nodo.servicio.almacen
        cliente = Cliente(*nodo.server_address, timeout=10)
        cliente.solicitar('AGREGAR_INCIDENTE', dict(tipo='Malware', descripcion='Secreto',
                          reportado_por='Persona', severidad='Alta'))
        self.assertEqual(len(list(almacen.bloques.glob('*.json'))), 1)
        bloque = cliente.solicitar('MINAR_BLOQUE')
        self.assertEqual({p.stem for p in almacen.bloques.glob('*.json')},
                         {b['hash'] for b in self.cadena(nodo)['cadena']})
        ruta = almacen.bloques / (bloque['hash'] + '.json')
        antes = ruta.read_bytes()
        for texto in ('Secreto', 'Persona', 'Malware', 'transacciones', 'nonce'):
            self.assertNotIn(texto.encode(), antes)
        almacen.guardar(nodo.servicio.bc)
        self.assertEqual(ruta.read_bytes(), antes)
        self.assertEqual(almacen.cargar().to_dict(), self.cadena(nodo))
        ruta.write_text(json.dumps({'version': 1, 'cifrado': 'alterado'}))
        for operacion in (almacen.cargar, lambda: almacen.guardar(nodo.servicio.bc)):
            with self.assertRaises(ValueError):
                operacion()
        self.assertIn('alterado', ruta.read_text())

    def test_solicitud_y_respuesta_cifradas_en_tcp(self):
        nodo = self.crear_nodo()
        solicitud = {'operacion': 'VER_CADENA'}
        salida = io.BytesIO()
        enviar_json(salida, solicitud)
        self.assertNotIn(b'VER_CADENA', salida.getvalue())
        with socket.create_connection(nodo.server_address, timeout=5) as conexion:
            conexion.sendall(salida.getvalue())
            with conexion.makefile('rb') as flujo:
                respuesta = flujo.readline()
        self.assertNotIn(b'cadena', respuesta)
        self.assertNotIn(b'transacciones', respuesta)
        self.assertEqual(recibir_json(io.BytesIO(respuesta))['resultado'], self.cadena(nodo))

    def test_manipulacion_clave_incorrecta_y_texto_plano_rechazados(self):
        nodo = self.crear_nodo()
        salida = io.BytesIO()
        enviar_json(salida, {'operacion': 'AGREGAR_INCIDENTE', 'datos': dict(
            tipo='X', descripcion='Secreto', reportado_por='Ana', severidad='Alta')})
        alterado = bytearray(salida.getvalue())
        alterado[70] = ord('A') if alterado[70] != ord('A') else ord('B')
        incorrecto = io.BytesIO()
        enviar_json(incorrecto, {'operacion': 'VER_CADENA'}, cifrador=Fernet(Fernet.generate_key()))
        for contenido in (bytes(alterado), incorrecto.getvalue(), b'{"operacion":"VER_CADENA"}\n'):
            with socket.create_connection(nodo.server_address, timeout=5) as conexion:
                conexion.sendall(contenido)
                with conexion.makefile('rb') as flujo:
                    self.assertFalse(recibir_json(flujo)['ok'])
        self.assertIsNone(Cliente(*nodo.server_address).solicitar('VER_BLOQUE_PROPUESTO'))
        with self.assertRaises(ValueError):
            recibir_json(io.BytesIO(salida.getvalue()), cifrador=Fernet(Fernet.generate_key()))
        self.assertEqual(len(self.cadena(nodo)['cadena']), 1)

    def test_wallet_no_puede_usar_operaciones_reservadas_a_pares(self):
        nodo = self.crear_nodo()
        with self.assertRaisesRegex(ValueError, 'reservada'):
            Cliente(*nodo.server_address).solicitar('RECIBIR_BLOQUE', {})

    def test_migracion_validada_con_copia_y_reinicio(self):
        nodo = self.crear_nodo()
        self.minar(nodo)
        cadena = self.cadena(nodo)
        ruta = self.directorio / 'migracion' / 'blockchain_7000.json'
        ruta.parent.mkdir()
        anterior = {'version': 1, **cadena}
        ruta.write_text(json.dumps(anterior), encoding='utf-8')
        servicio = ServicioBlockchain(1, self.clave, ruta)
        self.assertEqual(servicio.bc.to_dict(), cadena)
        self.assertEqual(json.loads(ruta.with_suffix('.v1.bak').read_text()), anterior)
        self.assertEqual(json.loads(servicio.almacen.ruta.read_text())['version'], 2)
        self.assertEqual(json.loads(ruta.read_text()), anterior)
        with patch('core.bloque.Bloque.minar', side_effect=AssertionError('No reminar')):
            self.assertEqual(AlmacenCadena(ruta).cargar().to_dict(), cadena)

    def test_bloque_autenticado_pero_pow_invalido_y_clave_perdida(self):
        nodo = self.crear_nodo()
        bloque = self.minar(nodo)
        almacen = nodo.servicio.almacen
        ruta = almacen.bloques / (bloque['hash'] + '.json')
        cifrador = Fernet(almacen.ruta_clave.read_bytes())
        bloque['nonce'] += 1
        ruta.write_text(json.dumps({'version': 1, 'cifrado': cifrador.encrypt(
            json.dumps(bloque).encode()).decode()}))
        with self.assertRaises(ValueError):
            almacen.cargar()
        almacen.ruta_clave.unlink()
        with self.assertRaisesRegex(ValueError, 'Falta la clave'):
            almacen.cargar()
        self.assertFalse(almacen.ruta_clave.exists())
