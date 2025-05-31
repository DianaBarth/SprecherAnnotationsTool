import os
import json
import re
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import simpledialog
from docx import Document

import Eingabe.config as config # Importiere das komplette config-Modul

class KapitelConfig(ttk.Frame):
    def __init__(self, parent, notebook):
        super().__init__(parent)

        self.dashboard = None  # Wird von Anwendung gesetzt
        self.output_folder = None
        self.notebook = notebook
        self.notebook.add(self, text="📖 Kapitel-Konfiguration")
        
        self.visible = False

        self.kapitel_liste = []    # Liste der Kapitelnamen in Reihenfolge
        self.kapitel_daten = {}    # Dict: Kapitelname -> Zusatzinfos (dict mit Keys "ZusatzInfo_2", "nicht_notwendige_unterschritte", ...)
        self.index = 0             # Aktuelles Kapitel-Index

        self.aufgaben =  config.KI_AUFGABEN
        self._build_widgets()

        self._update_current_label()

        self.notebook.hide(self)  # Versteckt den Tab
        
    def kapitel_manuell_bearbeiten(self):     

        self._load_current_kapitel()
        self._update_current_label()
        self.show()

    def lade_konfiguration(self):        
        dateipfad = filedialog.askopenfilename(
            title="Konfiguration laden",
            filetypes=[("JSON‑Dateien", "*.json"), ("Alle Dateien", "*.*")]
        )
        if not dateipfad:
            return
        try:
            with open(dateipfad, "r", encoding="utf-8") as f:
                daten = json.load(f)
            # Übernehme kapitel_liste und kapitel_daten wie gewohnt…
            if "kapitel_liste" in daten and "kapitel_daten" in daten:
                self.kapitel_liste = daten["kapitel_liste"]
                self.kapitel_daten = daten["kapitel_daten"]
            elif "kapitel_daten" in daten:
                self.kapitel_daten = daten["kapitel_daten"]
                self.kapitel_liste = list(daten["kapitel_daten"].keys())
            else:
                self.kapitel_daten = daten
                self.kapitel_liste = list(daten.keys())
            self.index = 0
            self._load_current_kapitel()
            self._update_current_label()
            self.show()
            messagebox.showinfo("Erfolg", "Kapitel-Konfiguration erfolgreich geladen.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Konfiguration:\n{e}")

    def _create_from_word(self, stilname, pfad, nummerierung="nein", praefix=None, aufsteigend=False, kapitel_trenner="***"):
        print(f"Starte Kapitel-Erkennung aus Word-Datei: {pfad}")
        print(f"Stilname: {stilname}, Numerierung: {nummerierung}, Präfix: {praefix}, Aufsteigend: {aufsteigend}")

        try:
            doc = Document(pfad)
            gefundene_kapitel = []
            letzte_nummer = 0

            import re

            def roemisch_zu_int(r):
                roem_zahlen = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
                result, prev = 0, 0
                for c in reversed(r.upper()):
                    val = roem_zahlen.get(c, 0)
                    if val < prev:
                        result -= val
                    else:
                        result += val
                    prev = val
                return result

            for para in doc.paragraphs:
                if para.style and para.style.name == stilname and para.text.strip():
                    text = para.text.strip()
                    print(f"Gefunden: '{text}' mit Stil '{stilname}'")

                    if praefix:
                        if not text.startswith(praefix):
                            print(f"Übersprungen (kein Präfix): {text}")
                            continue
                        text_nach_prefix = text[len(praefix):].lstrip()
                    else:
                        text_nach_prefix = text

                    nummer_aktuell = None
                    match_ok = False

                    if nummerierung == "nein":
                        match_ok = True

                    elif nummerierung == "arabische Zahlen [1,2,3…]":
                        m = re.match(r"^(\d+)[\.\)]?\s", text_nach_prefix)
                        if m:
                            nummer_aktuell = int(m.group(1))
                            match_ok = not aufsteigend or nummer_aktuell == letzte_nummer + 1

                    elif nummerierung == "römische Zahlen [I,II,III…]":
                        m = re.match(r"^(M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))[.\)]?\s", text_nach_prefix, re.IGNORECASE)
                        if m:
                            nummer_aktuell = roemisch_zu_int(m.group(1))
                            match_ok = not aufsteigend or nummer_aktuell == letzte_nummer + 1

                    elif nummerierung == "lateinisch Punkt [a.,b.,c.]":
                        m = re.match(r"^([a-z])\.\s", text_nach_prefix)
                        if m:
                            nummer_aktuell = ord(m.group(1)) - ord('a') + 1
                            match_ok = not aufsteigend or nummer_aktuell == letzte_nummer + 1

                    elif nummerierung == "lateinisch Klammer [a),b),c)]":
                        m = re.match(r"^([a-z])\)\s", text_nach_prefix)
                        if m:
                            nummer_aktuell = ord(m.group(1)) - ord('a') + 1
                            match_ok = not aufsteigend or nummer_aktuell == letzte_nummer + 1
                    if nummerierung == "nein":
                        match_ok = True

                    elif nummerierung == "arabische Zahlen [1,2,3…]":
                        m = re.match(r"^(\d+)[\.\)]?\s", text_nach_prefix)
                        if m:
                            nummer_aktuell = int(m.group(1))
                            match_ok = not aufsteigend or nummer_aktuell == letzte_nummer + 1

                    elif nummerierung == "römische Zahlen [I,II,III…]":
                        m = re.match(r"^(M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))[.\)]?\s", text_nach_prefix, re.IGNORECASE)
                        if m:
                            nummer_aktuell = roemisch_zu_int(m.group(1))
                            match_ok = not aufsteigend or nummer_aktuell == letzte_nummer + 1

                    elif nummerierung == "lateinisch Punkt [a.,b.,c.]":
                        m = re.match(r"^([a-z])\.\s", text_nach_prefix)
                        if m:
                            nummer_aktuell = ord(m.group(1)) - ord('a') + 1
                            match_ok = not aufsteigend or nummer_aktuell == letzte_nummer + 1

                    elif nummerierung == "lateinisch Klammer [a),b),c)]":
                        m = re.match(r"^([a-z])\)\s", text_nach_prefix)
                        if m:
                            nummer_aktuell = ord(m.group(1)) - ord('a') + 1
                            match_ok = not aufsteigend or nummer_aktuell == letzte_nummer + 1

                    if match_ok:
                        gefundene_kapitel.append(text)
                        print(f"Kapitel akzeptiert: {text}")
                        if nummer_aktuell:
                            letzte_nummer = nummer_aktuell
                    else:
                        print(f"Kapitel übersprungen wegen Nummerierung: {text}")

            if not gefundene_kapitel:
                print("Keine Kapitel gefunden!")
                messagebox.showinfo("Keine Kapitel gefunden", f"Keine Absätze mit Stil '{stilname}' und Numerierung '{nummerierung}' gefunden.")
                return

            print(f"Erkannte Kapitelanzahl: {len(gefundene_kapitel)}")
            self.kapitel_liste = gefundene_kapitel
            self.kapitel_daten = {k: {} for k in gefundene_kapitel}
            self.kapitel_trenner = kapitel_trenner 
            self.index = 0

            self._load_current_kapitel()
            self._update_current_label()
            self.show()

            messagebox.showinfo("Erfolg", f"{len(gefundene_kapitel)} Kapitel erfolgreich erkannt und übernommen.")
        except Exception as e:
            print(f"Fehler bei Kapitel-Erkennung: {e}")
            messagebox.showerror("Fehler", f"Fehler beim Laden der Word-Datei:\n{e}")

    def kapitel_auto_erzeugen(self):
        prefix = simpledialog.askstring("Kapitel Präfix", "Mit welchem Wort beginnen die Kapitel?", initialvalue="Kapitel")
        if not prefix:
            messagebox.showwarning("Warnung", "Bitte einen gültigen Präfix eingeben.")
            return
        anzahl = simpledialog.askinteger("Kapitelanzahl", "Wie viele Kapitel gibt es?", minvalue=1)
        if not anzahl:
            return
        # Erzeuge neue Kapitel
        self.kapitel_daten = {}
        self.kapitel_liste = [f"{prefix}{i}" for i in range(1, anzahl + 1)]
        self.index = 0
        self._load_current_kapitel()
        self._update_current_label()
        self.show()

    
    def load_from_file(self, dateiname):
        if os.path.exists(dateiname):
            self.index = 0
            try:
                with open(dateiname, "r", encoding="utf-8") as f:
                    daten = json.load(f)

                if "kapitel_liste" in daten and "kapitel_daten" in daten:
                    self.kapitel_liste = daten["kapitel_liste"]
                    self.kapitel_daten = daten["kapitel_daten"]
                elif "kapitel_daten" in daten:
                    self.kapitel_daten = daten["kapitel_daten"]
                    # Reihenfolge aus dict nicht garantiert → nach dem Namen sortieren
                    self.kapitel_liste = list(self.kapitel_daten.keys())
                else:
                    # Fallback
                    self.kapitel_daten = daten
                    self.kapitel_liste = list(daten.keys())

                self.index = 0  # <— sicher zurücksetzen!
                self._load_current_kapitel()
                self._update_current_label()


                print("Geladene Reihenfolge:", self.kapitel_liste)
                print("Aktueller Index:", self.index)
                print("Erstes Kapitel:", self.kapitel_liste[0])

                print("[DEBUG] geladene nicht_notwendige_unterschritte:", self.kapitel_daten.get(self.kapitel_liste[0], {}).get("nicht_notwendige_unterschritte"))
            except Exception as e:
                messagebox.showerror("Fehler", f"Laden der Konfiguration fehlgeschlagen:\n{e}")

    def _build_widgets(self):
        # Spalten konfigurieren: 0=Label, 1=Entry, 2=Checkbox, 3=Spacer, 4=X-Button (rechts)
        self.columnconfigure(0, weight=0)  # Label (fest)
        self.columnconfigure(1, weight=3)  # Eingabefelder wachsen stark
        self.columnconfigure(2, weight=1)  # Checkboxen wachsen leicht
        self.columnconfigure(3, weight=1)  # Spacer, damit alles schön verteilt wird
        self.columnconfigure(4, weight=0)  # X-Button rechts, fest

        # Zeile 0: Kapitelname + Eingabe + X-Button rechts
        ttk.Label(self, text="Kapitelname:", font=(None, 12, "bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.name_entry = ttk.Entry(self)
        self.name_entry.grid(row=0, column=1, columnspan=2, pady=5, sticky="ew")  # Spalte 1+2 für Eingabe

        btn_close = ttk.Button(self, text="✖️", width=3, command=self.button_konfiguration_schliessen)
        btn_close.grid(row=0, column=4, padx=10, sticky="e")

        self.vars = {}
        self.entries = {}

        for i, (nr, beschreibung) in enumerate(self.aufgaben.items(), start=1):
            ttk.Label(self, text=f"Zusatzinfo {nr}: {beschreibung}").grid(row=i, column=0, sticky="w", padx=10)
            ent = ttk.Entry(self)
            ent.grid(row=i, column=1, sticky="ew", pady=2)
            var = tk.BooleanVar()
            chk = ttk.Checkbutton(self, text="nicht notwendig", variable=var,
                                command=lambda n=nr: self._toggle_entry_state(n))
            chk.grid(row=i, column=2)
            # Leere Spalte 3 als Abstand
            spacer = ttk.Label(self, text="")
            spacer.grid(row=i, column=3)
            self.vars[nr] = var
            self.entries[nr] = ent

        # Navigation Buttons in einem Frame, links ausgerichtet, mit Grid auf voller Breite
        nav = ttk.Frame(self)
        nav.grid(row=len(self.aufgaben)+1, column=0, columnspan=4, pady=10, sticky="w")
        ttk.Button(nav, text="← Vorheriges Kapitel", command=self.prev).pack(side=tk.LEFT, padx=5)
        ttk.Button(nav, text="Nächstes Kapitel →", command=self.next).pack(side=tk.LEFT, padx=5)

        # Aktuelles Kapitel Label rechts von Navigation (in Spalte 4)
        self.current_label = ttk.Label(self)
        self.current_label.grid(row=len(self.aufgaben)+1, column=4, padx=10, sticky="e")

        # Label für aktive Aufgabe + Spinner rechts oben neben X-Button (Zeile 1, Spalte 4/5)
        self.aktive_aufgabe_label = ttk.Label(self, text="")
        self.aktive_aufgabe_label.grid(row=1, column=4, padx=(10,0), sticky="w")

        self.spinner_label = ttk.Label(self, text="", width=2)
        self.spinner_label.grid(row=1, column=5, sticky="w")

        # Unten: Buttons für Kapitel einfügen, löschen, schließen - über alle Spalten
        ttk.Button(self, text="neues Kapitel einfügen", command=self.kapitel_einfuegen).grid(row=98, column=0, columnspan=5, pady=15, sticky="ew", padx=10)
        ttk.Button(self, text="aktuelles Kapitel löschen", command=self.kapitel_loeschen).grid(row=99, column=0, columnspan=5, pady=15, sticky="ew", padx=10)
        ttk.Button(self, text="Kapitel-Konfiguration schließen", command=self.button_konfiguration_schliessen).grid(row=100, column=0, columnspan=5, pady=15, sticky="ew", padx=10)


    def _toggle_entry_state(self, nr):
        """Entry deaktivieren, wenn Checkbox aktiviert, sonst aktivieren."""
        if self.vars[nr].get():
            self.entries[nr].config(state=tk.DISABLED)
        else:
            self.entries[nr].config(state=tk.NORMAL)

    def _update_current_label(self):
        if self.kapitel_liste:
            self.current_label.config(text=f"Kapitel {self.index + 1} / {len(self.kapitel_liste)}")
        else:
            self.current_label.config(text="Keine Kapitel")

    def show(self):
        if not self.visible:
            self.notebook.add(self, text="Kapitel-Konfiguration")
            self.visible = True
        self._load_current_kapitel()
        self.notebook.select(self)  # Wichtig: Tab aktiv auswählen

    def prev(self):
        if self.kapitel_liste:
            self.save_current_kapitel()
            self.index = (self.index - 1) % len(self.kapitel_liste)
            self._load_current_kapitel()

    def next(self):
        if self.kapitel_liste:
            self.save_current_kapitel()
            self.index = (self.index + 1) % len(self.kapitel_liste)
            self._load_current_kapitel()

    def _load_current_kapitel(self):
        if not self.kapitel_liste:
            self.name_entry.delete(0, tk.END)
            for nr in self.aufgaben:
                self.entries[nr].delete(0, tk.END)
                self.entries[nr].config(state=tk.NORMAL)
                self.vars[nr].set(False)
            self._update_current_label()
            return

        kapitel_name = self.kapitel_liste[self.index]
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, kapitel_name)

        daten = self.kapitel_daten.get(kapitel_name, {})
        for nr in self.aufgaben:
            zusatz = daten.get(f"ZusatzInfo_{nr}", "")
            nicht_notwendig = False
            if "nicht_notwendige_unterschritte" in daten:
                nicht_notwendig = nr in daten["nicht_notwendige_unterschritte"]

            self.entries[nr].config(state=tk.NORMAL)
            self.entries[nr].delete(0, tk.END)
            self.entries[nr].insert(0, zusatz)

            self.vars[nr].set(nicht_notwendig)
            if nicht_notwendig:
                self.entries[nr].config(state=tk.DISABLED)

        self._update_current_label()

    def save_current_kapitel(self):
        if not self.kapitel_liste:
            return

        alter_name = self.kapitel_liste[self.index]
        neuer_name = self.name_entry.get().strip()

        if not neuer_name:
            messagebox.showwarning("Ungültiger Name", "Der Kapitelname darf nicht leer sein.")
            return

        if neuer_name != alter_name and neuer_name in self.kapitel_liste:
            messagebox.showwarning("Duplikat", f"Der Kapitelname '{neuer_name}' existiert bereits.")
            return

        self.kapitel_liste[self.index] = neuer_name

        zusatzinfos = {}
        nicht_notwendig_list = []
        for nr in self.aufgaben:
            if self.vars[nr].get():
                nicht_notwendig_list.append(nr)
            else:
                zusatzinfos[f"ZusatzInfo_{nr}"] = self.entries[nr].get().strip()

        # Immer "nicht_notwendige_unterschritte" setzen, auch wenn leer
        zusatzinfos["nicht_notwendige_unterschritte"] = nicht_notwendig_list

        self.kapitel_daten[neuer_name] = zusatzinfos

        if neuer_name != alter_name:
            self.kapitel_daten.pop(alter_name, None)

        self._update_current_label()
        

    def kapitel_loeschen(self):
            if not self.kapitel_liste:
                messagebox.showinfo("Info", "Keine Kapitel zum Löschen.")
                return

            aktuelles_kapitel = self.kapitel_liste[self.index]
            antwort = messagebox.askyesno("Kapitel löschen", f"Kapitel '{aktuelles_kapitel}' wirklich löschen?")
            if not antwort:
                return

            del self.kapitel_daten[aktuelles_kapitel]
            del self.kapitel_liste[self.index]

            if self.index >= len(self.kapitel_liste):
                self.index = max(0, len(self.kapitel_liste) - 1)

            if self.kapitel_liste:
                self._load_current_kapitel()
                self._update_current_label()
            else:
                messagebox.showinfo("Info", "Keine Kapitel mehr vorhanden.")
    def kapitel_einfuegen(self):
        neuer_name = simpledialog.askstring("Kapitel einfügen", "Name des neuen Kapitels:")
        if not neuer_name or neuer_name.strip() == "":
            messagebox.showwarning("Warnung", "Bitte einen gültigen Namen eingeben.")
            return

        neuer_name = neuer_name.strip()

        if neuer_name in self.kapitel_liste:
            messagebox.showerror("Fehler", "Dieses Kapitel existiert bereits.")
            return

        # Kapitel vor aktuellem Index einfügen
        self.kapitel_liste.insert(self.index, neuer_name)
        self.kapitel_daten[neuer_name] = {"nicht_notwendige_unterschritte": []}

        self.index = self.kapitel_liste.index(neuer_name)

        self._load_current_kapitel()
        self._update_current_label()

        if self.dashboard:
            self.dashboard.lade_kapitel_checkboxes()

    
    def button_konfiguration_schliessen(self):
        speichern = messagebox.askyesno("Speichern?", "Möchten Sie die Konfiguration vor dem Schließen speichern?")
        if speichern:
            self.save_current_kapitel()
            self.save_to_file()

        if self.visible:
            self.notebook.hide(self)
            self.visible = False

    def save_to_file(self):
        daten_kapitel_daten_neu = {}

        for kapitel in self.kapitel_liste:
            daten = self.kapitel_daten.get(kapitel, {})
            nicht_notwendig_list = daten.get("nicht_notwendige_unterschritte", [])
            neue_daten = {"nicht_notwendige_unterschritte": nicht_notwendig_list}

            for nr in sorted(self.aufgaben.keys(), key=int):
                key = f"ZusatzInfo_{nr}"
                if nr in nicht_notwendig_list:
                    continue
                neue_daten[key] = daten.get(key, "")

            daten_kapitel_daten_neu[kapitel] = neue_daten

        daten = {
            "kapitel_liste": self.kapitel_liste,
            "kapitel_daten": daten_kapitel_daten_neu,
            "Kapitel_trenner": self.kapitel_trenner
        }

        erfolg = False

        if self.output_folder:
            try:
                pfad = os.path.join(self.output_folder, "kapitel_config.json")
                with open(pfad, "w", encoding="utf-8") as f:
                    json.dump(daten, f, indent=4, ensure_ascii=False)
                erfolg = True
                messagebox.showinfo("Erfolg", f"Konfiguration gespeichert als\n{pfad}")
            except Exception as e:
                messagebox.showerror("Fehler", f"Speichern der Konfiguration fehlgeschlagen:\n{e}")

        eingabe_folder = os.path.join(os.getcwd(), "Eingabe")
        os.makedirs(eingabe_folder, exist_ok=True)
        lokal_pfad = os.path.join(eingabe_folder,"kapitel_config.json")
        try:
            with open(lokal_pfad, "w", encoding="utf-8") as f:
                json.dump(daten, f, indent=4, ensure_ascii=False)
            if not erfolg:
                messagebox.showinfo("Info", f"Konfiguration lokal gespeichert als\n{lokal_pfad}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Speichern der Konfiguration im lokalen Ordner fehlgeschlagen:\n{e}")

        if self.dashboard:
            self.dashboard.lade_kapitel_checkboxes()
 