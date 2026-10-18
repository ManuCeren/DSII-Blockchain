import os
from pathlib import Path
from cryptography.fernet import Fernet

class Encriptador:
    # Maneja la llave simétrica (Fernet/AES) usada para cifrar los datos sensibles de cada incidente
    def __init__(self, archivo_clave=None):
        self.archivo_clave = archivo_clave if archivo_clave is not None else Path(__file__).resolve().parents[1] / "clave_secreta.key"
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



