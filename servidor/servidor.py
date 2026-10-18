"""Servidor TCP de incidentes: estado local, persistencia y enlace con otros nodos."""
import argparse
import logging
from pathlib import Path
import socket
import socketserver
import threading

from cryptography.fernet import InvalidToken

from comunicacion import enviar_json, recibir_json
from core.blockchain import Blockchain
from core.bloque import Bloque, validar_dificultad
from core.incidente import Incidente
from core.encriptador import Encriptador
from servidor.consenso import es_preferible
from servidor.persistencia import AlmacenCadena

RAIZ = Path(__file__).resolve().parents[1]
log = logging.getLogger(__name__)


def serializar_bloque(bloque):
    return bloque.to_dict()


class BloqueDesenlazado(ValueError):
    """Puede ser una rama competidora o indicar que faltan bloques locales."""


class ServicioBlockchain:
    def __init__(self, dificultad=4, archivo_clave=None, archivo_cadena=None):
        self.almacen = AlmacenCadena(archivo_cadena or RAIZ / 'blockchain_7000.json')
        existente = self.almacen.ruta.exists()
        self.bc = self.almacen.cargar() if existente else Blockchain(dificultad)
        ruta_clave = Path(archivo_clave) if archivo_clave is not None else RAIZ / 'clave_secreta.key'
        if any(b.transacciones for b in self.bc.cadena) and not ruta_clave.exists():
            raise ValueError('Falta la clave Fernet de la cadena existente; restaura su clave original.')
        self.encriptador = Encriptador(ruta_clave)
        self._validar_cifrado(self.bc)
        if not existente:
            self.almacen.guardar(self.bc)
        self.bloque_propuesto = None
        self.contador_incidentes = self._maximo_id(self.bc)
        # Las decisiones sobre la cadena y su guardado forman una operación.
        # Ninguna conexión de red saliente se hace bajo este candado.
        self._lock = threading.Lock()

    @staticmethod
    def _maximo_id(bc):
        return max((t.id_incidente for b in bc.cadena for t in b.transacciones), default=0)

    def _validar_cifrado(self, bc):
        try:
            for bloque in bc.cadena:
                for incidente in bloque.transacciones:
                    incidente.descripcion(self.encriptador)
                    incidente.reportado_por(self.encriptador)
        except (InvalidToken, UnicodeError) as error:
            raise ValueError('Los incidentes no se pueden autenticar con la clave Fernet de este nodo.') from error

    def _confirmar(self, candidata, confirmados=()):
        """Primero disco, después memoria: si falla el guardado se conserva el estado."""
        self._validar_cifrado(candidata)
        # La dificultad para el próximo minado es una decisión local del operador.
        # La dificultad histórica viaja dentro de cada bloque y no se modifica.
        candidata.dificultad = self.bc.dificultad
        pendientes = self.bloque_propuesto.transacciones if self.bloque_propuesto else []
        # Si el consenso descarta una rama local, sus incidentes vuelven a la
        # propuesta en vez de desaparecer. Nunca se modifican bloques minados.
        pendientes = [t for b in self.bc.cadena for t in b.transacciones] + pendientes
        firmas = {t._descripcion_cifrada + t._reportado_por_cifrado
                  for b in candidata.cadena for t in b.transacciones}
        recuperados = []
        for incidente in pendientes:
            firma = incidente._descripcion_cifrada + incidente._reportado_por_cifrado
            if incidente not in confirmados and firma not in firmas:
                recuperados.append(Incidente.from_dict(incidente.to_dict()))
                firmas.add(firma)
        self.almacen.guardar(candidata)
        self.bc = candidata
        pendientes = recuperados
        self.contador_incidentes = self._maximo_id(candidata)
        self.bloque_propuesto = None
        if pendientes:
            ultimo = candidata.obtener_ultimo_bloque()
            self.bloque_propuesto = Bloque(ultimo.numero_bloque + 1, ultimo.hash)
            for incidente in pendientes:
                # Solo se renumeran transacciones aún no confirmadas. Las ya
                # minadas permanecen intactas, aunque lleguen desde otro nodo.
                self.contador_incidentes += 1
                incidente.id_incidente = self.contador_incidentes
                self.bloque_propuesto.agregar_transaccion(incidente)

    def ejecutar(self, solicitud):
        with self._lock:
            return self._ejecutar(solicitud)

    def _ejecutar(self, solicitud):
        operacion = solicitud.get('operacion')
        datos = solicitud.get('datos', {})
        if not isinstance(datos, dict):
            raise ValueError('datos debe ser un objeto JSON.')
        if operacion == 'AGREGAR_INCIDENTE':
            campos = ('tipo', 'descripcion', 'reportado_por', 'severidad')
            if any(not isinstance(datos.get(c), str) or not datos[c].strip() for c in campos):
                raise ValueError('Completa tipo, descripción, reportado_por y severidad.')
            incidente = Incidente(self.contador_incidentes + 1,
                                  *(datos[c] for c in campos), self.encriptador)
            if self.bloque_propuesto is None:
                ultimo = self.bc.obtener_ultimo_bloque()
                self.bloque_propuesto = Bloque(ultimo.numero_bloque + 1, ultimo.hash)
            self.bloque_propuesto.agregar_transaccion(incidente)
            self.contador_incidentes += 1
            return incidente.to_dict()
        if operacion == 'MINAR_BLOQUE':
            if self.bloque_propuesto is None or not self.bloque_propuesto.transacciones:
                raise ValueError('Agrega al menos un incidente antes de minar.')
            # Se mina una copia para poder reintentar si falla el disco.
            ultimo = self.bc.obtener_ultimo_bloque()
            bloque = Bloque(ultimo.numero_bloque + 1, ultimo.hash)
            bloque.timestamp = self.bloque_propuesto.timestamp
            bloque.transacciones = list(self.bloque_propuesto.transacciones)
            bloque.minar(self.bc.dificultad)
            candidata = Blockchain.from_dict({
                'dificultad': self.bc.dificultad,
                'cadena': [b.to_dict() for b in self.bc.cadena] + [bloque.to_dict()]})
            self._confirmar(candidata, confirmados=bloque.transacciones)
            return bloque.to_dict()
        if operacion == 'VER_CADENA':
            return self.bc.to_dict()
        if operacion == 'VER_BLOQUE_PROPUESTO':
            return self.bloque_propuesto.to_dict() if self.bloque_propuesto else None
        if operacion == 'CAMBIAR_DIFICULTAD':
            nueva = datos.get('dificultad')
            validar_dificultad(nueva)
            candidata = Blockchain.from_dict(self.bc.to_dict())
            candidata.dificultad = nueva
            self.almacen.guardar(candidata)
            self.bc = candidata
            return {'dificultad': nueva}
        if operacion == 'VER_INCIDENTE':
            for bloque in self.bc.cadena:
                if bloque.numero_bloque == datos.get('numero_bloque'):
                    for incidente in bloque.transacciones:
                        if incidente.id_incidente == datos.get('id_incidente'):
                            return {**incidente.to_dict(),
                                    'descripcion': incidente.descripcion(self.encriptador),
                                    'reportado_por': incidente.reportado_por(self.encriptador)}
            raise ValueError('Incidente no encontrado.')
        if operacion == 'RECIBIR_BLOQUE':
            bloque = Bloque.from_dict(datos.get('bloque'))
            if any(b.hash == bloque.hash for b in self.bc.cadena):
                return {'estado': 'duplicado', 'hash': bloque.hash}
            ultimo = self.bc.obtener_ultimo_bloque()
            if bloque.numero_bloque != ultimo.numero_bloque + 1 or bloque.hash_anterior != ultimo.hash:
                raise BloqueDesenlazado('El bloque no enlaza con el último bloque local; se requiere sincronización.')
            candidata = Blockchain.from_dict({
                'dificultad': self.bc.dificultad,
                'cadena': [b.to_dict() for b in self.bc.cadena] + [bloque.to_dict()]})
            # Se preservan hash, nonce y timestamp: nunca se mina un bloque recibido.
            self._confirmar(candidata)
            return {'estado': 'aceptado', 'hash': bloque.hash}
        raise ValueError('Operación desconocida.')

    def adoptar_cadena(self, datos):
        candidata = Blockchain.from_dict(datos)
        with self._lock:
            if not es_preferible(candidata, self.bc):
                return False
            self._confirmar(candidata)
            return True


class _Manejador(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(30)
        try:
            solicitud = recibir_json(self.rfile)
            resultado = self.server.procesar(solicitud)
            respuesta = {'ok': True, 'resultado': resultado}
        except (ValueError, UnicodeError, OSError, InvalidToken) as error:
            respuesta = {'ok': False, 'error': str(error)}
        try:
            enviar_json(self.wfile, respuesta)
        except (OSError, ValueError):
            pass


class ServidorBlockchain(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    address_family = socket.AF_INET

    def __init__(self, direccion=('127.0.0.1', 7000), dificultad=4, archivo_clave=None,
                 *, nodos=(), directorio_datos=None, intervalo=5, timeout_nodos=2):
        # Puerto 0 (asignado por el SO) se permite en esta API para las pruebas.
        # La CLI valida el rango académico 7000–8000.
        super().__init__(direccion, _Manejador, bind_and_activate=False)
        self.red = None
        try:
            self.server_bind()
            directorio = Path(directorio_datos) if directorio_datos is not None else (
                Path(archivo_clave).resolve().parent if archivo_clave is not None else RAIZ)
            ruta = directorio / f'blockchain_{self.server_address[1]}.json'
            self.servicio = ServicioBlockchain(dificultad, archivo_clave, ruta)
            from servidor.nodos import RedNodos
            self.red = RedNodos(self, nodos, intervalo, timeout_nodos)
            self.server_activate()
        except Exception:
            self.server_close()
            raise

    def procesar(self, solicitud):
        operacion = solicitud.get('operacion')
        if operacion == 'SINCRONIZAR':
            return self.red.sincronizar()
        if operacion == 'VER_NODOS':
            return self.red.estado()
        try:
            resultado = self.servicio.ejecutar(solicitud)
        except BloqueDesenlazado:
            self.red.pedir_sincronizacion()
            raise
        if operacion == 'MINAR_BLOQUE':
            self.red.propagar(resultado)
        elif operacion == 'RECIBIR_BLOQUE' and resultado['estado'] == 'aceptado':
            datos = solicitud['datos']
            self.red.propagar(datos['bloque'], datos.get('origen'))
        return resultado

    def serve_forever(self, poll_interval=0.1):
        self.red.iniciar()
        try:
            super().serve_forever(poll_interval)
        finally:
            self.red.detener()

    def shutdown(self):
        self.red.detener()
        super().shutdown()

    def server_close(self):
        if self.red is not None:
            self.red.detener()
        super().server_close()


def puerto_academico(texto):
    try:
        puerto = int(texto)
    except ValueError as error:
        raise argparse.ArgumentTypeError('El puerto debe ser un entero.') from error
    if not 7000 <= puerto <= 8000:
        raise argparse.ArgumentTypeError('El puerto debe estar entre 7000 y 8000.')
    return puerto


def direccion_nodo(texto):
    host, separador, puerto = texto.rpartition(':')
    if not host or not separador:
        raise argparse.ArgumentTypeError('Usa HOST:PUERTO para cada --nodo.')
    return host, puerto_academico(puerto)


def configurar_argumentos(parser):
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--puerto', type=puerto_academico, default=7000)
    parser.add_argument('--nodo', type=direccion_nodo, action='append', default=[],
                        help='Vecino HOST:PUERTO; se puede repetir.')
    parser.add_argument('--dificultad', type=int, choices=range(9), default=4)
    parser.add_argument('--datos', type=Path, default=RAIZ, help='Directorio de archivos JSON.')
    parser.add_argument('--clave', type=Path, default=RAIZ / 'clave_secreta.key')
    return parser


def ejecutar_desde_argumentos(args):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    with ServidorBlockchain((args.host, args.puerto), args.dificultad, args.clave,
                            nodos=args.nodo, directorio_datos=args.datos) as servidor:
        log.info('Nodo TCP %s:%s; persistencia: %s', *servidor.server_address,
                 servidor.servicio.almacen.ruta)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass


def main(argv=None):
    parser = configurar_argumentos(argparse.ArgumentParser(description=__doc__))
    args = parser.parse_args(argv)
    try:
        ejecutar_desde_argumentos(args)
    except (ValueError, OSError) as error:
        parser.exit(1, f'No se pudo iniciar el nodo: {error}\n')


if __name__ == '__main__':
    main()
