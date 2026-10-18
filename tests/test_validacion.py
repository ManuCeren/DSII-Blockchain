import copy

from core.blockchain import Blockchain
from core.bloque import Bloque
from servidor.consenso import es_preferible, trabajo_acumulado
from tests.soporte import PruebaConNodos


class PruebasValidacion(PruebaConNodos):
    def setUp(self):
        super().setUp()
        self.nodo = self.crear_nodo()
        self.minar(self.nodo, cantidad=2)
        self.datos = self.cadena(self.nodo)

    def test_valida_y_reconstruye_sin_cambiar_ningun_campo(self):
        reconstruida = Blockchain.from_dict(self.datos)
        self.assertTrue(reconstruida.validar_cadena())
        self.assertEqual(reconstruida.to_dict(), self.datos)

    def test_rechaza_alteraciones_estructurales_y_de_integridad(self):
        cambios = [
            lambda d: d['cadena'].clear(),
            lambda d: d['cadena'][0].update(timestamp=1),
            lambda d: d['cadena'][1].update(numero_bloque=4),
            lambda d: d['cadena'][1].update(hash_anterior='f' * 64),
            lambda d: d['cadena'][1].update(nonce=-1),
            lambda d: d['cadena'][1].update(nonce=True),
            lambda d: d['cadena'][1].update(timestamp=float('nan')),
            lambda d: d['cadena'][1].update(hash='f' * 64),
            lambda d: d['cadena'][1].update(dificultad=9),
            lambda d: d['cadena'][1].update(transacciones={}),
            lambda d: d['cadena'][1]['transacciones'][0].update(tipo='Alterado'),
            lambda d: d['cadena'][1]['transacciones'][0].update(descripcion='Texto plano'),
            lambda d: d['cadena'][1]['transacciones'][0].update(descripcion_cifrada='sin cifrar'),
            lambda d: d['cadena'][1]['transacciones'][0].update(id_incidente=True),
        ]
        for numero, cambio in enumerate(cambios):
            with self.subTest(cambio=numero):
                datos = copy.deepcopy(self.datos)
                cambio(datos)
                with self.assertRaises(ValueError):
                    Blockchain.from_dict(datos)

    def test_rechaza_pow_invalida_aunque_el_hash_coincida(self):
        bloque = Bloque.from_dict(self.datos['cadena'][1])
        while True:
            bloque.nonce += 1
            bloque.hash = bloque.calcular_hash()
            if not bloque.hash.startswith('0' * bloque.dificultad):
                break
        datos = copy.deepcopy(self.datos)
        datos['cadena'][1] = bloque.to_dict()
        with self.assertRaisesRegex(ValueError, 'Proof of Work'):
            Blockchain.from_dict(datos)

    def test_rechaza_ids_duplicados_incluso_con_hash_y_pow_validos(self):
        bloque = Bloque.from_dict(self.datos['cadena'][1])
        bloque.transacciones[1].id_incidente = bloque.transacciones[0].id_incidente
        bloque.hash = None  # Construcción deliberada de una cadena inválida para la prueba.
        bloque.minar(1)
        datos = copy.deepcopy(self.datos)
        datos['cadena'][1] = bloque.to_dict()
        with self.assertRaisesRegex(ValueError, 'duplicado'):
            Blockchain.from_dict(datos)

    def test_genesis_compartido_y_consenso_por_trabajo_no_por_longitud(self):
        a = Blockchain.from_dict(self.datos)
        b = Blockchain.from_dict(self.datos)
        self.assertEqual(Blockchain(1).cadena[0].to_dict(), a.cadena[0].to_dict())
        # Una rama corta con dificultad 2 pesa más que varios bloques de dificultad 0.
        a.dificultad = 2
        b.dificultad = 0
        from core.incidente import Incidente
        from core.encriptador import Encriptador
        encriptador = Encriptador(self.clave)
        for bc, cuantos in ((a, 1), (b, 3)):
            for _ in range(cuantos):
                bloque = Bloque(len(bc.cadena), bc.obtener_ultimo_bloque().hash)
                bloque.agregar_transaccion(Incidente(len(bc.cadena) + 2, 'Malware', 'D', 'R', 'Alta', encriptador))
                bc.agregar_bloque(bloque)
        self.assertLess(len(a.cadena), len(b.cadena))
        self.assertGreater(trabajo_acumulado(a), trabajo_acumulado(b))
        self.assertTrue(es_preferible(a, b))
        self.assertFalse(es_preferible(b, a))
        self.assertFalse(es_preferible(a, a))
        with self.assertRaisesRegex(ValueError, 'Génesis incompatible'):
            es_preferible(Blockchain(2), a)
