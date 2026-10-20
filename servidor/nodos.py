"""Difusión y reparación periódica entre pares mediante el mismo cliente TCP."""
import logging
import math
import queue
import threading
import time

from cliente.cliente import Cliente

log = logging.getLogger(__name__)


class RedNodos:
    def __init__(self, servidor, nodos, intervalo=5, timeout=2):
        if (not isinstance(intervalo, (int, float)) or not math.isfinite(intervalo)
                or intervalo <= 0 or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError('Intervalo y timeout de nodos deben ser positivos y finitos.')
        self.servidor = servidor
        self.direccion = servidor.server_address
        self.nodos = []
        for nodo in nodos:
            if (not isinstance(nodo, (list, tuple)) or len(nodo) != 2
                    or not isinstance(nodo[0], str) or not nodo[0]
                    or type(nodo[1]) is not int or not 1 <= nodo[1] <= 65535):
                raise ValueError('Dirección de nodo inválida.')
            direccion = tuple(nodo)
            if direccion != self.direccion and direccion not in self.nodos:
                self.nodos.append(direccion)
        self.intervalo = intervalo
        self.timeout = timeout
        self._cola = queue.Queue()
        self._detenido = threading.Event()
        self._hilo = None
        self._config_lock = threading.Lock()
        self._sync_lock = threading.Lock()
        self.ultimo_resultado = {'actualizada': False, 'errores': []}

    def iniciar(self):
        with self._config_lock:
            if self.nodos and self._hilo is None and not self._detenido.is_set():
                self._hilo = threading.Thread(target=self._trabajar, daemon=True,
                                              name=f'nodos-{self.direccion[1]}')
                self._hilo.start()

    def configurar_vecinos(self, nodos):
        """Reemplaza la colección completa; los recorridos en curso usan su copia previa."""
        if not isinstance(nodos, list):
            raise ValueError('Los vecinos deben ser una lista de direcciones.')
        nuevos = []
        for nodo in nodos:
            if (not isinstance(nodo, (list, tuple)) or len(nodo) != 2
                    or not isinstance(nodo[0], str) or not nodo[0].strip()
                    or type(nodo[1]) is not int or not 1 <= nodo[1] <= 65535):
                raise ValueError('Dirección de nodo inválida.')
            direccion = tuple(nodo)
            if direccion != self.direccion and direccion not in nuevos:
                nuevos.append(direccion)
        with self._config_lock:
            self.nodos = nuevos
        self.iniciar()
        self.pedir_sincronizacion()
        log.info('Vecinos actualizados: %s', nuevos)
        return self.estado()

    def detener(self):
        self._detenido.set()
        self._cola.put(None)
        if self._hilo is not None and self._hilo is not threading.current_thread():
            self._hilo.join(timeout=self.timeout + 1)

    def propagar(self, bloque, origen=None):
        if self.nodos and not self._detenido.is_set():
            self._cola.put(('bloque', bloque, origen))

    def pedir_sincronizacion(self):
        if self.nodos and not self._detenido.is_set():
            self._cola.put(('sincronizar', None, None))

    def _cliente(self, nodo):
        return Cliente(*nodo, timeout=self.timeout, contexto="nodos")

    def sincronizar(self):
        actualizada = False
        errores = []
        # Este candado serializa sincronizaciones, no bloquea las operaciones
        # locales. ServicioBlockchain vuelve a comparar bajo su propio candado.
        with self._sync_lock:
            for nodo in self.nodos:
                if self._detenido.is_set():
                    break
                try:
                    datos = self._cliente(nodo).solicitar('VER_CADENA')
                    if not self._detenido.is_set():
                        actualizada = self.servidor.servicio.adoptar_cadena(datos) or actualizada
                except (OSError, ValueError) as error:
                    errores.append({'nodo': list(nodo), 'error': str(error)})
            self.ultimo_resultado = {'actualizada': actualizada, 'errores': errores}
        if actualizada:
            log.info('Nodo %s sincronizó su cadena y guardó su JSON.', self.direccion[1])
        return self.ultimo_resultado

    def _difundir(self, bloque, origen):
        for nodo in self.nodos:
            if self._detenido.is_set():
                break
            if list(nodo) == origen:
                continue
            try:
                self._cliente(nodo).solicitar('RECIBIR_BLOQUE', {
                    'bloque': bloque, 'origen': list(self.direccion)})
            except (OSError, ValueError) as error:
                # Un vecino apagado o en otra rama no revierte el minado local.
                # La consulta periódica de cadenas repara mensajes perdidos.
                log.debug('No se propagó a %s: %s', nodo, error)

    def _trabajar(self):
        proxima = 0.0
        while not self._detenido.is_set():
            if time.monotonic() >= proxima:
                self.sincronizar()
                proxima = time.monotonic() + self.intervalo
            try:
                evento = self._cola.get(timeout=max(0.01, proxima - time.monotonic()))
            except queue.Empty:
                continue
            if evento is None:
                break
            tipo, bloque, origen = evento
            if tipo == 'bloque':
                self._difundir(bloque, origen)
            else:
                self.sincronizar()

    def estado(self):
        return {'direccion': list(self.direccion),
                'nodos': [list(n) for n in self.nodos],
                'archivo': str(self.servidor.servicio.almacen.ruta),
                'ultima_sincronizacion': self.ultimo_resultado}
