# Datei: Annotationen_Editor.py
from tkinter import ttk
import json
import os
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont

import Eingabe.config as config  # deine config mit KI_AUFGABEN und AUFGABEN_ANNOTATIONEN
from annotationen_renderer import AnnotationRenderer

class AnnotationenEditor(ttk.Frame):
    def __init__(self, parent, notebook, dateipfad_json):
        super().__init__(parent)

        self.annotationsrenderer = AnnotationRenderer()
        self.notebook = notebook
        self.dateipfad_json = dateipfad_json

        self.tokens = []
        self.token_buttons = []
        self.annotation_buttons = {}
        self.aktiver_token_index = None

        self.load_json()
        self.build_ui()

    def load_json(self):
        with open(self.dateipfad_json, "r", encoding="utf-8") as f:
            self.tokens = json.load(f)

    def save_json(self):
        with open(self.dateipfad_json, "w", encoding="utf-8") as f:
            json.dump(self.tokens, f, indent=2, ensure_ascii=False)

    def build_ui(self):
        # Feste Maße für Layout
        editor_width = 1000
        editor_height = 700
        token_area_width = 700
        annotation_area_width = 300

        style = ttk.Style()
        style.configure("Token.TFrame", background="white")

        self.place(width=editor_width, height=editor_height)

        # --- Linker Bereich (Canvas + Scrollbar) ---
        frame_links = ttk.Frame(self, width=token_area_width, height=editor_height)
        frame_links.place(x=0, y=0)

        self.canvas = tk.Canvas(frame_links, width=token_area_width - 20, height=editor_height)
        self.vscroll = ttk.Scrollbar(frame_links, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.canvas.place(x=0, y=0, width=token_area_width - 20, height=editor_height)
        self.vscroll.place(x=token_area_width - 20, y=0, width=20, height=editor_height)
        
        self.tokens_frame = ttk.Frame(self.canvas, style="Token.TFrame")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.tokens_frame, anchor="nw")

        self.tokens_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        # --- Rechter Bereich (Annotationen) ---
        self.annotation_frame = ttk.Frame(self, width=annotation_area_width, height=editor_height)
        self.annotation_frame.place(x=token_area_width, y=0)

        self.annotation_frame.columnconfigure(0, weight=1)

        # Tokenbuttons erstellen
        self.build_token_buttons()
        # self.build_annotation_buttons()

        self.canvas.yview_moveto(0)

    def on_canvas_resize(self, event):
        # Token-Frame auf Canvas-Breite anpassen
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def build_token_buttons(self):      
        style = ttk.Style()            
        style.configure("Token.TButton", font=(config.SCHRIFTART_STANDARD, config.TEXT_GROESSE))

        for widget in self.tokens_frame.winfo_children():
            widget.destroy()

        # Canvas-Breite in Pixel (nach Update!)
        self.tokens_frame.update_idletasks()
        self.tokens_frame.config(width=2000, height=800)  # Testgröße
        canvas_width = self.canvas.winfo_width()
        if canvas_width <= 0:
            canvas_width = 800  # Fallback bei Fensterstart

        #Font-Messung (für ttk Buttons etwas größer kalkulieren)
        font = tkFont.nametofont("TkDefaultFont")
      
        x_pos = 0
        y_pos = 0
        self.token_buttons.clear()

        max_breite_pro_zeile = canvas_width - 20  # Puffer für Scrollbar

        for idx, eintrag in enumerate(self.tokens[:50]):
            annotation = eintrag.get("annotation", "")
            annotation_elemente = [a.strip().lower() for a in annotation.split(",")]
            print(f"annotation_elemente:{annotation_elemente}")

            # Zeilenumbruch oder kein Platz mehr?
            if "zeilenumbruch" in annotation_elemente or (x_pos > max_breite_pro_zeile):
                x_pos = 0
                y_pos += 70
                
            result = self.annotationsrenderer.render(idx, eintrag, self.tokens_frame,None,x_pos,y_pos)
            if result["token_button"]:
                self.token_buttons.append(result['token_button'])
                x_pos += result['pixel_breite']
    
        self.tokens_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.configure(bg="lightgrey")
        # token_rows = (len(self.tokens_data) // 20) + 1  # grobe Schätzung
        # self.tokens_frame.config(width=2000, height=token_rows * 40)

    def build_annotation_buttons(self):
        pass
        # # Löschen vorheriger Buttons
        # for w in self.annotation_frame.winfo_children():
        #     w.destroy()
        # self.annotation_buttons.clear()

        # row = 0
        # max_spalten = 4

        # for aufgaben_id, feld in config.KI_AUFGABEN.items():
        #     annot_liste = config.AUFGABEN_ANNOTATIONEN.get(aufgaben_id, [])
        #     label = ttk.Label(self.annotation_frame, text=f"{feld.capitalize()}:")
        #     label.grid(row=row, column=0, sticky="w", pady=(5, 0))
        #     row += 1
        #     col = 0

        #     for eintrag in annot_liste:
        #         name = eintrag["name"]
            
        #         if name:
        #             if name.lower() == "zeilenumbruch":
        #                 row += 1
        #                 col = 0
        #                 continue

                   
        #             zeichenlaenge = len(name) + 1  # Breite des Tokens

        #             btn = ttk.Button(self.annotation_frame, text=name, width=zeichenlaenge,
        #                             command=lambda f=feld, n=name: self.toggle_annotation(f, n))


        #             btn.grid(row=row, column=col, sticky="w", padx=5, pady=2)
        #             self.annotation_buttons.setdefault(feld, []).append(btn)

        #             col += 1
        #             if col >= max_spalten:
        #                 row += 1
        #                 col = 0
        #         else:
        #             if feld =="person":
        #                 pass
        #             #combobox
        #                #  btn = ttk.Button(self.annotation_frame, text=name, width=zeichenlaenge,
        #               #      command=lambda f=feld, n=name: self.toggle_annotation(f, n))

        #             #person: name = none

    def on_token_click(self, index):
        self.aktiver_token_index = index
        self.update_annotation_buttons_markierung()

    def update_annotation_buttons_markierung(self):
        if self.aktiver_token_index is None:
            return

        token = self.tokens[self.aktiver_token_index]
        for feld, buttons in self.annotation_buttons.items():
            wert = token.get(feld, "")
            for btn in buttons:
                name = btn.cget("text")
                if wert == name:
                    btn.state(["pressed"])
                else:
                    btn.state(["!pressed"])

    def toggle_annotation(self, feld, name):
        if self.aktiver_token_index is None:
            return

        token = self.tokens[self.aktiver_token_index]
        aktueller_wert = token.get(feld, "")
        if aktueller_wert == name:
            token[feld] = ""
        else:
            token[feld] = name
        self.update_annotation_buttons_markierung()
        self.save_json()

