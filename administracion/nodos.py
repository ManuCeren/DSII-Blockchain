"""Capa sin Tkinter: configuración y propiedad de procesos del servidor existente."""
from dataclasses import dataclass, field, replace
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time

from cliente.cliente import Cliente
from core.bloque import validar_dificultad
from servidor.servidor import direccion_nodo, puerto_academico

RAIZ = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ConfiguracionNodo:
    nombre: str
    host: str
    puerto: int
    vecinos: tuple = ()
    dificultad: int = 4

    @property
    def identidad(self):
        return self.host, self.puerto

    def __post_init__(self):
        if not self.nombre.strip():
            raise ValueError('Escribe un nombre para el nodo.')
        ipaddress.IPv4Address(self.host)
        object.__setattr__(self, 'puerto', puerto_academico(str(self.puerto)))
        validar_dificultad(self.dificultad)
        vecinos = tuple(dict.fromkeys(direccion_nodo(f'{h}:{p}') for h, p in self.vecinos))
        if (self.host, self.puerto) in vecinos:
            raise ValueError('Un nodo no puede ser su propio vecino.')
        object.__setattr__(self, 'vecinos', vecinos)


@dataclass
class NodoAdministrado:
    configuracion: ConfiguracionNodo
    proceso: object = None
    registro: Path = None
    eventos: list = field(default_factory=list)
    token: str = field(default='', repr=False)
    error_topologia: str = ''
    disponible: bool = False

    @property
    def estado(self):
        if self.proceso is None:
            return 'DETENIDO'
        codigo = self.proceso.poll()
        if codigo is not None:
            return f'FINALIZADO ({codigo})'
        return 'ACTIVO' if self.disponible else 'NO DISPONIBLE'


class RegistroNodos(dict):
    """Identidad HOST+PUERTO; acepta puerto único para compatibilidad con la API previa."""
    def _identidad(self, clave):
        if isinstance(clave, int):
            return next((identidad for identidad in self if identidad[1] == clave), clave)
        return clave

    def __getitem__(self, clave):
        return super().__getitem__(self._identidad(clave))

    def __contains__(self, clave):
        return super().__contains__(self._identidad(clave))

    def __delitem__(self, clave):
        super().__delitem__(self._identidad(clave))


class AdministradorNodos:
    def __init__(self, datos=None, clave=None):
        self.datos = Path(datos) if datos is not None else RAIZ
        self.clave = Path(clave) if clave is not None else RAIZ / 'clave_secreta.key'
        self.nodos = RegistroNodos()
        self.archivo_red = self.datos / 'red_nodos.json'
        self._lock = threading.RLock()
        self._extras = {}
        self._cargar()

    def _cargar(self):
        if not self.archivo_red.exists():
            return
        try:
            contenido = json.loads(self.archivo_red.read_text(encoding='utf-8'))
            if (not isinstance(contenido, dict) or contenido.get('version') != 1
                    or not isinstance(contenido.get('nodos'), list)):
                raise ValueError('Formato de registro desconocido.')
            for datos in contenido['nodos']:
                c = ConfiguracionNodo(datos['nombre'], datos['host'], datos['puerto'],
                                      tuple(tuple(v) for v in datos.get('vecinos_adicionales', [])),
                                      datos.get('dificultad', 4))
                if c.puerto in self.nodos:
                    raise ValueError('Puerto duplicado en el registro.')
                self.nodos[c.identidad] = NodoAdministrado(c)
                self._extras[c.identidad] = c.vecinos
            for nodo in self.nodos.values():
                nodo.configuracion = replace(nodo.configuracion, vecinos=self.vecinos_para(nodo.configuracion.identidad))
        except (ValueError, argparse.ArgumentTypeError, KeyError, TypeError, IndexError, AttributeError) as error:
            raise ValueError(f'Registro de red inválido: {error}. Se conserva el archivo original.') from error

    def guardar(self):
        self.datos.mkdir(parents=True, exist_ok=True)
        contenido = {'version': 1, 'nodos': [
            {'nombre': n.configuracion.nombre, 'host': n.configuracion.host,
             'puerto': n.configuracion.puerto, 'dificultad': n.configuracion.dificultad,
             'vecinos_adicionales': list(self._extras[n.configuracion.identidad])}
            for n in self.nodos.values()]}
        temporal = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.datos,
                                             prefix='red_nodos.json.', suffix='.tmp', delete=False) as salida:
                temporal = Path(salida.name)
                json.dump(contenido, salida, ensure_ascii=False, indent=2)
                salida.flush()
                os.fsync(salida.fileno())
            os.replace(temporal, self.archivo_red)
        finally:
            if temporal is not None and temporal.exists():
                temporal.unlink()

    @staticmethod
    def _comprobar_puerto(host, puerto):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prueba:
                if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                    prueba.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                prueba.bind((host, puerto))
        except OSError as error:
            raise ValueError(f'No se puede usar {host}:{puerto}: puerto ocupado o IP no local. {error}') from error

    def siguiente_puerto(self, host='127.0.0.1'):
        ipaddress.IPv4Address(host)
        # Distinguir una IP no local de un rango agotado.
        self._comprobar_puerto(host, 0)
        with self._lock:
            for puerto in range(7000, 8001):
                if puerto in self.nodos:
                    continue
                try:
                    self._comprobar_puerto(host, puerto)
                    return puerto
                except ValueError:
                    continue
        raise ValueError('No hay puertos disponibles entre 7000 y 8000.')

    def vecinos_para(self, identidad):
        c = self.nodos[identidad].configuracion
        direcciones = [('127.0.0.1' if n.configuracion.host == '0.0.0.0' else n.configuracion.host,
                        n.configuracion.puerto) for n in self.nodos.values()
                       if n.configuracion.identidad != c.identidad]
        return tuple(dict.fromkeys(direcciones + list(self._extras[c.identidad])))

    def registrar(self, configuracion):
        with self._lock:
            if configuracion.puerto in self.nodos:
                raise ValueError('El puerto ya pertenece a un nodo del administrador.')
            self._comprobar_puerto(configuracion.host, configuracion.puerto)
            nodo = NodoAdministrado(configuracion)
            self.nodos[configuracion.identidad] = nodo
            self._extras[configuracion.identidad] = configuracion.vecinos
            try:
                self.guardar()
            except OSError:
                del self.nodos[configuracion.identidad]
                del self._extras[configuracion.identidad]
                raise
            self.actualizar_vecinos()
            return nodo

    def crear(self, configuracion):
        with self._lock:
            nodo = self.registrar(configuracion)
            self.iniciar(configuracion.identidad)
            return nodo

    def actualizar_vecinos(self):
        """Solo se muestra aplicada una configuración tras la confirmación del servidor."""
        with self._lock:
            for identidad, nodo in self.nodos.items():
                vecinos = self.vecinos_para(identidad)
                if nodo.proceso is None or nodo.proceso.poll() is not None:
                    nodo.configuracion = replace(nodo.configuracion, vecinos=vecinos)
                    nodo.error_topologia = ''
                    continue
                if nodo.configuracion.vecinos == vecinos and not nodo.error_topologia:
                    continue
                try:
                    estado = self._cliente(nodo).solicitar('CONFIGURAR_VECINOS',
                               {'token': nodo.token, 'nodos': list(vecinos)})
                    reales = tuple(tuple(v) for v in estado['nodos'])
                    if reales != vecinos:
                        raise ValueError('El servidor no confirmó los vecinos solicitados.')
                    nodo.configuracion = replace(nodo.configuracion, vecinos=reales)
                    nodo.error_topologia = ''
                    nodo.eventos.append('Malla actualizada por TCP sin reiniciar el proceso.')
                except (ValueError, OSError) as error:
                    nodo.error_topologia = str(error)
                    nodo.eventos.append(f'Actualización de vecinos pendiente: {error}')

    def iniciar(self, identidad):
        with self._lock:
            nodo = self.nodos[identidad]
            if nodo.proceso is not None and nodo.proceso.poll() is None:
                raise ValueError('El servidor ya está en ejecución.')
            nodo.configuracion = replace(nodo.configuracion, vecinos=self.vecinos_para(identidad))
            self._iniciar(nodo)
            self.actualizar_vecinos()

    def argumentos(self, configuracion):
        args = [sys.executable, '-u', '-m', 'servidor.servidor',
                '--host', configuracion.host, '--puerto', str(configuracion.puerto),
                '--dificultad', str(configuracion.dificultad),
                '--datos', str(self.datos.resolve()), '--clave', str(self.clave.resolve())]
        for host, puerto in configuracion.vecinos:
            args.extend(['--nodo', f'{host}:{puerto}'])
        return args

    def _iniciar(self, nodo):
        c = nodo.configuracion
        self._comprobar_puerto(c.host, c.puerto)
        self.datos.mkdir(parents=True, exist_ok=True)
        # El servidor valida la clave antes de cargar una cadena con incidentes.
        # Nunca generar otra clave aquí si desapareció la original.
        nodo.registro = self.datos / f'nodo_{c.puerto}.log'
        nodo.token = secrets.token_urlsafe(32)
        entorno = os.environ.copy()
        entorno['BLOCKCHAIN_ADMIN_TOKEN'] = nodo.token
        nodo.disponible = False
        with nodo.registro.open('ab') as salida:
            nodo.proceso = subprocess.Popen(
                self.argumentos(c), cwd=RAIZ, stdout=salida, stderr=salida,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env=entorno)
        nodo.eventos.append('Proceso iniciado; esperando respuesta TCP.')
        limite = time.monotonic() + 8
        while time.monotonic() < limite and nodo.proceso.poll() is None:
            try:
                self._cliente(nodo).solicitar('CONFIGURAR_VECINOS',
                                             {'token': nodo.token, 'nodos': list(c.vecinos)})
                nodo.disponible = True
                nodo.error_topologia = ''
                return
            except (OSError, ValueError):
                time.sleep(.05)
        # No dejar un hijo cuyo arranque no se pudo confirmar.
        self.detener(c.identidad)
        nodo.error_topologia = f'No arrancó el servidor; consulta {nodo.registro}.'
        raise ValueError(nodo.error_topologia)

    def reiniciar(self, puerto, configuracion=None):
        nodo = self.nodos[puerto]
        if configuracion is not None:
            if configuracion.identidad != nodo.configuracion.identidad:
                raise ValueError('Al editar conserva la IP y el puerto originales.')
            nodo.configuracion = configuracion
            self._extras[configuracion.identidad] = configuracion.vecinos
            self.guardar()
        self.detener(puerto)
        self.iniciar(puerto)

    def detener(self, puerto):
        nodo = self.nodos[puerto]
        proceso = nodo.proceso
        if proceso is not None:
            if proceso.poll() is None:
                proceso.terminate()
            try:
                proceso.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait(timeout=3)
            nodo.proceso = None
            nodo.disponible = False
            nodo.eventos.append('Proceso detenido; persistencia conservada.')

    def cerrar(self):
        for puerto in list(self.nodos):
            self.detener(puerto)

    def eliminar(self, identidad):
        with self._lock:
            nodo = self.nodos[identidad]
            if nodo.proceso is not None and nodo.proceso.poll() is None:
                raise ValueError('Detén el servidor antes de eliminar su registro.')
            identidad = nodo.configuracion.identidad
            del self.nodos[identidad]
            extras = self._extras.pop(identidad)
            try:
                self.guardar()
            except OSError:
                self.nodos[identidad] = nodo
                self._extras[identidad] = extras
                raise
            self.actualizar_vecinos()

    @staticmethod
    def _cliente(nodo):
        c = nodo.configuracion
        host = '127.0.0.1' if c.host == '0.0.0.0' else c.host
        return Cliente(host, c.puerto, timeout=1)

    def consultar(self, puerto):
        nodo = self.nodos[puerto]
        if nodo.proceso is None or nodo.proceso.poll() is not None:
            raise ValueError('El proceso del nodo está detenido o finalizó.')
        cliente = self._cliente(nodo)
        try:
            resultado = cliente.solicitar('VER_CADENA'), cliente.solicitar('VER_NODOS')
            nodo.disponible = True
            return resultado
        except (OSError, ValueError):
            nodo.disponible = False
            raise
