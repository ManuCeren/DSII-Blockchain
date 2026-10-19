"""Procesos reales y GUI sobre el administrador, sin topología fija."""
import argparse
from pathlib import Path
import socket
import tempfile
import time
import unittest
import gc

from administracion.nodos import AdministradorNodos, ConfiguracionNodo
from cliente.cliente import Cliente


class PruebasAdministrador(unittest.TestCase):
    def test_gui_crea_consulta_muestra_bloque_y_cierra_proceso(self):
        from interfaz.gui_administrador import AppAdministrador
        gc_activo = gc.isenabled()
        gc.disable()
        app = None
        try:
            with tempfile.TemporaryDirectory() as temporal:
                gestor = AdministradorNodos(temporal, Path(temporal) / 'clave.key')
                app = AppAdministrador(gestor)
                app.withdraw()
                puerto = None
                for p in range(7400, 8001):
                    with socket.socket() as prueba:
                        try:
                            prueba.bind(('127.0.0.1', p))
                            puerto = p
                            break
                        except OSError:
                            continue
                self.assertIsNotNone(puerto)
                app.campos['Puerto'].delete(0, 'end')
                app.campos['Puerto'].insert(0, str(puerto))
                app.crear()
                self.assertEqual(len(app.tabla.get_children()), 1)
                ventana = app.ventanas[puerto]
                ventana.withdraw()
                limite = time.monotonic() + 10
                while not ventana.arbol.get_children() and time.monotonic() < limite:
                    app.update()
                    time.sleep(.02)
                self.assertEqual(len(ventana.arbol.get_children()), 1)
                ventana.arbol.selection_set(ventana.arbol.get_children()[0])
                ventana.detalle(None)
                self.assertIn('timestamp', ventana.texto.get('1.0', 'end'))
                proceso = gestor.nodos[puerto].proceso
                app.cerrar()
                app = None
                self.assertIsNotNone(proceso.poll())
        finally:
            if app is not None:
                app.cerrar()
            gc.collect()
            if gc_activo:
                gc.enable()

    def test_validacion_y_vecinos_variables(self):
        for puerto in ('abc', 6999, 8001):
            with self.assertRaises((ValueError, argparse.ArgumentTypeError)):
                ConfiguracionNodo('Nodo', '127.0.0.1', puerto)
        with self.assertRaises(ValueError):
            ConfiguracionNodo('Nodo', 'IP inválida', 7010)
        with self.assertRaises(ValueError):
            ConfiguracionNodo('Nodo', '127.0.0.1', 7010, (('127.0.0.1', 7010),))
        for cantidad in (0, 1, 4, 10):
            vecinos = tuple(('127.0.0.1', 7100 + i) for i in range(cantidad))
            c = ConfiguracionNodo('Nodo', '127.0.0.1', 7010, vecinos)
            self.assertEqual(len(c.vecinos), cantidad)
            self.assertEqual(AdministradorNodos().argumentos(c).count('--nodo'), cantidad)

    def test_cinco_procesos_puerto_ocupado_reinicio_y_cierre(self):
        reservas = []
        puertos = []
        try:
            for p in range(7400, 8001):
                s = socket.socket()
                try:
                    s.bind(('127.0.0.1', p))
                except OSError:
                    s.close()
                    continue
                reservas.append(s)
                puertos.append(p)
                if len(puertos) == 6:
                    break
            self.assertEqual(len(puertos), 6)
            with tempfile.TemporaryDirectory() as temporal:
                gestor = AdministradorNodos(temporal, Path(temporal) / 'clave.key')
                with self.assertRaisesRegex(ValueError, 'ocupado'):
                    gestor.crear(ConfiguracionNodo('Ocupado', '127.0.0.1', puertos[-1]))
                # Un servidor externo de referencia no pertenece al gestor.
                externo = reservas.pop()
                for s in reservas:
                    s.close()
                reservas.clear()
                procesos = []
                try:
                    # Precrear la clave compartida para evitar una carrera inicial.
                    from core.encriptador import Encriptador
                    Encriptador(gestor.clave)
                    for p in reversed(puertos[:5]):
                        vecinos = tuple(('127.0.0.1', otro) for otro in puertos[:5] if otro != p)
                        nodo = gestor.crear(ConfiguracionNodo(f'Nodo {p}', '127.0.0.1', p, vecinos, 0))
                        procesos.append(nodo.proceso)
                    self.assertEqual(len(gestor.nodos), 5)
                    with self.assertRaisesRegex(ValueError, 'pertenece'):
                        gestor.crear(ConfiguracionNodo('Duplicado', '127.0.0.1', puertos[0]))

                    def esperar(funcion):
                        limite = time.monotonic() + 15
                        while time.monotonic() < limite:
                            try:
                                if funcion():
                                    return
                            except (OSError, ValueError):
                                pass
                            time.sleep(.05)
                        self.fail('No respondió la red a tiempo.')

                    esperar(lambda: all(len(gestor.consultar(p)[0]['cadena']) == 1 for p in puertos[:5]))
                    cliente = Cliente('127.0.0.1', puertos[0], timeout=2)
                    cliente.solicitar('AGREGAR_INCIDENTE', dict(tipo='Malware', descripcion='Prueba', reportado_por='Ana', severidad='Alta'))
                    cliente.solicitar('MINAR_BLOQUE')
                    esperar(lambda: all(len(gestor.consultar(p)[0]['cadena']) == 2 for p in puertos[:5]))
                    gestor.detener(puertos[1])
                    self.assertEqual(gestor.nodos[puertos[1]].estado, 'DETENIDO')
                    self.assertIsNone(gestor.nodos[puertos[0]].proceso.poll())
                    gestor.reiniciar(puertos[1])
                    procesos.append(gestor.nodos[puertos[1]].proceso)
                    esperar(lambda: len(gestor.consultar(puertos[1])[0]['cadena']) == 2)
                    for p in puertos[:5]:
                        self.assertTrue((Path(temporal) / f'blockchain_{p}.json').exists())
                    gestor.cerrar()
                    self.assertTrue(all(p.poll() is not None for p in procesos))
                    self.assertGreater(externo.fileno(), -1)
                finally:
                    gestor.cerrar()
                    externo.close()
        finally:
            for s in reservas:
                s.close()
