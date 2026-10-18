"""Demostración completa con tres intérpretes independientes del mismo servidor."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

from cliente.cliente import Cliente
from tests.soporte import PruebaConNodos


class PruebasProcesos(PruebaConNodos):
    def test_tres_procesos_sincronizan_recuperan_nodo_y_reinician(self):
        reservados = []
        puertos = []
        try:
            for puerto in range(7300, 8001):
                conexion = socket.socket()
                try:
                    conexion.bind(('127.0.0.1', puerto))
                except OSError:
                    conexion.close()
                    continue
                reservados.append(conexion)
                puertos.append(puerto)
                if len(puertos) == 3:
                    break
        finally:
            for conexion in reservados:
                conexion.close()
        self.assertEqual(len(puertos), 3, 'Se necesitan tres puertos libres entre 7300 y 8000.')
        procesos = {}
        clientes = {p: Cliente('127.0.0.1', p, timeout=3) for p in puertos}
        raiz = Path(__file__).resolve().parents[1]

        def detener(puerto):
            proceso = procesos.pop(puerto, None)
            if proceso is not None:
                if proceso.poll() is None:
                    proceso.terminate()
                try:
                    proceso.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                    proceso.wait(timeout=5)

        def iniciar(puerto):
            argumentos = [sys.executable, '-m', 'servidor.servidor',
                          '--puerto', str(puerto), '--dificultad', '1',
                          '--datos', str(self.directorio / str(puerto)),
                          '--clave', str(self.clave)]
            for otro in puertos:
                if otro != puerto:
                    argumentos.extend(['--nodo', f'127.0.0.1:{otro}'])
            registro = self.directorio / f'proceso_{puerto}.log'
            with registro.open('ab') as salida:
                procesos[puerto] = subprocess.Popen(
                    argumentos, cwd=raiz, stdout=salida, stderr=salida,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            limite = time.monotonic() + 10
            while time.monotonic() < limite:
                if procesos[puerto].poll() is not None:
                    self.fail(f'Falló el nodo {puerto}: {registro.read_text(errors="replace")}')
                try:
                    clientes[puerto].solicitar('VER_CADENA')
                    return
                except OSError:
                    time.sleep(0.05)
            self.fail(f'No arrancó el proceso del nodo {puerto}.')

        def cadena(puerto):
            return clientes[puerto].solicitar('VER_CADENA')

        def minar(puerto, cantidad):
            for _ in range(cantidad):
                clientes[puerto].solicitar('AGREGAR_INCIDENTE', {
                    'tipo': 'Malware', 'descripcion': 'Secreto de demostración',
                    'reportado_por': 'Ana', 'severidad': 'Alta'})
            clientes[puerto].solicitar('MINAR_BLOQUE')

        try:
            for puerto in puertos:
                iniciar(puerto)
            a, b, c = puertos
            self.assertEqual(cadena(a), cadena(b))
            self.assertEqual(cadena(a), cadena(c))
            minar(a, 2)
            self.esperar(lambda: cadena(a) == cadena(b) == cadena(c), segundos=15)
            ruta_c = self.directorio / str(c) / f'blockchain_{c}.json'
            antes = ruta_c.read_bytes()
            detener(c)
            minar(a, 1)
            self.esperar(lambda: cadena(a) == cadena(b), segundos=15)
            self.assertEqual(ruta_c.read_bytes(), antes)
            iniciar(c)
            self.esperar(lambda: cadena(a) == cadena(b) == cadena(c), segundos=15)
            esperado = cadena(a)
            for puerto in puertos:
                ruta = self.directorio / str(puerto) / f'blockchain_{puerto}.json'
                self.assertEqual(json.loads(ruta.read_text(encoding='utf-8'))['cadena'], esperado['cadena'])
                detener(puerto)
            for puerto in puertos:
                iniciar(puerto)
                self.assertEqual(cadena(puerto), esperado)
        finally:
            for puerto in puertos:
                detener(puerto)
