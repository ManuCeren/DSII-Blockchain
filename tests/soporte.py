"""Nodos TCP reales y datos temporales; nunca se usa la clave del repositorio."""
from pathlib import Path
import tempfile
import threading
import time
import unittest

from cliente.cliente import Cliente
from core.encriptador import Encriptador
from servidor.servidor import ServidorBlockchain


class PruebaConNodos(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.directorio = Path(temporal.name)
        self.clave = self.directorio / 'red.key'
        Encriptador(self.clave)
        self.nodos = []
        self.hilos = {}
        self.addCleanup(self.cerrar_todos)

    def crear_nodo(self, *, nodos=(), puerto=0, dificultad=1, directorio=None,
                   iniciar=True, intervalo=0.2):
        carpeta = directorio or self.directorio / f'nodo_{len(self.nodos)}'
        servidor = ServidorBlockchain(('127.0.0.1', puerto), dificultad, self.clave,
                                      nodos=nodos, directorio_datos=carpeta,
                                      intervalo=intervalo, timeout_nodos=0.5)
        self.nodos.append(servidor)
        if iniciar:
            self.iniciar(servidor)
        return servidor

    def iniciar(self, nodo):
        hilo = threading.Thread(target=nodo.serve_forever, daemon=True)
        self.hilos[nodo] = hilo
        hilo.start()

    def apagar(self, nodo):
        if nodo in self.hilos:
            nodo.shutdown()
            self.hilos.pop(nodo).join(timeout=5)
        nodo.server_close()

    def cerrar_todos(self):
        for nodo in reversed(self.nodos):
            self.apagar(nodo)

    @staticmethod
    def cliente(nodo):
        return Cliente(*nodo.server_address, timeout=10)

    def cadena(self, nodo):
        return self.cliente(nodo).solicitar('VER_CADENA')

    def minar(self, nodo, cantidad=1):
        cliente = self.cliente(nodo)
        for _ in range(cantidad):
            cliente.solicitar('AGREGAR_INCIDENTE', {
                'tipo': 'Malware', 'descripcion': 'Descripción secreta 🔐',
                'reportado_por': 'Persona confidencial', 'severidad': 'Alta'})
        return cliente.solicitar('MINAR_BLOQUE')

    def esperar(self, condicion, segundos=8):
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if condicion():
                return
            time.sleep(0.03)
        self.fail('Los nodos no alcanzaron el estado esperado a tiempo.')
