import base64
import binascii
import math
import time

class Incidente:
    def __init__(self, id_incidente, tipo, descripcion, reportado_por, severidad, encriptador):
        self.id_incidente = id_incidente
        self.tipo = tipo
        self.severidad = severidad
        self.timestamp = time.time()
        # descripcion y reportado_por nunca se guardan en texto plano, solo su versión cifrada
        self._descripcion_cifrada = encriptador.encriptar(descripcion)
        self._reportado_por_cifrado = encriptador.encriptar(reportado_por)

    def descripcion(self, encriptador):
        return encriptador.desencriptar(self._descripcion_cifrada)

    def reportado_por(self, encriptador):
        return encriptador.desencriptar(self._reportado_por_cifrado)

    def to_dict(self):
        return {
            "id_incidente": self.id_incidente,
            "tipo": self.tipo,
            "descripcion_cifrada": self._descripcion_cifrada,
            "reportado_por_cifrado": self._reportado_por_cifrado,
            "severidad": self.severidad,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, datos):
        """Reconstruye sin cifrar otra vez ni cambiar el timestamp original."""
        campos = {'id_incidente', 'tipo', 'severidad', 'timestamp',
                  'descripcion_cifrada', 'reportado_por_cifrado'}
        if not isinstance(datos, dict) or set(datos) != campos:
            raise ValueError('Estructura de incidente inválida; solo se permiten campos cifrados.')
        if type(datos['id_incidente']) is not int or datos['id_incidente'] <= 0:
            raise ValueError('ID de incidente inválido.')
        for campo in ('tipo', 'severidad'):
            if not isinstance(datos[campo], str) or not datos[campo].strip():
                raise ValueError(f'{campo} de incidente inválido.')
        validar_timestamp(datos['timestamp'])
        for campo in ('descripcion_cifrada', 'reportado_por_cifrado'):
            validar_token_fernet(datos[campo])
        incidente = cls.__new__(cls)
        incidente.id_incidente = datos['id_incidente']
        incidente.tipo = datos['tipo']
        incidente.severidad = datos['severidad']
        incidente.timestamp = datos['timestamp']
        incidente._descripcion_cifrada = datos['descripcion_cifrada']
        incidente._reportado_por_cifrado = datos['reportado_por_cifrado']
        return incidente

    def __repr__(self):
        return f"Incidente({self.id_incidente}, {self.tipo}, severidad={self.severidad}, [datos cifrados])"


def validar_timestamp(valor):
    if type(valor) not in (int, float) or not 0 <= valor <= 1e20 or not math.isfinite(valor):
        raise ValueError('Timestamp inválido.')


def validar_token_fernet(token):
    # Sin clave solo podemos comprobar la estructura. El servidor también
    # autentica estos tokens con Fernet antes de admitir datos externos.
    if not isinstance(token, str):
        raise ValueError('Token Fernet inválido.')
    try:
        contenido = base64.b64decode(token.encode('ascii'), altchars=b'-_', validate=True)
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise ValueError('Token Fernet inválido.') from error
    if len(contenido) < 73 or contenido[0] != 0x80 or (len(contenido) - 57) % 16:
        raise ValueError('Estructura de token Fernet inválida.')



