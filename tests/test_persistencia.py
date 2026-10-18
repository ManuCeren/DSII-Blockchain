import json
from unittest.mock import patch

from core.blockchain import Blockchain
from servidor.servidor import ServicioBlockchain
from tests.soporte import PruebaConNodos


class PruebasPersistencia(PruebaConNodos):
    def test_guarda_genesis_inmediatamente_y_reinicia_sin_minar(self):
        nodo = self.crear_nodo()
        ruta = nodo.servicio.almacen.ruta
        original = self.cadena(nodo)
        self.assertTrue(ruta.exists())
        self.assertEqual(json.loads(ruta.read_text(encoding='utf-8'))['cadena'], original['cadena'])
        puerto = nodo.server_address[1]
        self.apagar(nodo)
        with patch.object(Blockchain, '_crear_bloque_genesis', side_effect=AssertionError('No crear Génesis')):
            reiniciado = self.crear_nodo(puerto=puerto, directorio=ruta.parent)
        self.assertEqual(self.cadena(reiniciado), original)

    def test_persistencia_completa_cifrada_y_descifrado_despues_de_reinicio(self):
        nodo = self.crear_nodo()
        self.minar(nodo, cantidad=2)
        self.cliente(nodo).solicitar('CAMBIAR_DIFICULTAD', {'dificultad': 2})
        self.minar(nodo)
        original = self.cadena(nodo)
        ruta = nodo.servicio.almacen.ruta
        contenido = ruta.read_text(encoding='utf-8')
        self.assertNotIn('Descripción secreta', contenido)
        self.assertNotIn('Persona confidencial', contenido)
        for bloque in json.loads(contenido)['cadena']:
            for incidente in bloque['transacciones']:
                self.assertNotIn('descripcion', incidente)
                self.assertNotIn('reportado_por', incidente)
        self.apagar(nodo)
        with patch.object(Blockchain, '_crear_bloque_genesis', side_effect=AssertionError('No minar')):
            reiniciado = self.crear_nodo(puerto=nodo.server_address[1], directorio=ruta.parent)
        self.assertEqual(self.cadena(reiniciado), original)
        detalle = self.cliente(reiniciado).solicitar('VER_INCIDENTE', {
            'numero_bloque': 1, 'id_incidente': 1})
        self.assertEqual(detalle['descripcion'], 'Descripción secreta 🔐')
        self.assertEqual(detalle['reportado_por'], 'Persona confidencial')
        nuevo = self.minar(reiniciado)
        self.assertEqual(nuevo['transacciones'][0]['id_incidente'], 4)

    def test_archivo_corrupto_no_se_sustituye_por_genesis(self):
        ruta = self.directorio / 'invalida.json'
        for contenido in ('{incompleto', '{"version":2}', '{"version":1,"dificultad":1,"cadena":[]}'):
            with self.subTest(contenido=contenido):
                ruta.write_text(contenido, encoding='utf-8')
                with patch.object(Blockchain, '_crear_bloque_genesis', side_effect=AssertionError('No sobrescribir')):
                    with self.assertRaises(ValueError):
                        ServicioBlockchain(1, self.clave, ruta)
                self.assertEqual(ruta.read_text(encoding='utf-8'), contenido)

    def test_fallo_de_disco_no_confirma_ni_pierde_propuesto(self):
        nodo = self.crear_nodo()
        cliente = self.cliente(nodo)
        cliente.solicitar('AGREGAR_INCIDENTE', {
            'tipo': 'Malware', 'descripcion': 'Prueba', 'reportado_por': 'Ana', 'severidad': 'Alta'})
        ruta = nodo.servicio.almacen.ruta
        antes = ruta.read_bytes()
        with patch('servidor.persistencia.os.replace', side_effect=OSError('Disco no disponible')):
            with self.assertRaisesRegex(ValueError, 'Disco no disponible'):
                cliente.solicitar('MINAR_BLOQUE')
        self.assertEqual(len(self.cadena(nodo)['cadena']), 1)
        self.assertEqual(ruta.read_bytes(), antes)
        self.assertIsNone(cliente.solicitar('VER_BLOQUE_PROPUESTO')['hash'])
        self.assertFalse(list(ruta.parent.glob('*.tmp')))
        cliente.solicitar('MINAR_BLOQUE')
        self.assertEqual(len(self.cadena(nodo)['cadena']), 2)

    def test_clave_incorrecta_o_ausente_impide_cargar_incidentes(self):
        nodo = self.crear_nodo()
        self.minar(nodo)
        ruta = nodo.servicio.almacen.ruta
        antes = ruta.read_bytes()
        self.apagar(nodo)
        otra = self.directorio / 'otra.key'
        from core.encriptador import Encriptador
        Encriptador(otra)
        with self.assertRaisesRegex(ValueError, 'Fernet'):
            ServicioBlockchain(1, otra, ruta)
        ausente = self.directorio / 'ausente.key'
        with self.assertRaisesRegex(ValueError, 'Falta la clave'):
            ServicioBlockchain(1, ausente, ruta)
        self.assertFalse(ausente.exists())
        self.assertEqual(ruta.read_bytes(), antes)
