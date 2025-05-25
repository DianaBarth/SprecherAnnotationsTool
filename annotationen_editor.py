import os
import json
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont

import Eingabe.config as config
from annotationen_renderer import AnnotationRenderer

class AnnotationenEditor(ttk.Frame):
    def __init__(self, parent, notebook, dateipfad_json):
        super().__init__(notebook)
        self.notebook = notebook
        self.dateipfad_json = dateipfad_json
        self.renderer = AnnotationRenderer(max_width=680)  # Max. Breite Canvas-Teil anpassen
        self.tokens = []
        self._load_tokens()
        self._build_widgets()

    def _load_tokens(self):
        with open(self.dateipfad_json, 'r', encoding='utf-8') as f:
            self.tokens = json.load(f)

    def _build_widgets(self):
        # Gesamtgröße
        total_w, total_h = 1000, 700
        self.place(width=total_w, height=total_h)

        # Linker Bereich: Canvas für Tokens + Marker
        token_w = 700
        frame = tk.Frame(self, width=token_w, height=total_h)
        frame.place(x=0, y=0)

        self.canvas = tk.Canvas(frame, width=token_w, height=total_h, bg='white')
        self.canvas.pack(side='left', fill='both', expand=True)
        vsb = ttk.Scrollbar(frame, orient='vertical', command=self.canvas.yview)
        vsb.pack(side='right', fill='y')
        self.canvas.configure(yscrollcommand=vsb.set)

        # Scrollregion aktualisieren, wenn das Canvas konfiguriert wird
        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

        # Rechter Bereich: Annotationinspector etc.
        self.annotation_frame = ttk.Frame(self, width=total_w - token_w, height=total_h)
        self.annotation_frame.place(x=token_w, y=0)

        # Zeichne alles
        self._draw_all()

        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _draw_all(self):
        self.canvas.delete('all')
        self.renderer.reset_positions()  # Positionen intern zurücksetzen

        # Rechte Seite vorher leeren
        for child in self.annotation_frame.winfo_children():
            child.destroy()

        # Die Tokens einzeln rendern, der Renderer kümmert sich um Zeilenumbruch & Position
        for idx, tok in enumerate(self.tokens):
            self.renderer.render(
                gui_parent=self.canvas,
                idx=idx,
                dict_element=tok
            )
            # Klick-Event per Tag binden: ruft _on_token_click auf
            tag = f'token_{idx}'
            self.canvas.tag_bind(tag, '<Button-1>', lambda e, i=idx: self._on_token_click(i))

        # Optional: Text oben links zum Test
        # self.canvas.create_text(10, 10, anchor='nw', text="Testinhalt", fill='black')

    def _on_token_click(self, idx):
        # Wenn Token angeklickt wird, zeige rechts die Annotationen zu diesem Token
        token = self.tokens[idx]
        # Rechte Seite vorher leeren
        for child in self.annotation_frame.winfo_children():
            child.destroy()

        tk.Label(self.annotation_frame, text=f"Token {idx}: '{token.get('token','')}'", font=('Arial', 14, 'bold')).pack(anchor='w', pady=5)

        # Beispiel: Alle Annotationen (Schlüssel außer "token") als Buttons anzeigen
        for key, value in token.items():
            if key == 'token':
                continue
            btn_text = f"{key}: {value}"
            btn = ttk.Button(self.annotation_frame, text=btn_text)
            btn.pack(anchor='w', pady=2, padx=5)
