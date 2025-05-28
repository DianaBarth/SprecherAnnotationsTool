import os
import re
import json
import tkinter as tk
from tkinter import ttk

import Eingabe.config as config
from annotationen_renderer import AnnotationRenderer

class AnnotationenEditor(ttk.Frame):
    def __init__(self, parent, notebook, dateipfad_json):
        super().__init__(notebook)
        self.notebook = notebook
        self.dateipfad_json = dateipfad_json
        self.renderer = AnnotationRenderer(max_breite=680)  # Max. Breite des Canvas für Tokens
        self.json_dicts = []  # Liste mit Token-Dictionaries aus JSON
        self._lade_json_daten()
        self._erstelle_widgets()

    def _lade_json_daten(self):
        """Lädt die JSON-Daten aus der angegebenen Datei."""
        with open(self.dateipfad_json, 'r', encoding='utf-8') as f:
            self.json_dicts = json.load(f)


    def _erstelle_widgets(self):
        # Frame komplett mit grid füllen
        self.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=250)  # Rechte Spalte fix 250px
        self.rowconfigure(0, weight=1)

        # Linke Seite: Canvas + Scrollbar
        linker_frame = tk.Frame(self)
        linker_frame.grid(row=0, column=0, sticky='nsew')
        linker_frame.columnconfigure(0, weight=1)
        linker_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(linker_frame, bg='white')
        self.canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar_links = ttk.Scrollbar(linker_frame, orient='vertical', command=self.canvas.yview)
        scrollbar_links.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar_links.set)

        # Rechte Seite: Annotationen mit eigenem Scroll-Canvas
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

        # Spaltengewichte im annotation_frame, damit Comboboxen wachsen können
        self.annotation_frame.columnconfigure(0, weight=1)  # Label-Spalte
        self.annotation_frame.columnconfigure(1, weight=1)  # Combobox-Spalte

        def on_frame_configure(event):
            self.annotation_canvas.configure(scrollregion=self.annotation_canvas.bbox('all'))

        self.annotation_frame.bind("<Configure>", on_frame_configure)

        # Zeichne Tokens
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
            self.renderer.rendern(
                index=idx,
                gui_canvas=self.canvas,
                naechstes_dict_element=naechstes_element,
                dict_element=json_dict
            )
            tag = f'token_{idx}'
            self.canvas.tag_bind(tag, '<Button-1>', lambda e, i=idx: self._on_token_click(i))

    def _on_token_click(self, idx):
        json_dict = self.json_dicts[idx]

        # Basisnamen extrahieren (Dummy)
        basename = os.path.basename(self.dateipfad_json)
        self.kapitel_name = basename.replace("_gesamt.json", "")
        if not self.kapitel_name:
            self.kapitel_name = "Kapitel1"

        # Rechte Seite vorher leeren
        for child in self.annotation_frame.winfo_children():
            child.destroy()

        tk.Label(self.annotation_frame, text=f"Token {idx}: '{json_dict.get('token','')}'", font=('Arial', 14, 'bold')).grid(row=0, column=0, sticky='w', pady=5, padx=5, columnspan=2)

        row_index = 1
        for aufgabennr, aufgabenname in config.KI_AUFGABEN.items():
            label = ttk.Label(self.annotation_frame, text=aufgabenname)
            label.grid(row=row_index, column=0, sticky='w', padx=5, pady=2)

            werte = []
            if aufgabennr == 3:
                zusatzinfo = self.kapitel_konfig.kapitel_daten.get(self.kapitel_name, {}).get("ZusatzInfo_3", "")
                werte = re.findall(r"'(.*?)'", zusatzinfo)
            else:
                werte = [eintrag["name"] for eintrag in config.AUFGABEN_ANNOTATIONEN.get(aufgabennr, []) if eintrag["name"]]

            if not werte:
                werte = ['']

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
                self.renderer.annotation_aendern(self.canvas, idx)

            combobox.bind("<<ComboboxSelected>>", on_combobox_change)
            combobox.grid(row=row_index, column=1, sticky='ew', padx=10, pady=2)

            row_index += 1

    # def _erstelle_widgets(self):
    #     """Erstellt die Widgets mit grid-Layout und rechter schmaler Spalte mit Scrollbar."""

    #     gesamt_breite, gesamt_hoehe = 1000, 700
    #     self.config(width=gesamt_breite, height=gesamt_hoehe)
    #     self.grid_propagate(False)

    #     # Grid 2 Spalten (0=links, 1=rechts), 1 Zeile
    #     self.columnconfigure(0, weight=1)          # Linke Spalte nimmt restliche Breite ein
    #     self.columnconfigure(1, weight=0, minsize=250)  # Rechte Spalte fix 250 px breit
    #     self.rowconfigure(0, weight=1)

    #     # Linke Seite: Canvas + vertikale Scrollbar
    #     linker_frame = tk.Frame(self)
    #     linker_frame.grid(row=0, column=0, sticky='nsew')

    #     self.canvas = tk.Canvas(linker_frame, bg='white')
    #     self.canvas.grid(row=0, column=0, sticky='nsew')

    #     scrollbar_links = ttk.Scrollbar(linker_frame, orient='vertical', command=self.canvas.yview)
    #     scrollbar_links.grid(row=0, column=1, sticky='ns')

    #     self.canvas.configure(yscrollcommand=scrollbar_links.set)

    #     # Frame im Canvas für Tokens (für später, falls du interne Widgets brauchst)
    #     # Falls du nur mit Canvas zeichnest, brauchst du das nicht unbedingt.
    #     #self.token_frame = tk.Frame(self.canvas)
    #     #self.canvas.create_window((0,0), window=self.token_frame, anchor='nw')

    #     linker_frame.rowconfigure(0, weight=1)
    #     linker_frame.columnconfigure(0, weight=1)

    #     # Rechte Seite: Scrollbarer Frame für Annotationen
    #     rechts_frame = tk.Frame(self)
    #     rechts_frame.grid(row=0, column=1, sticky='nsew')

    #     self.annotation_canvas = tk.Canvas(rechts_frame)
    #     self.annotation_canvas.grid(row=0, column=0, sticky='nsew')

    #     scrollbar_rechts = ttk.Scrollbar(rechts_frame, orient='vertical', command=self.annotation_canvas.yview)
    #     scrollbar_rechts.grid(row=0, column=1, sticky='ns')

    #     self.annotation_canvas.configure(yscrollcommand=scrollbar_rechts.set)

    #     rechts_frame.rowconfigure(0, weight=1)
    #     rechts_frame.columnconfigure(0, weight=1)

    #     self.annotation_frame = ttk.Frame(self.annotation_canvas)
    #     self.annotation_canvas.create_window((0, 0), window=self.annotation_frame, anchor='nw')

    #     def on_frame_configure(event):
    #         self.annotation_canvas.configure(scrollregion=self.annotation_canvas.bbox('all'))

    #     self.annotation_frame.bind("<Configure>", on_frame_configure)

    #     # Zeichne alle Tokens mit Marker
    #     self._zeichne_alle_tokens()

    #     # Scrollregion initial setzen
    #     self.canvas.update_idletasks()
    #     self.canvas.configure(scrollregion=self.canvas.bbox('all'))


    # # def _erstelle_widgets(self):
    # #     """Erstellt die Widgets (Canvas links, Frame rechts) und richtet Scrollbar ein."""
    # #     gesamt_breite, gesamt_hoehe = 1000, 700
    # #     self.place(width=gesamt_breite, height=gesamt_hoehe)

    # #     # Linke Seite: Canvas für Tokens mit vertikalem Scrollbalken
    # #     token_breite = 700
    # #     linker_frame = tk.Frame(self, width=token_breite, height=gesamt_hoehe)
    # #     linker_frame.place(x=0, y=0)

    # #     self.canvas = tk.Canvas(linker_frame, width=token_breite, height=gesamt_hoehe, bg='white')
    # #     self.canvas.pack(side='left', fill='both', expand=True)

    # #     scrollbar = ttk.Scrollbar(linker_frame, orient='vertical', command=self.canvas.yview)
    # #     scrollbar.pack(side='right', fill='y')

    # #     self.canvas.configure(yscrollcommand=scrollbar.set)
    # #     # Scrollregion aktualisieren, wenn Canvasgröße sich ändert
    # #     self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

    # #     # Rechte Seite: Frame für Annotationen/Details
    # #     self.annotation_frame = ttk.Frame(self, width=gesamt_breite - token_breite, height=gesamt_hoehe)
    # #     self.annotation_frame.place(x=token_breite, y=0)

    # #     # Zeichne alle Tokens mit Marker
    # #     self._zeichne_alle_tokens()

    # #     # Scrollregion initial setzen
    # #     self.canvas.update_idletasks()
    # #     self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    # def _zeichne_alle_tokens(self):
    #     """Löscht und zeichnet alle Token-Elemente auf dem Canvas neu."""
    #     self.canvas.delete('all')
    #     self.renderer.positionen_zuruecksetzen()  # Interne Positionen im Renderer zurücksetzen

    #     # Rechts die Annotationen löschen
    #     for child in self.annotation_frame.winfo_children():
    #         child.destroy()

    #     # Jeden Token einzeln rendern
    #     for idx, json_dict in enumerate(self.json_dicts):
    #         naechstes_element = self.json_dicts[idx + 1] if idx + 1 < len(self.json_dicts) else None
    #         self.renderer.rendern(
    #             index=idx,
    #             gui_canvas=self.canvas,                
    #             naechstes_dict_element=naechstes_element,
    #             dict_element=json_dict
    #         )
    #         # Klick-Event für jeden Token-Tag binden, um Detailanzeige zu starten
    #         tag = f'token_{idx}'
    #         self.canvas.tag_bind(tag, '<Button-1>', lambda e, i=idx: self._on_token_click(i))



    # def _on_token_click(self, idx):
        import os
        import re
        json_dict = self.json_dicts[idx]
        
        print(f"Annotationen für Token {idx}: {json_dict}")
        
        # Kapitelname aus Pfad extrahieren (ohne '_gesamt.json')
        basename = os.path.basename(self.dateipfad_json)
        self.kapitel_name = basename.replace("_gesamt.json", "")
        row_index = 0
        
        # Rechte Seite vorher leeren
        for child in self.annotation_frame.winfo_children():
            child.destroy()

        # Token-Info anzeigen
        tk.Label(self.annotation_frame, text=f"Token {idx}: '{json_dict.get('token','')}'", font=('Arial', 14, 'bold')).pack(anchor='w', pady=5)

        for aufgabennr, aufgabenname in config.KI_AUFGABEN.items():
            # Überschrift
            label = ttk.Label(self.annotation_frame, text=aufgabenname)
            label.grid(row=row_index, column=0, sticky='w', padx=5, pady=2)

            # Werte für Combobox vorbereiten
            werte = []
            if aufgabennr == 3:
                # Spezialfall: Person → ZusatzInfo_3 aus kapitel_config
                zusatzinfo = self.kapitel_konfig.kapitel_daten.get(self.kapitel_name, {}).get("ZusatzInfo_3", "")
                werte = re.findall(r"'(.*?)'", zusatzinfo)
            else:
                werte = [eintrag["name"] for eintrag in config.AUFGABEN_ANNOTATIONEN.get(aufgabennr, []) if eintrag["name"]]

            if not werte:
                werte = ['']  # Verhindert Fehler bei leerer Liste

            # Standardwert (falls vorhanden)
            aktueller_wert = json_dict.get(aufgabenname, "")
            combobox = ttk.Combobox(self.annotation_frame, values=werte, state='readonly')
            if aktueller_wert in werte:
                combobox.set(aktueller_wert)

            # Callback beim Ändern
            def on_combobox_change(event, aufgabennr=aufgabennr, combobox=combobox, aufgabenname=aufgabenname):
                neuer_wert = combobox.get()
                if neuer_wert:
                    json_dict[aufgabenname] = neuer_wert
                elif aufgabenname in json_dict:
                    del json_dict[aufgabenname]

                self.renderer.annotation_aendern(self.canvas, idx)

            combobox.bind("<<ComboboxSelected>>", on_combobox_change)
            combobox.grid(row=row_index, column=1, sticky='ew', padx=10, pady=2)
            print(f"Combobox für Aufgabe '{aufgabenname}' erstellt mit Werten: {werte} und aktuellem Wert: '{aktueller_wert}'")

            row_index += 1