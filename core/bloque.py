import hashlib
import json
import time
from .incidente import Incidente, validar_timestamp


def validar_dificultad(dificultad):
    if type(dificultad) is not int or not 0 <= dificultad <= 8:
        raise ValueError('La dificultad debe ser un entero entre 0 y 8.')


def es_hash(valor):
    return (isinstance(valor, str) and len(valor) == 64
            and all(c in '0123456789abcdef' for c in valor))

class Bloque:
    def __init__(self, numero_bloque, hash_anterior):
        self.numero_bloque = numero_bloque
        self.hash_anterior = hash_anterior
        self.transacciones = []
        self.timestamp = time.time()
        self.nonce = 0
        self.hash = None  # se llena hasta que el bloque se mina
        self.dificultad = None

    def agregar_transaccion(self, incidente):
        # una vez minado el bloque queda cerrado, ya no se le puede meter nada más
        if self.hash is not None:
            raise ValueError("No se pueden agregar transacciones a un bloque ya minado.")
        if not isinstance(incidente, Incidente):
            raise TypeError("Solo se pueden agregar objetos de tipo Incidente")
        self.transacciones.append(incidente)

    def _contenido_para_hash(self):
        contenido = {
            "numero_bloque": self.numero_bloque,
            "hash_anterior": self.hash_anterior,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "transacciones": [t.to_dict() for t in self.transacciones],
        }
        if self.dificultad is not None:
            # La dificultad histórica también queda protegida por SHA-256.
            contenido['dificultad'] = self.dificultad
        return contenido

    def to_dict(self):
        return {**self._contenido_para_hash(), 'hash': self.hash}

    @classmethod
    def from_dict(cls, datos):
        campos = {'numero_bloque', 'hash_anterior', 'timestamp', 'nonce',
                  'hash', 'transacciones', 'dificultad'}
        if not isinstance(datos, dict) or set(datos) != campos:
            raise ValueError('Estructura de bloque inválida.')
        if type(datos['numero_bloque']) is not int or datos['numero_bloque'] < 0:
            raise ValueError('Número de bloque inválido.')
        if type(datos['nonce']) is not int or datos['nonce'] < 0:
            raise ValueError('Nonce inválido.')
        if datos['hash_anterior'] != '0' and not es_hash(datos['hash_anterior']):
            raise ValueError('Hash anterior inválido.')
        if not es_hash(datos['hash']):
            raise ValueError('Hash de bloque inválido.')
        validar_timestamp(datos['timestamp'])
        validar_dificultad(datos['dificultad'])
        if not isinstance(datos['transacciones'], list):
            raise ValueError('Las transacciones deben ser una lista.')
        bloque = cls.__new__(cls)
        for campo in campos - {'transacciones'}:
            setattr(bloque, campo, datos[campo])
        bloque.transacciones = [Incidente.from_dict(t) for t in datos['transacciones']]
        bloque.validar()
        return bloque

    def validar(self):
        if self.hash != self.calcular_hash():
            raise ValueError('El hash no coincide con el contenido del bloque.')
        if not self.hash.startswith('0' * self.dificultad):
            raise ValueError('Proof of Work inválida.')
        return True

    def calcular_hash(self):
        # SHA-256 sobre el contenido del bloque serializado en JSON
        contenido = json.dumps(self._contenido_para_hash(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(contenido).hexdigest()

    def minar(self, dificultad=4):
        if self.hash is not None:
            raise ValueError("Este bloque ya fue minado y no puede volver a minarse.")

        validar_dificultad(dificultad)
        self.dificultad = dificultad

        # Prueba de Trabajo: se prueba nonce tras nonce hasta que el hash empiece con N ceros
        prefijo_requerido = "0" * dificultad
        print(f"Minando bloque #{self.numero_bloque}...")
        inicio = time.time()

        self.hash = self.calcular_hash()
        while not self.hash.startswith(prefijo_requerido):
            self.nonce += 1
            self.hash = self.calcular_hash()

        duracion = time.time() - inicio
        print(f"Bloque #{self.numero_bloque} minado en {duracion:.2f}s (nonce={self.nonce})")
        print(f"Hash: {self.hash}")
        return self.hash

    def __repr__(self):
        return f"Bloque(#{self.numero_bloque}, txns={len(self.transacciones)}, hash={self.hash})"



