"""
Módulo de Bloque, Minado y Encriptación (Servidor)
Blockchain para Registro de Incidentes de Seguridad Informática
"""

import hashlib
import json
import os
import time

from cryptography.fernet import Fernet


class Encriptador:
    # Maneja la llave simétrica (Fernet/AES) usada para cifrar los datos sensibles de cada incidente
    def __init__(self, archivo_clave="clave_secreta.key"):
        self.archivo_clave = archivo_clave
        self.clave = self._cargar_o_generar_clave()
        self._fernet = Fernet(self.clave)

    def _cargar_o_generar_clave(self):
        # Si ya existe una llave guardada la reutiliza, si no genera una nueva y la persiste en disco
        if os.path.exists(self.archivo_clave):
            with open(self.archivo_clave, "rb") as f:
                return f.read()
        clave = Fernet.generate_key()
        with open(self.archivo_clave, "wb") as f:
            f.write(clave)
        return clave

    def encriptar(self, texto_plano):
        return self._fernet.encrypt(texto_plano.encode("utf-8")).decode("utf-8")

    def desencriptar(self, texto_cifrado):
        return self._fernet.decrypt(texto_cifrado.encode("utf-8")).decode("utf-8")


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


class Blockchain:
    def __init__(self, dificultad=4):
        self.dificultad = dificultad
        self.cadena = []
        self._crear_bloque_genesis()

    def _crear_bloque_genesis(self):
        # primer bloque de la cadena, no tiene bloque anterior (hash_anterior = "0")
        genesis = Bloque(numero_bloque=0, hash_anterior="0")
        genesis.minar(self.dificultad)
        self.cadena.append(genesis)

    def obtener_ultimo_bloque(self):
        return self.cadena[-1]

    def agregar_bloque(self, bloque_propuesto):
        # enlaza el bloque con el hash del último de la cadena y recién ahí lo mina
        bloque_propuesto.hash_anterior = self.obtener_ultimo_bloque().hash
        bloque_propuesto.minar(self.dificultad)
        self.cadena.append(bloque_propuesto)
        return bloque_propuesto

    def __repr__(self):
        return f"Blockchain({len(self.cadena)} bloques, dificultad={self.dificultad})"


# ------------------- Interfaz de consola -------------------

def mostrar_menu():
    print("\n===== MENÚ - Blockchain de Incidentes =====")
    print("1. Ver cadena completa")
    print("2. Ver bloque propuesto (aún sin minar)")
    print("3. Agregar incidente al bloque propuesto")
    print("4. Minar y agregar el bloque propuesto a la cadena")
    print("5. Cambiar dificultad de minado")
    print("6. Salir")
    return input("Elige una opción: ").strip()


def pedir_incidente(siguiente_id, encriptador):
    print("\n--- Nuevo incidente ---")
    tipo = input("Tipo de incidente (ej. Malware, Acceso no autorizado): ").strip()
    descripcion = input("Descripción: ").strip()
    reportado_por = input("Reportado por: ").strip()
    severidad = input("Severidad (Baja/Media/Alta/Critica): ").strip()
    return Incidente(siguiente_id, tipo, descripcion, reportado_por, severidad, encriptador)


def imprimir_cadena(bc, encriptador):
    print(f"\n--- Cadena actual ({len(bc.cadena)} bloques) ---")
    for b in bc.cadena:
        print(b)
        for t in b.transacciones:
            print(f"    {t}")
            print(f"        Descripción: {t.descripcion(encriptador)}")
            print(f"        Reportado por: {t.reportado_por(encriptador)}")


def main():
    encriptador = Encriptador()
    bc = Blockchain(dificultad=4)
    contador_incidentes = 0
    bloque_propuesto = None

    print("\nBlockchain de incidentes lista. Bloque génesis minado.")

    while True:
        opcion = mostrar_menu()

        if opcion == "1":
            imprimir_cadena(bc, encriptador)

        elif opcion == "2":
            if bloque_propuesto is None:
                print("\nNo hay ningún bloque propuesto todavía. Agrega un incidente (opción 3) para crear uno.")
            else:
                print(f"\nBloque propuesto #{bloque_propuesto.numero_bloque} "
                      f"con {len(bloque_propuesto.transacciones)} incidente(s):")
                for t in bloque_propuesto.transacciones:
                    print(f"    {t}")

        elif opcion == "3":
            if bloque_propuesto is None:
                bloque_propuesto = Bloque(
                    numero_bloque=bc.obtener_ultimo_bloque().numero_bloque + 1,
                    hash_anterior=bc.obtener_ultimo_bloque().hash,
                )
            contador_incidentes += 1
            incidente = pedir_incidente(contador_incidentes, encriptador)
            bloque_propuesto.agregar_transaccion(incidente)
            print(f"Incidente agregado al bloque propuesto #{bloque_propuesto.numero_bloque}.")

        elif opcion == "4":
            if bloque_propuesto is None or len(bloque_propuesto.transacciones) == 0:
                print("\nNo puedes minar un bloque sin incidentes. Agrega al menos uno (opción 3).")
            else:
                bc.agregar_bloque(bloque_propuesto)
                print(f"Bloque #{bloque_propuesto.numero_bloque} agregado a la cadena.")
                bloque_propuesto = None

        elif opcion == "5":
            try:
                nueva_dificultad = int(input("Nueva dificultad (número de ceros, ej. 4): ").strip())
                if nueva_dificultad < 0:
                    raise ValueError
                bc.dificultad = nueva_dificultad
                print(f"Dificultad actualizada a {nueva_dificultad}.")
            except ValueError:
                print("Valor inválido. Debe ser un número entero positivo.")

        elif opcion == "6":
            print("Saliendo...")
            break

        else:
            print("Opción no válida, intenta de nuevo.")


if __name__ == "__main__":
    main()