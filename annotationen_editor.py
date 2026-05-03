import os
from pathlib import Path
import re
import json
import tkinter as tk
import ast
import yaml
import unicodedata
import copy
from datetime import date
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas as pdfcanvas
import Eingabe.config as config
from annotationen_renderer import AnnotationRenderer
from config_editor import register_custom_font
import personen_resolver


def _anzeige_name(wert: str) -> str:
    """
    Wandelt interne ASCII-Namen (z.B. 'Rechtsbuendig') in UI-Anzeigenamen ('Rechtsbündig') um.
    """
    return (wert
        .replace("Rechtsbuendig", "Rechtsbündig")
        .replace("Einrueckung", "Einrückung")
    )

def _interner_name(wert: str) -> str:
    """
    Wandelt UI-Namen (z.B. 'Rechtsbündig') zurück in ASCII-kompatible interne Namen ('Rechtsbuendig').
    """
    return (wert
        .replace("Rechtsbündig", "Rechtsbuendig")
        .replace("Einrückung", "Einrueckung")
    )

class AnnotationenEditor(ttk.Frame):
    def __init__(self, parent, notebook, kapitel_config):
        super().__init__(parent)
        self.notebook = notebook
        self.kapitel_config = kapitel_config

        # Kapitel-Liste aus config_editor holen
        if not kapitel_config.kapitel_liste and kapitel_config.kapitel_daten:
            self.kapitel_liste = list(kapitel_config.kapitel_daten.keys())
        else:
             self.kapitel_liste = kapitel_config.kapitel_liste 
        
        # Start mit erstem Hauptkapitel und erstem Abschnitt
        self.current_hauptkapitel_index = 0
        self.current_abschnitt_index = 0

        # Initiale Kapitelpfade noch leer, werden beim Laden gesetzt
        self.kapitel_pfade = []

        # Initialisiere weitere Variablen
        self.renderer = AnnotationRenderer()
        self.json_dicts = []
        self.alle_json_dicts = []
        self.index_to_wortnr = {}
        self.wortnr_to_index = {}
        self.wortnr_to_eintrag = {}
        self.undo_stack = []
        self.redo_stack = []
        self.filter_vars = {}
        self.use_number_words_var = tk.BooleanVar(value=True)
        self.personen_bereich_start_idx = None
        self.aktuell_gewaehlter_token_idx = None
        self.personen_bereich_ende_idx = None
        self.shortcut_icons = {}   
        self.sprecher_modus_var = tk.BooleanVar(value=False)
        self.rechts_frame= None

        self.in_takes_aufteilen_var = tk.BooleanVar(value=False)
        self.audioanalyse_anzeigen_var = tk.BooleanVar(value=False)

        # Widgets bauen
        self._erstelle_widgets()

        # Lade Pfade und JSON-Daten für das erste Hauptkapitel und ersten Abschnitt
        self._lade_kapitel_abschnitte()

    def _lade_json_daten(self):
        aktueller_pfad = self.kapitel_pfade[self.current_abschnitt_index]
        print(f"[Editor] Lade Daten für: {aktueller_pfad}")

        with open(aktueller_pfad, "r", encoding="utf-8") as f:
            daten = json.load(f)

        if not isinstance(daten, list):
            raise ValueError(f"JSON-Datei enthält keine Liste: {aktueller_pfad}")

        self.alle_json_dicts = daten
        self.dateipfad_json = aktueller_pfad

        kapitelname = str(self.kapitel_liste[self.current_hauptkapitel_index])
        print(f"[Editor] aktuelles Kapitel aus Combo: {kapitelname}")
        print(f"[Editor] Einträge gesamt: {len(self.alle_json_dicts)}")

        if self.alle_json_dicts:
            print("[Editor] Beispiel-Eintrag keys:", self.alle_json_dicts[0].keys())
            print("[Editor] Beispiel KapitelNummer:", self.alle_json_dicts[0].get("KapitelNummer"))
            print("[Editor] Beispiel WortNr:", self.alle_json_dicts[0].get("WortNr"))
            print("[Editor] Beispiel token:", self.alle_json_dicts[0].get("token"))

        gefiltert = [
            eintrag for eintrag in self.alle_json_dicts
            if isinstance(eintrag, dict)
            and self._eintrag_gehoert_zu_aktuellem_kapitel(eintrag)
        ]

        # WICHTIGER FALLBACK:
        # Wenn die Datei ohnehin schon kapitel-/abschnittsweise ist,
        # oder KapitelNummer nicht exakt passt, darf nichts leer werden.
        if not gefiltert and self.alle_json_dicts:
            print(
                "[Editor WARNUNG] Kapitel-Filter ergab 0 Einträge. "
                "Fallback: komplette Datei wird angezeigt."
            )
            gefiltert = [
                eintrag for eintrag in self.alle_json_dicts
                if isinstance(eintrag, dict)
            ]

        gefiltert.sort(
            key=lambda e: int(e.get("WortNr", 10**12))
            if str(e.get("WortNr", "")).isdigit()
            else 10**12
        )

        self.json_dicts = gefiltert
        self._baue_lokale_indexe()

        self.aktuell_gewaehlter_token_idx = None
        self.personen_bereich_start_idx = None
        self.personen_bereich_ende_idx = None

        print(
            f"[Editor] angezeigt={len(self.json_dicts)} "
            f"von gesamt={len(self.alle_json_dicts)}"
        )


    def _kapitel_id_aus_name(self, kapitel):
        """
        Nutzt den Index aus kapitel_liste.
        Vorwort -> 000
        1. Einstieg ... -> 001
        Nachwort -> z.B. 009
        """
        kapitel = str(kapitel).strip()

        try:
            idx = list(self.kapitel_liste).index(kapitel)
            return f"{idx:03d}"
        except ValueError:
            print(f"[Editor WARNUNG] Kapitel nicht in kapitel_liste gefunden: {kapitel!r}")
            return None
        
    def _lade_alle_kapiteldateien(self, kapitel):
        merge_ordner = config.GLOBALORDNER["merge"]
        manuell_ordner = config.GLOBALORDNER["manuell"]

        kapitel_id = self._kapitel_id_aus_name(kapitel)

        if not kapitel_id:
            return []

        # Neues Format:
        # 002_001.json
        neues_pattern = re.compile(rf"^{kapitel_id}_(\d{{3}})\.json$")

        # Altes Format bleibt als Fallback erlaubt:
        # 2. Aufbau der Welt (Kapitel IV–VI)_001_annotierungen.json
        kapitel_text = str(kapitel).strip()
        altes_pattern = re.compile(
            rf"^{re.escape(kapitel_text)}_(\d+)_annotierungen\.json$"
        )

        dateien_dict = {}

        def scan_ordner(ordner, quelle):
            if not os.path.isdir(ordner):
                print(f"[Editor WARNUNG] Ordner fehlt: {ordner}")
                return

            for dateiname in os.listdir(ordner):
                match = neues_pattern.match(dateiname) or altes_pattern.match(dateiname)

                if not match:
                    continue

                abschnitt_idx = int(match.group(1))
                pfad = os.path.join(ordner, dateiname)

                # manuell überschreibt merge
                if quelle == "manuell" or abschnitt_idx not in dateien_dict:
                    dateien_dict[abschnitt_idx] = pfad

        scan_ordner(merge_ordner, "merge")
        scan_ordner(manuell_ordner, "manuell")

        print(f"[Editor] Kapitel: {kapitel}")
        print(f"[Editor] Kapitel-ID: {kapitel_id}")
        print(f"[Editor] gefundene Abschnitte: {dateien_dict}")

        return [dateien_dict[idx] for idx in sorted(dateien_dict.keys())]

    def _lade_kapitel_abschnitte(self):
        kapitelname = self.kapitel_liste[self.current_hauptkapitel_index]

        self.kapitel_pfade = self._lade_alle_kapiteldateien(kapitelname)

        abschnittswerte = [f"Abschnitt {i+1}" for i in range(len(self.kapitel_pfade))]
        self.abschnitt_combo['values'] = abschnittswerte

        if abschnittswerte:
            self.abschnitt_combo.current(0)
            self.current_abschnitt_index = 0
            self._lade_json_daten()
            self._zeichne_alle_tokens()
            self.canvas.update_idletasks()
        else:
            # Kein Abschnitt vorhanden: Auswahl zurücksetzen, ggf. Daten leeren
            self.abschnitt_combo.set('')
            self.json_dicts = []
            self.canvas.delete('all')
            self.default_annotation_label.grid()


    def _erstelle_widgets(self):
        self.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)
        self.rowconfigure(4, weight=1)

        # ---------------------------
        # 1. Zeile: Kapitel + Buttons
        # ---------------------------
        top_frame = ttk.Frame(self)
        top_frame.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        max_len = max((len(str(k)) for k in self.kapitel_liste), default=5)

        self.hauptkapitel_combo = ttk.Combobox(
            top_frame,
            values=self.kapitel_liste,
            state="readonly",
            width=max(max_len, 20)
        )
        self.hauptkapitel_combo.current(self.current_hauptkapitel_index)
        self.hauptkapitel_combo.grid(row=0, column=0, padx=(0, 10))
        self.hauptkapitel_combo.bind("<<ComboboxSelected>>", self._hauptkapitel_gewechselt)

        self.abschnitt_combo = ttk.Combobox(top_frame, values=[], state="readonly")
        self.abschnitt_combo.grid(row=0, column=1)
        self.abschnitt_combo.bind("<<ComboboxSelected>>", self._abschnitt_gewechselt)

        speichern_button = ttk.Button(top_frame, text="JSON speichern", command=self._json_speichern)
        speichern_button.grid(row=0, column=3)

        export_button = ttk.Button(top_frame, text="Exportiere als PDF", command=self._exportiere_pdf)
        export_button.grid(row=0, column=4, padx=(10, 0))

        sprecher_button = ttk.Checkbutton(
            top_frame,
            text="Sprecher-Modus",
            variable=self.sprecher_modus_var,
            command=self._toggle_sprecher_modus
        )
        sprecher_button.grid(row=0, column=5, padx=(10, 0))

        # ---------------------------
        # 2. Zeile: Zahlwörter
        # ---------------------------
        top_frame_2 = ttk.Frame(self)
        top_frame_2.grid(row=1, column=0, sticky="w", padx=5, pady=(5, 0))

        zahlwoerter_checkbox = ttk.Checkbutton(
            top_frame_2,
            text="Verwende Zahlwörter",
            variable=self.use_number_words_var,
            command=self._zeichne_alle_tokens
        )
        zahlwoerter_checkbox.grid(row=0, column=0, sticky="w")

        takes_checkbox = ttk.Checkbutton(
            top_frame_2,
            text="In Takes aufteilen",
            variable=self.in_takes_aufteilen_var,
            command=self._zeichne_alle_tokens
        )
        takes_checkbox.grid(row=0, column=1, sticky="w", padx=(15, 0))


        audioanalyse_checkbox = ttk.Checkbutton(
            top_frame_2,
            text="Audioanalyse anzeigen",
            variable=self.audioanalyse_anzeigen_var,
            command=self._zeichne_alle_tokens
        )
        audioanalyse_checkbox.grid(row=0, column=3, sticky="w", padx=(15, 0))

        # ---------------------------
        # 3. Zeile: Filter (NEU!)
        # ---------------------------
        top_frame_3 = ttk.Frame(self)
        top_frame_3.grid(row=2, column=0, sticky="w", padx=5, pady=(10, 0))

        filter_label = ttk.Label(top_frame_3, text="Annotationen ausblenden für:")
        filter_label.grid(row=0, column=0, sticky="w", padx=(0, 10))

        col = 1

        self.filter_vars = {}

        for feldname, definition in config.RECORDING_ANNOTATIONEN.items():
            var = tk.BooleanVar(value=False)
            self.filter_vars[feldname] = var

            btn = ttk.Checkbutton(
                top_frame_3,
                text=definition["label"],
                variable=var,
                command=self._zeichne_alle_tokens
            )
            btn.grid(row=0, column=col, sticky="w", padx=2)
            col += 1

        # ---------------------------
        # 4. Spacer
        # ---------------------------
        spacer = ttk.Frame(self)
        spacer.grid(row=3, column=0, sticky="ew", pady=5)

        # ---------------------------
        # 5. Canvas + Sidebar
        # ---------------------------
        canvas_frame = ttk.Frame(self)
        canvas_frame.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)

        canvas_frame.columnconfigure(0, weight=25)
        canvas_frame.columnconfigure(1, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        # Canvas links
        linker_frame = ttk.Frame(canvas_frame)
        linker_frame.grid(row=0, column=0, sticky='nsew')

        linker_frame.columnconfigure(0, weight=1)
        linker_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(linker_frame, bg='white')
        self.canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar_links = ttk.Scrollbar(linker_frame, orient='vertical', command=self.canvas.yview)
        scrollbar_links.grid(row=0, column=1, sticky='ns')

        self.canvas.configure(yscrollcommand=scrollbar_links.set)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Sidebar rechts
        self.rechts_frame= ttk.Frame(canvas_frame)
        self.rechts_frame.grid(row=0, column=1, sticky='nsew')

        self.rechts_frame.columnconfigure(0, weight=1)
        self.rechts_frame.rowconfigure(0, weight=1)

        self.annotation_canvas = tk.Canvas(self.rechts_frame)
        self.annotation_canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar_rechts = ttk.Scrollbar(self.rechts_frame, orient='vertical', command=self.annotation_canvas.yview)
        scrollbar_rechts.grid(row=0, column=1, sticky='ns')

        self.annotation_canvas.configure(yscrollcommand=scrollbar_rechts.set)

        self.annotation_frame = ttk.Frame(self.annotation_canvas)
        self.annotation_canvas.create_window((0, 0), window=self.annotation_frame, anchor='nw')

        self.annotation_frame.columnconfigure(0, weight=1)
        self.annotation_frame.columnconfigure(1, weight=1)

        self.annotation_frame.bind(
            "<Configure>",
            lambda e: self.annotation_canvas.configure(
                scrollregion=self.annotation_canvas.bbox('all')
            )
        )

        self.default_annotation_label = ttk.Label(
            self.annotation_frame,
            text="Bitte Wort auswählen, um Annotationen zu bearbeiten",
            foreground="gray",
            font=('Arial', 12, 'italic'),
            wraplength=150,
            justify='left'
        )

        self.default_annotation_label.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky='nw')

        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
      
        self._registriere_shortcuts()

    def _zeichne_alle_tokens(self):
        self.canvas.delete('all')
        self.renderer.positionen_zuruecksetzen()
        self._baue_lokale_indexe()
        
        aktive_filter = [name for name, var in self.filter_vars.items() if var.get()]
        self.renderer.ignorierte_annotationen = set(a.lower() for a in aktive_filter)
        self.renderer.use_number_words = self.use_number_words_var.get()

        self.renderer.take_umbruch_indices = (
            self._berechne_take_umbruch_indices()
            if self.in_takes_aufteilen_var.get()
            else {}
        )

        self.renderer.audioanalyse_anzeigen = self.audioanalyse_anzeigen_var.get()

        self.renderer.satzanalyse_map = (
            self._lade_satzanalyse_map()
            if self.audioanalyse_anzeigen_var.get()
            else {}
        )

        for idx, json_dict in enumerate(self.json_dicts):
            naechstes_element = self.json_dicts[idx + 1] if idx + 1 < len(self.json_dicts) else None
            try:
                print(
                    f"[Editor] render token idx={idx} "
                    f"token='{json_dict.get('token', '')}' "
                    f"person='{json_dict.get(config.KI_AUFGABEN.get(3, ''), '')}'"
                )

                self.renderer.rendern(
                    index=idx,
                    gui_canvas=self.canvas,
                    naechstes_dict_element=naechstes_element,
                    dict_element=json_dict
                )

                tag = f'token_{idx}'
                self.canvas.tag_bind(tag, '<Button-1>', lambda e, i=idx: self._on_token_click(i))

            except Exception as e:
                print(f"[Editor] FEHLER beim Rendern von Token idx={idx} token='{json_dict.get('token', '')}': {e}")
                import traceback
                traceback.print_exc()
                break


    def _on_token_click(self, idx):
        print(f"Token {idx} wurde angeklickt.")

        # Bereichslogik für sprechende Person:
        # 1. Klick = Start merken
        # 2. Klick = Ende setzen
        if self.personen_bereich_start_idx is None:
            self.personen_bereich_start_idx = idx
            self.personen_bereich_ende_idx = None
        elif self.personen_bereich_ende_idx is None:
            self.personen_bereich_ende_idx = idx
        else:
            # Neuer Bereich beginnt
            self.personen_bereich_start_idx = idx
            self.personen_bereich_ende_idx = None

        self.aktuell_gewaehlter_token_idx = idx
        self.default_annotation_label.grid_forget()

        json_dict = self.json_dicts[idx]
        self.renderer.markiere_token_mit_rahmen(self.canvas, idx)

        self.kapitel_name = self.kapitel_liste[self.current_hauptkapitel_index]

        print(f"Vor dem Löschen Widgets im annotation_frame: {[type(c) for c in self.annotation_frame.winfo_children()]}")
        for child in self.annotation_frame.winfo_children():
            if child != self.default_annotation_label:
                child.destroy()
        self.annotation_frame.update_idletasks()
        print(f"Nach dem Löschen Widgets: {[type(c) for c in self.annotation_frame.winfo_children()]}")

        wort_nr = self.index_to_wortnr.get(idx, json_dict.get("WortNr"))

        tk.Label(
            self.annotation_frame,
            text=f"Annotationen für WortNr {wort_nr}: \n '{json_dict.get('token','')}'",
            font=('Arial', 14, 'bold')
        ).grid(row=0, column=0, sticky='w', pady=5, padx=5, columnspan=2)

        # Statuszeile für Personenbereich
        status_text = None
        if self.personen_bereich_start_idx is not None and self.personen_bereich_ende_idx is None:
            status_text = (
                f"Sprecherbereich: Start bei Token {self.personen_bereich_start_idx}. "
                f"Jetzt anderes Wort anklicken und dann Person auswählen."
            )
        elif (
            self.personen_bereich_start_idx is not None
            and self.personen_bereich_ende_idx is not None
        ):
            a = self.personen_bereich_start_idx
            b = self.personen_bereich_ende_idx
            status_text = f"Sprecherbereich gewählt: Token {min(a,b)} bis {max(a,b)}. Jetzt Person auswählen."

        row_index = 1
        if status_text:
            ttk.Label(
                self.annotation_frame,
                text=status_text,
                foreground="gray",
                wraplength=260,
                justify='left'
            ).grid(row=row_index, column=0, columnspan=2, sticky='w', padx=5, pady=(0, 8))
            row_index += 1

       

        personen_werte = self._lade_personen_fuer_aktuellen_abschnitt()
        print("[DEBUG] personen_werte:", personen_werte)
        
        for feldname, definition in config.RECORDING_ANNOTATIONEN.items():
            label = ttk.Label(self.annotation_frame, text=definition["label"])
            label.grid(row=row_index, column=0, sticky='w', padx=5, pady=2)

            values_def = definition.get("values", [])

            if values_def == "personen":
                werte = personen_werte[:]
            elif values_def and isinstance(values_def[0], dict):
                werte = [e.get("name", "") for e in values_def if e.get("name")]
            else:
                werte = [str(e) for e in values_def if e is not None]

            if "" not in werte:
                werte.append("")

            aktueller_wert = json_dict.get(feldname, "")

            anzeige_werte = [_anzeige_name(w) for w in werte]
            anzeige_aktueller_wert = _anzeige_name(aktueller_wert)

            combobox = ttk.Combobox(
                self.annotation_frame,
                values=anzeige_werte,
                state="readonly"
            )
            combobox.set(anzeige_aktueller_wert)

            def on_combobox_change(event, feldname=feldname, combobox=combobox):
                neuer_wert = _interner_name(combobox.get()) or ""
                self._push_undo_state()

                if feldname == "person":
                    start_idx = self.personen_bereich_start_idx
                    end_idx = self.personen_bereich_ende_idx

                    if start_idx is None:
                        start_idx = idx
                    if end_idx is None:
                        end_idx = idx

                    self._setze_person_im_bereich(start_idx, end_idx, neuer_wert)
                    return

                json_dict[feldname] = neuer_wert

                if feldname == "position":
                    self._zeichne_alle_tokens()
                else:
                    self.renderer.annotation_aendern(self.canvas, idx, feldname, json_dict)

            combobox.bind("<<ComboboxSelected>>", on_combobox_change)
            combobox.grid(row=row_index, column=1, sticky='ew', padx=10, pady=2)

            row_index += 1

        
        shortcut_frame = ttk.Frame(self.annotation_frame)
        shortcut_frame.grid(
            row=row_index,
            column=0,
            columnspan=2,
            sticky="w",
            padx=5,
            pady=(12, 5)
        )

        ttk.Label(
            shortcut_frame,
            text="Annotationen:",
            foreground="gray",
            font=("Arial", 9, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        r = 1

        for key, (feldname, wert) in config.ANNOTATION_SHORTCUTS.items():
            bildname = self._hole_bild_fuer_annotation(feldname, wert)
            icon = self._lade_shortcut_icon(bildname)

            ttk.Label(
                shortcut_frame,
                text=f"{key.upper()} =",
                foreground="gray",
                font=("Arial", 9)
            ).grid(row=r, column=0, sticky="w")

            if icon:
                ttk.Label(
                    shortcut_frame,
                    image=icon
                ).grid(row=r, column=1, sticky="w", padx=(4, 4))

            ttk.Label(
                shortcut_frame,
                text=wert,
                foreground="gray",
                font=("Arial", 9)
            ).grid(row=r, column=2, sticky="w")

            r += 1

        ttk.Label(
            shortcut_frame,
            text="",
        ).grid(row=r, column=0)
        r += 1

        ttk.Label(
            shortcut_frame,
            text="Bedienung:",
            foreground="gray",
            font=("Arial", 9, "bold")
        ).grid(row=r, column=0, columnspan=3, sticky="w")
        r += 1

        for shortcut_def in config.UI_SHORTCUTS.values():
            label = shortcut_def.get("label", "")
            desc = shortcut_def.get("description", "")

            ttk.Label(
                shortcut_frame,
                text=f"{label} = {desc}",
                foreground="gray",
                font=("Arial", 9)
            ).grid(row=r, column=0, columnspan=3, sticky="w")

            r += 1


        self.annotation_canvas.update_idletasks()
        self.annotation_canvas.configure(scrollregion=self.annotation_canvas.bbox('all'))

        # Speichern
        self.bind_all("<Control-s>", lambda e: self._json_speichern())

        # Undo / Redo
        self.bind_all("<Control-z>", self._undo)
        self.bind_all("<Control-y>", self._redo)
        self.bind_all("<Control-Shift-Z>", self._redo)

        # Auswahl / Navigation
        self.bind_all("<Left>", lambda e: self._waehle_token_delta(-1))
        self.bind_all("<Right>", lambda e: self._waehle_token_delta(1))
        self.bind_all("<Control-Left>", lambda e: self._waehle_token_delta(-5))
        self.bind_all("<Control-Right>", lambda e: self._waehle_token_delta(5))

        # Annotation löschen für aktuelles Wort
        self.bind_all("<Delete>", self._loesche_annotationen_aktuelles_wort)

        # Abschnitt wechseln
        self.bind_all("<Alt-Left>", lambda e: self._wechsle_abschnitt(-1))
        self.bind_all("<Alt-Right>", lambda e: self._wechsle_abschnitt(1))

        # PDF Export
        self.bind_all("<Control-e>", lambda e: self._exportiere_pdf())

    def _json_speichern(self):
        try:
            zielpfad = os.path.join(
                config.GLOBALORDNER["manuell"],
                os.path.basename(self.dateipfad_json)
            )

            daten_zum_speichern = (
                self.alle_json_dicts
                if getattr(self, "alle_json_dicts", None)
                else self.json_dicts
            )

            with open(zielpfad, "w", encoding="utf-8") as f:
                json.dump(daten_zum_speichern, f, ensure_ascii=False, indent=2)

            messagebox.showinfo("Erfolg", f"JSON erfolgreich gespeichert nach:\n{zielpfad}")

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Speichern:\n{str(e)}")


    def _on_canvas_resize(self, event):
        self.renderer.max_breite = event.width

        if hasattr(self, "_resize_after_id"):
            self.after_cancel(self._resize_after_id)

        self._resize_after_id = self.after(200, self._zeichne_alle_tokens)

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

    def _hauptkapitel_gewechselt(self, event):
        self.current_hauptkapitel_index = self.hauptkapitel_combo.current()
        self.current_abschnitt_index = 0
        self.aktuell_gewaehlter_token_idx = None
        self.personen_bereich_start_idx = None
        self.personen_bereich_ende_idx = None
        self._lade_kapitel_abschnitte()
        self.zeige_default_annotation_label()


    def _abschnitt_gewechselt(self, event):
        self.current_abschnitt_index = self.abschnitt_combo.current()
        self.aktuell_gewaehlter_token_idx = None
        self.personen_bereich_start_idx = None
        self.personen_bereich_ende_idx = None
        self._lade_json_daten()
        self._zeichne_alle_tokens()
        self.zeige_default_annotation_label()

    def _exportiere_pdf(self):
      
        hauptkapitel = self.kapitel_liste[self.current_hauptkapitel_index]
        abschnitt = self.abschnitt_combo.get() or f"abschnitt_{self.current_abschnitt_index}"
        dateiname = f"{hauptkapitel}_{abschnitt}.pdf".replace(" ", "_").replace("/", "_")
        pfad = os.path.join(config.GLOBALORDNER["pdf2"], dateiname)

        c = pdfcanvas.Canvas(pfad)

        # Einstellungen übernehmen
        aktive_filter = [name for name, var in self.filter_vars.items() if var.get()]
        self.renderer.ignorierte_annotationen = set(a.lower() for a in aktive_filter)
        self.renderer.use_number_words = self.use_number_words_var.get()

        # Entferne Seitenumbruch: alle Elemente werden auf EINER Seite gezeichnet
        for idx, json_dict in enumerate(self.json_dicts):
            naechstes_element = self.json_dicts[idx + 1] if idx + 1 < len(self.json_dicts) else None
            self.renderer.rendern(
                index=idx,
                dict_element=json_dict,
                naechstes_dict_element=naechstes_element,
                gui_canvas=None,
                pdf_canvas=c
            )
        c.save()
        print(f"[PDF Export] gespeichert unter: {pfad}")
  
    
    def _get_personen_feldname(self):
        return config.KI_AUFGABEN.get(
            getattr(config, "PERSON_AUFGABE_ID", 4),
            "person"
        )
    def _setze_person_im_bereich(self, start_idx, end_idx, personenname):
        if start_idx is None:
            return

        if not self.json_dicts:
            return

        if end_idx is None:
            end_idx = start_idx

        start_idx = max(0, min(start_idx, len(self.json_dicts) - 1))
        end_idx = max(0, min(end_idx, len(self.json_dicts) - 1))

        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        personen_feldname = self._get_personen_feldname()

        print(
            f"[AnnotationenEditor] Setze Person '{personenname}' "
            f"im lokalen Bereich {start_idx} bis {end_idx}"
        )

        for i in range(start_idx, end_idx + 1):
            eintrag = self.json_dicts[i]

            if personenname:
                eintrag[personen_feldname] = personenname
            else:
                eintrag.pop(personen_feldname, None)

        self.personen_bereich_start_idx = None
        self.personen_bereich_ende_idx = None

        self._zeichne_alle_tokens()
        self._on_token_click(end_idx)     

    def _lade_personen_fuer_aktuellen_abschnitt(self):
        try:
            dateipfad = getattr(self, "dateipfad_json", None)

            if not dateipfad:
                print("[AnnotationenEditor] Kein dateipfad_json gesetzt.")
                return []

            if hasattr(personen_resolver, "lade_personen_fuer_datei"):
                personen = personen_resolver.lade_personen_fuer_datei(
                    self.kapitel_config,
                    dateipfad
                )
                print("[AnnotationenEditor] personen_werte:", personen)
                return personen

            if hasattr(personen_resolver, "lade_personen_fuer_datei_ohne_kapitel_config"):
                personen = personen_resolver.lade_personen_fuer_datei_ohne_kapitel_config(
                    dateipfad
                )
                print("[AnnotationenEditor] personen_werte:", personen)
                return personen

        except Exception as e:
            print(f"[AnnotationenEditor] Personen konnten nicht geladen werden: {e}")
            import traceback
            traceback.print_exc()

        return []
    
    def _push_undo_state(self):
        self.undo_stack.append(copy.deepcopy(self.json_dicts))
        self.redo_stack.clear()

        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)


    def _undo(self, event=None):
        if not self.undo_stack:
            return

        self.redo_stack.append(copy.deepcopy(self.json_dicts))
        self.json_dicts = self.undo_stack.pop()

        self._zeichne_alle_tokens()
        self.zeige_default_annotation_label()


    def _redo(self, event=None):
        if not self.redo_stack:
            return

        self.undo_stack.append(copy.deepcopy(self.json_dicts))
        self.json_dicts = self.redo_stack.pop()

        self._zeichne_alle_tokens()
        self.zeige_default_annotation_label()

    def _waehle_token_delta(self, delta):
        if self.aktuell_gewaehlter_token_idx is None:
            idx = 0
        else:
            idx = self.aktuell_gewaehlter_token_idx + delta

        idx = max(0, min(idx, len(self.json_dicts) - 1))
        self._on_token_click(idx)

    def _shortcut_annotation_setzen(self, event):
        key = event.keysym.lower()

        if key not in config.ANNOTATION_SHORTCUTS:
            return

        if self.aktuell_gewaehlter_token_idx is None:
            return

        feldname, wert = config.ANNOTATION_SHORTCUTS[key]

        idx = self.aktuell_gewaehlter_token_idx
        json_dict = self.json_dicts[idx]

        self._push_undo_state()

        if json_dict.get(feldname) == wert:
            json_dict[feldname] = ""
        else:
            json_dict[feldname] = wert

        if feldname == "position":
            self._zeichne_alle_tokens()
        else:
            self.renderer.annotation_aendern(
                self.canvas,
                idx,
                feldname,
                json_dict
            )

        self._on_token_click(idx)


    def _registriere_shortcuts(self):
        self.bind_all("<Key>", self._shortcut_annotation_setzen)

        action_map = {
            "toggle_speaker_mode": lambda e: self._shortcut_toggle_sprecher_modus(),
            "save": lambda e: self._json_speichern(),
            "undo": self._undo,
            "redo": self._redo,
            "token_prev": lambda e: self._waehle_token_delta(-1),
            "token_next": lambda e: self._waehle_token_delta(1),
            "line_up": lambda e: self._springe_zeile("hoch"),
            "line_down": lambda e: self._springe_zeile("runter"),
            "token_prev_5": lambda e: self._waehle_token_delta(-5),
            "token_next_5": lambda e: self._waehle_token_delta(5),
            "delete_current_annotations": self._loesche_annotationen_aktuelles_wort,
            "section_prev": lambda e: self._wechsle_abschnitt(-1),
            "section_next": lambda e: self._wechsle_abschnitt(1),
            "export_pdf": lambda e: self._exportiere_pdf(),
            
        }

        for sequence, shortcut_def in config.UI_SHORTCUTS.items():
            action_name = shortcut_def.get("action")
            callback = action_map.get(action_name)

            if not callback:
                print(f"[Shortcuts] Unbekannte Aktion: {action_name}")
                continue

            if len(sequence) == 1:
                self.bind_all(sequence, callback)
            else:
                self.bind_all(sequence, callback)


    def _loesche_annotationen_aktuelles_wort(self, event=None):
        idx = self.aktuell_gewaehlter_token_idx

        if idx is None or idx < 0 or idx >= len(self.json_dicts):
            return

        self._push_undo_state()

        json_dict = self.json_dicts[idx]

        for feldname in config.RECORDING_ANNOTATIONEN.keys():
            # position bei Delete  NICHT löschen
            if feldname == "position":
                continue

            json_dict[feldname] = ""

        self._zeichne_alle_tokens()
        self._on_token_click(idx)

    def _lade_shortcut_icon(self, bildname, size=(14, 14)):
        if not bildname:
            return None

        key = (bildname, size)
        if key in self.shortcut_icons:
            return self.shortcut_icons[key]

        pfad = os.path.join(config.GLOBALORDNER["Eingabe"], "bilder", bildname)

        try:
            img = Image.open(pfad)
            img = img.resize(size)
            tk_img = ImageTk.PhotoImage(img)
            self.shortcut_icons[key] = tk_img
            return tk_img
        except Exception:
            return None


    def _hole_bild_fuer_annotation(self, feldname, wert):
        for annot in config.ANNOTATIONEN.get(feldname, []):
            if annot.get("name") == wert:
                return annot.get("bild")
        return None
    
    def _springe_zeile(self, richtung):
        if self.aktuell_gewaehlter_token_idx is None:
            return

        aktuelle_idx = self.aktuell_gewaehlter_token_idx
        aktuelle_pos = self.renderer.canvas_elemente_pro_token.get(aktuelle_idx)

        if not aktuelle_pos:
            return

        aktuelle_y = aktuelle_pos["y"]

        kandidaten = []

        for idx, pos in self.renderer.canvas_elemente_pro_token.items():
            y = pos["y"]

            if richtung == "hoch" and y < aktuelle_y:
                kandidaten.append((abs(y - aktuelle_y), idx, y))
            elif richtung == "runter" and y > aktuelle_y:
                kandidaten.append((abs(y - aktuelle_y), idx, y))

        if not kandidaten:
            return

        # Nächste Zeile finden (kleinster Abstand)
        kandidaten.sort(key=lambda x: x[0])

        ziel_y = kandidaten[0][2]

        # Jetzt Token auf dieser Zeile wählen (ähnlich gleiche X-Position)
        aktuelle_x = aktuelle_pos["x"]

        gleiche_zeile = [
            (abs(pos["x"] - aktuelle_x), idx)
            for idx, pos in self.renderer.canvas_elemente_pro_token.items()
            if pos["y"] == ziel_y
        ]

        if not gleiche_zeile:
            return

        gleiche_zeile.sort(key=lambda x: x[0])

        ziel_idx = gleiche_zeile[0][1]

        self._on_token_click(ziel_idx)

    def _toggle_sprecher_modus(self):
        if not self.rechts_frame:
            return

        if self.sprecher_modus_var.get():
            self.rechts_frame.grid_remove()
        else:
            self.rechts_frame.grid(row=0, column=1, sticky="nsew")

    def _shortcut_toggle_sprecher_modus(self, event=None):
        self.sprecher_modus_var.set(not self.sprecher_modus_var.get())
        self._toggle_sprecher_modus()
        return "break"
    
    def _aktuelle_kapitelnummer_kandidaten(self):
        kapitelname = str(self.kapitel_liste[self.current_hauptkapitel_index])
        idx = int(self.current_hauptkapitel_index)

        kandidaten = {
            kapitelname,
            kapitelname.strip(),
            str(idx),
            idx,
            f"{idx:03d}",
        }

        # Fallback für alte Daten, falls früher 1-basiert gespeichert wurde
        kandidaten.add(str(idx + 1))
        kandidaten.add(idx + 1)

        match = re.search(r"(\d+)", kapitelname)
        if match:
            nummer = match.group(1)
            kandidaten.add(nummer)
            kandidaten.add(str(int(nummer)))
            kandidaten.add(int(nummer))

        return kandidaten

    def _eintrag_gehoert_zu_aktuellem_kapitel(self, eintrag):
        # Wenn kein KapitelNummer-Feld vorhanden ist:
        # Datei als bereits passenden Abschnitt behandeln.
        if "KapitelNummer" not in eintrag:
            return True

        wert = eintrag.get("KapitelNummer")

        # Leere KapitelNummer ebenfalls nicht rausfiltern
        if wert in (None, ""):
            return True

        kandidaten = self._aktuelle_kapitelnummer_kandidaten()

        wert_str = str(wert).strip()
        kandidaten_str = {str(k).strip() for k in kandidaten}

        return wert_str in kandidaten_str

    def _baue_lokale_indexe(self):
        self.index_to_wortnr = {}
        self.wortnr_to_index = {}
        self.wortnr_to_eintrag = {}

        for idx, eintrag in enumerate(self.json_dicts):
            wortnr = eintrag.get("WortNr")

            self.index_to_wortnr[idx] = wortnr

            if wortnr is not None:
                self.wortnr_to_index[wortnr] = idx
                self.wortnr_to_eintrag[wortnr] = eintrag

    def _ist_wort_token(self, eintrag):
        token = str(eintrag.get("token", "")).strip()
        return bool(token) and re.search(r"\w", token, re.UNICODE)


    def _ist_satzende(self, eintrag):
        token = str(eintrag.get("token", "")).strip()
        return token in {".", "!", "?", "…"} or token.endswith((".", "!", "?", "…"))


    def _hat_echten_zeilenumbruch(self, eintrag):
        annotation = eintrag.get("annotation", "")

        if isinstance(annotation, dict):
            return "zeilenumbruch" in {str(k).lower() for k in annotation.keys()}

        if isinstance(annotation, list):
            return any(str(a).lower() == "zeilenumbruch" for a in annotation)

        return "zeilenumbruch" in str(annotation).lower()


    def _berechne_take_umbruch_indices(self):
        MIN_WOERTER = 50
        OPTIMAL_MIN = 70
        OPTIMAL_MAX = 120
        MAX_WOERTER = 170

        breaks = {}

        take_woerter = 0
        take_nr = 1

        aktueller_take_start_satz_nr = 1
        satz_nr = 1

        kandidat_idx = None
        kandidat_wortzahl = None
        kandidat_end_satz_nr = None

        for idx, eintrag in enumerate(self.json_dicts):
            if self._hat_echten_zeilenumbruch(eintrag):
                if take_woerter > 0 and idx + 1 < len(self.json_dicts):
                    end_satz_nr = max(aktueller_take_start_satz_nr, satz_nr)

                    take_nr += 1
                    breaks[idx + 1] = {
                        "take_nr": take_nr,
                        "wortanzahl": take_woerter,
                        "start_satz_nr": aktueller_take_start_satz_nr,
                        "end_satz_nr": end_satz_nr,
                        "grund": "manueller_zeilenumbruch",
                    }

                    aktueller_take_start_satz_nr = end_satz_nr + 1

                take_woerter = 0
                kandidat_idx = None
                kandidat_wortzahl = None
                kandidat_end_satz_nr = None
                continue

            if self._ist_wort_token(eintrag):
                take_woerter += 1

            if not self._ist_satzende(eintrag):
                continue

            aktueller_satz_nr = satz_nr
            satz_nr += 1

            if OPTIMAL_MIN <= take_woerter <= OPTIMAL_MAX:
                if idx + 1 < len(self.json_dicts):
                    take_nr += 1
                    breaks[idx + 1] = {
                        "take_nr": take_nr,
                        "wortanzahl": take_woerter,
                        "start_satz_nr": aktueller_take_start_satz_nr,
                        "end_satz_nr": aktueller_satz_nr,
                        "grund": "optimal",
                    }

                    aktueller_take_start_satz_nr = aktueller_satz_nr + 1

                take_woerter = 0
                kandidat_idx = None
                kandidat_wortzahl = None
                kandidat_end_satz_nr = None
                continue

            if MIN_WOERTER <= take_woerter < OPTIMAL_MIN:
                kandidat_idx = idx
                kandidat_wortzahl = take_woerter
                kandidat_end_satz_nr = aktueller_satz_nr

            if take_woerter >= MAX_WOERTER:
                ziel_idx = kandidat_idx if kandidat_idx is not None else idx
                wortzahl = kandidat_wortzahl if kandidat_wortzahl is not None else take_woerter
                end_satz_nr = kandidat_end_satz_nr if kandidat_end_satz_nr is not None else aktueller_satz_nr

                if ziel_idx + 1 < len(self.json_dicts):
                    take_nr += 1
                    breaks[ziel_idx + 1] = {
                        "take_nr": take_nr,
                        "wortanzahl": wortzahl,
                        "start_satz_nr": aktueller_take_start_satz_nr,
                        "end_satz_nr": end_satz_nr,
                        "grund": "maximum",
                    }

                    aktueller_take_start_satz_nr = end_satz_nr + 1

                take_woerter = 0
                kandidat_idx = None
                kandidat_wortzahl = None
                kandidat_end_satz_nr = None

        return breaks
    
    def _lade_satzanalyse_map(self):
        try:
            audioanalyse_ordner = config.GLOBALORDNER.get("audioanalyse")
            if not audioanalyse_ordner:
                return {}

            basis = Path(self.dateipfad_json).stem  # z.B. 002_001
            pfad = Path(audioanalyse_ordner) / f"{basis}_satzanalyse.json"

            if not pfad.is_file():
                return {}

            with open(pfad, "r", encoding="utf-8") as f:
                daten = json.load(f)

            return {
                int(k): v
                for k, v in daten.items()
                if str(k).isdigit()
            }

        except Exception as e:
            print(f"[Audioanalyse] Satzanalyse konnte nicht geladen werden: {e}")
            return {}