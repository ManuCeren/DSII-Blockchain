"""
Interfaz Gráfica (Tkinter) - Módulo de Bloque, Minado y Encriptación (Servidor)
Blockchain para Registro de Incidentes de Seguridad Informática
"""

import argparse
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from types import SimpleNamespace
from cliente.cliente import Cliente, argumentos_cliente, puerto_cliente


class AppBlockchain(tk.Tk):
    def __init__(self, cliente=None):
        super().__init__()
        self.title("Wallet de Incidentes de Seguridad")
        self.geometry("900x560")
        self.minsize(760, 480)

        # Estas son vistas locales de JSON; el servidor administra el estado real.
        self.cliente = cliente if cliente is not None else Cliente()
        self.title(f'Wallet de Incidentes de Seguridad — {self.cliente.host}:{self.cliente.puerto}')
        self.bc = SimpleNamespace(cadena=[], dificultad=4)
        self.bloque_propuesto = None
        self.minando = False
        self.cola_minado = queue.Queue()
        self._construir_interfaz()
        self._refrescar_arbol()
        self._actualizar_estado_bloque_propuesto()

    # ------------------------------------------------------------------ UI
    def _construir_interfaz(self):
        barra = ttk.Frame(self, padding=8)
        barra.pack(side="top", fill="x")

        ttk.Button(barra, text="➕ Agregar incidente",
                   command=self._abrir_formulario_incidente).pack(side="left", padx=4)
        ttk.Button(barra, text="⛏ Minar bloque propuesto",
                   command=self._minar_bloque_propuesto).pack(side="left", padx=4)
        ttk.Button(barra, text="⚙ Cambiar dificultad",
                   command=self._cambiar_dificultad).pack(side="left", padx=4)
        ttk.Button(barra, text="🔄 Refrescar",
                   command=self._refrescar_arbol).pack(side="left", padx=4)
        ttk.Button(barra, text="Servidor", command=self._configurar_servidor).pack(side="left", padx=4)

        self.lbl_estado = ttk.Label(barra, text="", font=("Segoe UI", 9, "italic"))
        self.lbl_estado.pack(side="right", padx=4)

        panel = ttk.Panedwindow(self, orient="horizontal")
        panel.pack(fill="both", expand=True, padx=8, pady=8)

        # Árbol de la cadena (izquierda)
        frame_arbol = ttk.Frame(panel)
        panel.add(frame_arbol, weight=1)

        ttk.Label(frame_arbol, text="Cadena de bloques", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.arbol = ttk.Treeview(frame_arbol, columns=("info",), show="tree headings", height=20)
        self.arbol.heading("#0", text="Bloque / Incidente")
        self.arbol.heading("info", text="Detalle")
        self.arbol.column("#0", width=180)
        self.arbol.column("info", width=260)
        self.arbol.pack(fill="both", expand=True, pady=4)
        self.arbol.bind("<<TreeviewSelect>>", self._mostrar_detalle_seleccion)

        # Panel de detalle (derecha)
        frame_detalle = ttk.Frame(panel)
        panel.add(frame_detalle, weight=1)

        ttk.Label(frame_detalle, text="Detalle", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.txt_detalle = tk.Text(frame_detalle, wrap="word", height=20, state="disabled")
        self.txt_detalle.pack(fill="both", expand=True, pady=4)

        ttk.Label(frame_detalle, text="Bloque propuesto (aún sin minar)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.lbl_propuesto = ttk.Label(frame_detalle, text="", justify="left")
        self.lbl_propuesto.pack(anchor="w", fill="x")

    # ---------------------------------------------------------- Formulario
    def _abrir_formulario_incidente(self):
        ventana = tk.Toplevel(self)
        ventana.title("Nuevo incidente")
        ventana.geometry("400x340")
        ventana.transient(self)
        ventana.grab_set()

        ttk.Label(ventana, text="Tipo de incidente:").pack(anchor="w", padx=10, pady=(10, 0))
        combo_tipo = ttk.Combobox(ventana, values=[
            "Acceso no autorizado", "Malware", "Phishing",
            "Fuga de información", "Denegación de servicio (DoS)", "Otro"
        ])
        combo_tipo.pack(fill="x", padx=10)

        ttk.Label(ventana, text="Descripción:").pack(anchor="w", padx=10, pady=(10, 0))
        txt_desc = tk.Text(ventana, height=5)
        txt_desc.pack(fill="x", padx=10)

        ttk.Label(ventana, text="Reportado por:").pack(anchor="w", padx=10, pady=(10, 0))
        entry_reportado = ttk.Entry(ventana)
        entry_reportado.pack(fill="x", padx=10)

        ttk.Label(ventana, text="Severidad:").pack(anchor="w", padx=10, pady=(10, 0))
        combo_severidad = ttk.Combobox(ventana, values=["Baja", "Media", "Alta", "Critica"], state="readonly")
        combo_severidad.pack(fill="x", padx=10)
        combo_severidad.current(0)

        def guardar():
            tipo = combo_tipo.get().strip()
            descripcion = txt_desc.get("1.0", "end").strip()
            reportado_por = entry_reportado.get().strip()
            severidad = combo_severidad.get().strip()

            if not tipo or not descripcion or not reportado_por:
                messagebox.showwarning("Datos incompletos",
                                        "Completa tipo, descripción y quién reporta.")
                return

            if self.minando:
                messagebox.showinfo("Minado en curso", "Espera a que termine el minado.")
                return
            try:
                self.cliente.solicitar("AGREGAR_INCIDENTE", {
                    "tipo": tipo, "descripcion": descripcion,
                    "reportado_por": reportado_por, "severidad": severidad,
                })
            except (OSError, ValueError) as error:
                messagebox.showerror("Error del servidor", str(error))
                return
            self._actualizar_estado_bloque_propuesto()
            ventana.destroy()

        ttk.Button(ventana, text="Agregar al bloque propuesto", command=guardar).pack(pady=14)

    # ------------------------------------------------------------- Minado
    def _minar_bloque_propuesto(self):
        if self.minando:
            return
        self._actualizar_estado_bloque_propuesto()
        if self.bloque_propuesto is None or not self.bloque_propuesto.transacciones:
            messagebox.showinfo("Nada que minar",
                                 "Agrega al menos un incidente antes de minar.")
            return

        self.minando = True
        self.lbl_estado.config(text="Minando bloque, por favor espera...")

        # el minado corre en un hilo aparte para no congelar la ventana; el resultado
        # se recoge después con la cola en _revisar_cola_minado
        # El trabajador recibe solo el cliente y la cola, nunca la ventana Tk.
        # Así tampoco retiene el intérprete Tcl si se cierra la GUI al minar.
        hilo = threading.Thread(target=AppBlockchain._minar_en_hilo,
                                args=(self.cliente, self.cola_minado), daemon=True)
        hilo.start()
        self.after(100, self._revisar_cola_minado)

    @staticmethod
    def _minar_en_hilo(cliente, cola_minado):
        try:
            cliente.solicitar("MINAR_BLOQUE")
            cola_minado.put(None)
        except (OSError, ValueError) as error:
            cola_minado.put(error)

    def _revisar_cola_minado(self):
        try:
            error = self.cola_minado.get_nowait()
        except queue.Empty:
            self.after(100, self._revisar_cola_minado)
            return
        self.minando = False
        if error is not None:
            self.lbl_estado.config(text="No se pudo confirmar el minado.")
            messagebox.showerror("Error del servidor", str(error))
        else:
            self.lbl_estado.config(text="Bloque minado y agregado a la cadena.")
        self._refrescar_arbol()
        self._actualizar_estado_bloque_propuesto()
    # ------------------------------------------------------------- Ajustes
    def _configurar_servidor(self):
        if self.minando:
            return
        direccion = simpledialog.askstring(
            'Conectar a servidor', 'IP o nombre del servidor y puerto (HOST:PUERTO):',
            initialvalue=f'{self.cliente.host}:{self.cliente.puerto}')
        if direccion is None:
            return
        try:
            host, separador, puerto = direccion.strip().rpartition(':')
            if not host or not separador:
                raise ValueError('Usa HOST:PUERTO, por ejemplo 127.0.0.1:7001.')
            puerto = puerto_cliente(puerto)
            Cliente(host, puerto, timeout=3).solicitar('VER_CADENA')
        except (OSError, ValueError, argparse.ArgumentTypeError) as error:
            messagebox.showerror('No se pudo conectar', str(error))
            return
        self.cliente = Cliente(host, puerto)
        self.title(f'Wallet de Incidentes de Seguridad — {host}:{puerto}')
        self._refrescar_arbol()

    def _cambiar_dificultad(self):
        if self.minando:
            return
        nueva = simpledialog.askinteger(
            "Cambiar dificultad",
            "Número de ceros requeridos al inicio del hash (recomendado 4-6):",
            initialvalue=self.bc.dificultad, minvalue=0, maxvalue=8,
        )
        if nueva is not None:
            try:
                self.cliente.solicitar("CAMBIAR_DIFICULTAD", {"dificultad": nueva})
            except (OSError, ValueError) as error:
                messagebox.showerror("Error del servidor", str(error))
                return
            self.bc.dificultad = nueva
            self.lbl_estado.config(text=f"Dificultad actualizada a {nueva}.")

    # -------------------------------------------------------------- Vistas
    def _actualizar_estado_bloque_propuesto(self):
        if self.minando:
            return
        try:
            datos = self.cliente.solicitar("VER_BLOQUE_PROPUESTO")
            self.bloque_propuesto = self._vista_bloque(datos) if datos else None
        except (OSError, ValueError) as error:
            messagebox.showerror("Error del servidor", str(error))
            return
        if self.bloque_propuesto is None:
            self.lbl_propuesto.config(text="(No hay ningún bloque propuesto todavía)")
        else:
            n = len(self.bloque_propuesto.transacciones)
            self.lbl_propuesto.config(
                text=f"Bloque #{self.bloque_propuesto.numero_bloque} — {n} incidente(s) sin minar"
            )

    @staticmethod
    def _vista_bloque(datos):
        copia = dict(datos)
        copia["transacciones"] = [SimpleNamespace(**t) for t in datos["transacciones"]]
        return SimpleNamespace(**copia)

    def _refrescar_arbol(self):
        if self.minando:
            return
        try:
            datos = self.cliente.solicitar("VER_CADENA")
            self.bc = SimpleNamespace(
                cadena=[self._vista_bloque(b) for b in datos["cadena"]],
                dificultad=datos["dificultad"])
        except (OSError, ValueError) as error:
            messagebox.showerror("Error del servidor", str(error))
            return
        self._actualizar_estado_bloque_propuesto()
        self.arbol.delete(*self.arbol.get_children())
        for b in self.bc.cadena:
            texto_bloque = f"Bloque #{b.numero_bloque}"
            info_bloque = f"hash: {b.hash[:16]}..."
            nodo_bloque = self.arbol.insert("", "end", text=texto_bloque,
                                             values=(info_bloque,), tags=("bloque", b.numero_bloque))
            for t in b.transacciones:
                self.arbol.insert(nodo_bloque, "end",
                                   text=f"Incidente #{t.id_incidente}",
                                   values=(f"{t.tipo} - {t.severidad}",),
                                   tags=("incidente", b.numero_bloque, t.id_incidente))

    def _mostrar_detalle_seleccion(self, _evento):
        seleccion = self.arbol.selection()
        if not seleccion:
            return
        item = self.arbol.item(seleccion[0])
        tags = item["tags"]
        if not tags:
            return

        self.txt_detalle.config(state="normal")
        self.txt_detalle.delete("1.0", "end")

        if tags[0] == "bloque":
            numero_bloque = int(tags[1])
            bloque = next(b for b in self.bc.cadena if b.numero_bloque == numero_bloque)
            detalle = (
                f"Bloque #{bloque.numero_bloque}\n"
                f"Hash anterior: {bloque.hash_anterior}\n"
                f"Hash: {bloque.hash}\n"
                f"Nonce: {bloque.nonce}\n"
                f"Timestamp: {bloque.timestamp}\n"
                f"Transacciones: {len(bloque.transacciones)}\n"
            )
        else:
            # Se pide al servidor el descifrado solo cuando se abre el detalle.
            numero_bloque, id_incidente = int(tags[1]), int(tags[2])
            bloque = next(b for b in self.bc.cadena if b.numero_bloque == numero_bloque)
            t = next(i for i in bloque.transacciones if i.id_incidente == id_incidente)
            if self.minando:
                self.txt_detalle.config(state="disabled")
                return
            try:
                datos = self.cliente.solicitar("VER_INCIDENTE", {
                    "numero_bloque": numero_bloque, "id_incidente": id_incidente})
            except (OSError, ValueError) as error:
                messagebox.showerror("Error del servidor", str(error))
                self.txt_detalle.config(state="disabled")
                return
            detalle = (
                f"Incidente #{t.id_incidente}\n"
                f"Tipo: {t.tipo}\n"
                f"Severidad: {t.severidad}\n"
                f"Descripción (descifrada): {datos['descripcion']}\n"
                f"Reportado por (descifrado): {datos['reportado_por']}\n"
            )

        self.txt_detalle.insert("1.0", detalle)
        self.txt_detalle.config(state="disabled")


def main(argv=None):
    parser = argumentos_cliente(argparse.ArgumentParser(description='GUI cliente de Blockchain.'))
    args = parser.parse_args(argv)
    app = AppBlockchain(Cliente(args.host, args.puerto))
    app.mainloop()


if __name__ == "__main__":
    main()
