from core.bloque import Bloque
from core.blockchain import Blockchain
from core.incidente import Incidente
from core.encriptador import Encriptador

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
    """Conserva el menú original; todas las operaciones se envían al servidor."""
    import json
    from cliente.cliente import Cliente
    cliente = Cliente()
    while True:
        opcion = mostrar_menu()
        try:
            if opcion == "1":
                estado = cliente.solicitar("VER_CADENA")
                print(json.dumps(estado, indent=2, ensure_ascii=False))
                for bloque in estado["cadena"]:
                    for incidente in bloque["transacciones"]:
                        print(cliente.solicitar("VER_INCIDENTE", {
                            "numero_bloque": bloque["numero_bloque"],
                            "id_incidente": incidente["id_incidente"]}))
            elif opcion == "2":
                print(cliente.solicitar("VER_BLOQUE_PROPUESTO"))
            elif opcion == "3":
                print(cliente.solicitar("AGREGAR_INCIDENTE", {
                    "tipo": input("Tipo de incidente: ").strip(),
                    "descripcion": input("Descripción: ").strip(),
                    "reportado_por": input("Reportado por: ").strip(),
                    "severidad": input("Severidad (Baja/Media/Alta/Critica): ").strip(),
                }))
            elif opcion == "4":
                print(cliente.solicitar("MINAR_BLOQUE"))
            elif opcion == "5":
                nueva = int(input("Nueva dificultad (0-8): ").strip())
                print(cliente.solicitar("CAMBIAR_DIFICULTAD", {"dificultad": nueva}))
            elif opcion == "6":
                print("Saliendo...")
                break
            else:
                print("Opción no válida, intenta de nuevo.")
        except (OSError, ValueError) as error:
            print(f"Error: {error}")


if __name__ == "__main__":
    main()
