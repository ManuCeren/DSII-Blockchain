import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from core.blockchain import Blockchain
from core.bloque import Bloque
from core.incidente import Incidente
from core.encriptador import Encriptador


class PruebasBlockchain(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ruta = Path(self.temporal.name) / 'clave.key'
        self.encriptador = Encriptador(self.ruta)
        # Dificultad baja acelera pruebas sin cambiar el algoritmo de PoW.
        self.bc = Blockchain(dificultad=2)

    def incidente(self, numero=1):
        return Incidente(numero, 'Malware', 'Descripción áé 🔐', 'Ana', 'Alta', self.encriptador)

    def test_genesis_automatico_y_sha256(self):
        genesis = self.bc.obtener_ultimo_bloque()
        self.assertEqual(len(self.bc.cadena), 1)
        self.assertEqual(genesis.numero_bloque, 0)
        self.assertEqual(genesis.hash_anterior, '0')
        self.assertEqual(genesis.transacciones, [])
        self.assertTrue(genesis.hash.startswith('00'))
        esperado = hashlib.sha256(json.dumps(genesis._contenido_para_hash(), sort_keys=True).encode()).hexdigest()
        self.assertEqual(genesis.hash, esperado)

    def test_varias_transacciones_minado_y_encadenamiento(self):
        anterior = self.bc.obtener_ultimo_bloque()
        for numero in (1, 2):
            bloque = Bloque(numero, anterior.hash)
            for identificador in (numero * 2, numero * 2 + 1):
                bloque.agregar_transaccion(self.incidente(identificador))
            self.assertIsNone(bloque.hash)
            self.assertEqual(len(bloque.transacciones), 2)
            self.bc.agregar_bloque(bloque)
            self.assertEqual(bloque.hash_anterior, anterior.hash)
            self.assertEqual(bloque.hash, bloque.calcular_hash())
            self.assertTrue(bloque.hash.startswith('00'))
            self.assertGreaterEqual(bloque.nonce, 0)
            anterior = bloque
        self.assertEqual(len(self.bc.cadena), 3)

    def test_bloque_minado_rechaza_transacciones_y_reminado(self):
        bloque = Bloque(1, self.bc.obtener_ultimo_bloque().hash)
        bloque.agregar_transaccion(self.incidente())
        self.bc.agregar_bloque(bloque)
        original = bloque._contenido_para_hash()
        with self.assertRaises(ValueError):
            bloque.agregar_transaccion(self.incidente(2))
        with self.assertRaises(ValueError):
            bloque.minar(2)
        with self.assertRaises(ValueError):
            self.bc.agregar_bloque(bloque)
        self.assertEqual(bloque._contenido_para_hash(), original)
        self.assertEqual(len(self.bc.cadena), 2)

    def test_solo_objetos_incidente(self):
        with self.assertRaises(TypeError):
            Bloque(1, '0').agregar_transaccion({})

    def test_cifrado_descifrado_y_reutilizacion_de_clave(self):
        incidente = self.incidente()
        datos = incidente.to_dict()
        self.assertNotIn('descripcion', datos)
        self.assertNotEqual(datos['descripcion_cifrada'], 'Descripción áé 🔐')
        self.assertNotEqual(datos['reportado_por_cifrado'], 'Ana')
        otro = Encriptador(self.ruta)
        self.assertEqual(self.encriptador.clave, otro.clave)
        self.assertEqual(incidente.descripcion(otro), 'Descripción áé 🔐')
        self.assertEqual(incidente.reportado_por(otro), 'Ana')


if __name__ == '__main__':
    unittest.main()
