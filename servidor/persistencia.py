"""Bloques Fernet inmutables e índice atómico de la rama confirmada."""
import json
import os
from pathlib import Path
import tempfile
from cryptography.fernet import InvalidToken
from comunicacion import cargar_clave
from core.blockchain import Blockchain
from core.bloque import es_hash


class AlmacenCadena:
    def __init__(self, ruta):
        ruta = Path(ruta)
        # Aceptar tanto la entrada histórica como el índice canónico mostrado por el nodo.
        if ruta.name == 'indice.json' and ruta.parent.name.startswith('nodo_'):
            self.directorio = ruta.parent
            identidad = self.directorio.name.removeprefix('nodo_')
            self.ruta_anterior = self.directorio.parent / ('blockchain_' + identidad + '.json')
        else:
            self.ruta_anterior = ruta
            identidad = ruta.stem.removeprefix('blockchain_')
            self.directorio = ruta.parent / ('nodo_' + identidad)
        self.ruta = self.directorio / 'indice.json'
        self.respaldo_anterior = self.ruta_anterior.with_suffix('.v1.bak')
        self.bloques = self.directorio / 'bloques'
        self.ruta_clave = self.directorio / 'persistencia.key'

    @property
    def origen(self):
        # Un índice canónico existente siempre manda, incluso si está corrupto.
        # Nunca ocultar corrupción recurriendo silenciosamente a una copia vieja.
        for ruta in (self.ruta, self.ruta_anterior):
            if ruta.exists():
                return ruta
        if self.bloques.exists() and self.respaldo_anterior.exists():
            return self.respaldo_anterior
        return None

    @staticmethod
    def _leer(ruta):
        with ruta.open(encoding='utf-8') as archivo:
            return json.load(archivo)

    def _descifrar(self, ruta, cifrador):
        datos = self._leer(ruta)
        if not isinstance(datos, dict) or set(datos) != {'version', 'cifrado'} or datos['version'] != 1:
            raise ValueError('Formato de bloque cifrado desconocido.')
        try:
            bloque = json.loads(cifrador.decrypt(datos['cifrado'].encode('ascii')).decode('utf-8'))
        except (InvalidToken, UnicodeError, TypeError, AttributeError) as error:
            raise ValueError('Bloque persistido no autenticado con su clave Fernet.') from error
        if not isinstance(bloque, dict) or bloque.get('hash') != ruta.stem:
            raise ValueError('El nombre del archivo no coincide con el hash del bloque.')
        return bloque

    def cargar(self):
        origen = self.origen
        if origen is None:
            raise ValueError('Falta el índice de la cadena: ' + str(self.ruta))
        datos = self._leer(origen)
        if not isinstance(datos, dict) or type(datos.get('version')) is not int:
            raise ValueError('Formato de persistencia desconocido.')
        if datos['version'] == 1:
            if set(datos) != {'version', 'dificultad', 'cadena'}:
                raise ValueError('Formato de persistencia desconocido.')
            bc = Blockchain.from_dict({'dificultad': datos['dificultad'], 'cadena': datos['cadena']})
            if origen == self.respaldo_anterior:
                # El respaldo v1 puede ser anterior a nuevos minados o reorganizaciones.
                # Solo recuperarlo si identifica exactamente los archivos disponibles.
                esperados = {b.hash + '.json' for b in bc.cadena}
                disponibles = {p.name for p in self.bloques.glob('*.json')}
                if disponibles != esperados:
                    raise ValueError('El respaldo v1 no identifica todos los bloques actuales; '
                                     'restaura el índice de la rama activa. Se conservan los archivos.')
                cifrador = cargar_clave(self.ruta_clave, crear=False)
                for bloque in bc.cadena:
                    if self._descifrar(self.bloques / (bloque.hash + '.json'), cifrador) != bloque.to_dict():
                        raise ValueError('El respaldo v1 no coincide con los bloques cifrados.')
            return bc
        if datos['version'] != 2 or set(datos) != {'version', 'dificultad', 'bloques'}:
            raise ValueError('Formato de persistencia desconocido.')
        hashes = datos['bloques']
        if not isinstance(hashes, list) or not hashes or any(not es_hash(h) for h in hashes):
            raise ValueError('Índice de bloques inválido.')
        cifrador = cargar_clave(self.ruta_clave, crear=False)
        return Blockchain.from_dict({'dificultad': datos['dificultad'], 'cadena': [
            self._descifrar(self.bloques / (h + '.json'), cifrador) for h in hashes]})

    @staticmethod
    def _atomico(ruta, datos, exclusivo=False):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=ruta.parent,
                                             prefix=ruta.name + '.', suffix='.tmp', delete=False) as archivo:
                temporal = Path(archivo.name)
                json.dump(datos, archivo, ensure_ascii=False, allow_nan=False, indent=2)
                archivo.flush()
                os.fsync(archivo.fileno())
            if exclusivo:
                os.link(temporal, ruta)
            else:
                os.replace(temporal, ruta)
        finally:
            if temporal is not None:
                temporal.unlink(missing_ok=True)

    def guardar(self, bc):
        bc.validar_cadena()
        cifrador = cargar_clave(self.ruta_clave, crear=not self.bloques.exists())
        for bloque in bc.cadena:
            datos = bloque.to_dict()
            ruta = self.bloques / (bloque.hash + '.json')
            if not ruta.exists():
                token = cifrador.encrypt(json.dumps(datos, ensure_ascii=False, allow_nan=False).encode('utf-8'))
                try:
                    self._atomico(ruta, {'version': 1, 'cifrado': token.decode('ascii')}, exclusivo=True)
                except FileExistsError:
                    pass
            if self._descifrar(ruta, cifrador) != datos:
                raise ValueError('Conflicto: ya existe contenido diferente para el hash del bloque.')
        indice = {'version': 2, 'dificultad': bc.dificultad,
                  'bloques': [b.hash for b in bc.cadena]}
        # Migración segura: conservar copia íntegra del formato anterior antes del cambio.
        if not self.ruta.exists() and self.ruta_anterior.exists() and self._leer(self.ruta_anterior).get('version') == 1:
            copia = self.respaldo_anterior
            anterior = self._leer(self.ruta_anterior)
            if copia.exists():
                if self._leer(copia) != anterior:
                    raise ValueError('La copia de migración ya existe con contenido diferente.')
            else:
                self._atomico(copia, anterior, exclusivo=True)
        self._atomico(self.ruta, indice)
