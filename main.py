"""Arranque: python main.py [gui|servidor|consola]."""
import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('modo', nargs='?', default='gui', choices=('gui', 'servidor', 'consola'))
    modo = parser.parse_args().modo
    if modo == 'servidor':
        from servidor.servidor import main as iniciar
    elif modo == 'consola':
        from blockchain_incidentes import main as iniciar
    else:
        from interfaz.gui_incidentes import main as iniciar
    iniciar()


if __name__ == '__main__':
    main()
