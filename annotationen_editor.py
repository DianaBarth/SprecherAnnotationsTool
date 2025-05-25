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
        self.renderer = AnnotationRenderer()
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

        # Frame in Canvas (optional)
        self.inner = tk.Frame(self.canvas)
        self.win = self.canvas.create_window((0,0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.win, width=e.width))

        # Rechter Bereich: Annotationinspector etc.
        self.annotation_frame = ttk.Frame(self, width=total_w-token_w, height=total_h)
        self.annotation_frame.place(x=token_w, y=0)

        # Zeichne alles
        self._draw_all()

    def _draw_all(self):
        self.canvas.delete('all')
        font = tkFont.nametofont('TkDefaultFont')
        x, y = 10, 10
        line_h = font.metrics('linespace') + 20
        max_w = self.canvas.winfo_reqwidth() - 20
        prev_line = None

        for idx, tok in enumerate(self.tokens):
            token = tok.get('token', '')
            zeile = tok.get('zeile', 0)

            # Zeilenumbruch-Token
            if token == '':
                x = 10
                y += line_h
                prev_line = None
                continue

            # Neue Zeile, wenn Linienwechsel oder Überlauf
            if zeile != prev_line or x + font.measure(token) > max_w:
                x = 10
                y += line_h

            # Verwendung von AnnotationRenderer
            self.renderer.render_on_canvas(
                canvas=self.canvas,
                idx=idx,
                element=tok,
                x_pos=x,
                y_pos=y,
                prev_line=prev_line
            )

            # Klick-Event per Tag binden
            tag = f'token_{idx}'
            self.canvas.tag_bind(tag, '<Button-1>', lambda e, i=idx: print(f"Token {i} clicked"))

            # Abstand zum nächsten Token
            x += font.measure(token) + 10
            prev_line = zeile