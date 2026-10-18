import argparse
import gc
import io
import unittest
from unittest.mock import patch

from cliente.cliente import argumentos_cliente
import main
from servidor.servidor import configurar_argumentos
from tests.soporte import PruebaConNodos


class PruebasConfiguracion(unittest.TestCase):
    def test_servidor_configura_puerto_nodos_y_valida_rango(self):
        parser = configurar_argumentos(argparse.ArgumentParser())
        args = parser.parse_args(['--puerto', '7001', '--nodo', '127.0.0.1:7000',
                                  '--nodo', 'localhost:7002'])
        self.assertEqual(args.puerto, 7001)
        self.assertEqual(args.nodo, [('127.0.0.1', 7000), ('localhost', 7002)])
        for argumentos in (['--puerto', '5000'], ['--puerto', '8001'],
                           ['--puerto', 'texto'], ['--nodo', 'sin-puerto']):
            with self.subTest(argumentos=argumentos), patch('sys.stderr', new=io.StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args(argumentos)

    def test_cliente_y_puntos_de_entrada_reciben_host_y_puerto(self):
        args = argumentos_cliente(argparse.ArgumentParser()).parse_args(
            ['--host', '127.0.0.2', '--puerto', '7002'])
        self.assertEqual((args.host, args.puerto), ('127.0.0.2', 7002))
        for modo, destino in [('servidor', 'servidor.servidor.main'),
                              ('gui', 'interfaz.gui_incidentes.main'),
                              ('consola', 'blockchain_incidentes.main')]:
            with self.subTest(modo=modo), patch(destino) as iniciar:
                main.main([modo, '--puerto', '7002'])
                iniciar.assert_called_once_with(['--puerto', '7002'])


class PruebasConfiguracionGUI(PruebaConNodos):
    def setUp(self):
        super().setUp()
        self.gc_activo = gc.isenabled()
        gc.disable()

    def tearDown(self):
        # La liberación del intérprete Tcl se realiza en este hilo principal.
        gc.collect()
        if self.gc_activo:
            gc.enable()

    def test_boton_servidor_cambia_la_conexion_y_refresca_la_cadena(self):
        from interfaz.gui_incidentes import AppBlockchain
        a = self.crear_nodo()
        b = self.crear_nodo()
        self.minar(b)
        app = AppBlockchain(self.cliente(a))
        try:
            app.withdraw()
            with patch('interfaz.gui_incidentes.simpledialog.askstring',
                       return_value=f'127.0.0.1:{b.server_address[1]}'):
                app._configurar_servidor()
            self.assertEqual(app.cliente.puerto, b.server_address[1])
            self.assertEqual(len(app.arbol.get_children()), 2)
            self.assertIn(str(b.server_address[1]), app.title())
        finally:
            app.destroy()
