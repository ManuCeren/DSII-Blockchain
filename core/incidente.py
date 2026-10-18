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

    def __repr__(self):
        return f"Incidente({self.id_incidente}, {self.tipo}, severidad={self.severidad}, [datos cifrados])"



