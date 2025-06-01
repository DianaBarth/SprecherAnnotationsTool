import os
import re
import json
import tkinter as tk
from tkinter import ttk, messagebox

import Eingabe.config as config
from annotationen_renderer import AnnotationRenderer

class AnnotationenEditor(ttk.Frame):
    def __init__(self, parent, notebook, kapitel ,config_editor ):
        super().__init__(parent)
        self.kapitel = kapitel
        self.kapitel_pfade = self._lade_alle_kapiteldateien(kapitel)

        if not self.kapitel_pfade:
            messagebox.showerror("Fehler", f"Keine Annotationsdateien für Kapitel '{kapitel}' gefunden.")
            return
        else:
            print("Pfadliste:", self.kapitel_pfade)

        self.current_index = 0  # Starte mit erster Datei
        self.config_editor = config_editor
        self.renderer = AnnotationRenderer(max_breite=680)
        self.json_dicts = []
        self.filter_vars = {}
        self.use_number_words_var = tk.BooleanVar(value=True)

        self._lade_json_daten()
        self._erstelle_widgets()
     

    def _lade_alle_kapiteldateien(self, kapitel):
        merge_ordner = config.GLOBALORDNER["merge"]
        pattern = re.compile(rf"^{kapitel}_(\d+)_annotierungen\.json$")
        dateien = []

        for dateiname in os.listdir(merge_ordner):
            match = pattern.match(dateiname)
            if match:
                idx = int(match.group(1))
                dateien.append((idx, os.path.join(merge_ordner, dateiname)))

        dateien.sort()  # nach Index sortieren
        return [pfad for _, pfad in dateien]

    def _lade_json_daten(self):
        aktueller_pfad = self.kapitel_pfade[self.current_index]
        with open(aktueller_pfad, 'r', encoding='utf-8') as f:
            self.json_dicts = json.load(f)
        self.dateipfad_json = aktueller_pfad

    def _erstelle_widgets(self):
        self.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)  # Canvas-Bereich bekommt den meisten Platz

        # 1. Zeile: dateiauswahl + speichern button
        top_frame_1 = ttk.Frame(self)
        top_frame_1.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))
        top_frame_1.columnconfigure(0, weight=0)
        top_frame_1.columnconfigure(1, weight=0)

        self.dateiauswahl = ttk.Combobox(
            top_frame_1,
            values=[f"{self.kapitel}_{i+1}" for i in range(len(self.kapitel_pfade))],
            state="readonly"
        )
        self.dateiauswahl.current(self.current_index)
        self.dateiauswahl.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.dateiauswahl.bind("<<ComboboxSelected>>", self._wechsel_datei)

        speichern_button = ttk.Button(top_frame_1, text="JSON speichern", command=self._json_speichern)
        speichern_button.grid(row=0, column=1, sticky="w")

        # 2. Zeile: zahlwoerter_checkbox
        top_frame_2 = ttk.Frame(self)
        top_frame_2.grid(row=1, column=0, sticky="w", padx=5, pady=(5, 0))

        zahlwoerter_checkbox = ttk.Checkbutton(
            top_frame_2,
            text="Verwende Zahlwörter",
            variable=self.use_number_words_var,
            command=self._zeichne_alle_tokens
        )
        zahlwoerter_checkbox.grid(row=0, column=0, sticky="w")

        # 3. Zeile: Annotationen ausblenden für
        top_frame_3 = ttk.Frame(self)
        top_frame_3.grid(row=2, column=0, sticky="w", padx=5, pady=(10, 0))

        filter_label = ttk.Label(top_frame_3, text="Annotationen ausblenden für:")
        filter_label.grid(row=0, column=0, sticky="w", padx=(0, 10))

        col = 1
        for aufgabenname in config.KI_AUFGABEN.values():
            var = tk.BooleanVar(value=False)
            self.filter_vars[aufgabenname] = var
            btn = ttk.Checkbutton(
                top_frame_3, text=aufgabenname, variable=var, command=self._zeichne_alle_tokens
            )
            btn.grid(row=0, column=col, sticky="w", padx=2)
            col += 1

        # 4. Zeile: frei (leer)
        # Einfach eine leere Zeile als Abstand (kann ggf. auch mit padding gemacht werden)

        # 5. Zeile: Canvas + Annotationen (links + rechts)
        canvas_frame = ttk.Frame(self)
        canvas_frame.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.columnconfigure(1, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        # Linker Bereich: Canvas + Scrollbar
        linker_frame = ttk.Frame(canvas_frame)
        linker_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        linker_frame.columnconfigure(0, weight=1)
        linker_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(linker_frame, bg='white')
        self.canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar_links = ttk.Scrollbar(linker_frame, orient='vertical', command=self.canvas.yview)
        scrollbar_links.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar_links.set)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Rechter Bereich: Annotationen
        rechts_frame = ttk.Frame(canvas_frame)
        rechts_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
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

        self.annotation_frame.bind(
            "<Configure>",
            lambda e: self.annotation_canvas.configure(scrollregion=self.annotation_canvas.bbox('all'))
        )

        self.default_annotation_label = ttk.Label(
            self.annotation_frame,
            text="Bitte Wort auswählen, um dessen Annotationen zu sehen und zu ändern!",
            foreground="gray",
            font=('Arial', 12, 'italic'),
            wraplength=200,
            justify='left'
        )
        self.default_annotation_label.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky='nw')

        self._zeichne_alle_tokens()
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _zeichne_alle_tokens(self):
        self.canvas.delete('all')
        self.renderer.positionen_zuruecksetzen()

        # 🧠 Filter-Status an Renderer übergeben
        aktive_filter = [name for name, var in self.filter_vars.items() if var.get()]
        self.renderer.ignorierte_annotationen = set(a.lower() for a in aktive_filter)
        self.renderer.use_number_words = self.use_number_words_var.get()
        
        for idx, json_dict in enumerate(self.json_dicts):
            naechstes_element = self.json_dicts[idx + 1] if idx + 1 < len(self.json_dicts) else None
            self.renderer.rendern(index=idx, gui_canvas=self.canvas, naechstes_dict_element=naechstes_element, dict_element=json_dict)
            tag = f'token_{idx}'
            self.canvas.tag_bind(tag, '<Button-1>', lambda e, i=idx: self._on_token_click(i))

    def _on_token_click(self, idx):
        print(f"Token {idx} wurde angeklickt.")
        self.default_annotation_label.grid_forget()

        json_dict = self.json_dicts[idx]
        self.renderer.markiere_token_mit_rahmen(self.canvas, idx)

        basename = os.path.basename(self.dateipfad_json)
        self.kapitel_name = basename.replace("_gesamt.json", "") 

        self.kapitel_konfig = self.lade_kapitel_konfig("Eingabe/kapitel_config.json")

        print(f"Vor dem Löschen Widgets im annotation_frame: {[type(c) for c in self.annotation_frame.winfo_children()]}")
        # Alle Widgets außer default_label löschen
        for child in self.annotation_frame.winfo_children():
            if child != self.default_annotation_label:
                child.destroy()
        self.annotation_frame.update_idletasks()
        print(f"Nach dem Löschen Widgets: {[type(c) for c in self.annotation_frame.winfo_children()]}")

        # Neue Annotationen bauen
        tk.Label(self.annotation_frame, text=f"Annotationen für Token {idx}: \n '{json_dict.get('token','')}'", font=('Arial', 14, 'bold')).grid(row=0, column=0, sticky='w', pady=5, padx=5, columnspan=2)

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

        self.annotation_canvas.update_idletasks()
        self.annotation_canvas.configure(scrollregion=self.annotation_canvas.bbox('all'))


    def _json_speichern(self):
        try:
            zielpfad = os.path.join(config.GLOBALORDNER["manuell"], os.path.basename(self.dateipfad_json))
            with open(zielpfad, 'w', encoding='utf-8') as f:
                json.dump(self.json_dicts, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Erfolg", f"JSON erfolgreich gespeichert nach:\n{zielpfad}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Speichern:\n{str(e)}")


    def _on_canvas_resize(self, event):
        neue_breite = event.width
        print(f"Canvas wurde resized, neue Breite: {neue_breite}")
        self.renderer.max_breite = neue_breite
        self._zeichne_alle_tokens()

    def zeige_default_annotation_label(self):
        for child in self.annotation_frame.winfo_children():
            if child != self.default_annotation_label:
                child.destroy()
        self.default_annotation_label.grid()

    def _on_tab_changed(self, event):
        aktuelles_tab = event.widget.select()
        aktuelles_widget = event.widget.nametowidget(aktuelles_tab)

        # Alle Kinder des Tabs durchsuchen, um einen AnnotationenEditor zu finden
        for child in aktuelles_widget.winfo_children():
            if isinstance(child, AnnotationenEditor):
                child.zeige_default_annotation_label()

    def _toggle_filter(self, name):
        name = name.lower()
        if name in self.renderer.ignorierte_annotationen:
            self.renderer.ignorierte_annotationen.remove(name)
        else:
            self.renderer.ignorierte_annotationen.add(name)
        self._zeichne_alle_tokens()

    def _wechsel_datei(self, event=None):
        neue_index = self.dateiauswahl.current()
        if neue_index != self.current_index:
            self.current_index = neue_index
            self._lade_json_daten()
            self._zeichne_alle_tokens()