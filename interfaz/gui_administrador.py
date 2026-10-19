"""Administrador Tkinter de N procesos TCP independientes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import queue
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

from administracion.nodos import AdministradorNodos, ConfiguracionNodo, RAIZ
from cliente.cliente import Cliente


class VentanaNodo(tk.Toplevel):
    def __init__(self, app, puerto):
        super().__init__(app)
        self.app, self.puerto = app, puerto
        self.title(f'Nodo Blockchain - {app.gestor.nodos[puerto].configuracion.nombre}')
        self.geometry('850x720')
        self.resumen = ttk.Label(self, padding=10, wraplength=810, justify='left')
        self.resumen.pack(fill='x')
        self.arbol = ttk.Treeview(self, columns=('hash',), height=9)
        self.arbol.heading('#0', text='Bloque / Incidente')
        self.arbol.heading('hash', text='Hash / Tipo')
        self.arbol.pack(fill='both', expand=True, padx=10)
        scroll = ttk.Scrollbar(self, command=self.arbol.yview)
        scroll.pack(side='right', fill='y')
        self.arbol.configure(yscrollcommand=scroll.set)
        self.arbol.bind('<<TreeviewSelect>>', self.detalle)
        self.texto = tk.Text(self, height=9, wrap='word', state='disabled')
        self.texto.pack(fill='both', expand=True, padx=10, pady=5)
        ttk.Label(self, text='Actividad del nodo (consultas y registro del servidor)').pack(anchor='w', padx=10)
        self.actividad = tk.Text(self, height=7, state='disabled', wrap='word')
        self.actividad.pack(fill='both', padx=10, pady=5)
        self.items = {}
        self.firma = None

    @staticmethod
    def escribir(widget, texto):
        if not widget.winfo_exists():
            return
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', texto)
        widget.configure(state='disabled')

    def actualizar(self, resultado=None, error=None):
        nodo = self.app.gestor.nodos[self.puerto]
        c = nodo.configuracion
        cabecera = f'{c.nombre}\nIP: {c.host}    Puerto: {c.puerto}    Estado: {nodo.estado}\n'
        vecinos = resultado[1]['nodos'] if resultado else c.vecinos
        cabecera += ('Vecinos actuales: ' if resultado else 'Vecinos configurados (sin consulta actual): ') + (', '.join(f'{h}:{p}' for h, p in vecinos) or 'ninguno')
        if nodo.error_topologia:
            cabecera += f'\nConfiguración pendiente/error: {nodo.error_topologia}'
        if resultado:
            cadena, red = resultado
            ultimo = cadena['cadena'][-1]
            cabecera += (f"\nTCP: disponible | Bloques: {len(cadena['cadena'])} | Dificultad: {cadena['dificultad']}"
                         f" | Último bloque: {ultimo['numero_bloque']}\nÚltimo hash: {ultimo['hash']}"
                         f"\nÚltima sincronización: {json.dumps(red['ultima_sincronizacion'], ensure_ascii=False)}")
            firma = json.dumps(resultado, sort_keys=True)
            if firma != self.firma:
                nodo.eventos.append('Estado TCP actualizado: cadena y última sincronización consultadas.')
                self.firma = firma
            # Conservar la selección y el detalle mientras la cadena no cambie.
            if getattr(self, 'cadena', None) != cadena:
                self.cadena = cadena
                self.arbol.delete(*self.arbol.get_children())
                self.items.clear()
                for b in cadena['cadena']:
                    item = self.arbol.insert('', 'end', text=f"Bloque #{b['numero_bloque']}", values=(b['hash'],))
                    self.items[item] = ('bloque', b)
                    for t in b['transacciones']:
                        hijo = self.arbol.insert(item, 'end', text=f"Incidente #{t['id_incidente']}", values=(t['tipo'],))
                        self.items[hijo] = ('incidente', (b['numero_bloque'], t['id_incidente']))
        elif error:
            cabecera += f'\nTCP: no disponible ({error})'
        self.resumen.configure(text=cabecera)
        registro = ''
        if nodo.registro and nodo.registro.exists():
            with nodo.registro.open('rb') as archivo:
                archivo.seek(max(0, nodo.registro.stat().st_size - 8000))
                registro = archivo.read().decode('utf-8', errors='replace')
        self.escribir(self.actividad, '\n'.join(nodo.eventos[-30:]) + '\n' + registro)

    def detalle(self, _evento):
        seleccion = self.arbol.selection()
        if not seleccion:
            return
        tipo, datos = self.items[seleccion[0]]
        if tipo == 'bloque':
            self.escribir(self.texto, json.dumps({k: v for k, v in datos.items() if k != 'transacciones'}, indent=2)
                          + f"\nCantidad de incidentes: {len(datos['transacciones'])}")
        else:
            c = self.app.gestor.nodos[self.puerto].configuracion
            host = '127.0.0.1' if c.host == '0.0.0.0' else c.host
            self.app.trabajar(lambda: Cliente(host, c.puerto, timeout=2).solicitar('VER_INCIDENTE',
                              {'numero_bloque': datos[0], 'id_incidente': datos[1]}),
                              lambda valor: self.escribir(self.texto, str(valor) if isinstance(valor, Exception)
                                                         else json.dumps(valor, indent=2, ensure_ascii=False)))


class AppAdministrador(tk.Tk):
    def __init__(self, gestor=None):
        super().__init__()
        self.title('Blockchain de Incidentes - Administrador de Red')
        self.geometry('1000x680')
        self.gestor = gestor or AdministradorNodos()
        self.ventanas = {}
        self.clientes = []
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.cola = queue.Queue()
        self.ocupados = set()
        self.cerrando = False
        self.protocol('WM_DELETE_WINDOW', self.cerrar)
        formulario = ttk.LabelFrame(self, text='Configuración de nodo local', padding=10)
        formulario.pack(fill='x', padx=10, pady=10)
        self.campos = {}
        for fila, (etiqueta, valor) in enumerate([('Nombre/Ubicación', 'Nodo 1'), ('IP', '127.0.0.1'), ('Puerto', '7000'), ('Dificultad', '4')]):
            ttk.Label(formulario, text=etiqueta).grid(row=fila, column=0, sticky='w')
            campo = ttk.Entry(formulario, width=35)
            campo.insert(0, valor)
            campo.grid(row=fila, column=1, sticky='ew', padx=5, pady=2)
            self.campos[etiqueta] = campo
        ttk.Button(formulario, text='Crear servidor', command=self.crear).grid(row=4, column=1, pady=8)
        ttk.Button(formulario, text='Buscar siguiente puerto', command=self.sugerir_puerto).grid(row=2, column=2, padx=10)
        informacion = ttk.Frame(self)
        informacion.pack(fill='x', padx=10)
        ttk.Label(informacion, text='Malla completa automática. El registro se recupera con los servidores detenidos.').pack(side='left')
        ttk.Button(informacion, text='Reintentar conexiones', command=lambda: self.accion(self.gestor.actualizar_vecinos)).pack(side='right')
        self.tabla = ttk.Treeview(self, columns=('nombre', 'ip', 'puerto', 'estado'), show='headings')
        for columna in self.tabla['columns']:
            self.tabla.heading(columna, text=columna.capitalize())
        self.tabla.pack(fill='both', expand=True, padx=10, pady=5)
        scroll = ttk.Scrollbar(self, command=self.tabla.yview)
        scroll.pack(side='right', fill='y')
        self.tabla.configure(yscrollcommand=scroll.set)
        acciones = ttk.Frame(self, padding=10)
        acciones.pack(fill='x')
        for texto, funcion in [('Ver nodo', self.abrir), ('Iniciar servidor', self.iniciar), ('Detener servidor', self.detener), ('Reiniciar servidor', self.reiniciar), ('Eliminar nodo', self.eliminar), ('Abrir cliente de incidentes', self.cliente)]:
            ttk.Button(acciones, text=texto, command=funcion).pack(side='left', padx=3)
        self.sincronizar_tabla()
        self.campos['Nombre/Ubicación'].delete(0, 'end')
        self.campos['Nombre/Ubicación'].insert(0, f'Nodo {len(self.gestor.nodos) + 1}')
        self.sugerir_puerto(silencioso=True)
        self._ciclo_id = self.after(100, self.ciclo)

    def trabajar(self, funcion, callback):
        futuro = self.executor.submit(funcion)
        futuro.add_done_callback(lambda f: self.cola.put((f, callback)))

    def configuracion(self):
        return ConfiguracionNodo(self.campos['Nombre/Ubicación'].get().strip(), self.campos['IP'].get().strip(),
                                 self.campos['Puerto'].get().strip(),
                                 dificultad=int(self.campos['Dificultad'].get()))

    def sugerir_puerto(self, silencioso=False):
        try:
            puerto = self.gestor.siguiente_puerto(self.campos['IP'].get().strip())
            self.campos['Puerto'].delete(0, 'end')
            self.campos['Puerto'].insert(0, str(puerto))
        except ValueError as error:
            if not silencioso:
                messagebox.showerror('Puerto no disponible', str(error), parent=self)

    def sincronizar_tabla(self):
        puertos = {str(n.configuracion.puerto) for n in self.gestor.nodos.values()}
        for item in self.tabla.get_children():
            if item not in puertos:
                self.tabla.delete(item)
        for nodo in list(self.gestor.nodos.values()):
            c = nodo.configuracion
            valores = (c.nombre, c.host, c.puerto, nodo.estado)
            if self.tabla.exists(str(c.puerto)):
                self.tabla.item(str(c.puerto), values=valores)
            else:
                self.tabla.insert('', 'end', iid=str(c.puerto), values=valores)

    def crear(self):
        try:
            nodo = self.gestor.crear(self.configuracion())
            p = nodo.configuracion.puerto
            self.sincronizar_tabla()
            self.tabla.selection_set(str(p))
            self.abrir()
            nombre = self.campos['Nombre/Ubicación']
            nombre.delete(0, 'end')
            nombre.insert(0, f'Nodo {len(self.gestor.nodos) + 1}')
            self.sugerir_puerto(silencioso=True)
        except (ValueError, OSError, argparse.ArgumentTypeError) as error:
            self.sincronizar_tabla()
            messagebox.showerror('No se pudo crear el servidor', str(error), parent=self)

    def seleccionado(self):
        seleccion = self.tabla.selection()
        return int(seleccion[0]) if seleccion else None

    def abrir(self):
        p = self.seleccionado()
        if p is not None:
            if p not in self.ventanas or not self.ventanas[p].winfo_exists():
                self.ventanas[p] = VentanaNodo(self, p)
            self.ventanas[p].actualizar()
            self.ventanas[p].lift()

    def detener(self):
        p = self.seleccionado()
        if p is not None:
            self.accion(lambda: self.gestor.detener(p))

    def accion(self, funcion):
        try:
            funcion()
        except (ValueError, OSError) as error:
            messagebox.showerror('Administración del nodo', str(error), parent=self)
        self.sincronizar_tabla()

    def iniciar(self):
        p = self.seleccionado()
        if p is not None:
            self.accion(lambda: self.gestor.iniciar(p))
            self.abrir()

    def eliminar(self):
        p = self.seleccionado()
        if p is not None:
            self.accion(lambda: self.gestor.eliminar(p))
            if p not in self.gestor.nodos:
                ventana = self.ventanas.pop(p, None)
                if ventana and ventana.winfo_exists():
                    ventana.destroy()

    def reiniciar(self):
        p = self.seleccionado()
        if p is not None:
            self.accion(lambda: self.gestor.reiniciar(p))

    def cliente(self):
        p = self.seleccionado()
        if p is not None:
            c = self.gestor.nodos[p].configuracion
            host = '127.0.0.1' if c.host == '0.0.0.0' else c.host
            self.clientes.append(subprocess.Popen([sys.executable, '-m', 'interfaz.gui_incidentes', '--host', host, '--puerto', str(p)], cwd=RAIZ,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))

    def recibido(self, p, resultado):
        self.ocupados.discard(p)
        if p not in self.gestor.nodos:
            return
        ventana = self.ventanas.get(p)
        if ventana and ventana.winfo_exists():
            ventana.actualizar(error=resultado if isinstance(resultado, Exception) else None,
                               resultado=None if isinstance(resultado, Exception) else resultado)

    def ciclo(self):
        while not self.cola.empty():
            futuro, callback = self.cola.get_nowait()
            try:
                valor = futuro.result()
            except Exception as error:
                valor = error
            callback(valor)
        if self.cerrando:
            return
        self.sincronizar_tabla()
        for nodo in list(self.gestor.nodos.values()):
            p = nodo.configuracion.puerto
            if p not in self.ocupados:
                self.ocupados.add(p)
                self.trabajar(lambda p=p: self.gestor.consultar(p), lambda r, p=p: self.recibido(p, r))
        self._ciclo_id = self.after(1000, self.ciclo)

    def cerrar(self):
        self.cerrando = True
        self.after_cancel(self._ciclo_id)
        self.executor.shutdown(wait=True, cancel_futures=True)
        try:
            self.gestor.cerrar()
        finally:
            for proceso in self.clientes:
                if proceso.poll() is None:
                    proceso.terminate()
                proceso.wait()
            self.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos', type=Path, default=RAIZ)
    parser.add_argument('--clave', type=Path, default=RAIZ / 'clave_secreta.key')
    args = parser.parse_args(argv)
    try:
        gestor = AdministradorNodos(args.datos, args.clave)
    except (OSError, ValueError) as error:
        parser.exit(1, f'No se pudo cargar el registro: {error}\n')
    AppAdministrador(gestor).mainloop()


if __name__ == '__main__':
    main()
