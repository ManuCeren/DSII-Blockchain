from .bloque import Bloque

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
        if bloque_propuesto.hash is not None:
            raise ValueError('Este bloque ya fue minado.')
        # enlaza el bloque con el hash del último de la cadena y recién ahí lo mina
        bloque_propuesto.hash_anterior = self.obtener_ultimo_bloque().hash
        bloque_propuesto.minar(self.dificultad)
        self.cadena.append(bloque_propuesto)
        return bloque_propuesto

    def __repr__(self):
        return f"Blockchain({len(self.cadena)} bloques, dificultad={self.dificultad})"



