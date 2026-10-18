"""Integración real de widgets Tkinter con el servidor TCP de prueba."""
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from cliente.cliente import Cliente
from interfaz.gui_incidentes import AppBlockchain
from servidor.servidor import ServidorBlockchain


class PruebasInterfaz(unittest.TestCase):
    def test_formulario_minado_vistas_y_detalle(self):
        with tempfile.TemporaryDirectory() as temporal:
            with ServidorBlockchain(('127.0.0.1', 0), 1, Path(temporal) / 'clave.key') as servidor:
                hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
                hilo.start()
                app = None
                try:
                    cliente = Cliente(*servidor.server_address, timeout=10)
                    app = AppBlockchain(cliente)
                    app.withdraw()
                    self.assertEqual(len(app.arbol.get_children()), 1)
                    app._abrir_formulario_incidente()
                    formulario = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
                    formulario.withdraw()
                    widgets = formulario.winfo_children()
                    combos = [w for w in widgets if isinstance(w, ttk.Combobox)]
                    combos[0].set('Malware')
                    combos[1].set('Alta')
                    next(w for w in widgets if isinstance(w, tk.Text)).insert('1.0', 'Incidente de prueba')
                    next(w for w in widgets if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)).insert(0, 'Ana')
                    next(w for w in widgets if isinstance(w, ttk.Button)).invoke()
                    self.assertEqual(len(app.bloque_propuesto.transacciones), 1)
                    app._minar_bloque_propuesto()
                    limite = time.monotonic() + 10
                    while app.minando and time.monotonic() < limite:
                        app.update()
                        time.sleep(0.01)
                    self.assertFalse(app.minando)
                    self.assertEqual(len(app.arbol.get_children()), 2)
                    self.assertIsNone(app.bloque_propuesto)
                    bloque = app.arbol.get_children()[1]
                    incidente = app.arbol.get_children(bloque)[0]
                    app.arbol.selection_set(incidente)
                    app._mostrar_detalle_seleccion(None)
                    detalle = app.txt_detalle.get('1.0', 'end')
                    self.assertIn('Incidente de prueba', detalle)
                    self.assertIn('Ana', detalle)
                    with patch('interfaz.gui_incidentes.simpledialog.askinteger', return_value=2):
                        app._cambiar_dificultad()
                    self.assertEqual(cliente.solicitar('VER_CADENA')['dificultad'], 2)
                finally:
                    if app is not None:
                        app.destroy()
                    servidor.shutdown()
                    hilo.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
