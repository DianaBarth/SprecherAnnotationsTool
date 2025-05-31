import os
import re
import json
import tkinter as tk
from tkinter import ttk, messagebox

import Eingabe.config as config
from annotationen_renderer import AnnotationRenderer

class AnnotationenEditor(ttk.Frame):
    def __init__(self, parent, notebook, dateipfad_json):
        super().__init__(notebook)
        self.notebook = notebook
        self.dateipfad_json = dateipfad_json
        self.renderer = AnnotationRenderer(max_breite=680)
        self.json_dicts = []
        self._lade_json_daten()
        self._erstelle_widgets()

    def _lade_json_daten(self):
        with open(self.dateipfad_json, 'r', encoding='utf-8') as f:
            self.json_dicts = json.load(f)

    def lade_kapitel_konfig(self, pfad):
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)

    def _erstelle_widgets(self):
        self.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=250)
        self.rowconfigure(0, weight=1)

        # Oben: Button-Leiste
        top_frame = ttk.Frame(self)
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        top_frame.columnconfigure(0, weight=1)

        speichern_button = ttk.Button(top_frame, text="JSON speichern", command=self._json_speichern)
        speichern_button.pack(side='left', padx=5)

        # Linker Bereich: Canvas + Scrollbar
        linker_frame = tk.Frame(self)
        linker_frame.grid(row=0, column=0, sticky='nsew')
        linker_frame.columnconfigure(0, weight=1)
        linker_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(linker_frame, bg='white')
        self.canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar_links = ttk.Scrollbar(linker_frame, orient='vertical', command=self.canvas.yview)
        scrollbar_links.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar_links.set)

        # Rechter Bereich: Annotationen
        rechts_frame = tk.Frame(self)
        rechts_frame.grid(row=0, column=1, sticky='nsew')
        rechts_frame.columnconfigure(0, weight=1)
        rechts_frame.rowconfigure(0, weight=1)

        self.annotation_canvas = tk.Canvas(rechts_frame)
        self.annotation_canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar_rechts = ttk.Scrollbar(rechts_frame, orient='vertical', command=self.annotation_canvas.yview)
        scrollbar_rechts.grid(row=0, column=1, sticky='ns')
        self.annotation_canvas.configure(yscrollcommand=scrollbar_rechts.set)

        self.annotation_frame = ttk.Frame(self.annotation_canvas)
        self.annotation_canvas.create_window((0, 0), window=self.annotation_frame, anchor='nw')

        self.annotation_frame.columnconfigure(0, weight=1)
        self.annotation_frame.columnconfigure(1, weight=1)

        self.annotation_frame.bind("<Configure>", lambda e: self.annotation_canvas.configure(scrollregion=self.annotation_canvas.bbox('all')))

        self._zeichne_alle_tokens()

        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _zeichne_alle_tokens(self):
        self.canvas.delete('all')
        self.renderer.positionen_zuruecksetzen()
        for child in self.annotation_frame.winfo_children():
            child.destroy()

        for idx, json_dict in enumerate(self.json_dicts):
            naechstes_element = self.json_dicts[idx + 1] if idx + 1 < len(self.json_dicts) else None
            self.renderer.rendern(index=idx, gui_canvas=self.canvas, naechstes_dict_element=naechstes_element, dict_element=json_dict)
            tag = f'token_{idx}'
            self.canvas.tag_bind(tag, '<Button-1>', lambda e, i=idx: self._on_token_click(i))

    def _on_token_click(self, idx):
        json_dict = self.json_dicts[idx]
        self.renderer.markiere_token_mit_rahmen(self.canvas, idx)

        basename = os.path.basename(self.dateipfad_json)
        self.kapitel_name = basename.replace("_gesamt.json", "") or "Kapitel1"
        self.kapitel_konfig = self.lade_kapitel_konfig("Eingabe/kapitel_config.json")

        for child in self.annotation_frame.winfo_children():
            child.destroy()

        tk.Label(self.annotation_frame, text=f"Token {idx}: '{json_dict.get('token','')}'", font=('Arial', 14, 'bold')).grid(row=0, column=0, sticky='w', pady=5, padx=5, columnspan=2)

        row_index = 1
        for aufgabennr, aufgabenname in config.KI_AUFGABEN.items():
            label = ttk.Label(self.annotation_frame, text=aufgabenname)
            label.grid(row=row_index, column=0, sticky='w', padx=5, pady=2)

            if aufgabennr == 3:
                zusatzinfo = self.kapitel_konfig.get("kapitel_daten", {}).get(self.kapitel_name, {}).get("ZusatzInfo_3", "")
                werte = re.findall(r"'(.*?)'", zusatzinfo)
            else:
                werte = [e["name"] for e in config.AUFGABEN_ANNOTATIONEN.get(aufgabennr, []) if e["name"]]

            if werte and werte[-1] != "":
                 werte.append("")
                 
            werte = werte or ['']
            aktueller_wert = json_dict.get(aufgabenname, "")

            combobox = ttk.Combobox(self.annotation_frame, values=werte, state='readonly')
            if aktueller_wert in werte:
                combobox.set(aktueller_wert)

            def on_combobox_change(event, aufgabennr=aufgabennr, combobox=combobox, aufgabenname=aufgabenname):
                neuer_wert = combobox.get()
                if neuer_wert:
                    json_dict[aufgabenname] = neuer_wert
                elif aufgabenname in json_dict:
                    del json_dict[aufgabenname]
                self.renderer.annotation_aendern(self.canvas, idx,json_dict)

            combobox.bind("<<ComboboxSelected>>", on_combobox_change)
            combobox.grid(row=row_index, column=1, sticky='ew', padx=10, pady=2)

            row_index += 1

    def _json_speichern(self):
        try:
            zielpfad = os.path.join(config.GLOBALORDNER["manuell"], os.path.basename(self.dateipfad_json))
            with open(zielpfad, 'w', encoding='utf-8') as f:
                json.dump(self.json_dicts, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Erfolg", f"JSON erfolgreich gespeichert nach:\n{zielpfad}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Speichern:\n{str(e)}")