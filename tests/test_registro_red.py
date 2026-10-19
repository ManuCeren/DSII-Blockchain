"""Registro administrativo separado de la blockchain y malla TCP real."""
import gc
import json
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from administracion.nodos import AdministradorNodos, ConfiguracionNodo
from cliente.cliente import Cliente
from servidor.servidor import ServidorBlockchain


class PruebasRegistroRed(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.datos = Path(self.temporal.name)
        self.clave = self.datos / 'clave.key'
        self.gestor = AdministradorNodos(self.datos, self.clave)
        self.addCleanup(self.gestor.cerrar)

    def esperar(self, funcion):
        limite = time.monotonic() + 15
        while time.monotonic() < limite:
            try:
                if funcion():
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.05)
        self.fail('La red no alcanzó el estado esperado.')

    def test_registro_vacio_cinco_nodos_detenidos_y_recarga(self):
        self.assertEqual(len(self.gestor.nodos), 0)
        self.assertFalse(self.gestor.archivo_red.exists())
        for i in range(5):
            p = self.gestor.siguiente_puerto()
            self.gestor.registrar(ConfiguracionNodo(f'Nodo {i + 1}', '127.0.0.1', p))
            self.assertEqual(len(self.gestor.nodos), i + 1)
        guardado = json.loads(self.gestor.archivo_red.read_text(encoding='utf-8'))
        self.assertEqual(len(guardado['nodos']), 5)
        self.assertNotIn('proceso', self.gestor.archivo_red.read_text())
        cargado = AdministradorNodos(self.datos, self.clave)
        self.addCleanup(cargado.cerrar)
        self.assertEqual(set(cargado.nodos), set(self.gestor.nodos))
        for identidad, nodo in cargado.nodos.items():
            self.assertEqual(nodo.estado, 'DETENIDO')
            self.assertIsNone(nodo.proceso)
            self.assertEqual(len(nodo.configuracion.vecinos), 4)
            self.assertNotIn(identidad, nodo.configuracion.vecinos)
        with self.assertRaisesRegex(ValueError, 'pertenece'):
            cargado.registrar(ConfiguracionNodo('Otro nombre', '127.0.0.1', next(iter(cargado.nodos))[1]))

    def test_busca_primer_puerto_omite_ocupado_registrado_y_detecta_agotamiento(self):
        p = self.gestor.siguiente_puerto()
        with socket.socket() as externo:
            externo.bind(('127.0.0.1', p))
            siguiente = self.gestor.siguiente_puerto()
            self.assertGreater(siguiente, p)
            self.gestor.registrar(ConfiguracionNodo('Registrado', '127.0.0.1', siguiente))
            self.assertGreater(self.gestor.siguiente_puerto(), siguiente)
        def rango_ocupado(host, puerto):
            if puerto:
                raise ValueError('Ocupado')

        with patch.object(self.gestor, '_comprobar_puerto', side_effect=rango_ocupado):
            with self.assertRaisesRegex(ValueError, 'No hay puertos'):
                self.gestor.siguiente_puerto()

    def test_registro_corrupto_y_fallo_guardado_no_destruyen_configuracion(self):
        p = self.gestor.siguiente_puerto()
        self.gestor.registrar(ConfiguracionNodo('Original', '127.0.0.1', p))
        anterior = self.gestor.archivo_red.read_bytes()
        with patch('administracion.nodos.os.replace', side_effect=OSError('Disco')):
            with self.assertRaises(OSError):
                self.gestor.registrar(ConfiguracionNodo('No guardado', '127.0.0.1', self.gestor.siguiente_puerto()))
        self.assertEqual(len(self.gestor.nodos), 1)
        self.assertEqual(self.gestor.archivo_red.read_bytes(), anterior)
        self.assertEqual(list(self.datos.glob('red_nodos.json.*.tmp')), [])
        self.gestor.archivo_red.write_text('{no es json', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Registro de red inválido'):
            AdministradorNodos(self.datos, self.clave)
        self.assertEqual(self.gestor.archivo_red.read_text(), '{no es json')

    def test_malla_cinco_procesos_sin_vecinos_manuales_conserva_proceso_y_pendientes(self):
        primero = self.gestor.crear(ConfiguracionNodo('Primero', '127.0.0.1', self.gestor.siguiente_puerto(), dificultad=0))
        identidad = primero.configuracion.identidad
        proceso = primero.proceso
        cliente = Cliente(*identidad, timeout=3)
        cliente.solicitar('AGREGAR_INCIDENTE', dict(tipo='Malware', descripcion='Pendiente conservado', reportado_por='Ana', severidad='Alta'))
        for i in range(4):
            self.gestor.crear(ConfiguracionNodo(f'Nodo {i + 2}', '127.0.0.1', self.gestor.siguiente_puerto(), dificultad=0))
            self.assertIs(primero.proceso, proceso)
            self.assertIsNone(proceso.poll())
            self.assertEqual(len(cliente.solicitar('VER_BLOQUE_PROPUESTO')['transacciones']), 1)
            for clave, nodo in self.gestor.nodos.items():
                reales = {tuple(v) for v in Cliente(*clave, timeout=2).solicitar('VER_NODOS')['nodos']}
                self.assertEqual(reales, set(self.gestor.nodos) - {clave})
                self.assertEqual(reales, set(nodo.configuracion.vecinos))
        # La operación administrativa rechaza tokens ausentes o incorrectos.
        for datos in ({'nodos': []}, {'token': 'incorrecto', 'nodos': []}):
            with self.assertRaisesRegex(ValueError, 'no autorizada'):
                cliente.solicitar('CONFIGURAR_VECINOS', datos)
        with self.assertRaises(ValueError):
            cliente.solicitar('CONFIGURAR_VECINOS', {'token': primero.token, 'nodos': [['host', 'mal']]})
        self.assertEqual(len(cliente.solicitar('VER_NODOS')['nodos']), 4)
        cliente.solicitar('MINAR_BLOQUE')
        self.esperar(lambda: all(len(self.gestor.consultar(k)[0]['cadena']) == 2 for k in self.gestor.nodos))
        esperada = cliente.solicitar('VER_CADENA')
        self.gestor.cerrar()
        cargado = AdministradorNodos(self.datos, self.clave)
        self.addCleanup(cargado.cerrar)
        self.assertTrue(all(n.estado == 'DETENIDO' for n in cargado.nodos.values()))
        for clave in cargado.nodos:
            cargado.iniciar(clave)
            self.assertEqual(cargado.consultar(clave)[0], esperada)
        # Agregar y minar mientras un nodo está apagado; al volver se sincroniza.
        ultimo = next(reversed(cargado.nodos))
        cargado.detener(ultimo)
        cliente.solicitar('AGREGAR_INCIDENTE', dict(tipo='Phishing', descripcion='Recuperación', reportado_por='Ana', severidad='Alta'))
        cliente.solicitar('MINAR_BLOQUE')
        cargado.iniciar(ultimo)
        self.esperar(lambda: len(cargado.consultar(ultimo)[0]['cadena']) == 3)
        # Eliminar solo el registro; actualizar vecinos reales sin borrar cadena.
        with self.assertRaisesRegex(ValueError, 'Detén'):
            cargado.eliminar(ultimo)
        cargado.detener(ultimo)
        archivo = self.datos / f'blockchain_{ultimo[1]}.json'
        antes = archivo.read_bytes()
        cargado.eliminar(ultimo)
        self.assertEqual(archivo.read_bytes(), antes)
        self.assertEqual(len(json.loads(cargado.archivo_red.read_text())['nodos']), 4)
        for clave in cargado.nodos:
            self.assertEqual({tuple(v) for v in Cliente(*clave, timeout=2).solicitar('VER_NODOS')['nodos']}, set(cargado.nodos) - {clave})

    def test_actualizacion_fallida_conserva_vecinos_reales_y_permite_reintentar(self):
        primero = self.gestor.crear(ConfiguracionNodo('Nodo', '127.0.0.1', self.gestor.siguiente_puerto(), dificultad=0))
        with patch.object(self.gestor, '_cliente', side_effect=OSError('Sin conexión')):
            self.gestor.registrar(ConfiguracionNodo('Otro', '127.0.0.1', self.gestor.siguiente_puerto(), dificultad=0))
        self.assertEqual(primero.configuracion.vecinos, ())
        self.assertIn('Sin conexión', primero.error_topologia)
        self.gestor.actualizar_vecinos()
        self.assertEqual(len(primero.configuracion.vecinos), 1)
        self.assertEqual(primero.error_topologia, '')

    def test_reinicio_explicito_conserva_cadena_y_falta_clave_no_genera_otra(self):
        nodo = self.gestor.crear(ConfiguracionNodo('Nodo', '127.0.0.1', self.gestor.siguiente_puerto(), dificultad=0))
        identidad = nodo.configuracion.identidad
        cliente = Cliente(*identidad, timeout=3)
        cliente.solicitar('AGREGAR_INCIDENTE', dict(tipo='Malware', descripcion='Dato persistido', reportado_por='Ana', severidad='Alta'))
        cliente.solicitar('MINAR_BLOQUE')
        cadena = cliente.solicitar('VER_CADENA')
        proceso_anterior = nodo.proceso
        self.gestor.reiniciar(identidad)
        self.assertIsNot(nodo.proceso, proceso_anterior)
        self.assertIsNotNone(proceso_anterior.poll())
        self.assertEqual(cliente.solicitar('VER_CADENA'), cadena)
        self.gestor.detener(identidad)
        archivo = self.datos / f'blockchain_{identidad[1]}.json'
        antes = archivo.read_bytes()
        self.clave.unlink()
        with self.assertRaisesRegex(ValueError, 'No arrancó'):
            self.gestor.iniciar(identidad)
        self.assertEqual(nodo.estado, 'DETENIDO')
        self.assertIsNone(nodo.proceso)
        self.assertFalse(self.clave.exists())
        self.assertEqual(archivo.read_bytes(), antes)
        recuperado = AdministradorNodos(self.datos, self.clave)
        self.assertIn(identidad, recuperado.nodos)
        self.assertEqual(recuperado.nodos[identidad].estado, 'DETENIDO')

    def test_servidor_manual_no_habilita_administracion(self):
        with ServidorBlockchain(('127.0.0.1', 0), 0, self.clave) as servidor:
            with self.assertRaisesRegex(ValueError, 'no autorizada'):
                servidor.procesar({'operacion': 'CONFIGURAR_VECINOS', 'datos': {'token': 'x', 'nodos': []}})

    def test_gui_recupera_tabla_sin_iniciar_procesos(self):
        from interfaz.gui_administrador import AppAdministrador
        for i in range(3):
            self.gestor.registrar(ConfiguracionNodo(f'Nodo {i}', '127.0.0.1', self.gestor.siguiente_puerto()))
        cargado = AdministradorNodos(self.datos, self.clave)
        activo = gc.isenabled()
        gc.disable()
        app = None
        try:
            app = AppAdministrador(cargado)
            app.withdraw()
            self.assertEqual(len(app.tabla.get_children()), 3)
            for item in app.tabla.get_children():
                self.assertEqual(app.tabla.item(item)['values'][-1], 'DETENIDO')
            self.assertTrue(all(n.proceso is None for n in cargado.nodos.values()))
        finally:
            if app is not None:
                app.cerrar()
            gc.collect()
            if activo:
                gc.enable()
