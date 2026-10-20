"""Presentación Tk/ttk del nodo con consultas al servidor TCP real."""
import copy
import gc
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from unittest.mock import Mock

from administracion.nodos import NodoAdministrado
from cliente.cliente import Cliente
from interfaz.gui_administrador import AppAdministrador, VentanaNodo
from tests.soporte import PruebaConNodos


class AppDePrueba(tk.Tk):
    """Cola inmediata para verificar los callbacks de la vista sin procesos extra."""
    recibido = AppAdministrador.recibido

    def trabajar(self, funcion, callback):
        try:
            resultado = funcion()
        except Exception as error:
            resultado = error
        callback(resultado)


class PruebasPresentacionNodo(PruebaConNodos):
    def setUp(self):
        super().setUp()
        gc_activo = gc.isenabled()
        gc.disable()
        self.addCleanup(self.restaurar_gc, gc_activo)
        self.nodo = self.crear_nodo()
        self.minar(self.nodo)
        self.puerto = self.nodo.server_address[1]
        self.cliente_tcp = Cliente(*self.nodo.server_address, timeout=5)
        configuracion = SimpleNamespace(nombre='Nodo de prueba', host='127.0.0.1',
                                        puerto=self.puerto, vecinos=())
        self.administrado = NodoAdministrado(configuracion, proceso=Mock(), disponible=True)
        self.administrado.proceso.poll.return_value = None
        self.app = AppDePrueba()
        self.app.withdraw()
        self.addCleanup(self.app.destroy)
        self.app.gestor = SimpleNamespace(nodos={self.puerto: self.administrado},
                                         consultar=Mock(side_effect=self.consultar_tcp))
        self.app.ocupados = set()
        self.app.cerrando = False
        self.app.ventanas = {}
        self.ventana = VentanaNodo(self.app, self.puerto)
        self.app.ventanas[self.puerto] = self.ventana
        self.ventana.actualizar(self.consultar_tcp(self.puerto))
        self.app.update()

    @staticmethod
    def restaurar_gc(activo):
        gc.collect()
        if activo:
            gc.enable()

    def consultar_tcp(self, puerto):
        self.assertEqual(puerto, self.puerto)
        return (self.cliente_tcp.solicitar('VER_CADENA'), self.cliente_tcp.solicitar('VER_NODOS'))

    def contenido(self, widget):
        return widget.get('1.0', 'end').strip()

    def test_resumen_compacto_y_tecnica_oculta_con_todos_los_datos(self):
        v = self.ventana
        self.assertEqual(v.nombre.cget('text'), 'Nodo de prueba')
        self.assertEqual(v.estado.cget('text'), '● ACTIVO')
        resumen = v.resumen.cget('text')
        for texto in ('Bloques: 2', 'Dificultad: 1', 'Vecinos: 0'):
            self.assertIn(texto, resumen)
        for texto in ('TCP', 'Último hash', 'sincronización', 'nonce'):
            self.assertNotIn(texto, resumen)
        self.assertFalse(v.tecnica_visible)
        self.assertFalse(v.informacion_tecnica.winfo_ismapped())
        cadena, _ = self.consultar_tcp(self.puerto)
        self.assertIn(cadena['cadena'][-1]['hash'], self.contenido(v.tecnico))
        self.assertIn('TCP: disponible', self.contenido(v.tecnico))
        self.assertIn('Estado: Sin cambios', self.contenido(v.sincronizacion))
        self.assertIn('Estado TCP actualizado', self.contenido(v.actividad))

    def test_plegar_desplegar_no_consulta_ni_altera_servidor_y_cabe_en_ventana(self):
        v = self.ventana
        original = self.cliente_tcp.solicitar('VER_CADENA')
        almacen = self.nodo.servicio.almacen
        archivos = {p: p.read_bytes() for p in almacen.directorio.rglob('*') if p.is_file()}
        eventos = list(self.administrado.eventos)
        for _ in range(2):
            v.geometry('800x640')
            v.boton_tecnica.invoke()
            self.app.update()
            self.assertTrue(v.informacion_tecnica.winfo_ismapped())
            self.assertIn('Ocultar', v.boton_tecnica.cget('text'))
            for widget in (v.arbol, v.texto, v.tecnico, v.sincronizacion, v.actividad):
                self.assertGreater(widget.winfo_height(), 10)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                     v.winfo_rooty() + v.winfo_height())
            v.boton_tecnica.invoke()
            self.app.update()
            self.assertFalse(v.informacion_tecnica.winfo_ismapped())
            self.assertIn('Ver información', v.boton_tecnica.cget('text'))
        self.app.gestor.consultar.assert_not_called()
        self.assertEqual(self.administrado.eventos, eventos)
        self.assertEqual(self.cliente_tcp.solicitar('VER_CADENA'), original)
        self.assertEqual({p: p.read_bytes() for p in archivos}, archivos)

    def test_actualizar_consulta_tcp_y_conserva_seleccion_y_detalle(self):
        v = self.ventana
        bloque = v.arbol.get_children()[1]
        v.arbol.selection_set(bloque)
        v.detalle(None)
        self.app.update()
        detalle = self.contenido(v.texto)
        v.boton_actualizar.invoke()
        self.app.gestor.consultar.assert_called_once_with(self.puerto)
        self.assertEqual(v.arbol.selection(), (bloque,))
        self.assertEqual(self.contenido(v.texto), detalle)
        self.assertNotIn(self.puerto, self.app.ocupados)

    def test_seleccionar_bloque_e_incidente_conserva_detalles_reales(self):
        v = self.ventana
        bloque = v.arbol.get_children()[1]
        v.arbol.selection_set(bloque)
        v.detalle(None)
        for campo in ('numero_bloque', 'hash_anterior', 'timestamp', 'nonce', 'dificultad', 'hash'):
            self.assertIn(campo, self.contenido(v.texto))
        self.assertIn('Cantidad de incidentes: 1', self.contenido(v.texto))
        incidente = v.arbol.get_children(bloque)[0]
        v.arbol.selection_set(incidente)
        v.detalle(None)
        self.assertIn('Persona confidencial', self.contenido(v.texto))
        self.assertIn('Descripción secreta', self.contenido(v.texto))

    def test_sincronizacion_legible_sin_modificar_objeto_original(self):
        cadena, red = self.consultar_tcp(self.puerto)
        red['nodos'] = [['127.0.0.1', 7001], ['127.0.0.1', 7002]]
        red['ultima_sincronizacion'] = {'actualizada': False, 'errores': [
            {'nodo': ['127.0.0.1', 7002], 'error': 'timed out'}]}
        original = copy.deepcopy(red)
        self.ventana.actualizar((cadena, red))
        texto = self.contenido(self.ventana.sincronizacion)
        self.assertIn('Estado: Sin cambios', texto)
        self.assertIn('Nodo 127.0.0.1:7001 — Sin errores reportados', texto)
        self.assertIn('Nodo 127.0.0.1:7002 — No respondió (tiempo de espera agotado)', texto)
        self.assertNotIn("'errores'", texto)
        self.assertEqual(red, original)

    def test_nodo_detenido_o_timeout_no_rompe_la_vista(self):
        self.administrado.proceso = None
        self.app.gestor.consultar.side_effect = TimeoutError('timed out')
        self.ventana.boton_actualizar.invoke()
        self.assertEqual(self.ventana.estado.cget('text'), '● DETENIDO')
        self.assertIn('tiempo de espera agotado', self.contenido(self.ventana.tecnico))
        self.assertEqual(len(self.ventana.arbol.get_children()), 2)
        self.assertNotIn(self.puerto, self.app.ocupados)
        self.ventana.boton_tecnica.invoke()
        self.app.update()
        self.assertTrue(self.ventana.informacion_tecnica.winfo_ismapped())


    def preparar_registro_desplazable(self):
        self.administrado.registro = self.directorio / 'actividad.log'
        self.administrado.registro.write_text(''.join(f'Línea {i:03d}\n' for i in range(100)),
                                              encoding='utf-8')
        self.ventana.boton_tecnica.invoke()
        self.ventana.actualizar(self.consultar_tcp(self.puerto))
        self.app.update()
        self.assertLess(self.ventana.actividad.yview()[1] - self.ventana.actividad.yview()[0], 0.5)

    def test_actividad_conserva_scroll_manual_en_actualizaciones(self):
        self.preparar_registro_desplazable()
        actividad = self.ventana.actividad
        actividad.yview_moveto(0.4)
        self.app.update()
        inicio = actividad.yview()[0]
        for _ in range(3):
            self.ventana.actualizar(self.consultar_tcp(self.puerto))
            self.app.update()
            self.assertAlmostEqual(actividad.yview()[0], inicio, delta=0.001)
        with self.administrado.registro.open('a', encoding='utf-8') as archivo:
            archivo.write('Nueva línea al final\n' * 10)
        self.ventana.actualizar(self.consultar_tcp(self.puerto))
        self.app.update()
        self.assertAlmostEqual(actividad.yview()[0], inicio, delta=0.01)
        self.assertLess(actividad.yview()[1], 1.0)

    def test_actividad_sigue_el_final_hasta_que_el_usuario_sube(self):
        self.preparar_registro_desplazable()
        actividad = self.ventana.actividad
        actividad.yview_moveto(1.0)
        self.app.update()
        self.assertAlmostEqual(actividad.yview()[1], 1.0)
        with self.administrado.registro.open('a', encoding='utf-8') as archivo:
            archivo.write('Última entrada del registro\n' * 10)
        self.ventana.actualizar(self.consultar_tcp(self.puerto))
        self.app.update()
        self.assertAlmostEqual(actividad.yview()[1], 1.0)
        self.assertIn('Última entrada', self.contenido(actividad))
        actividad.yview_moveto(0.25)
        self.app.update()
        inicio = actividad.yview()[0]
        with self.administrado.registro.open('a', encoding='utf-8') as archivo:
            archivo.write('Otra entrada\n' * 10)
        self.ventana.actualizar(self.consultar_tcp(self.puerto))
        self.app.update()
        self.assertAlmostEqual(actividad.yview()[0], inicio, delta=0.01)
        self.assertLess(actividad.yview()[1], 1.0)

    def test_actividad_conserva_inicio_elegido_manualmente(self):
        self.preparar_registro_desplazable()
        self.ventana.actividad.yview_moveto(0.0)
        self.app.update()
        self.ventana.actualizar(self.consultar_tcp(self.puerto))
        self.app.update()
        self.assertAlmostEqual(self.ventana.actividad.yview()[0], 0.0)
