"""Arranque: python main.py [gui|servidor|consola]."""
import sys


def main(argv=None):
    argumentos = list(sys.argv[1:] if argv is None else argv)
    modo = argumentos.pop(0) if argumentos and argumentos[0] in ('gui', 'servidor', 'consola') else 'gui'
    if modo == 'servidor':
        from servidor.servidor import main as iniciar
    elif modo == 'consola':
        from blockchain_incidentes import main as iniciar
    else:
        from interfaz.gui_incidentes import main as iniciar
    iniciar(argumentos)


if __name__ == '__main__':
    main()
