import os
import re
import json
import tkinter as tk
import ast
import yaml
import unicodedata
from datetime import date
from tkinter import ttk, messagebox
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
        self.filter_vars = {}
        self.use_number_words_var = tk.BooleanVar(value=True)
        self.personen_bereich_start_idx = None
        self.aktuell_gewaehlter_token_idx = None
        self.personen_bereich_ende_idx = None
    
        # Widgets bauen
        self._erstelle_widgets()

        # Lade Pfade und JSON-Daten für das erste Hauptkapitel und ersten Abschnitt
        self._lade_kapitel_abschnitte()

    def _lade_json_daten(self):
        aktueller_pfad = self.kapitel_pfade[self.current_abschnitt_index]
        print(f"Lade Daten für: {aktueller_pfad}")
        with open(aktueller_pfad, 'r', encoding='utf-8') as f:
            self.json_dicts = json.load(f)
        self.dateipfad_json = aktueller_pfad


    def _lade_alle_kapiteldateien(self, kapitel):
        merge_ordner = config.GLOBALORDNER["merge"]
        manuell_ordner = config.GLOBALORDNER["manuell"]
        pattern = re.compile(rf"^{kapitel}_(\d+)_annotierungen\.json$")
        
        dateien_dict = {}

        # Zuerst alle manuell-Dateien einsammeln
        for dateiname in os.listdir(manuell_ordner):
            match = pattern.match(dateiname)
            if match:
                idx = int(match.group(1))
                dateien_dict[idx] = os.path.join(manuell_ordner, dateiname)

        # Dann merge-Dateien nur ergänzen, wenn Index noch nicht drin ist
        for dateiname in os.listdir(merge_ordner):
            match = pattern.match(dateiname)
            if match:
                idx = int(match.group(1))
                if idx not in dateien_dict:
                    dateien_dict[idx] = os.path.join(merge_ordner, dateiname)

        # Nach Index sortieren und Pfade zurückgeben
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
        rechts_frame = ttk.Frame(canvas_frame)
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

    def _zeichne_alle_tokens(self):
        self.canvas.delete('all')
        self.renderer.positionen_zuruecksetzen()

        aktive_filter = [name for name, var in self.filter_vars.items() if var.get()]
        self.renderer.ignorierte_annotationen = set(a.lower() for a in aktive_filter)
        self.renderer.use_number_words = self.use_number_words_var.get()

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

        wort_nr = json_dict.get("WortNr", idx)

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
        self._lade_kapitel_abschnitte()
        self._zeichne_alle_tokens()

    def _abschnitt_gewechselt(self, event):
        self.current_abschnitt_index = self.abschnitt_combo.current()
        self._lade_json_daten()
        self._zeichne_alle_tokens()

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
        return config.KI_AUFGABEN.get(3, "person")

    def _setze_person_im_bereich(self, start_idx, end_idx, personenname):
        if start_idx is None:
            return

        if end_idx is None:
            end_idx = start_idx

        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        personen_feldname = self._get_personen_feldname()

        print(f"[AnnotationenEditor] Setze Person '{personenname}' im Bereich {start_idx} bis {end_idx}")

        for i in range(start_idx, end_idx + 1):
            if personenname:
                self.json_dicts[i][personen_feldname] = personenname
            else:
                self.json_dicts[i].pop(personen_feldname, None)

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