"""Un archivo por nodo; reemplazo atómico para no dejar JSON escrito a medias."""
import json
import os
from pathlib import Path
import tempfile

from core.blockchain import Blockchain


class AlmacenCadena:
    def __init__(self, ruta):
        self.ruta = Path(ruta)

    def cargar(self):
        with self.ruta.open(encoding='utf-8') as archivo:
            datos = json.load(archivo)
        if (not isinstance(datos, dict) or set(datos) != {'version', 'dificultad', 'cadena'}
                or type(datos['version']) is not int or datos['version'] != 1):
            raise ValueError('Formato de persistencia desconocido.')
        return Blockchain.from_dict({'dificultad': datos['dificultad'], 'cadena': datos['cadena']})

    def guardar(self, bc):
        bc.validar_cadena()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=self.ruta.parent,
                                             prefix=self.ruta.name + '.', suffix='.tmp',
                                             delete=False) as archivo:
                temporal = Path(archivo.name)
                json.dump({'version': 1, **bc.to_dict()}, archivo,
                          ensure_ascii=False, allow_nan=False, indent=2)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, self.ruta)
        finally:
            if temporal is not None and temporal.exists():
                temporal.unlink()
