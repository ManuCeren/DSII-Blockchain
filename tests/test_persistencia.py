import json
from unittest.mock import patch

from core.blockchain import Blockchain
from core.bloque import Bloque
from servidor.persistencia import AlmacenCadena
from servidor.servidor import ServicioBlockchain
from tests.soporte import PruebaConNodos


class PruebasPersistencia(PruebaConNodos):
    def test_guarda_genesis_inmediatamente_y_reinicia_sin_minar(self):
        nodo = self.crear_nodo()
        ruta = nodo.servicio.almacen.ruta
        original = self.cadena(nodo)
        self.assertTrue(ruta.exists())
        self.assertEqual(nodo.servicio.almacen.cargar().to_dict()['cadena'], original['cadena'])
        puerto = nodo.server_address[1]
        self.apagar(nodo)
        with patch.object(Blockchain, '_crear_bloque_genesis', side_effect=AssertionError('No crear Génesis')):
            reiniciado = self.crear_nodo(puerto=puerto, directorio=ruta.parent.parent)
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
        for bloque in nodo.servicio.almacen.cargar().to_dict()['cadena']:
            for incidente in bloque['transacciones']:
                self.assertNotIn('descripcion', incidente)
                self.assertNotIn('reportado_por', incidente)
        self.apagar(nodo)
        with patch.object(Blockchain, '_crear_bloque_genesis', side_effect=AssertionError('No minar')):
            reiniciado = self.crear_nodo(puerto=nodo.server_address[1], directorio=ruta.parent.parent)
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


class PruebasIndiceAutosuficiente(PruebaConNodos):
    def _cadena_con_cinco_bloques(self):
        nodo = self.crear_nodo()
        for _ in range(4):
            self.minar(nodo)
        # La dificultad local no se puede deducir del último bloque histórico.
        self.cliente(nodo).solicitar('CAMBIAR_DIFICULTAD', {'dificultad': 2})
        return nodo

    def _reiniciar_sin_archivos_anteriores(self, nodo):
        almacen = nodo.servicio.almacen
        original = self.cadena(nodo)
        self.assertEqual(len(original['cadena']), 5)
        self.assertEqual(almacen.ruta, almacen.directorio / 'indice.json')
        self.assertTrue(almacen.ruta.exists())
        archivos = {p.name: p.read_bytes() for p in almacen.bloques.glob('*.json')}
        self.assertEqual(set(archivos), {b['hash'] + '.json' for b in original['cadena']})
        for contenido in archivos.values():
            datos = json.loads(contenido)
            self.assertEqual(set(datos), {'version', 'cifrado'})
            self.assertNotIn(b'transacciones', contenido)
            self.assertNotIn(b'nonce', contenido)
        self.apagar(nodo)
        almacen.ruta_anterior.unlink(missing_ok=True)
        almacen.respaldo_anterior.unlink(missing_ok=True)
        with patch.object(Bloque, 'minar', side_effect=AssertionError('No volver a minar')), \
             patch.object(Blockchain, '_crear_bloque_genesis', side_effect=AssertionError('No crear Génesis')):
            reiniciado = self.crear_nodo(puerto=nodo.server_address[1],
                                        directorio=almacen.directorio.parent)
        recuperada = self.cadena(reiniciado)
        self.assertEqual(recuperada, original)
        for antes, despues in zip(original['cadena'], recuperada['cadena']):
            for campo in ('hash', 'nonce', 'timestamp', 'hash_anterior', 'transacciones', 'dificultad'):
                self.assertEqual(despues[campo], antes[campo])
        self.assertEqual({p.name: p.read_bytes() for p in almacen.bloques.glob('*.json')}, archivos)
        self.assertFalse(almacen.ruta_anterior.exists())
        self.assertFalse(almacen.respaldo_anterior.exists())
        self.assertEqual(self.cliente(reiniciado).solicitar('VER_INCIDENTE', {
            'numero_bloque': 4, 'id_incidente': 4})['reportado_por'], 'Persona confidencial')

    def test_cadena_nueva_reinicia_solo_con_indice_y_bloques_del_nodo(self):
        nodo = self._cadena_con_cinco_bloques()
        self.assertFalse(nodo.servicio.almacen.ruta_anterior.exists())
        self._reiniciar_sin_archivos_anteriores(nodo)

    def test_migracion_v1_reinicia_sin_json_anterior_ni_respaldo(self):
        origen = self._cadena_con_cinco_bloques()
        original = self.cadena(origen)
        self.apagar(origen)
        directorio = self.directorio / 'migrado'
        directorio.mkdir()
        anterior = directorio / f'blockchain_{origen.server_address[1]}.json'
        anterior.write_text(json.dumps({'version': 1, **original}), encoding='utf-8')
        antes = anterior.read_bytes()
        with patch.object(Bloque, 'minar', side_effect=AssertionError('No minar al migrar')):
            migrado = self.crear_nodo(puerto=origen.server_address[1], directorio=directorio)
        self.assertEqual(anterior.read_bytes(), antes)
        self.assertEqual(json.loads(migrado.servicio.almacen.respaldo_anterior.read_text()),
                         {'version': 1, **original})
        self._reiniciar_sin_archivos_anteriores(migrado)

    def test_traslada_indice_v2_anterior_sin_tocar_bloques_ni_archivo_fuente(self):
        nodo = self._cadena_con_cinco_bloques()
        almacen = nodo.servicio.almacen
        original = self.cadena(nodo)
        self.apagar(nodo)
        contenido = almacen.ruta.read_bytes()
        almacen.ruta_anterior.write_bytes(contenido)
        almacen.ruta.unlink()
        with patch.object(Bloque, 'minar', side_effect=AssertionError('No minar')):
            migrado = self.crear_nodo(puerto=nodo.server_address[1], directorio=almacen.directorio.parent)
        self.assertEqual(self.cadena(migrado), original)
        self.assertEqual(almacen.ruta_anterior.read_bytes(), contenido)
        self._reiniciar_sin_archivos_anteriores(migrado)

    def test_recupera_desde_respaldo_solo_si_coincide_con_bloques_cifrados(self):
        nodo = self._cadena_con_cinco_bloques()
        almacen = nodo.servicio.almacen
        original = self.cadena(nodo)
        self.apagar(nodo)
        respaldo = json.dumps({'version': 1, **original}).encode()
        almacen.respaldo_anterior.write_bytes(respaldo)
        almacen.ruta.unlink()
        with patch.object(Bloque, 'minar', side_effect=AssertionError('No minar')):
            recuperado = self.crear_nodo(puerto=nodo.server_address[1], directorio=almacen.directorio.parent)
        self.assertEqual(self.cadena(recuperado), original)
        self.assertEqual(almacen.respaldo_anterior.read_bytes(), respaldo)
        self._reiniciar_sin_archivos_anteriores(recuperado)

    def test_respaldo_desactualizado_no_descarta_bloques_actuales(self):
        nodo = self._cadena_con_cinco_bloques()
        almacen = nodo.servicio.almacen
        original = self.cadena(nodo)
        self.apagar(nodo)
        original['cadena'].pop()
        almacen.respaldo_anterior.write_text(json.dumps({'version': 1, **original}))
        almacen.ruta.unlink()
        antes = {p: p.read_bytes() for p in almacen.directorio.rglob('*') if p.is_file()}
        with patch.object(Bloque, 'minar', side_effect=AssertionError('No minar')):
            with self.assertRaisesRegex(ValueError, 'no identifica todos'):
                ServicioBlockchain(1, self.clave, almacen.ruta_anterior)
        self.assertFalse(almacen.ruta.exists())
        self.assertEqual({p: p.read_bytes() for p in almacen.directorio.rglob('*') if p.is_file()}, antes)

    def test_indice_canonico_prevalece_y_corrupcion_no_carga_una_copia_vieja(self):
        nodo = self._cadena_con_cinco_bloques()
        almacen = nodo.servicio.almacen
        original = self.cadena(nodo)
        self.apagar(nodo)
        original['cadena'].pop()
        almacen.ruta_anterior.write_text(json.dumps({'version': 1, **original}))
        self.assertEqual(len(almacen.cargar().cadena), 5)
        almacen.ruta.write_text('{corrupto')
        with self.assertRaises(ValueError):
            ServicioBlockchain(1, self.clave, almacen.ruta_anterior)
        self.assertEqual(almacen.ruta.read_text(), '{corrupto')

    def test_sin_indices_ni_respaldo_no_inventa_la_rama_activa(self):
        nodo = self._cadena_con_cinco_bloques()
        almacen = nodo.servicio.almacen
        self.apagar(nodo)
        almacen.ruta.unlink()
        with patch.object(Bloque, 'minar', side_effect=AssertionError('No crear Génesis')):
            with self.assertRaisesRegex(ValueError, 'Falta el índice'):
                ServicioBlockchain(1, self.clave, almacen.ruta_anterior)
        self.assertEqual(len(list(almacen.bloques.glob('*.json'))), 5)
        self.assertFalse(almacen.ruta.exists())
