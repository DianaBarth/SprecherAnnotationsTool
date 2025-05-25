# ------------------ Imports ------------------

import os
import glob
import shutil
import threading
import json
import tkinter as tk
import datetime
import time
from tkinter import ttk, filedialog, messagebox, simpledialog
import inspect
from pathlib import Path
from docx import Document
from huggingface_client import HuggingFaceClient
from Eingabe import config
from docx import Document
import queue
import subprocess
import sys
import concurrent.futures
from collections import defaultdict
import importlib
from shutdown import ShutdownController
from system_ressourcen import Systemressourcen
import os
import threading
import re
import json
import traceback

import Eingabe.config as config # Importiere das komplette config-Modul
from annotationen_editor import AnnotationenEditor
from Schritt1 import extrahiere_kapitel_mit_config
from Schritt2 import verarbeite_kapitel_und_speichere_json
from Schritt3 import dateien_aufteilen
from Schritt4 import daten_verarbeiten
from Schritt5 import Merge_annotationen
from Schritt6 import visualisiere_annotationen

class FehlerAnzeige(ttk.LabelFrame):
    def __init__(self, parent, logfile_path, refresh_interval=2000):
        super().__init__(parent, text="Fehler")
        self.logfile_path = logfile_path
        self.refresh_interval = refresh_interval
        self.error_entries = []  # Liste von Fehlern (strings)
        self.widgets = []  # Für Buttons + Text (für Auf-/Zuklappen)
        self.expanded = {}  # Fehlerindex -> bool (aufgeklappt?)

        # Scrollbares Canvas mit Frame drin
        self.canvas = tk.Canvas(self, height=150)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0,0), window=self.inner_frame, anchor="nw")

        self.inner_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.update_errors()  # Starte Updates

    def update_errors(self):
        try:
            with open(self.logfile_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            # Logfile noch nicht vorhanden oder Fehler beim Lesen
            lines = []

        # Filter Fehlerzeilen (hier Beispiel: Zeilen mit "ERROR" extrahieren)
        errors = []
        current_error = []
        collecting = False

        for line in lines:
            if "ERROR" in line or "Error" in line:
                if collecting and current_error:
                    errors.append("".join(current_error))
                    current_error = []
                collecting = True
                current_error.append(line)
            elif collecting:
                # Zeile gehört zum vorherigen Fehler (Stacktrace etc.)
                if line.strip() == "":
                    # Leerzeile beendet Fehlerblock
                    errors.append("".join(current_error))
                    current_error = []
                    collecting = False
                else:
                    current_error.append(line)

        if collecting and current_error:
            errors.append("".join(current_error))

        # Update nur, wenn Fehlerliste sich geändert hat
        if errors != self.error_entries:
            self.error_entries = errors
            self._refresh_widgets()

        # Timer fürs nächste Update
        self.after(self.refresh_interval, self.update_errors)

    def _refresh_widgets(self):
        # Entferne alte Widgets
        for w in self.widgets:
            w.destroy()
        self.widgets.clear()
        self.expanded.clear()

        for idx, err_text in enumerate(self.error_entries):
            # Erste Zeile als Überschrift (kurz)
            first_line = err_text.splitlines()[0] if err_text else "Fehler"

            btn = ttk.Button(self.inner_frame, text=first_line, style="TButton")
            btn.grid(row=2*idx, column=0, sticky="ew", pady=2)
            btn.bind("<1>", lambda e, i=idx: self._toggle(i))
            self.widgets.append(btn)

            # Fehlerdetails (anfangs versteckt)
            lbl = ttk.Label(self.inner_frame, text=err_text, justify="left", background="white")
            lbl.grid(row=2*idx+1, column=0, sticky="ew")
            lbl.grid_remove()
            self.widgets.append(lbl)
            self.expanded[idx] = False

    def _toggle(self, idx):
        # Auf-/Zuklappen
        lbl = self.widgets[2*idx+1]
        if self.expanded[idx]:
            lbl.grid_remove()
            self.expanded[idx] = False
        else:
            lbl.grid()
            self.expanded[idx] = True

class DashBoard(ttk.Frame):
    def __init__(self, parent, notebook, kapitel_config, client):
        super().__init__(notebook)
        self.client = client
        self.queue = queue.Queue()  # Queue für UI-Updates und Thread-Kommunikation
        self.after(100, self.process_queue)
        self.master= parent  # Zugriff auf die Hauptanwendung
        
      
        self.threads = []
        self.abort_flag = threading.Event()
   
        self.notebook = notebook
        self.notebook.add(self, text="🎤 Sprecher-Annotationen Hauptansicht")
     
        self.kapitel_config = kapitel_config

        self.kapitel_config_datei = None
        self.ordner = None
        self.output_folder = None  # Wird gesetzt beim Dateiauswahl
        
        self.selected_file = tk.StringVar()
        
        self.chapter_vars: dict[str, tk.BooleanVar] = {}
        self.task_vars: dict[str, tk.BooleanVar] = {}
        self.force_var = tk.BooleanVar(value=False)  # Checkbox für --force
        
        # Spinner-Labels für Tasks
        self.task_spinner_labels = {}  # task_id -> ttk.Label (Spinner)
        
        # Kapitel-Status-Labels & Progressbars
        self.kapitel_task_labels = {}  # key: kapitelname, value: ttk.Label
        self.kapitel_progressbars = {}  # key: kapitelname, value: ttk.Progressbar
        
        # Aktive Aufgabe Label (Anzeige)
        self.aktive_aufgabe_label = ttk.Label(self, text="")
        
        # Spinner für Kapitel-Aufgaben (key: (kapitelname, aufgaben_id) -> ttk.Label)
        self.kapitel_spinner_labels = {}
        
        # Spinner Animation State (Index pro (kapitel, aufgabe))
        self._aktive_spinner = {}  # key: (kapitel, aufgabe), value: Index (0-3)
        
        # Spinner Frames für Animation
        self._spinner_frames = ["◐", "◓", "◑", "◒"]
        self._spinner_index = 0
        
        # Generisches Spinner-Label (wird ggf. genutzt)
        self._spinner_label = ttk.Label(self, text="", font=("Consolas", 14))
        
        self.kapitel_fortschritte = {}  # kapitel_name -> aktueller Fortschritt (0-100)
      
        self.shutdown_controller = ShutdownController(self)

        self.laufende_ki_tasks = defaultdict(set)  # Kapitelname → Menge von Aufgaben-IDs

         # UI-Elemente bauen (muss als Methode definiert sein)
        self._build_widgets()

        if config.FehlerAnzeigen:
            logfile = os.path.join("Eingabe", "meinLog_lezterDurchlauf.log")  # Beispiel-Logpfad anpassen
            self.fehlermonitor = FehlerAnzeige(self, logfile)
            self.fehlermonitor.grid(row=7, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
            self.rowconfigure(7, weight=0)  # optional: fixierte Höhe durch Fehleranzeige

    def toggle_tab(self, tab_text):
        for tab_id in self.notebook.tabs():
            if self.notebook.tab(tab_id, "text") == tab_text:
                state = self.notebook.tab(tab_id, "state")
                current = self.notebook.select()

                if state == "hidden":
                    self.notebook.tab(tab_id, state="normal")
                    if current != tab_id:
                        self.notebook.select(tab_id)
                    else:
                        # Tab ist schon aktiv, Event wird nicht gefeuert,
                        # also manuell deine Logik ausführen
                        self.lade_aufgaben_checkboxes()
                else:
                    if current == tab_id:
                        for t in self.notebook.tabs():
                            if self.notebook.tab(t, "text") == "Hauptseite":
                                self.notebook.select(t)
                                break
                    self.notebook.hide(tab_id)
                break

    def kapitel_annotation_editor_starten(self):
        ausgewaehlte_kapitel = [k for k, v in self.chapter_vars.items() if v.get()]
        if not ausgewaehlte_kapitel:
            print("Keine Kapitel ausgewählt!")
            return

        for kapitel in ausgewaehlte_kapitel:
            dateipfad = os.path.join(config.GLOBALORDNER["merge"], f"{kapitel}_gesamt.json")
            
            # Tab-Frame anlegen
            tab_frame = ttk.Frame(self.notebook)
            
            # AnnotationenEditor in diesem Tab initialisieren
            editor = AnnotationenEditor(tab_frame,self.notebook, dateipfad)
            editor.pack(expand=True, fill="both")
            
            # Tab zum Notebook hinzufügen
            self.notebook.add(tab_frame, text=kapitel)
            
        # Optional: erster neuer Tab aktivieren
        if ausgewaehlte_kapitel:
            self.notebook.select(len(self.notebook.tabs()) - len(ausgewaehlte_kapitel))

    def _build_widgets(self):
        
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        #     self.columnconfigure(2, weight=1)  # Spalte 3 für Systemressourcen

        # Frame für die beiden Buttons oben rechts
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=0, column=1, sticky="ne", padx=5, pady=5)
        
        # Button "Installation" links im Button-Frame
        btn_open_install = ttk.Button(btn_frame, text="🔧", command=lambda: self.toggle_tab("🔧 Installation und Modellwahl"), width=3)
        btn_open_install.grid(row=0, column=0, sticky="e", padx=(0,5))
        
        # Button "Konfiguration" rechts im Button-Frame
        btn_open_config = ttk.Button(btn_frame, text="⚙️", command=lambda: self.toggle_tab("⚙️ Einstellungen"), width=3)
        btn_open_config.grid(row=0, column=1, sticky="e")

        # Damit der btn_frame nicht seine Größe minimiert, Spalte 1 "dehnt" sich
        btn_frame.columnconfigure(0, weight=0)
        btn_frame.columnconfigure(1, weight=0)
     
        # Zeile 1: Quelle (.docx) Frame und weitere UI-Elemente
        frm_file = ttk.Labelframe(self, text="Quelle (.docx)")
        frm_file.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        frm_file.columnconfigure(1, weight=1)  # Label darf wachsen

        btn_datei_waehlen = ttk.Button(frm_file, text="Datei wählen", command=self.select_word_file)
        btn_datei_waehlen.grid(row=0, column=0, padx=5, pady=5)

        lbl_datei = ttk.Label(frm_file, textvariable=self.selected_file)
        lbl_datei.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        ttk.Button(frm_file, text="📖 Kapitel‑Konfiguration öffnen", command=self.open_kapitel_config) \
            .grid(row=0, column=2, padx=5, pady=5)

        # Zeile 2: Hauptpane mit zwei Spalten: Aufgaben | Kapitel
        pan = ttk.Frame(self)
        pan.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        pan.columnconfigure(0, weight=2)
        pan.columnconfigure(1, weight=3)
        pan.rowconfigure(0, weight=1)

        # — Aufgaben links —
        self.aufg_frame = ttk.LabelFrame(pan, text="Aufgaben und Modelle")
        self.aufg_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.aufg_frame.columnconfigure(1, weight=1)  # Spinner‑Label kann wachsen

       # Checkboxen für Aufgaben laden
        self.lade_aufgaben_checkboxes()

     
        # — Kapitel rechts (scrollbar) —
        chap_container = ttk.Frame(pan)
        chap_container.grid(row=0, column=1, sticky="nsew")
        chap_container.columnconfigure(0, weight=1)
        chap_container.rowconfigure(0, weight=1)

        # Canvas und Scrollbar
        self.chapter_canvas = tk.Canvas(chap_container, borderwidth=0, highlightthickness=0)
        self.chapter_canvas.grid(row=0, column=0, sticky="nsew")
        chap_scroll = ttk.Scrollbar(chap_container, orient="vertical", command=self.chapter_canvas.yview)
        chap_scroll.grid(row=0, column=1, sticky="ns")
        self.chapter_canvas.configure(yscrollcommand=chap_scroll.set)

        # Frame für Kapitel‑Checkboxen
        self.chapter_frame = ttk.LabelFrame(self.chapter_canvas, text="Kapitel")
        self.chapter_canvas.create_window((0, 0), window=self.chapter_frame, anchor="nw")

        # Scrollregion bei Änderung automatisch anpassen
        self.chapter_frame.bind(
            "<Configure>",
            lambda e: self.chapter_canvas.configure(scrollregion=self.chapter_canvas.bbox("all"))
        )

        # — Force‑Checkbox und Start‑Button unten —
        # ttk.Checkbutton(self, text="Force (überschreibe vorhandene Dateien)", variable=self.force_var) \
        #     .grid(row=3, column=0, columnspan=2, sticky="w", pady=5, padx=10)

        # Rahmen für Start- und Stop-Buttons zentriert
        self.start_stop_button_frame = ttk.Frame(self)
        self.start_stop_button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        self.start_button = ttk.Button(self.start_stop_button_frame, text="Ausgewählte Aufgaben starten", command=self.start_tasks)
        self.start_button.grid(row=0, column=0, padx=10)

        self.stop_button = ttk.Button(self.start_stop_button_frame, text="Stoppen", command=self.stop_tasks)
        self.stop_button.grid(row=0, column=1, padx=10)

        # — Info‑Zeile mit aktiver Aufgabe und globalem Spinner —
        info_zeile = ttk.Frame(self)
        info_zeile.grid(row=5, column=0, columnspan=2, sticky="ew", pady=5, padx=10)
        info_zeile.columnconfigure(0, weight=1)
        info_zeile.columnconfigure(1, weight=1)

        self.aktive_aufgabe_label.grid(in_=info_zeile, row=0, column=0, sticky="w")
        self._spinner_label.grid(in_=info_zeile, row=0, column=1, sticky="e")

        # — Layout‑Expansion im Haupt‑Frame erlauben —
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)  # Wichtig: Hauptbereich wächst mit!

        # Starte Spinner‑Animation
        self._active_task_spinners = {}
        self._spinner_index = 0
        self.after(200, self._animate_task_spinners)

      # --- Spalte 3: Systemressourcen ---
        #      self.systemressourcen_anzeigen = tk.BooleanVar(value=False)
                
        #    '     # Checkbox zum Ein-/Ausblenden
        #         chk = ttk.Checkbutton(self, text="Systemressourcen anzeigen",
        #                               variable=self.systemressourcen_anzeigen,
        #                               command=self._toggle_systemressourcen)
        #         chk.grid(row=1, column=2, sticky="nw", padx=5, pady=5)
                
        #         # Frame für Systemressourcen
        #         self.sys_frame = ttk.Labelframe(self, text="Systemressourcen")
        #         self.sys_frame.grid(row=2, column=2, rowspan=2, sticky="nsew", padx=5, pady=5)
        #         self.sys_frame.columnconfigure(1, weight=1)
                
        #         self.sys_labels = {}
        #         labels = [
        #             "RAM Genutzt", "RAM Gesamt", "RAM Prozent",
        #             "Swap Genutzt", "Swap Gesamt", "Swap Prozent", "Swap Bytes In", "Swap Bytes Out",
        #             "Logische CPU-Kerne", "Physische CPU-Kerne", "CPU Auslastung gesamt", "CPU Auslastung pro Kern",
        #             "Festplatte Genutzt", "Festplatte Gesamt", "Festplatte Prozent",
        #             "Netzwerk Gesendet (MB)", "Netzwerk Empfangen (MB)"
        #         ]
                
        #         for i, label in enumerate(labels):
        #             ttk.Label(self.sys_frame, text=label).grid(row=i, column=0, sticky="w", padx=5, pady=2)
        #             val_lbl = ttk.Label(self.sys_frame, text="—")
        #             val_lbl.grid(row=i, column=1, sticky="w", padx=5, pady=2)
        #             self.sys_labels[label] = val_lbl
                
        #         # Starte Thread
        #         self._start_systemressourcen_thread()

        # Shutdown nur einblenden, wenn supported
        if self.shutdown_controller._is_shutdown_supported():

            shutdown_options = ["Nein", "5 min", "10 min", "15 min", "30 min", "45 min", "1h"]
            self.shutdown_var = tk.StringVar(value="Nein")

            lbl_shutdown = ttk.Label(self, text="Automatisches Herunterfahren bei Inaktivität nach Fertigstellung:")
            cb_shutdown = ttk.Combobox(self, values=shutdown_options, textvariable=self.shutdown_var, state="readonly", width=10)
           
            lbl_shutdown.grid(row=5, column=0,columnspan=2, pady=(10, 5), sticky="n")
            cb_shutdown.grid(row=6, column=0,columnspan=2, pady=(0, 10), sticky="n")

            def on_shutdown_changed(event=None):
                auswahl = self.shutdown_var.get()
                if auswahl == "Nein":
                    self.shutdown_controller.disabled()
                else:
                    # Umwandeln in Sekunden
                    mapping = {
                        "5 min": 5*60,
                        "10 min": 10*60,
                        "15 min": 15*60,
                        "30 min": 30*60,
                        "45 min": 45*60,
                        "1h": 60*60,
                    }
                    sekunden = mapping.get(auswahl, 0)
                    if sekunden > 0:
                        self.shutdown_controller.set_shutdown_timeout(sekunden)

            cb_shutdown.bind("<<ComboboxSelected>>", on_shutdown_changed)

    def _start_systemressourcen_thread(self):
        thread = threading.Thread(target=self._systemressourcen_worker, daemon=True)
        thread.start()

    def _systemressourcen_worker(self):
        import time
        while True:
            if self.systemressourcen_anzeigen.get():
                ram = Systemressourcen.get_ram_info()
                swap = Systemressourcen.get_swap_info()
                cpu = Systemressourcen.get_cpu_info()
                disk = Systemressourcen.get_disk_info()
                net = Systemressourcen.get_network_stats()
                self.after(0, self._update_labels, ram, swap, cpu, disk, net)
            time.sleep(2)

    def _update_labels(self, ram, swap, cpu, disk, net):
        self.sys_labels["RAM Genutzt"].config(text=f"{ram['used'] / (1024**3):.2f} GB")
        self.sys_labels["RAM Gesamt"].config(text=f"{ram['total'] / (1024**3):.2f} GB")
        self.sys_labels["RAM Prozent"].config(text=f"{ram['percent']} %")

        self.sys_labels["Swap Genutzt"].config(text=f"{swap['used'] / (1024**3):.2f} GB")
        self.sys_labels["Swap Gesamt"].config(text=f"{swap['total'] / (1024**3):.2f} GB")
        self.sys_labels["Swap Prozent"].config(text=f"{swap['percent']} %")
        self.sys_labels["Swap Bytes In"].config(text=f"{swap['sin'] / (1024**2):.2f} MB")
        self.sys_labels["Swap Bytes Out"].config(text=f"{swap['sout'] / (1024**2):.2f} MB")

        self.sys_labels["Logische CPU-Kerne"].config(text=str(cpu['logical_cores']))
        self.sys_labels["Physische CPU-Kerne"].config(text=str(cpu['physical_cores']))
        self.sys_labels["CPU Auslastung gesamt"].config(text=f"{cpu['cpu_percent_total']} %")
        self.sys_labels["CPU Auslastung pro Kern"].config(text=", ".join(f"{p}%" for p in cpu['cpu_percent_per_core']))

        self.sys_labels["Festplatte Genutzt"].config(text=f"{disk['used'] / (1024**3):.2f} GB")
        self.sys_labels["Festplatte Gesamt"].config(text=f"{disk['total'] / (1024**3):.2f} GB")
        self.sys_labels["Festplatte Prozent"].config(text=f"{disk['percent']} %")

        self.sys_labels["Netzwerk Gesendet (MB)"].config(text=f"{net['bytes_sent'] / (1024**2):.2f} MB")
        self.sys_labels["Netzwerk Empfangen (MB)"].config(text=f"{net['bytes_recv'] / (1024**2):.2f} MB")



    @staticmethod
    def lade_prompt_datei(ki_id):
        print(f"[INFO] Lade Prompt für KI-ID: {ki_id}")

        if ki_id not in config.KI_AUFGABEN:
            raise ValueError(f"[FEHLER] Unbekannte KI-ID: {ki_id}")

        prompts_ordner = os.path.join("Eingabe", "prompts")

        dateiname = config.KI_AUFGABEN[ki_id] + ".txt"
        dateipfad = os.path.join(prompts_ordner, dateiname)

        print(f"[INFO] Erwarteter Pfad zur Prompt-Datei: {dateipfad}")

        try:
            with open(dateipfad, "r", encoding="utf-8") as f:
                inhalt = f.read()
                print(f"[OK] Prompt-Datei erfolgreich geladen ({len(inhalt)} Zeichen).")
                return inhalt
        except FileNotFoundError:
            raise FileNotFoundError(f"[FEHLER] Die Datei '{dateipfad}' wurde nicht gefunden.")



    def _set_task_spinner(self, task_id, aktivieren=True):
        if not hasattr(self, "_active_task_spinners"):
            self._active_task_spinners = {}
        self._active_task_spinners[task_id] = aktivieren

        label = self.task_spinner_labels.get(task_id)
        if label:
            if aktivieren:
                label.config(text=self._spinner_frames[0])
            else:
                label.config(text="")

    def _animate_task_spinners(self):
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        frame = self._spinner_frames[self._spinner_index]

        # Spinner nur bei aktiven Tasks zeigen
        for task_id, label in list(self.task_spinner_labels.items()):
            if not label.winfo_exists():
                # Widget existiert nicht mehr, entferne Label aus dict, um späteren Zugriff zu verhindern
                del self.task_spinner_labels[task_id]
                continue
            
            if self.task_vars.get(task_id, tk.BooleanVar()).get():
                # Wenn der Spinner für die Aufgabe aktiv sein soll, setze Frame
                if getattr(self, "_active_task_spinners", {}).get(task_id, False):
                    label.config(text=frame)
                else:
                    label.config(text="")
            else:
                label.config(text="")

        # Nach 200 ms wieder aufrufen, aber nur wenn noch Labels vorhanden sind
        if self.task_spinner_labels:
            self.after(200, self._animate_task_spinners)


    def aktualisiere_progressbar(self, kapitel_name, task_id = None, wert = 0):
        pb = self.kapitel_progressbars.get(kapitel_name)
        lbl = self.kapitel_task_labels.get(kapitel_name)

        if pb and lbl:
            pb["value"] = wert
            if wert == 0:
                pb.grid_remove()
                lbl.grid_remove()
            else:
                lbl.config(text=f"Aufgabe: {task_id}")
                lbl.grid()
                pb.grid()

        # Gesamtfortschritt aktualisieren
        self.kapitel_fortschritte[kapitel_name] = wert

        # Durchschnitt berechnen
        if self.kapitel_fortschritte:
            gesamt = sum(self.kapitel_fortschritte.values()) / len(self.kapitel_fortschritte)
        else:
            gesamt = 0

        # Gesamt-Progressbar aktualisieren (wenn vorhanden)
        if hasattr(self, "gesamt_progressbar") and self.gesamt_progressbar:
            self.gesamt_progressbar["value"] = gesamt

        # Optional: Gesamtstatus-Label aktualisieren
        if hasattr(self, "gesamt_status_label") and self.gesamt_status_label:
            self.gesamt_status_label["text"] = f"Gesamtfortschritt: {int(gesamt)} %"


    def aktualisiere_laufende_ki_tasks(self, kapitel_name, task_id=None, wert=None):
        if not hasattr(self, "task_fortschritt"):
            self.task_fortschritt = {}

        if kapitel_name not in self.task_fortschritt:
            self.task_fortschritt[kapitel_name] = {}

        if task_id is not None and wert is not None:
            self.task_fortschritt[kapitel_name][task_id] = wert
        elif task_id is not None and wert is None:
            # Task abgeschlossen
            self.task_fortschritt[kapitel_name][task_id] = 1.0

        # Durchschnitt berechnen
        task_dict = self.task_fortschritt.get(kapitel_name, {})
        if task_dict:
            durchschnitt = sum(task_dict.values()) / len(task_dict)
        else:
            durchschnitt = 0

        self.aktualisiere_progressbar(kapitel_name, task_id, round(durchschnitt * 100, 1))


    def InhaltsverzeichnisAuslesenMitDialog(self):
        if not self.selected_file.get():
            messagebox.showwarning("Fehler", "Bitte zuerst eine Word-Datei laden.")
            return
        try:
            doc = Document(self.selected_file.get())
            styles = sorted({p.style.name for p in doc.paragraphs if p.style and p.style.name})
            if not styles:
                messagebox.showerror("Fehler", "Keine Formatvorlagen gefunden.")
                return
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Öffnen der Datei:\n{e}")
            return

        if hasattr(self, 'kapitel_config_dialog'):
            self.kapitel_config_dialog.destroy()

        dialog = tk.Toplevel(self)
        dialog.title("Kapitel-Stil auswählen")
        dialog.columnconfigure(1, weight=1)

        # Stil-Auswahl
        ttk.Label(dialog, text="Kapitelstil:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        style_var = tk.StringVar()
        combo_style = ttk.Combobox(dialog, textvariable=style_var, values=styles, state="readonly")
        combo_style.grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        # Numerierung
        ttk.Label(dialog, text="Numerierung:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        nummer_var = tk.StringVar(value="nein")
        combo_num = ttk.Combobox(
            dialog,
            textvariable=nummer_var,
            values=[
                "nein",
                "arabische Zahlen [1,2,3…]",
                "römische Zahlen [I,II,III…]",
                "lateinisch Punkt [a.,b.,c.]",
                "lateinisch Klammer [a),b),c)]"
            ],
            state="readonly"
        )
        combo_num.grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # Aufsteigend Checkbox
        aufst_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog, text="Nummerierung muss aufsteigend sein", variable=aufst_var)\
            .grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        # Präfix-Einstellungen
        praefix_frame = ttk.Frame(dialog)
        praefix_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        praefix_frame.columnconfigure(1, weight=1)

        ttk.Label(praefix_frame, text="Präfix:").grid(row=0, column=0, sticky="w")
        praefix_var = tk.StringVar(value="Kapitel")
        ttk.Entry(praefix_frame, textvariable=praefix_var).grid(row=0, column=1, sticky="ew", padx=5)
        nur_pref_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(praefix_frame, text="nur Präfix berücksichtigen", variable=nur_pref_var)\
            .grid(row=0, column=2, sticky="w", padx=(5, 0))

        # OK-Button
        def auswahl_bestaetigen():
            stil = style_var.get()
            nummer = nummer_var.get()
            praefix = praefix_var.get().strip() if nur_pref_var.get() else None
            aufsteigend = aufst_var.get()

            if not stil:
                messagebox.showwarning("Auswahl erforderlich", "Bitte einen Stil auswählen.")
                return

            if nur_pref_var.get() and praefix == "":
                messagebox.showwarning("Warnung", "Präfix darf nicht leer sein, wenn 'nur Präfix berücksichtigen' aktiviert ist.")
                return

            dialog.destroy()
            self.kapitel_config._create_from_word(stil, self.selected_file.get(), nummer, praefix, aufsteigend)

        btn_ok = ttk.Button(dialog, text="Kapitel übernehmen", command=auswahl_bestaetigen)
        btn_ok.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 15))

        # Dialog zentrieren
        dialog.update_idletasks()
        w, h = max(dialog.winfo_width(), 350), dialog.winfo_height()
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    def open_kapitel_config(self):

        self.kapitel_config_dialog = tk.Toplevel(self)
        dialog = self.kapitel_config_dialog
        dialog.title("Kapitel-Konfig")
        dialog.columnconfigure(0, weight=1)

        btn_laden = ttk.Button(dialog, text="existierende Konfiguration laden", 
                            command=lambda: (dialog.destroy(), self.kapitel_config.lade_konfiguration()))
        btn_laden.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))

        if self.selected_file.get():
            btn_inhalt = ttk.Button(dialog, text="Kapitel aus Word-Datei auslesen",  command=self.InhaltsverzeichnisAuslesenMitDialog)
            btn_inhalt.grid(row=1, column=0, sticky="ew", padx=10, pady=2)

        btn_auto = ttk.Button(dialog, text="Kapitel automatisch erzeugen", 
                            command=lambda: (dialog.destroy(), self.kapitel_config.kapitel_auto_erzeugen()))
        btn_auto.grid(row=2, column=0, sticky="ew", padx=10, pady=2)

        btn_manuell = ttk.Button(dialog, text="manuell bearbeiten", 
                                command=lambda: (dialog.destroy(), self.kapitel_config.kapitel_manuell_bearbeiten()))
        btn_manuell.grid(row=3, column=0, sticky="ew", padx=10, pady=(2, 10))

        
        # Warte auf Layoutberechnung
        dialog.update_idletasks()

        # Fenstergröße
        width = max(dialog.winfo_width(),350) # Mindestbreite        
        height = dialog.winfo_height() 
        
        # Fenster zentrieren relativ zum Hauptfenster (self)
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2

        dialog.geometry(f"{width}x{height}+{x}+{y}")

        # Optional: Modalität
        dialog.transient(self)
        dialog.grab_set()

    def lade_aufgaben_checkboxes(self):
        print("Aufgaben-Checkboxen geladen!")
        importlib.reload(config)
        for widget in self.aufg_frame.winfo_children():
            widget.destroy()

        self.task_vars = {}

        # Feste Einträge 1 und 2
        self.aufgaben_input = {
            1: "Text nach Kapiteln aufteilen",
            2: "Kapitel für KI vorbereiten",
        }

        if getattr(config, "NUTZE_KI",True):
            print("KI nutzen!")
            for key, wert in sorted(config.KI_AUFGABEN.items()):
                self.aufgaben_input[key] = f"{wert.capitalize()}-Erkennung (mit KI)"
            if config.KI_AUFGABEN:
                max_key = max(config.KI_AUFGABEN.keys())
                next_key = max_key + 1
            else:
                next_key = 3
        else:
            next_key = 3

        self.aufgaben_input[next_key] = "Erzeugung (Merge + PDF)"

        # Modelle abrufen
        try:
            modelle = self.client.get_installed_models()
            if not modelle:
                raise RuntimeError("Keine Modelle gefunden.")
        except Exception as e:
            print(f"[WARN] Modelle konnten nicht geladen werden: {e}")
            # Tab wechseln - Beispielcode
            for tab_id in self.notebook.tabs():
                if self.notebook.tab(tab_id, "text") == "InstallationModellwahl":
                    self.notebook.select(tab_id)
                    break
            return

        self.model_selection_boxes = {}
        self.task_status_labels = {}

        for i, (schritt_nr, beschreibung) in enumerate(self.aufgaben_input.items()):
            var = tk.BooleanVar(value=(schritt_nr == 1))  # hier int 1 statt str "1"
            frame = ttk.Frame(self.aufg_frame)
            frame.grid(row=i, column=0, sticky="ew", pady=2)
            frame.columnconfigure(0, weight=3)
            frame.columnconfigure(1, weight=1)
            frame.columnconfigure(2, weight=0)
            frame.columnconfigure(3, weight=0)

            cb = tk.Checkbutton(frame, text=beschreibung, variable=var)
            cb.grid(row=0, column=0, sticky="w")

            spinner_lbl = ttk.Label(frame, text="", font=("Consolas", 12))
            spinner_lbl.grid(row=0, column=1, sticky="w", padx=5)

            self.task_vars[schritt_nr] = var
            self.task_spinner_labels[schritt_nr] = spinner_lbl

            if "(mit ki)" in beschreibung.lower() and modelle:
                combo = ttk.Combobox(frame, values=modelle, state="readonly", width=40)
                combo.set(modelle[0])
                combo.grid(row=0, column=2, padx=5, sticky="w")
                self.model_selection_boxes[schritt_nr] = combo

            status_label = ttk.Label(frame, text="", foreground="gray", width=30)
            status_label.grid(row=0, column=3, padx=5, sticky="w")
            self.task_status_labels[schritt_nr] = status_label

        # Button außerhalb der Loop in eigenem Frame
        btn_frame = ttk.Frame(self.aufg_frame)
        btn_frame.grid(row=len(self.aufgaben_input), column=0, sticky="w", pady=5)
        btn_kapitel_bearbeiten = ttk.Button(
            btn_frame,
            text="Annotationen manuell optimieren",
            command=self.kapitel_annotation_editor_starten
        )
        btn_kapitel_bearbeiten.grid(row=0, column=0, sticky="w")


    def select_word_file(self):
        # 1. Word-Datei auswählen
        file_path = filedialog.askopenfilename(
            title="Word-Datei auswählen",
            filetypes=[("Word-Dateien", "*.docx")]
        )
        if not file_path:
            return

        pfad_obj = Path(file_path)
        self.selected_file.set(str(pfad_obj))
        print(f"[DEBUG] Ausgewählter Pfad: {repr(pfad_obj)}")

        # 3. Ausgabe-Ordnerstruktur vorbereiten
        ergebnisse_basis = pfad_obj.parent / "Annotationstoolergebnisse"
        dateiname_ohne_endung = pfad_obj.stem
        ergebnisse_ordner = ergebnisse_basis / dateiname_ohne_endung
        ergebnisse_ordner.mkdir(parents=True, exist_ok=True)
        print(f"[DEBUG] Ausgabeordner: {repr(ergebnisse_ordner)}")

        self.output_folder = ergebnisse_ordner  # als Path speichern, nicht str
        self.kapitel_config.output_folder = str(self.output_folder)

        # 4. Kapitel-Konfigurationsdatei laden
        self.kapitel_config_datei = ergebnisse_ordner / "kapitel_config.json"
        print(f"[DEBUG] Kapitel-Konfigurationsdatei Pfad: {repr(self.kapitel_config_datei)}")

        if self.kapitel_config_datei.is_file():
            try:
                self.kapitel_config.load_from_file(str(self.kapitel_config_datei))
                print(f"[INFO] Kapitel-Konfiguration aus {self.kapitel_config_datei} geladen.")
                print("[DEBUG] geladene kapitel_config:", self.kapitel_config.kapitel_daten)
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Kapitel-Konfiguration nicht laden: {e}")
                self.kapitel_config_datei = None
        else:
            messagebox.showwarning("Bitte Kapitel-Konfiguration laden oder erzeugen!")
            self.kapitel_config_datei = None

        # Weitere Ausgabe-Unterordner anlegen
        self.ordner = {
            "Eingabe":  ergebnisse_ordner / "Eingabe",
            "txt":    ergebnisse_ordner / "txt",
            "json":   ergebnisse_ordner / "json",
            "satz":   ergebnisse_ordner / "satz",
            "ki":     ergebnisse_ordner / "ki",
            "merge":  ergebnisse_ordner / "merge",
            "pdf":    ergebnisse_ordner / "pdf",
        }
        
        for pfad in self.ordner.values():
            pfad.mkdir(parents=True, exist_ok=True)
            print(f"[DEBUG] Ordner erstellt: {repr(pfad)}")
        
        config.GLOBALORDNER.clear() 
        config.GLOBALORDNER.update(self.ordner)

        # 6. Kapitel-Checkboxes aktualisieren
        self.lade_kapitel_checkboxes()

    def lade_kapitel_checkboxes(self):

        # Vorherige Inhalte löschen
        for widget in self.chapter_frame.winfo_children():
            widget.destroy()

        self.chapter_vars.clear()
        self.kapitel_progressbars = {}
        self.kapitel_task_labels = {}

        if not self.kapitel_config.kapitel_liste:
            label = ttk.Label(self.chapter_frame, text="Keine Kapitel gefunden.")
            label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
            return

        self.all_var = tk.BooleanVar(value=False)

        def alle_auswaehlen_toggle():
            wert = self.all_var.get()
            for var in self.chapter_vars.values():
                var.set(wert)

        style = ttk.Style()
        style.configure("HervorgehobeneCheckbutton.TCheckbutton",
                        font=("Segoe UI", 10, "bold"),
                        foreground="blue")

        rahmen = ttk.Frame(self.chapter_frame, padding=5, style="HervorhebungsFrame.TFrame")
        rahmen.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 10))
        rahmen.grid_columnconfigure(0, weight=1)

        cb_all = ttk.Checkbutton(
            rahmen,
            text="★ Alle Kapitel",
            variable=self.all_var,
            command=alle_auswaehlen_toggle,
            style="HervorgehobeneCheckbutton.TCheckbutton"
        )
        cb_all.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 10))

        # Kapitel-Checkboxen ab Zeile 1
        for idx, name in enumerate(self.kapitel_config.kapitel_liste, start=1):
            var = tk.BooleanVar(value=False)
            self.chapter_vars[name] = var

            frame = ttk.Frame(self.chapter_frame)
            frame.grid(row=idx, column=0, sticky="ew", padx=5, pady=2)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_columnconfigure(1, weight=0)
            frame.grid_columnconfigure(2, weight=0)

            cb = ttk.Checkbutton(frame, text=name, variable=var)
            cb.grid(row=0, column=0, sticky="w")

            pb = ttk.Progressbar(frame, orient="horizontal", length=150, mode="determinate")
            pb.grid(row=0, column=1, sticky="e", padx=5)
            pb.grid_remove()
            self.kapitel_progressbars[name] = pb

            lbl_task = ttk.Label(frame, text="", width=20, anchor="w")
            lbl_task.grid(row=0, column=1, sticky="w", padx=(5, 0))
            lbl_task.grid_remove()
            self.kapitel_task_labels[name] = lbl_task

            def einzel_cb_callback(*args, kapitel=name, var=var):
                if var.get():
                    self.kapitel_progressbars[kapitel].grid()
                else:
                    self.kapitel_progressbars[kapitel].grid_remove()

                alle_aktiv = all(v.get() for v in self.chapter_vars.values())
                self.all_var.set(alle_aktiv)

            var.trace_add("write", einzel_cb_callback)

        # Initial: "Alle auswählen" prüfen (wahrscheinlich False, da alle aus)
        alle_aktiv = all(v.get() for v in self.chapter_vars.values())
        self.all_var.set(alle_aktiv)

    def start_tasks(self):
        print("[DEBUG] Starte Aufgabenverarbeitung")
        self.abort_flag.clear()
        self.task_flags = {key: var.get() for key, var in self.task_vars.items()}


        ausgewaehlte_kapitel = [name for name, var in self.chapter_vars.items() if var.get()]
        print(f"[DEBUG] Ausgewählte Kapitel: {ausgewaehlte_kapitel}")

        for kapitel in ausgewaehlte_kapitel:
            thread = threading.Thread(target=self.verarbeite_kapitel, args=(kapitel,))
            thread.start()
            self.threads.append(thread)

    def verarbeite_kapitel(self, kapitel_name):
        self.laufende_ki_tasks[kapitel_name] = set()
        try:
            print(f"[DEBUG] Beginne Verarbeitung für Kapitel: {kapitel_name}")         
            ordner = self.ordner

            if self.task_flags.get(1, False):
                self._set_task_spinner(1, True)
                self.aktualisiere_progressbar(kapitel_name, "1", 0.1)
                # aufgabe 1 - schritt1
                extrahiere_kapitel_mit_config(
                    self.selected_file.get(),
                    self.kapitel_config.kapitel_liste,
                    ordner["txt"],
                    [kapitel_name], 
                    lambda k, w: self.aktualisiere_progressbar(k, "1", w)
                )
                self._set_task_spinner(1, False)

            if self.task_flags.get(2, False):
                self._set_task_spinner(2, True)
                # aufgabe 2.1- schritt 2
                if self.abort_flag.is_set(): return
                self.aktualisiere_progressbar(kapitel_name, "Vorverarbeitung", 0.1)
                verarbeite_kapitel_und_speichere_json(
                    ordner["txt"],
                    ordner["json"],
                    [kapitel_name],
                    lambda kapitel, fortschritt: self.aktualisiere_progressbar(kapitel, "2.1", fortschritt)
                )

                # aufgabe 2.2 - schritt 3
                if self.abort_flag.is_set(): return
                self.aktualisiere_progressbar(kapitel_name, "Satzbildung", 0.1)
                dateien_aufteilen(
                    kapitel_name,
                    ordner["json"],
                    ordner["satz"],
                    lambda kapitel, fortschritt: self.aktualisiere_progressbar(kapitel, "2.2", fortschritt)
                )
                self._set_task_spinner(2, False)


            if getattr(config, "NUTZE_KI",True):
                # aufgaben 3-7 etc - schritt 4
                if self.abort_flag.is_set():
                    return
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = []

                    aktive_tasks = [aid for aid in config.KI_AUFGABEN if self.task_flags.get(aid, False)]

                    for idx, aufgaben_id in enumerate(aktive_tasks):
                        aufgaben_key = config.KI_AUFGABEN[aufgaben_id]
                        task_name = f"Aufgabe {aufgaben_id}: {aufgaben_key}"
                        print(f"[DEBUG] Plane {task_name} für {kapitel_name}")

                        prompt = self.lade_prompt_datei(aufgaben_id) + "\n" + self.kapitel_config.kapitel_daten.get(kapitel_name, {}).get(f"ZusatzInfo_{aufgaben_id}", "")
                        print(f"(Aufgabenstellung {aufgaben_key}: {prompt})")

                        modell_name = None
                        if hasattr(self, "model_selection_boxes") and aufgaben_id in self.model_selection_boxes:
                            modell_name = self.model_selection_boxes[aufgaben_id].get()
                            print(f"[DEBUG] Modell für {task_name}: {modell_name}")

                        self.client.CheckandSet_model(modell_name)

                        futures.append(
                            executor.submit(
                                self.verarbeite_KI_Task,
                                kapitel_name,
                                aufgaben_id,
                                prompt,
                                modell_name,
                                ordner,
                                idx + 1,  # tasknr
                                len(aktive_tasks)  # anzahl_tasks
                            )
                        )

                    # Warte auf alle Tasks
                    for future in futures:
                        future.result()

                    # Bestimme den nächsten Key nach dem höchsten in KI_AUFGABEN
                    if config.KI_AUFGABEN:
                        max_key = max(config.KI_AUFGABEN.keys())
                        next_key = max_key + 1
                    else:
                        next_key = 3  # fallback, falls KI_AUFGABEN leer ist
            else:
                next_key = 3
                
            if self.task_flags.get(next_key, False):
                # aufgabe 8.1 schritt 5
                if self.abort_flag.is_set(): return
                self.aktualisiere_progressbar(kapitel_name, "final 1", 0.1)
                Merge_annotationen(                
                    ordner["json"],
                    ordner["ki"],
                    ordner["merge"],
                    [kapitel_name],
                    lambda w: self.aktualisiere_progressbar(kapitel_name, "final 1", w)
                )

                # aufgabe 8.2 schritt 6
                if self.abort_flag.is_set(): return
                self.aktualisiere_progressbar(kapitel_name, "final 2", 0.1)
                visualisiere_annotationen(
                    ordner["merge"],
                    ordner["pdf"],
                    [kapitel_name],
                    lambda w: self.aktualisiere_progressbar(kapitel_name, "final 2", w)
                )

            self.aktualisiere_progressbar(kapitel_name, "Fertig", 1.0)
            print(f"[INFO] Kapitel abgeschlossen: {kapitel_name}")

        except Exception as e:
            print(f"[FEHLER] Verarbeitung für Kapitel '{kapitel_name}' fehlgeschlagen:", str(e))
            traceback.print_exc()


    def verarbeite_KI_Task(self, kapitel_name, aufgaben_id, prompt, modell_name, ordner, tasknr=None, anzahl_tasks=None):
        try:
            # Spinner für diese Aufgabe aktivieren
            self._set_task_spinner(aufgaben_id, True)

            # Task-Label zusammensetzen
            aufgaben_text = config.KI_AUFGABEN.get(aufgaben_id, f"ID {aufgaben_id}")
            task_label = f"Task {tasknr}/{anzahl_tasks}: {aufgaben_text}" if tasknr and anzahl_tasks else f"Aufgabe {aufgaben_id}: {aufgaben_text}"
            print(f"[THREAD-DEBUG] Starte {task_label} für {kapitel_name}")

            # Satzdateien für dieses Kapitel sammeln
            satzdateien = [f for f in os.listdir(ordner["satz"]) if kapitel_name in f]
            anzahl = len(satzdateien)

            # Laufenden Task registrieren
            self.laufende_ki_tasks[kapitel_name].add(aufgaben_id)
            self.aktualisiere_laufende_ki_tasks(kapitel_name, task_label, 0)

            # Verarbeite jede Satzdatei
            for i, dateiname in enumerate(satzdateien, start=1):
                if self.abort_flag.is_set():
                    print(f"[ABBRUCH] Während {task_label} bei Satzdatei {dateiname}")
                    return

                fortschritt = i / anzahl
                pfad_satz = os.path.join(ordner["satz"], dateiname)

                # Fortschritt aktualisieren
                #self.aktualisiere_laufende_ki_tasks(kapitel_name, task_label, fortschritt)

                # Verarbeitung starten mit Callback
                daten_verarbeiten(
                    self.client,
                    prompt,
                    pfad_satz,
                    ordner["ki"],
                    aufgaben_id,
                    self.force_var,
                    None
                )
                    #lambda w: self.aktualisiere_laufende_ki_tasks(
                     #   kapitel_name, task_label, min(1.0, fortschritt + w / anzahl)
             #       )
          #      )

            # Task als abgeschlossen markieren
       #     self.aktualisiere_laufende_ki_tasks(kapitel_name, task_label, 1.0)
            self.laufende_ki_tasks[kapitel_name].discard(aufgaben_id)

            # Spinner für diese Aufgabe deaktivieren
            self._set_task_spinner(aufgaben_id, False)

            print(f"[THREAD-DEBUG] {task_label} abgeschlossen für {kapitel_name}")

        except Exception as e:
            # Spinner deaktivieren auch bei Fehler
            self._set_task_spinner(aufgaben_id, False)
            print(f"[FEHLER] bei {task_label}: {e}")

        
        
    def stop_tasks(self):
        print("[DEBUG] Abbruchsignal wird gesetzt")
        self.abort_flag.set()
        for t in self.threads:
            if t.is_alive():
                print(f"[DEBUG] Warte auf Thread: {t.name}")
                t.join()



    # def start_tasks(self):
    #     print("start_tasks wurde aufgerufen")
    #     self.abort_flag = threading.Event()
    #     self.abort_flag.clear()
    #     startzeit = time.time()
    #     self.disable_controls()

    #     chosen_tasks = [k for k, v in self.task_vars.items() if v.get()]
    #     ausgewaehlte_kapitel = [k for k, v in self.chapter_vars.items() if v.get()]

    #     if not self.selected_file.get():
    #         messagebox.showwarning("Fehler", "Bitte zuerst eine .docx-Datei auswählen.")
    #         self.enable_controls()
    #         return

    #     if not chosen_tasks:
    #         messagebox.showwarning("Fehler", "Bitte Aufgaben auswählen.")
    #         self.enable_controls()
    #         return

    #     if not self.ordner:
    #         messagebox.showwarning("Fehler", "Ordner für Ergebnisse nicht gefunden. Bitte Word-Datei erneut auswählen.")
    #         self.enable_controls()
    #         return

    #     force = self.force_var.get()

    #     def run_task_parallel(task_id):
    #         if self.abort_flag.is_set():
    #             print(f"[INFO] Task {task_id} übersprungen (Abbruch erkannt)")
    #             return
    #         print(f"[INFO] Starte Task {task_id} mit paralleler Kapitelverarbeitung")
    #         threads = []
    #         for kapitel in ausgewaehlte_kapitel:
    #             if self.abort_flag.is_set():
    #                 break
    #             t = threading.Thread(target=self._execute_task_einzeln, args=(task_id, kapitel, force))
    #             t.start()
    #             threads.append(t)
    #         for t in threads:
    #             t.join()
    #         print(f"[INFO] Task {task_id} fertig")

    #     ki_task_ids = {str(k) for k in config.KI_AUFGABEN.keys()}

    #     # Task 1 (Kapitel extrahieren mit Config) - parallel pro Kapitel
    #     if "1" in chosen_tasks:
    #         run_task_parallel("1")

    #     # Task 2 (Verarbeitung und Aufteilen) - parallel pro Kapitel
    #     if "2" in chosen_tasks:
    #         run_task_parallel("2")

    #     # KI-Tasks 3-7 (oder beliebige aus config.KI_AUFGABEN) - parallel pro Kapitel
    #     tasks_ki = [t for t in chosen_tasks if t in ki_task_ids]
    #     ki_threads = []
    #     for task_id in tasks_ki:
    #         if self.abort_flag.is_set():
    #             break
    #         t = threading.Thread(target=run_task_parallel, args=(task_id,))
    #         t.start()
    #         ki_threads.append(t)
    #     for t in ki_threads:
    #         t.join()

    #     # Task 8 (Merge + PDF-Erzeugung), immer am Ende, wenn gewählt und nicht abgebrochen
    #     if "8" in chosen_tasks and not self.abort_flag.is_set():
    #         print("[INFO] Starte Task 8 (Merge + PDF-Erzeugung)")
    #         Schritt5.Merge_annotationen(
    #             quellordner_kapitel=self.ordner["json"],
    #             quellordner_annotationen=self.ordner["ki"],
    #             ziel_ordner=self.ordner["merge"],
    #             ausgewaehlte_kapitel=ausgewaehlte_kapitel,
    #             progress_callback=lambda kapitel, wert: self.queue.put(('aktualisiere_progressbar', kapitel, wert))
    #         )
    #         threads_pdf = []
    #         for kapitel in ausgewaehlte_kapitel:
    #             if self.abort_flag.is_set():
    #                 break
    #             t = threading.Thread(target=Schritt6.visualisiere_annotationen, kwargs={
    #                 "eingabe_ordner": self.ordner["merge"],
    #                 "ausgabe_ordner": self.ordner["pdf"],
    #                 "ausgewaehlte_kapitel": [kapitel],
    #                 "progress_callback": lambda k, w: self.queue.put(('aktualisiere_progressbar', k, w))
    #             })
    #             t.start()
    #             threads_pdf.append(t)
    #         for t in threads_pdf:
    #             t.join()
    #         print("[INFO] Task 8 fertig")

    #     self.enable_controls()

    #     dauer_str = f"{time.time() - startzeit:.2f} Sekunden"
    #     self.aktive_aufgabe_label["text"] = "Abgebrochen" if self.abort_flag.is_set() else ""

    #     if hasattr(self, 'task_manager'):
    #         self.task_manager.show_task_finished_popup("Tasks", dauer_str)


    # def _execute_task_einzeln(self, task_id, kapitel, force):
    #     print(f"[DEBUG] Einzel-Task {task_id} startet für Kapitel {kapitel}")

    #     try:
    #         self._set_task_spinner(task_id, True)
    #         self.queue.put(('aktualisiere_progressbar', kapitel, 0))
    #         self.queue.put(('update_status', kapitel, f"Starte Aufgabe {task_id}"))

    #         ki_task_ids = {str(k) for k in config.KI_AUFGABEN.keys()}

    #         if task_id == "1":
    #             print(f"[DEBUG] Task 1: Kapitel extrahieren mit Config für {kapitel}")
    #             Schritt1.extrahiere_kapitel_mit_config(
    #                 self.selected_file.get(),
    #                 self.kapitel_config_datei,
    #                 self.ordner["txt"],
    #                 ausgewaehlte_kapitel=[kapitel],
    #                 progress_callback=lambda k, w: self.queue.put(('aktualisiere_progressbar', k, w))
    #             )

    #         elif task_id == "2":
    #             print(f"[DEBUG] Task 2: Verarbeitung + Aufteilen für {kapitel}")
    #             Schritt2.verarbeite_kapitel_und_speichere_json(
    #                 self.ordner["txt"], self.ordner["json"],
    #                 ausgewaehlte_kapitel=[kapitel],
    #                 progress_callback=lambda k, w: self.queue.put(('aktualisiere_progressbar', k, w))
    #             )
    #             Schritt3.dateien_aufteilen(
    #                 self.ordner["json"], self.ordner["satz"],
    #                 progress_callback=lambda k, w: self.queue.put(('aktualisiere_progressbar', k, w))
    #             )

    #         elif task_id in ki_task_ids:
    #             ki_id = int(task_id)
    #             prompt_text = lade_prompt_datei(ki_id)

    #             modell_name = None
    #             if hasattr(self, "model_selection_boxes") and task_id in self.model_selection_boxes:
    #                 modell_name = self.model_selection_boxes[task_id].get()
    #                 print(f"[DEBUG] Modell für Task {task_id}: {modell_name}")

    #             self.client.CheckandSet_model(modell_name)

    #             nicht_notwendig = self.kapitel_config.kapitel_daten.get(kapitel, {}).get("nicht_notwendige_unterschritte", [])
    #             if ki_id in nicht_notwendig:
    #                 print(f"[INFO] Task {task_id} für Kapitel {kapitel} übersprungen (nicht notwendig)")
    #                 self.queue.put(('update_status', task_id, f"{kapitel} übersprungen"))
    #                 return

    #             zusatzinfo = self.kapitel_config.kapitel_daten.get(kapitel, {}).get(f"ZusatzInfo_{ki_id}", "")
    #             prompt = prompt_text + zusatzinfo
    #             kapitel_satz_ordner = self.ordner["satz"]

    #             satz_dateien = sorted([
    #                 f for f in os.listdir(kapitel_satz_ordner)
    #                 if f.startswith(kapitel) and f.endswith(".json")
    #             ])
    #             if not satz_dateien:
    #                 print(f"[INFO] Task {task_id} für Kapitel {kapitel} übersprungen (keine Satzdateien)")
    #                 self.queue.put(('update_status', task_id, f"{kapitel} übersprungen"))
    #                 return

    #             gesamt_satz = len(satz_dateien)
    #             for i, satz_datei_name in enumerate(satz_dateien, 1):
    #                 if self.abort_flag.is_set():
    #                     print(f"[INFO] Abbruch Task {task_id} Satz {i} Kapitel {kapitel}")
    #                     break
    #                 self.queue.put(('update_status', task_id, f"{kapitel}: Satz {i}/{gesamt_satz}"))
    #                 satz_datei = os.path.join(kapitel_satz_ordner, satz_datei_name)
    #                 Schritt4.daten_verarbeiten(
    #                     self.client, prompt, satz_datei, self.ordner["ki"], ki_id, force,
    #                     modell=modell_name
    #                 )
    #                 fortschritt = int(i / gesamt_satz * 100)
    #                 self.queue.put(('aktualisiere_progressbar', f"{kapitel} Satz {i}", fortschritt))

    #         else:
    #             print(f"[WARN] Task {task_id} nicht erkannt")

    #         self.queue.put(('aktualisiere_progressbar', kapitel, 100))
    #         self.queue.put(('update_status', kapitel, f"Aufgabe {task_id} für {kapitel} abgeschlossen"))

    #     except Exception as e:
    #         print(f"[ERROR] Fehler bei Aufgabe {task_id}, Kapitel {kapitel}: {e}")
    #         self.queue.put(('update_status', kapitel, f"Fehler: {e}"))

    #     finally:
    #         self._set_task_spinner(task_id, False)
    #         self.queue.put(('set_label', ""))

    #         if hasattr(self, "gesamt_progressbar"):
    #             self.queue.put(('aktualisiere_progressbar', "gesamt", 100))
    #         if hasattr(self, "gesamt_status_label"):
    #             self.queue.put(('update_status', "gesamt", "Gesamtfortschritt: 100 %"))

    #         endzeit_str = datetime.datetime.now().strftime("%H:%M:%S")
    #         status_label = self.kapitel_task_labels.get("Dokument")
    #         progressbar = self.kapitel_progressbars.get("Dokument")
    #         if status_label:
    #             self.queue.put(('update_status', "Dokument", f"✔ abgeschlossen ({endzeit_str})"))
    #         if progressbar:
    #             self.queue.put(('aktualisiere_progressbar', "Dokument", 100))

    #         dauer = time.time() - startzeit
    #         print(f"[INFO] Einzel-Task {task_id} für Kapitel {kapitel} fertig in {dauer:.2f} Sekunden")
    #         self.aktive_aufgabe_label["text"] = ""

    #         if hasattr(self, "shutdown_controller") and self.shutdown_controller._is_shutdown_supported():
    #             self.shutdown_controller.show_task_finished_popup(task_id, f"{dauer:.2f} Sekunden")


    # def start_tasks(self):
    #         print("start_tasks wurde aufgerufen")
    #         self.abort_flag = threading.Event()  # Abbruch-Flag
    #         self.abort_flag.clear()
    #         startzeit = time.time()
    #         self.disable_controls()
    #         chosen_tasks = [k for k, v in self.task_vars.items() if v.get()]

    #         if not self.selected_file.get():
    #             messagebox.showwarning("Fehler", "Bitte zuerst eine .docx-Datei auswählen.")
    #             self.enable_controls()
    #             return
    #         if not chosen_tasks:
    #             messagebox.showwarning("Fehler", "Bitte Aufgaben auswählen.")
    #             self.enable_controls()
    #             return
    #         if not self.ordner:
    #             messagebox.showwarning("Fehler", "Ordner für Ergebnisse nicht gefunden. Bitte Word-Datei erneut auswählen.")
    #             self.enable_controls()
    #             return

    #         force = self.force_var.get()

    #         def run_task_parallel(task_id):
    #             if self.abort_flag.is_set():
    #                 print(f"[INFO] Task {task_id} übersprungen (Abbruch erkannt)")
    #                 return
    #             print(f"[INFO] Starte Task {task_id} mit paralleler Kapitelverarbeitung")
    #             ausgewaehlte_kapitel = [k for k, v in self.chapter_vars.items() if v.get()]
    #             threads = []
    #             for kapitel in ausgewaehlte_kapitel:
    #                 if self.abort_flag.is_set():
    #                     break
    #                 t = threading.Thread(target=self._execute_task_einzeln, args=(task_id, kapitel, force))
    #                 t.start()
    #                 threads.append(t)
    #             for t in threads:
    #                 t.join()
    #             print(f"[INFO] Task {task_id} fertig")

    #         ki_task_ids = {str(k) for k in config.KI_AUFGABEN.keys()}

    #         if "1" in chosen_tasks:
    #             run_task_parallel("1")

    #         if "2" in chosen_tasks:
    #             run_task_parallel("2")

    #         tasks_3_7 = [t for t in chosen_tasks if t in ki_task_ids]
    #         threads_3_7 = []
    #         for task_id in tasks_3_7:
    #             if self.abort_flag.is_set():
    #                 break
    #             t = threading.Thread(target=run_task_parallel, args=(task_id,))
    #             t.start()
    #             threads_3_7.append(t)

    #         for t in threads_3_7:
    #             t.join()

    #         if config.KI_AUFGABEN:
    #             max_key = max(config.KI_AUFGABEN.keys())
    #             last_task_id = str(max_key + 1)
    #         else:
    #             last_task_id = "3"

    #         if last_task_id in chosen_tasks and not self.abort_flag.is_set():
    #             print(f"[INFO] Starte Task {last_task_id}")
    #             Schritt5.Merge_annotationen(
    #                 quellordner_kapitel=self.ordner["json"],
    #                 quellordner_annotationen=self.ordner["ki"],
    #                 ziel_ordner=self.ordner["merge"],
    #                 ausgewaehlte_kapitel=[k for k, v in self.chapter_vars.items() if v.get()],
    #                 progress_callback=lambda kapitel, wert: self.queue.put(('aktualisiere_progressbar', kapitel, wert))
    #             )
    #             ausgewaehlte_kapitel = [k for k, v in self.chapter_vars.items() if v.get()]
    #             threads_schritt6 = []
    #             for kapitel in ausgewaehlte_kapitel:
    #                 if self.abort_flag.is_set():
    #                     break
    #                 t = threading.Thread(target=Schritt6.visualisiere_annotationen, kwargs={
    #                     "eingabe_ordner": self.ordner["merge"],
    #                     "ausgabe_ordner": self.ordner["pdf"],
    #                     "ausgewaehlte_kapitel": [kapitel],
    #                     "progress_callback": lambda k, w: self.queue.put(('aktualisiere_progressbar', k, w))
    #                 })
    #                 t.start()
    #                 threads_schritt6.append(t)
    #             for t in threads_schritt6:
    #                 t.join()
    #             print(f"[INFO] Task {last_task_id} fertig")
    #             self.aktive_aufgabe_label["text"] = ""
    #             dauer_str = f"{time.time() - startzeit:.2f} Sekunden"
    #             if hasattr(self, 'task_manager'):
    #                 self.task_manager.show_task_finished_popup(last_task_id, dauer_str)

    #         self.enable_controls()
    #         if self.abort_flag.is_set():
    #             self.aktive_aufgabe_label["text"] = "Abgebrochen"

    
    # def _execute_task_einzeln(self, task_id, kapitel, force):
    #     print(f"[DEBUG] Einzel-Task {task_id} startet für Kapitel {kapitel}")
    #     ausgewaehlte_kapitel = [k for k, v in self.chapter_vars.items() if v.get()]
    #     print(f"[DEBUG] Task {task_id} - Ausgewählte Kapitel: {ausgewaehlte_kapitel}")

    #     startzeit = time.time()

    #     self.kapitel_fortschritte.clear()
    #     for kapitel_item in ausgewaehlte_kapitel:
    #         self.queue.put(('aktualisiere_progressbar', kapitel_item, 0))
    #     if hasattr(self, "gesamt_progressbar"):
    #         self.queue.put(('aktualisiere_progressbar', "gesamt", 0))
    #     if hasattr(self, "gesamt_status_label"):
    #         self.queue.put(('update_status', "gesamt", "Gesamtfortschritt: 0 %"))

    #     ki_task_ids = {str(k) for k in config.KI_AUFGABEN.keys()}
    #     print(f"[DEBUG] KI Task IDs: {ki_task_ids}")

    #     try:
    #         print(f"[DEBUG] Starte Ausführung für Task {task_id} Kapitel {kapitel}")
    #         self._set_task_spinner(task_id, True)

    #         self.queue.put(('aktualisiere_progressbar', kapitel, 0))
    #         self.queue.put(('update_status', kapitel, f"Starte Aufgabe {task_id}"))

    #         if task_id == "1":
    #             print("[DEBUG] Task 1: Kapitel extrahieren mit Config")
    #             Schritt1.extrahiere_kapitel_mit_config(
    #                 self.selected_file.get(),
    #                 self.kapitel_config_datei,
    #                 self.ordner["txt"],
    #                 ausgewaehlte_kapitel=[kapitel],
    #                 progress_callback=lambda k, w: self.queue.put(('aktualisiere_progressbar', k, w))
    #             )
    #             print(f"[DEBUG] Task 1 für Kapitel {kapitel} abgeschlossen")

    #         elif task_id == "2":
    #             print("[DEBUG] Task 2: Kapitel verarbeiten und JSON speichern")
    #             Schritt2.verarbeite_kapitel_und_speichere_json(
    #                 self.ordner["txt"], self.ordner["json"],
    #                 ausgewaehlte_kapitel=[kapitel],
    #                 progress_callback=lambda k, w: self.queue.put(('aktualisiere_progressbar', k, w))
    #             )
    #             print("[DEBUG] Task 2: Aufteilen der Dateien")
    #             Schritt3.dateien_aufteilen(
    #                 self.ordner["json"], self.ordner["satz"],
    #                 progress_callback=lambda k, w: self.queue.put(('aktualisiere_progressbar', k, w))
    #             )
    #             print(f"[DEBUG] Task 2 für Kapitel {kapitel} abgeschlossen")

    #         elif task_id in ki_task_ids:
    #             ki_id = int(task_id)
    #             print(f"[DEBUG] KI Task {ki_id} starten")
    #             prompt_text = lade_prompt_datei(ki_id)

    #             modell_name = None
    #             if hasattr(self, "model_selection_boxes") and task_id in self.model_selection_boxes:
    #                 modell_box = self.model_selection_boxes[task_id]
    #                 if modell_box:
    #                     modell_name = modell_box.get()
    #                     print(f"[DEBUG] Verwendetes Modell für Task {task_id}: {modell_name}")

    #             self.client.CheckandSet_model(modell_name)

    #             nicht_notwendig = self.kapitel_config.kapitel_daten.get(kapitel, {}).get("nicht_notwendige_unterschritte", [])
    #             print(f"[DEBUG] Nicht notwendige Unterschritte für Kapitel {kapitel}: {nicht_notwendig}")
    #             if ki_id in nicht_notwendig:
    #                 print(f"[INFO] Task {task_id} für Kapitel {kapitel} übersprungen (nicht notwendig)")
    #                 self.queue.put(('update_status', task_id, f"{kapitel} übersprungen"))
    #                 return

    #             zusatzinfo = self.kapitel_config.kapitel_daten.get(kapitel, {}).get(f"ZusatzInfo_{ki_id}", "")
    #             prompt = prompt_text + zusatzinfo
    #             kapitel_satz_ordner = self.ordner["satz"]

    #             satz_dateien = sorted(
    #                 [f for f in os.listdir(kapitel_satz_ordner) if f.startswith(kapitel) and f.endswith(".json")]
    #             )
    #             print(f"[DEBUG] {len(satz_dateien)} Satzdateien gefunden für Kapitel {kapitel}")
    #             if not satz_dateien:
    #                 print(f"[INFO] Task {task_id} für Kapitel {kapitel} übersprungen (keine Satzdateien)")
    #                 self.queue.put(('update_status', task_id, f"{kapitel} übersprungen"))
    #                 return

    #             gesamt_satz = len(satz_dateien)
    #             for i, satz_datei_name in enumerate(satz_dateien, 1):
    #                 if self.abort_flag.is_set():
    #                     print(f"[INFO] Abbruch während Task {task_id} Satz {i} Kapitel {kapitel}")
    #                     break
    #                 self.queue.put(('update_status', task_id, f"{kapitel}: Satz {i}/{gesamt_satz}"))
    #                 satz_datei = os.path.join(kapitel_satz_ordner, satz_datei_name)
    #                 print(f"[DEBUG] Verarbeite Satzdatei {satz_datei_name} ({i}/{gesamt_satz})")
    #                 Schritt4.daten_verarbeiten(
    #                     self.client, prompt, satz_datei, self.ordner["ki"], ki_id, force,
    #                     modell=modell_name
    #                 )
    #                 fortschritt = int(i / gesamt_satz * 100)
    #                 self.queue.put(('aktualisiere_progressbar', f"{kapitel} Satz {i}", fortschritt))

    #             print(f"[DEBUG] KI Task {task_id} für Kapitel {kapitel} abgeschlossen")

    #         else:
    #             print(f"[WARN] Task {task_id} nicht erkannt oder wird extern behandelt")

    #         self.queue.put(('aktualisiere_progressbar', kapitel, 100))
    #         self.queue.put(('update_status', kapitel, f"Aufgabe {task_id} für {kapitel} abgeschlossen"))

    #     except Exception as e:
    #         print(f"[ERROR] Fehler bei Aufgabe {task_id}, Kapitel {kapitel}: {e}")
    #         self.queue.put(('update_status', kapitel, f"Fehler: {e}"))

    #     finally:
    #         self._set_task_spinner(task_id, False)
    #         self.queue.put(('set_label', ""))

    #         if hasattr(self, "gesamt_progressbar"):
    #             self.queue.put(('aktualisiere_progressbar', "gesamt", 100))
    #         if hasattr(self, "gesamt_status_label"):
    #             self.queue.put(('update_status', "gesamt", "Gesamtfortschritt: 100 %"))

    #         endzeit = time.time()
    #         dauer = endzeit - startzeit
    #         dauer_str = f"{dauer:.2f} Sekunden"

    #         status_label = self.kapitel_task_labels.get("Dokument")
    #         progressbar = self.kapitel_progressbars.get("Dokument")
    #         endzeit_str = datetime.datetime.now().strftime("%H:%M:%S")

    #         if status_label:
    #             self.queue.put(('update_status', "Dokument", f"✔ abgeschlossen ({endzeit_str})"))
    #         if progressbar:
    #             self.queue.put(('aktualisiere_progressbar', "Dokument", 100))

    #         print(f"[INFO] Einzel-Task {task_id} für Kapitel {kapitel} fertig in {dauer_str}")
    #         self.aktive_aufgabe_label["text"] = ""

    #         if hasattr(self, "shutdown_controller") and self.shutdown_controller._is_shutdown_supported():
    #             print("[DEBUG] Zeige Shutdown-Popup an")
    #             self.shutdown_controller.show_task_finished_popup(task_id, dauer_str)


    def process_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item[0] == 'update_status':
                    _, task_id, text = item
                    if task_id == "gesamt":
                        if hasattr(self, "gesamt_status_label"):
                            self.gesamt_status_label.config(text=text)
                    elif task_id in self.task_status_labels:
                        self.task_status_labels[task_id].config(text=text)
                    elif task_id == "Dokument" and "Dokument" in self.kapitel_task_labels:
                        self.kapitel_task_labels["Dokument"].config(text=text)
                elif item[0] == 'aktualisiere_progressbar':
                    _, task_id, wert = item
                    if task_id == "gesamt":
                        if hasattr(self, "gesamt_progressbar"):
                            self.gesamt_progressbar["value"] = wert
                    elif task_id in self.kapitel_progressbars:
                        self.kapitel_progressbars[task_id]["value"] = wert
                elif item[0] == 'set_label':
                    _, text = item
                    self.aktive_aufgabe_label.config(text=text)
                self.queue.task_done()
        except queue.Empty:
            pass
        self.after(100, self.process_queue)

    def stop_tasks(self):
        if hasattr(self, 'abort_flag'):
            antwort = messagebox.askyesno("Bestätigen", "Möchten Sie die laufenden Aufgaben wirklich abbrechen?")
            if antwort:
                self.abort_flag.set()
                print("[INFO] Benutzer hat Abbruch angefordert.")
            else:
                print("[INFO] Abbruch vom Benutzer abgelehnt.")

    def disable_controls(self):
        # Alle Buttons und Checkbuttons außer Stop-Button deaktivieren
        for widget in self.iterate_widgets(self):
            if isinstance(widget, (ttk.Button, ttk.Checkbutton)) and widget != self.stop_button:
                widget.config(state="disabled")
        self.stop_button.config(state="normal")
        
    def enable_controls(self):
        # Alle Buttons und Checkbuttons außer Stop-Button aktivieren
        for widget in self.iterate_widgets(self):
            if isinstance(widget, (ttk.Button, ttk.Checkbutton)) and widget != self.stop_button:
                widget.config(state="normal")
        self.stop_button.config(state="disabled")
        
    def iterate_widgets(self, parent):
        # Generator, der alle Widgets in parent rekursiv durchläuft
        for widget in parent.winfo_children():
            yield widget
            if widget.winfo_children():
                yield from self.iterate_widgets(widget)