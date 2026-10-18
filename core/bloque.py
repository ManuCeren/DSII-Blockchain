import hashlib
import json
import time
from .incidente import Incidente

class Bloque:
    def __init__(self, numero_bloque, hash_anterior):
        self.numero_bloque = numero_bloque
        self.hash_anterior = hash_anterior
        self.transacciones = []
        self.timestamp = time.time()
        self.nonce = 0
        self.hash = None  # se llena hasta que el bloque se mina

    def agregar_transaccion(self, incidente):
        # una vez minado el bloque queda cerrado, ya no se le puede meter nada más
        if self.hash is not None:
            raise ValueError("No se pueden agregar transacciones a un bloque ya minado.")
        if not isinstance(incidente, Incidente):
            raise TypeError("Solo se pueden agregar objetos de tipo Incidente")
        self.transacciones.append(incidente)

    def _contenido_para_hash(self):
        return {
            "numero_bloque": self.numero_bloque,
            "hash_anterior": self.hash_anterior,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "transacciones": [t.to_dict() for t in self.transacciones],
        }

    def calcular_hash(self):
        # SHA-256 sobre el contenido del bloque serializado en JSON
        contenido = json.dumps(self._contenido_para_hash(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(contenido).hexdigest()

    def minar(self, dificultad=4):
        if self.hash is not None:
            raise ValueError("Este bloque ya fue minado y no puede volver a minarse.")

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



