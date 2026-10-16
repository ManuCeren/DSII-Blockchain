"""
Interfaz Gráfica (Tkinter) - Módulo de Bloque, Minado y Encriptación (Servidor)
Blockchain para Registro de Incidentes de Seguridad Informática
"""

import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from blockchain_incidentes import Bloque, Incidente, Blockchain, Encriptador


class AppBlockchain(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Blockchain de Incidentes de Seguridad Informática")
        self.geometry("900x560")
        self.minsize(760, 480)

        # Estado del negocio: la cadena real, el bloque que se está armando y la llave de cifrado
        self.encriptador = Encriptador()
        self.bc = Blockchain(dificultad=4)
        self.bloque_propuesto = None
        self.contador_incidentes = 0
        self.cola_minado = queue.Queue()  # para pasar el resultado del hilo de minado a la UI

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

            # el bloque propuesto se crea hasta que hay al menos un incidente listo para meterle
            if self.bloque_propuesto is None:
                self.bloque_propuesto = Bloque(
                    numero_bloque=self.bc.obtener_ultimo_bloque().numero_bloque + 1,
                    hash_anterior=self.bc.obtener_ultimo_bloque().hash,
                )

            self.contador_incidentes += 1
            incidente = Incidente(self.contador_incidentes, tipo, descripcion,
                                   reportado_por, severidad, self.encriptador)
            self.bloque_propuesto.agregar_transaccion(incidente)

            self._actualizar_estado_bloque_propuesto()
            ventana.destroy()

        ttk.Button(ventana, text="Agregar al bloque propuesto", command=guardar).pack(pady=14)

    # ------------------------------------------------------------- Minado
    def _minar_bloque_propuesto(self):
        if self.bloque_propuesto is None or not self.bloque_propuesto.transacciones:
            messagebox.showinfo("Nada que minar",
                                 "Agrega al menos un incidente antes de minar.")
            return

        self.lbl_estado.config(text="Minando bloque, por favor espera...")

        # el minado corre en un hilo aparte para no congelar la ventana; el resultado
        # se recoge después con la cola en _revisar_cola_minado
        hilo = threading.Thread(target=self._minar_en_hilo, daemon=True)
        hilo.start()
        self.after(100, self._revisar_cola_minado)

    def _minar_en_hilo(self):
        bloque = self.bloque_propuesto
        self.bc.agregar_bloque(bloque)
        self.cola_minado.put(bloque)

    def _revisar_cola_minado(self):
        try:
            self.cola_minado.get_nowait()
        except queue.Empty:
            self.after(100, self._revisar_cola_minado)
            return

        self.bloque_propuesto = None
        self.lbl_estado.config(text="Bloque minado y agregado a la cadena.")
        self._refrescar_arbol()
        self._actualizar_estado_bloque_propuesto()

    # ------------------------------------------------------------- Ajustes
    def _cambiar_dificultad(self):
        nueva = simpledialog.askinteger(
            "Cambiar dificultad",
            "Número de ceros requeridos al inicio del hash (recomendado 4-6):",
            initialvalue=self.bc.dificultad, minvalue=0, maxvalue=8,
        )
        if nueva is not None:
            self.bc.dificultad = nueva
            self.lbl_estado.config(text=f"Dificultad actualizada a {nueva}.")

    # -------------------------------------------------------------- Vistas
    def _actualizar_estado_bloque_propuesto(self):
        if self.bloque_propuesto is None:
            self.lbl_propuesto.config(text="(No hay ningún bloque propuesto todavía)")
        else:
            n = len(self.bloque_propuesto.transacciones)
            self.lbl_propuesto.config(
                text=f"Bloque #{self.bloque_propuesto.numero_bloque} — {n} incidente(s) sin minar"
            )

    def _refrescar_arbol(self):
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
                f"Transacciones: {len(bloque.transacciones)}\n"
            )
        else:
            # aquí es donde se desencripta la info sensible del incidente, solo al mostrarla
            numero_bloque, id_incidente = int(tags[1]), int(tags[2])
            bloque = next(b for b in self.bc.cadena if b.numero_bloque == numero_bloque)
            t = next(i for i in bloque.transacciones if i.id_incidente == id_incidente)
            detalle = (
                f"Incidente #{t.id_incidente}\n"
                f"Tipo: {t.tipo}\n"
                f"Severidad: {t.severidad}\n"
                f"Descripción (descifrada): {t.descripcion(self.encriptador)}\n"
                f"Reportado por (descifrado): {t.reportado_por(self.encriptador)}\n"
            )

        self.txt_detalle.insert("1.0", detalle)
        self.txt_detalle.config(state="disabled")


if __name__ == "__main__":
    app = AppBlockchain()
    app.mainloop()