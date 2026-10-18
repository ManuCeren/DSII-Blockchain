from .bloque import Bloque, validar_dificultad

class Blockchain:
    def __init__(self, dificultad=4):
        validar_dificultad(dificultad)
        self.dificultad = dificultad
        self.cadena = []
        self._crear_bloque_genesis()

    def _crear_bloque_genesis(self):
        # primer bloque de la cadena, no tiene bloque anterior (hash_anterior = "0")
        genesis = Bloque(numero_bloque=0, hash_anterior="0")
        # Mismo contenido + misma dificultad inicial = mismo Génesis en la red.
        # Solo se crea al fundar una cadena; cargar JSON no llama al constructor.
        genesis.timestamp = 0
        genesis.minar(self.dificultad)
        self.cadena.append(genesis)

    def obtener_ultimo_bloque(self):
        return self.cadena[-1]

    def agregar_bloque(self, bloque_propuesto):
        if bloque_propuesto.hash is not None:
            raise ValueError('Este bloque ya fue minado.')
        # enlaza el bloque con el hash del último de la cadena y recién ahí lo mina
        bloque_propuesto.hash_anterior = self.obtener_ultimo_bloque().hash
        bloque_propuesto.minar(self.dificultad)
        self.cadena.append(bloque_propuesto)
        return bloque_propuesto

    def to_dict(self):
        return {'dificultad': self.dificultad,
                'cadena': [b.to_dict() for b in self.cadena]}

    @classmethod
    def from_dict(cls, datos):
        if not isinstance(datos, dict) or set(datos) != {'dificultad', 'cadena'}:
            raise ValueError('Estructura de Blockchain inválida.')
        validar_dificultad(datos['dificultad'])
        if not isinstance(datos['cadena'], list) or not datos['cadena']:
            raise ValueError('La cadena debe contener un Génesis.')
        # No se llama __init__: nunca se mina de nuevo un bloque cargado.
        bc = cls.__new__(cls)
        bc.dificultad = datos['dificultad']
        bc.cadena = [Bloque.from_dict(b) for b in datos['cadena']]
        bc.validar_cadena()
        return bc

    def validar_cadena(self):
        """Devuelve True si es válida; explica la primera infracción con ValueError."""
        validar_dificultad(self.dificultad)
        if not self.cadena:
            raise ValueError('Falta el Génesis.')
        ids = set()
        hashes = set()
        anterior = '0'
        for numero, original in enumerate(self.cadena):
            # Validar la representación también detecta alteraciones de tipos,
            # campos y transacciones en objetos que ya estaban en memoria.
            bloque = Bloque.from_dict(original.to_dict())
            if bloque.numero_bloque != numero or bloque.hash_anterior != anterior:
                raise ValueError('Secuencia o encadenamiento inválido.')
            if numero == 0:
                if bloque.transacciones or bloque.timestamp != 0:
                    raise ValueError('Génesis incoherente.')
            elif not bloque.transacciones:
                raise ValueError('Un bloque de incidentes no puede estar vacío.')
            if bloque.hash in hashes:
                raise ValueError('Hash de bloque duplicado.')
            hashes.add(bloque.hash)
            for incidente in bloque.transacciones:
                if incidente.id_incidente in ids:
                    raise ValueError('ID de incidente duplicado en la cadena.')
                ids.add(incidente.id_incidente)
            anterior = bloque.hash
        return True

    def __repr__(self):
        return f"Blockchain({len(self.cadena)} bloques, dificultad={self.dificultad})"



