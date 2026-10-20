import copy
import json
import time
from unittest.mock import patch

from core.blockchain import Blockchain
from core.bloque import Bloque
from servidor.consenso import es_preferible
from servidor.nodos import RedNodos
from tests.soporte import PruebaConNodos


class PruebasNodos(PruebaConNodos):
    def test_acepta_bloque_sin_reminarlo_y_no_propaga_duplicados(self):
        origen = self.crear_nodo()
        destino = self.crear_nodo()
        bloque = self.minar(origen, 2)
        cliente = self.cliente(destino)
        with patch.object(Bloque, 'minar', side_effect=AssertionError('No volver a minar')):
            with patch.object(destino.red, 'propagar', wraps=destino.red.propagar) as propagar:
                respuesta = cliente.solicitar('RECIBIR_BLOQUE', {'bloque': bloque})
                self.assertEqual(respuesta['estado'], 'aceptado')
                self.assertEqual(cliente.solicitar('RECIBIR_BLOQUE', {'bloque': bloque})['estado'], 'duplicado')
                self.assertEqual(propagar.call_count, 1)
        self.assertEqual(self.cadena(destino), self.cadena(origen))
        disco = destino.servicio.almacen.cargar().to_dict()
        self.assertEqual(disco['cadena'][-1], bloque)

    def test_rechaza_hash_pow_numero_padre_y_transacciones_invalidos(self):
        origen = self.crear_nodo()
        destino = self.crear_nodo()
        original = self.minar(origen)
        antes = self.cadena(destino)
        invalidos = []
        malo = copy.deepcopy(original)
        malo['hash'] = 'f' * 64
        invalidos.append(malo)
        malo = copy.deepcopy(original)
        malo['transacciones'][0]['descripcion'] = 'Texto plano prohibido'
        invalidos.append(malo)
        bloque = Bloque.from_dict(original)
        while True:
            bloque.nonce += 1
            bloque.hash = bloque.calcular_hash()
            if not bloque.hash.startswith('0'):
                break
        invalidos.append(bloque.to_dict())
        for campo, valor in (('hash_anterior', 'f' * 64), ('numero_bloque', 3)):
            bloque = Bloque.from_dict(original)
            setattr(bloque, campo, valor)
            bloque.hash = None
            bloque.minar(1)
            invalidos.append(bloque.to_dict())
        for numero, datos in enumerate(invalidos):
            with self.subTest(bloque=numero):
                with self.assertRaises(ValueError):
                    self.cliente(destino).solicitar('RECIBIR_BLOQUE', {'bloque': datos})
                self.assertEqual(self.cadena(destino), antes)

    def test_sincronizacion_manual_entre_dos_nodos(self):
        origen = self.crear_nodo()
        destino = self.crear_nodo(nodos=[origen.server_address], intervalo=60)
        self.minar(origen)
        self.minar(origen)
        self.cliente(destino).solicitar('SINCRONIZAR')
        self.assertEqual(self.cadena(destino), self.cadena(origen))
        disco = destino.servicio.almacen.cargar().to_dict()
        self.assertEqual(disco['cadena'], self.cadena(origen)['cadena'])
        estado = self.cliente(destino).solicitar('VER_NODOS')
        self.assertEqual(estado['nodos'], [list(origen.server_address)])

    def test_cadena_invalida_o_genesis_distinto_nunca_reemplazan_la_local(self):
        origen = self.crear_nodo()
        destino = self.crear_nodo()
        self.minar(origen)
        original = self.cadena(destino)
        invalida = self.cadena(origen)
        invalida['cadena'][1]['nonce'] += 1
        with self.assertRaises(ValueError):
            destino.servicio.adoptar_cadena(invalida)
        with self.assertRaisesRegex(ValueError, 'Génesis incompatible'):
            destino.servicio.adoptar_cadena(Blockchain(2).to_dict())
        self.assertEqual(self.cadena(destino), original)

    def test_tres_nodos_propagan_en_ciclo_sin_bucle_infinito(self):
        a = self.crear_nodo(iniciar=False)
        b = self.crear_nodo(iniciar=False)
        c = self.crear_nodo(iniciar=False)
        nodos = (a, b, c)
        # Se configuran antes de iniciar: el SO ya asignó puertos libres.
        for nodo in nodos:
            nodo.red.nodos = [otro.server_address for otro in nodos if otro is not nodo]
        eventos = []
        difundir = RedNodos._difundir

        def contar(red, bloque, origen):
            eventos.append((red.direccion, bloque['hash']))
            difundir(red, bloque, origen)

        with patch.object(RedNodos, '_difundir', contar):
            for nodo in nodos:
                self.iniciar(nodo)
            bloque = self.minar(a, 2)
            self.esperar(lambda: all(len(self.cadena(n)['cadena']) == 2 for n in nodos))
            self.esperar(lambda: len(eventos) == 3)
            for nodo in nodos:
                respuesta = self.cliente(nodo).solicitar('RECIBIR_BLOQUE', {'bloque': bloque})
                self.assertEqual(respuesta['estado'], 'duplicado')
            self.assertEqual(len(eventos), 3)
        for nodo in nodos:
            self.assertEqual(self.cadena(nodo), self.cadena(a))
        rutas = {n.servicio.almacen.ruta for n in nodos}
        self.assertEqual(len(rutas), 3)

    def test_nodo_apagado_se_pone_al_dia_y_todos_persisten_al_reiniciar(self):
        a = self.crear_nodo(iniciar=False)
        b = self.crear_nodo(nodos=[a.server_address], iniciar=False)
        c = self.crear_nodo(nodos=[a.server_address, b.server_address], iniciar=False)
        a.red.nodos = [b.server_address, c.server_address]
        b.red.nodos.append(c.server_address)
        for nodo in (a, b, c):
            self.iniciar(nodo)
        self.minar(a, 2)
        self.esperar(lambda: self.cadena(b) == self.cadena(a) == self.cadena(c))
        ruta_c = c.servicio.almacen.ruta
        viejo = ruta_c.read_bytes()
        self.apagar(c)
        self.minar(a)
        self.esperar(lambda: self.cadena(b) == self.cadena(a))
        self.assertEqual(ruta_c.read_bytes(), viejo)
        nuevo_c = self.crear_nodo(puerto=c.server_address[1], directorio=ruta_c.parent.parent,
                                 nodos=[a.server_address, b.server_address])
        self.esperar(lambda: self.cadena(nuevo_c) == self.cadena(a))
        esperado = self.cadena(a)
        actuales = (a, b, nuevo_c)
        for nodo in actuales:
            self.apagar(nodo)
        with patch.object(Blockchain, '_crear_bloque_genesis', side_effect=AssertionError('No recrear Génesis')):
            for nodo in actuales:
                nuevo = self.crear_nodo(puerto=nodo.server_address[1],
                                        directorio=nodo.servicio.almacen.directorio.parent)
                self.assertEqual(self.cadena(nuevo), esperado)

    def test_consenso_resuelve_ramas_y_conserva_incidentes_pendientes(self):
        a = self.crear_nodo()
        b = self.crear_nodo()
        self.minar(a)
        self.minar(b)
        cadenas = {n: self.cadena(n) for n in (a, b)}
        ganador, perdedor = (a, b) if es_preferible(
            Blockchain.from_dict(cadenas[a]), Blockchain.from_dict(cadenas[b])) else (b, a)
        perdedor.red.nodos = [ganador.server_address]
        self.cliente(perdedor).solicitar('AGREGAR_INCIDENTE', {
            'tipo': 'Phishing', 'descripcion': 'Pendiente', 'reportado_por': 'Ana', 'severidad': 'Media'})
        self.cliente(perdedor).solicitar('SINCRONIZAR')
        self.assertEqual(self.cadena(perdedor), self.cadena(ganador))
        propuesto = self.cliente(perdedor).solicitar('VER_BLOQUE_PROPUESTO')
        # Incidente de la rama descartada + incidente que ya estaba pendiente.
        self.assertEqual(len(propuesto['transacciones']), 2)
        self.assertEqual([t['id_incidente'] for t in propuesto['transacciones']], [2, 3])
        self.assertEqual(propuesto['hash_anterior'], self.cadena(ganador)['cadena'][-1]['hash'])
        self.cliente(perdedor).solicitar('MINAR_BLOQUE')
        self.assertTrue(perdedor.servicio.bc.validar_cadena())

    def test_nodo_inaccesible_no_impide_minar_ni_responder(self):
        apagado = self.crear_nodo()
        direccion = apagado.server_address
        self.apagar(apagado)
        nodo = self.crear_nodo(nodos=[direccion])
        inicio = time.monotonic()
        self.minar(nodo)
        self.assertLess(time.monotonic() - inicio, 5)
        estado = self.cliente(nodo).solicitar('SINCRONIZAR')
        self.assertEqual(len(estado['errores']), 1)
        self.assertEqual(len(self.cadena(nodo)['cadena']), 2)
