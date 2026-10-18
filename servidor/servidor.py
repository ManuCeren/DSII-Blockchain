"""El servidor es el único dueño del estado de negocio y de la clave Fernet."""
import socket
import socketserver
import threading

from comunicacion import enviar_json, recibir_json
from core.blockchain import Blockchain
from core.bloque import Bloque
from core.incidente import Incidente
from core.encriptador import Encriptador


def serializar_bloque(bloque):
    # Se envían copias JSON, nunca referencias a objetos del servidor.
    return {**bloque._contenido_para_hash(), 'hash': bloque.hash}


class ServicioBlockchain:
    def __init__(self, dificultad=4, archivo_clave=None):
        self.encriptador = Encriptador(archivo_clave)
        self.bc = Blockchain(dificultad)
        self.bloque_propuesto = None
        self.contador_incidentes = 0
        # Una operación completa es atómica incluso si llegan varios clientes.
        # Por ahora el minado mantiene este candado: priorizamos consistencia.
        self._lock = threading.Lock()

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
            bloque = self.bc.agregar_bloque(self.bloque_propuesto)
            self.bloque_propuesto = None
            return serializar_bloque(bloque)
        if operacion == 'VER_CADENA':
            return {'cadena': [serializar_bloque(b) for b in self.bc.cadena],
                    'dificultad': self.bc.dificultad}
        if operacion == 'VER_BLOQUE_PROPUESTO':
            return serializar_bloque(self.bloque_propuesto) if self.bloque_propuesto else None
        if operacion == 'CAMBIAR_DIFICULTAD':
            nueva = datos.get('dificultad')
            if type(nueva) is not int or not 0 <= nueva <= 8:
                raise ValueError('La dificultad debe ser un entero entre 0 y 8.')
            self.bc.dificultad = nueva
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
        raise ValueError('Operación desconocida.')


class _Manejador(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(30)
        try:
            solicitud = recibir_json(self.rfile)
            resultado = self.server.servicio.ejecutar(solicitud)
            respuesta = {'ok': True, 'resultado': resultado}
        except (ValueError, UnicodeError, ConnectionError, socket.timeout) as error:
            respuesta = {'ok': False, 'error': str(error)}
        try:
            enviar_json(self.wfile, respuesta)
        except (OSError, ValueError):
            # Desconectar un cliente no debe detener el servidor.
            pass


class ServidorBlockchain(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    address_family = socket.AF_INET

    def __init__(self, direccion=('127.0.0.1', 5000), dificultad=4, archivo_clave=None):
        self.servicio = ServicioBlockchain(dificultad, archivo_clave)
        super().__init__(direccion, _Manejador)


def main():
    with ServidorBlockchain() as servidor:
        print('Servidor TCP escuchando en 127.0.0.1:5000')
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
