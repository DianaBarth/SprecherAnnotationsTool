import os
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
        """Erstellt die Widgets (Canvas links, Frame rechts) und richtet Scrollbar ein."""
        gesamt_breite, gesamt_hoehe = 1000, 700
        self.place(width=gesamt_breite, height=gesamt_hoehe)

        # Linke Seite: Canvas für Tokens mit vertikalem Scrollbalken
        token_breite = 700
        linker_frame = tk.Frame(self, width=token_breite, height=gesamt_hoehe)
        linker_frame.place(x=0, y=0)

        self.canvas = tk.Canvas(linker_frame, width=token_breite, height=gesamt_hoehe, bg='white')
        self.canvas.pack(side='left', fill='both', expand=True)

        scrollbar = ttk.Scrollbar(linker_frame, orient='vertical', command=self.canvas.yview)
        scrollbar.pack(side='right', fill='y')

        self.canvas.configure(yscrollcommand=scrollbar.set)
        # Scrollregion aktualisieren, wenn Canvasgröße sich ändert
        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

        # Rechte Seite: Frame für Annotationen/Details
        self.annotation_frame = ttk.Frame(self, width=gesamt_breite - token_breite, height=gesamt_hoehe)
        self.annotation_frame.place(x=token_breite, y=0)

        # Zeichne alle Tokens mit Marker
        self._zeichne_alle_tokens()

        # Scrollregion initial setzen
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _zeichne_alle_tokens(self):
        """Löscht und zeichnet alle Token-Elemente auf dem Canvas neu."""
        self.canvas.delete('all')
        self.renderer.positionen_zuruecksetzen()  # Interne Positionen im Renderer zurücksetzen

        # Rechts die Annotationen löschen
        for child in self.annotation_frame.winfo_children():
            child.destroy()

        # Jeden Token einzeln rendern
        for idx, json_dict in enumerate(self.json_dicts):
            naechstes_element = self.json_dicts[idx + 1] if idx + 1 < len(self.json_dicts) else None
            self.renderer.rendern(
                index=idx,
                gui_canvas=self.canvas,                
                naechstes_dict_element=naechstes_element,
                dict_element=json_dict
            )
            # Klick-Event für jeden Token-Tag binden, um Detailanzeige zu starten
            tag = f'token_{idx}'
            self.canvas.tag_bind(tag, '<Button-1>', lambda e, i=idx: self._on_token_click(i))

    def _on_token_click(self, idx):
        """Wird aufgerufen, wenn ein Token im Canvas angeklickt wird."""
        json_dict = self.json_dicts[idx]

           # Token visuell markieren (roten Rahmen)
        self.renderer.markiere_token_mit_rahmen(self.canvas, idx)

        # Rechte Seite vorher leeren
        for child in self.annotation_frame.winfo_children():
            child.destroy()

        # Token-Info anzeigen
        tk.Label(self.annotation_frame, text=f"Token {idx}: '{json_dict.get('token','')}'", font=('Arial', 14, 'bold')).pack(anchor='w', pady=5)

        # Beispiel: Alle Annotationen (Schlüssel außer 'token') als Buttons anzeigen
        for key, value in json_dict.items():
            if key == 'token':
                continue
            btn_text = f"{key}: {value}"
            btn = ttk.Button(self.annotation_frame, text=btn_text)
            btn.pack(anchor='w', pady=2, padx=5)
