import os
import re
import regex
import json
import sys
import tkinter as tk
from tkinter import ttk, messagebox,simpledialog
from reportlab.pdfgen import canvas as pdfcanvas
import Eingabe.config as config
from annotationen_renderer import AnnotationRenderer
from config_editor import register_custom_font
import Schritt2

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
        self.master_window = self.winfo_toplevel()
        self.master_window.protocol("WM_DELETE_WINDOW", self._on_close)

        self.ist_geaendert = False

        # Kapitel-Liste aus config_editor holen
        if not kapitel_config.kapitel_liste and kapitel_config.kapitel_daten:
            self.kapitel_liste = list(kapitel_config.kapitel_daten.keys())
        else:
             self.kapitel_liste = kapitel_config.kapitel_liste 
        
        # Start mit keinem Hauptkapitel und keinem Abschnitt
        self.current_hauptkapitel_index = None
        self.current_abschnitt_index = None

        # Initiale Kapitelpfade noch leer, werden beim Laden gesetzt
        self.kapitel_pfade = []

        # Initialisiere weitere Variablen
        self.renderer = AnnotationRenderer()
        self.json_dicts = []
        self.filter_vars = {}
        self.use_number_words_var = tk.BooleanVar(value=True)
    
        # Widgets bauen
        self._erstelle_widgets()
    
    def _on_close(self):
        if self.ist_geaendert:
            if messagebox.askyesno("Änderungen speichern", "Es gibt ungespeicherte Änderungen. Möchtest du sie speichern?"):
                self._json_speichern()
        

        if messagebox.askyesno("Wirklich beenden", "Willst du wirklich alles beenden?"):        
            # Anwendung komplett schließen
            self.master_window.quit()  # Bricht mainloop ab
            self.master_window.destroy()  # Zerstört Fenster
            sys.exit()  # Beendet das Script vollständig

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
        self.rowconfigure(0, weight=0)  # Zeile 0: Buttons + Comboboxen
        self.rowconfigure(1, weight=0)  # Zeile 1: Zahlwörter Checkbox
        self.rowconfigure(2, weight=0)  # Zeile 2: Filter Checkboxen
        self.rowconfigure(3, weight=0)  # Zeile 3: leerer Abstand
        self.rowconfigure(4, weight=1)  # Zeile 4: Canvas + Annotationen wächst

        # 1. Zeile: Hauptkapitel Auswahl + Speichern-Button
        top_frame = ttk.Frame(self)
        top_frame.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        top_frame.columnconfigure(0, weight=0)
        top_frame.columnconfigure(1, weight=0)

        max_len = max((len(str(k)) for k in self.kapitel_liste), default=5)
        self.hauptkapitel_combo = ttk.Combobox(
            top_frame,
            values=self.kapitel_liste,
            state="readonly",
            width=max(max_len, 20)
        )
        self.hauptkapitel_combo.set('')  # zu Beginn keine Auswahl
        self.hauptkapitel_combo.grid(row=0, column=0, padx=(0,10))
        self.hauptkapitel_combo.bind("<<ComboboxSelected>>", self._hauptkapitel_gewechselt)

        self.abschnitt_combo = ttk.Combobox(top_frame, values=[], state="readonly")
        self.abschnitt_combo.set('')  # leer zu Beginn
        self.abschnitt_combo.grid(row=0, column=1)
        self.abschnitt_combo.bind("<<ComboboxSelected>>", self._abschnitt_gewechselt)

        speichern_button = ttk.Button(top_frame, text="JSON speichern", command=self._json_speichern)
        speichern_button.grid(row=0, column=3)

        export_button = ttk.Button(top_frame, text="Exportiere als PDF", command=self._exportiere_pdf)
        export_button.grid(row=0, column=4, padx=(10, 0))

        # Wortanzahl-label
        self.wortanzahl_label = ttk.Label(top_frame, text="Wörter: 0")
        self.wortanzahl_label.grid(row=0, column=5, padx=10, pady=5, sticky='w')


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

        # Neue Variable für Personen-Auto-Checkbox
        self.auto_person_bis_redeende_var = tk.BooleanVar(value=True)

        personen_auto_checkbox = ttk.Checkbutton(
            top_frame_2,
            text="Personen automatisch bis zum Ende der wörtlichen Rede",
            variable=self.auto_person_bis_redeende_var
        )
        personen_auto_checkbox.grid(row=0, column=1, sticky="w", padx=(10, 0))

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

        # 4. Zeile: leerer Abstand
        spacer = ttk.Frame(self)
        spacer.grid(row=3, column=0, sticky="ew", pady=5)

        # 5. Zeile: Canvas + Annotationen (links + rechts)
        canvas_frame = ttk.Frame(self)
        canvas_frame.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
        canvas_frame.columnconfigure(0, weight=25)  # linker Bereich (Canvas)
        canvas_frame.columnconfigure(1, weight=1)  # rechter Bereich (Annotationen)
        canvas_frame.rowconfigure(0, weight=1)

        # Linker Bereich (Canvas + Scrollbar) – Kind von canvas_frame
        linker_frame = ttk.Frame(canvas_frame)
        linker_frame.grid(row=0, column=0, sticky='nsew', padx=0)
        linker_frame.columnconfigure(0, weight=1)
        linker_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(linker_frame, bg='white')
        self.canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar_links = ttk.Scrollbar(linker_frame, orient='vertical', command=self.canvas.yview)
        scrollbar_links.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar_links.set)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Rechter Bereich (Annotationen) – Kind von canvas_frame
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
            lambda e: self.annotation_canvas.configure(scrollregion=self.annotation_canvas.bbox('all'))
        )

        self.default_annotation_label = ttk.Label(
            self.annotation_frame,
            text="Bitte Wort auswählen, um dessen Annotationen zu sehen und zu ändern!",
            foreground="gray",
            font=('Arial', 12, 'italic'),
            wraplength=150,
            justify='left'
        )
        self.default_annotation_label.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky='nw')
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))


    def aktualisiere_wortanzahl_label(self):
        if not self.json_dicts:
            self.wortanzahl_label.config(text="Wörter: 0")
            return

        letzte_wortnr = max(eintrag.get("WortNr", 0) for eintrag in self.json_dicts)
        self.wortanzahl_label.config(text=f"Wörter: {letzte_wortnr}")


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

        self.aktualisiere_wortanzahl_label()
        self.canvas.update_idletasks()
        
    def berechne_positionen_vor_rendern(self, bis_index):
        x_pos = config.LINKER_SEITENRAND
        y_pos = config.LINKER_SEITENRAND
        zeilenhoehe = self.renderer.zeilen_hoehe
        spacing = 10  # Optional als config konfigurierbar

        for i in range(bis_index):
            elem = self.json_dicts[i]
            annotation_text = str(elem.get("annotation", ""))
            if "zeilenumbruch" in annotation_text.lower():
                y_pos += zeilenhoehe
                x_pos = config.LINKER_SEITENRAND
            else:
                token = elem.get("token", "")
                schrift = self.renderer.schrift_holen(elem)
                text_breite, _, _ = self.renderer._berechne_textgroesse(self.canvas, schrift, token)
                x_pos += text_breite + spacing

        return x_pos, y_pos

    def neu_rendern_bereich(self, start_index, end_index):
        print("----------------------------------------------------------")
        print(f"Teil-Render von Index {start_index} bis {end_index}")

        # Gruppe zurücksetzen, damit kein alter Status stört
        self.renderer._reset_gruppe()

        # Bereich erweitern, um ganze Gruppen zu erfassen
        # Suche rückwärts bis zum Gruppenstart (zentriertstart/rechtsbuendigstart/einrueckungstart)
        while start_index > 0:
            elem = self.json_dicts[start_index]
            position = elem.get("position", "").lower()
            if position in ("zentriertstart", "rechtsbuendigstart", "einrueckungstart"):
                break
            start_index -= 1

        # Suche vorwärts bis Gruppenende (zentriertende/rechtsbuendigende/einrueckungende)
        while end_index < len(self.json_dicts) - 1:
            elem = self.json_dicts[end_index]
            position = elem.get("position", "").lower()
            if position in ("zentriertende", "rechtsbuendigende", "einrueckungende"):
                break
            end_index += 1

        # Lösche alle Canvas-Elemente im Bereich, aber NICHT die Einträge aus canvas_elemente_pro_token
        for i in range(start_index, end_index + 1):
            elem = self.json_dicts[i]
            wortNr = elem.get("WortNr")
            if wortNr is not None:
                eintrag = self.renderer.canvas_elemente_pro_token.get(wortNr - 1)
                if eintrag:
                    canvas_id = eintrag.get("canvas_id")
                    if canvas_id:
                        self.canvas.delete(canvas_id)
                    # Wichtig: NICHT das Dict-Element löschen!
                    # del self.renderer.canvas_elemente_pro_token[wortNr - 1]

        # X/Y Positionen anhand voriger Tokens berechnen
        x_pos, y_pos = self.berechne_positionen_vor_rendern(start_index)
        self.renderer.x_pos = x_pos
        self.renderer.y_pos = y_pos

        # Rendern
        for i in range(start_index, end_index + 1):
            naechstes = self.json_dicts[i + 1] if i + 1 < len(self.json_dicts) else None
            self.renderer.rendern(
                index=i,
                gui_canvas=self.canvas,
                naechstes_dict_element=naechstes,
                dict_element=self.json_dicts[i]
            )

    
    def _on_token_click(self, idx):
        print(f"Token {idx} wurde angeklickt.")
        self.ist_geaendert = True
        self.default_annotation_label.grid_forget()

        json_dict = self.json_dicts[idx]
        self.renderer.markiere_token_mit_rahmen(self.canvas, idx)

        basename = os.path.basename(self.dateipfad_json)
        print(f"Vor Annotation ändern, canvas_elemente_pro_token Keys: {list(self.renderer.canvas_elemente_pro_token.keys())}")

        self.kapitel_name = self.hauptkapitel_combo.get()

        print(f"Vor dem Löschen Widgets im annotation_frame: {[type(c) for c in self.annotation_frame.winfo_children()]}")
        # Alle Widgets außer default_label löschen
        for child in self.annotation_frame.winfo_children():
            if child != self.default_annotation_label:
                child.destroy()
        self.annotation_frame.update_idletasks()
        print(f"Nach dem Löschen Widgets: {[type(c) for c in self.annotation_frame.winfo_children()]}")

        tk.Label(
            self.annotation_frame,
            text=f"Annotationen für Token {idx +1}: \n '{json_dict.get('token','')}'",
            font=('Arial', 14, 'bold')
        ).grid(row=0, column=0, sticky='w', pady=5, padx=5, columnspan=2)
        
        def bearbeite_token():
            
            aktuelles_token = json_dict.get('token', '')
            neues_token = simpledialog.askstring("Token bearbeiten", "Neues Token eingeben:", initialvalue=aktuelles_token)

            if neues_token is not None and neues_token != aktuelles_token:
                teile = neues_token.strip().split()

                if teile:
                    vorher_token = self.json_dicts[idx - 1]['token'] if idx > 0 else None
                    naechstes_token = self.json_dicts[idx + 1]['token'] if idx + 1 < len(self.json_dicts) else None                 
                    vorher_wortNr = self.json_dicts[idx - 1]['WortNr'] if idx > 0 else 1
                    kapitelnummer = self.json_dicts[idx].get("KapitelNummer", "")

                    # Alle Zusatzfelder auf leeren String setzen, wenn nicht vorhanden
                    standardfelder = {
                        "annotation": "",
                    }

                    # KI-Aufgaben-Felder dynamisch aus config ergänzen
                    for feld in config.KI_AUFGABEN.values():
                        standardfelder[feld] = ""

                    # Haupttoken aktualisieren
                    ersetztes_token = Schritt2.ersetze_zahl_in_token(teile[0], vorher_token, naechstes_token)

                    # Annotation bestimmen
                    annotationen = []
                    if regex.match(r"[\p{P}]", teile[0]):
                        if teile[0] in ['–', '(', ')', '{', '}', '[', ']']:
                            annotationen.append("satzzeichenMitSpace")
                        elif teile[0] in ['„']:
                            annotationen.append("satzzeichenOhneSpaceDanach")
                        else:
                            annotationen.append("satzzeichenOhneSpaceDavor")

                    self.json_dicts[idx]['token'] = teile[0]
                    self.json_dicts[idx]['tokenInklZahlwoerter'] = ersetztes_token
                    self.json_dicts[idx]['annotation'] = ",".join(annotationen)

                    # Weitere Wörter einfügen, falls durch Split mehrere entstanden
                    for i, wort in enumerate(teile[1:], start=1):
                        neues_annotationen = []
                        if regex.match(r"[\p{P}]", wort):
                            if wort in ['–', '(', ')', '{', '}', '[', ']']:
                                neues_annotationen.append("satzzeichenMitSpace")
                            elif wort in ['„']:
                                neues_annotationen.append("satzzeichenOhneSpaceDanach")
                            else:
                                neues_annotationen.append("satzzeichenOhneSpaceDavor")

                        ersetztes_wort = Schritt2.ersetze_zahl_in_token(wort, vorher_token, naechstes_token)
                        neues_token_dict = {
                            "KapitelNummer": kapitelnummer,
                            'WortNr': i + vorher_wortNr - 1,
                            'token': wort,
                            'tokenInklZahlwoerter': ersetztes_wort,
                            'annotation': ",".join(neues_annotationen),
                            **standardfelder
                        }
                        self.json_dicts.insert(idx + i, neues_token_dict)

                    # WortNr aller Tokens ab idx neu nummerieren
                    for i in range(idx, len(self.json_dicts)):
                        self.json_dicts[i]['WortNr'] = i + 1

                    print("Tokens nach Bearbeitung:")
                    for i, t in enumerate(self.json_dicts):
                        print(i, t['token'])

                    self._zeichne_alle_tokens()
                    self.renderer.markiere_token_mit_rahmen(self.canvas, idx + len(teile) - 1)
                    self._on_token_click(idx + len(teile) - 1)
                    self.aktualisiere_wortanzahl_label()
                


        bearbeiten_button = tk.Button(
            self.annotation_frame,
            text="Token bearbeiten",
            command=bearbeite_token
        )
        bearbeiten_button.grid(row=1, column=1, padx=5, pady=5, sticky='e')


        row_index = 2
        for aufgabennr, aufgabenname in config.KI_AUFGABEN.items():
            label = ttk.Label(self.annotation_frame, text=aufgabenname)
            label.grid(row=row_index, column=0, sticky='w', padx=5, pady=2)

            if aufgabennr == 3:
                zusatzinfo = self.kapitel_config.kapitel_daten.get(self.kapitel_name, {}).get("ZusatzInfo_3", "")
                
                zusatzinfo = zusatzinfo.replace("‘", "'").replace("’", "'")
                print(f"zusatzinfo für {self.kapitel_name} = {zusatzinfo}")
                werte = re.findall(r"'(.*?)'", zusatzinfo)
                print(f"werte = {werte}")
            else:
                werte = [e["name"] for e in config.AUFGABEN_ANNOTATIONEN.get(aufgabennr, []) if e["name"]]

            if werte and werte[-1] != "":
                werte.append("")

            werte = werte or ['']
            aktueller_wert = json_dict.get(aufgabenname, "")

            # Anzeige-Werte in der Combobox (mit Umlauten, nur für Anzeige)
            anzeige_werte = [_anzeige_name(w) for w in werte]
            anzeige_aktueller_wert = _anzeige_name(aktueller_wert)

            combobox = ttk.Combobox(self.annotation_frame, values=anzeige_werte, state='readonly')
            if aktueller_wert:
                combobox.set(anzeige_aktueller_wert)

            def on_combobox_change(event, aufgabennr=aufgabennr, combobox=combobox, aufgabenname=aufgabenname):
                neuer_wert = combobox.get()
                # Rückkonvertierung für Speicherung
                neuer_wert = _interner_name(neuer_wert)
                
                if neuer_wert:
                    json_dict[aufgabenname] = neuer_wert
                elif aufgabenname in json_dict:
                    del json_dict[aufgabenname]

                if aufgabenname.lower() == "position":
                    print(f"Position geändert bei Token {idx}: '{neuer_wert}'")

                    # Finde Start- und Endindex der aktuellen Gruppe (zentriert oder rechtsbuendig)
                    start_index = None
                    end_index = None
                    typ = None

                    for i in range(len(self.json_dicts)):
                        pos = self.json_dicts[i].get("position", "").lower()
                        if pos in ("zentriertstart", "rechtsbuendigstart") and start_index is None:
                            start_index = i
                            typ = "zentriert" if "zentriert" in pos else "rechtsbuendig"
                        elif pos in ("zentriertende", "rechtsbuendigende") and start_index is not None:
                            end_index = i
                            break

                    # Wenn beides vorhanden, dann nur diesen Bereich rendern
                    if start_index is not None and end_index is not None and start_index <= end_index:
                        self.neu_rendern_bereich(start_index, end_index)
                    else:
                        print("Kein vollständiges Start/Ende-Paar gefunden – kein Teilrendering möglich.")

                elif aufgabenname.lower() == "person":
                    print(f"Person geändert bei Token {idx}: '{neuer_wert}'")
                    self.renderer.annotation_aendern(self.canvas, idx, aufgabenname, json_dict)


                    if self.auto_person_bis_redeende_var.get():
                        # --- Erweiterung: automatische Personenzuweisung bei Start-/Endezeichen ---
                        annot_def = next((a for a in config.AUFGABEN_ANNOTATIONEN.get(3, []) if a.get("name") is None), None)
                        if annot_def:
                            startzeichen = annot_def.get("StartZeichen")
                            endezeichen = annot_def.get("EndeZeichen")

                            if idx > 0 and self.json_dicts[idx - 1].get("token") == startzeichen:
                                print(f"Startzeichen '{startzeichen}' erkannt vor Token {idx}, automatische Übertragung beginnt.")
                                i = idx + 1
                                while i < len(self.json_dicts):
                                    token_text = self.json_dicts[i].get("token")
                                    if token_text == endezeichen:
                                        print(f"Endezeichen '{endezeichen}' bei Token {i} erkannt, automatische Übertragung endet.")
                                        break
                                    self.json_dicts[i]["person"] = neuer_wert
                                    self.renderer.annotation_aendern(self.canvas, i, "person", self.json_dicts[i])
                                    i += 1
                else:
                    # Alle anderen Annotationen werden einzeln neu gezeichnet
                    self.renderer.annotation_aendern(self.canvas, idx, aufgabenname, json_dict)

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
                self.ist_geaendert = False
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

    def _hauptkapitel_gewechselt(self, event):

        if self.ist_geaendert:
            if messagebox.askyesno("Änderungen speichern", "Es gibt ungespeicherte Änderungen. Möchtest du sie speichern?"):
                self._json_speichern()

        self.current_hauptkapitel_index = self.hauptkapitel_combo.current()
        self.current_abschnitt_index = None

        kapitelname = self.kapitel_liste[self.current_hauptkapitel_index]
        self.kapitel_pfade = self._lade_alle_kapiteldateien(kapitelname)

        abschnittswerte = [f"Abschnitt {i+1}" for i in range(len(self.kapitel_pfade))]
        self.abschnitt_combo['values'] = abschnittswerte
        self.abschnitt_combo.set('')  # zurücksetzen

        # Canvas und Daten leeren, da noch kein Abschnitt gewählt ist
        self.json_dicts = []
        self.canvas.delete('all')
        self.default_annotation_label.grid()

    def _abschnitt_gewechselt(self, event):
        idx = self.abschnitt_combo.current()
        if idx == -1:
            # Kein Abschnitt ausgewählt, Daten und Canvas leeren
            self.json_dicts = []
            self.canvas.delete('all')
            self.default_annotation_label.grid()
            return

        if self.ist_geaendert:
            if messagebox.askyesno("Änderungen speichern", "Es gibt ungespeicherte Änderungen. Möchtest du sie speichern?"):
                self._json_speichern()

        self.current_abschnitt_index = idx
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