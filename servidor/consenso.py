"""Regla académica explícita; no implementa consenso de Bitcoin ni finalidad."""


def trabajo_acumulado(bc):
    # Con N ceros hexadecimales la búsqueda requiere en promedio 16**N intentos.
    # Nunca se confunde una cadena larga de dificultad 0 con más trabajo real.
    return sum(16 ** bloque.dificultad for bloque in bc.cadena)


def es_preferible(candidata, local):
    candidata.validar_cadena()
    local.validar_cadena()
    if candidata.cadena[0].hash != local.cadena[0].hash:
        raise ValueError('Génesis incompatible: estos nodos no pertenecen a la misma red.')
    # Desempate determinista para que dos ramas de igual trabajo puedan converger.
    # Es una convención didáctica, no una garantía contra ataques a la red.
    def puntaje(bc):
        return trabajo_acumulado(bc), -int(bc.obtener_ultimo_bloque().hash, 16)
    return puntaje(candidata) > puntaje(local)
