# ------------------ Imports ------------------
import ast
import copy
import concurrent.futures
import os
import psutil
import threading
import time
import tkinter as tk
import traceback
import queue
import importlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from docx import Document
from multiprocessing import Manager
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path


import Eingabe.config as config
from annotationen_editor import AnnotationenEditor
from Schritt1 import extrahiere_kapitel_mit_config
from Schritt2 import verarbeite_kapitel_und_speichere_json
from Schritt3 import dateien_aufteilen
from Schritt4 import daten_verarbeiten
from Schritt5 import Merge_annotationen
from Schritt6 import visualisiere_annotationen
from huggingface_client import HuggingFaceClient
from shutdown import ShutdownController
from system_ressourcen import Systemressourcen
from config_editor import ConfigEditor

def lade_prompt_datei(ki_id):
        print(f"[INFO] Lade Prompt für KI-ID: {ki_id}")

        # Überprüfe, ob ki_id in der Konfiguration existiert
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
            raise FileNotFoundError(f"[FEHLER] Die Datei '{dateipfad}' wurde nicht gefunden. Bitte sicherstellen, dass die Datei vorhanden ist.")
        except Exception as e:
            # Fange unerwartete Fehler ab
            raise RuntimeError(f"[FEHLER] Fehler beim Laden der Prompt-Datei '{dateipfad}': {e}")
        

def ki_task_process(kapitel_name, aufgaben_id, prompt, modell_name, ordner, mp_progress_queue=None):
    print(f"[DEBUG] KI-Task für Kapitel '{kapitel_name}', Aufgabe {aufgaben_id}", flush = True)

    max_retries = 3
    for versuch in range(1, max_retries + 1):
        try:
            print(f"[DEBUG] KI-Task start Versuch {versuch} für Kapitel '{kapitel_name}', Aufgabe {aufgaben_id}", flush = True)

            try:
                print(f"[DEBUG] Initialisiere HuggingFaceClient() für {kapitel_name}/{aufgaben_id}")
                client = HuggingFaceClient()
            except Exception as e:
                print(f"[FEHLER] Fehler bei Initialisierung des HuggingFaceClient: {e}", flush=True)
                traceback.print_exc()
                return None

            print(f"[DEBUG] Modell prüfen/setzen: {modell_name}")
            client.check_and_set_model(modell_name)

            satz_ordner = Path(ordner["satz"])
            if not satz_ordner.exists() or not satz_ordner.is_dir():
                raise FileNotFoundError(f"Ordner für Satzdateien nicht gefunden: {satz_ordner}")

            satzdateien = [f for f in satz_ordner.iterdir() if kapitel_name in f.name]
            anzahl = len(satzdateien)
            print(f"[DEBUG] Gefundene Satzdateien: {anzahl} für Kapitel {kapitel_name}")

            if anzahl == 0:
                if mp_progress_queue:
                    mp_progress_queue.put((kapitel_name, aufgaben_id, 100))
                return f"Keine Satzdateien für Kapitel {kapitel_name} gefunden."

            for i, datei in enumerate(satzdateien, start=1):
                print(f"[DEBUG] Verarbeite Satzdatei {i}/{anzahl}: {datei}")
                pfad_satz = datei  # Path-Objekt

                daten_verarbeiten(
                    client,
                    prompt,
                    str(pfad_satz),
                    ordner["ki"],
                    aufgaben_id,
                    force=False,
                )
                if mp_progress_queue:
                    fortschritt = int((i / anzahl) * 100)
                    mp_progress_queue.put((kapitel_name, aufgaben_id, fortschritt))
                    print(f"[DEBUG] Fortschritt gesendet: {fortschritt}%")

            print(f"[INFO] Task {aufgaben_id} für Kapitel {kapitel_name} erfolgreich abgeschlossen.")
            return f"Task {aufgaben_id} für Kapitel {kapitel_name} abgeschlossen"

        except Exception as e:
            print(f"[WARNUNG] Fehler bei KI-Task (Versuch {versuch}/{max_retries}): {e}")
            traceback.print_exc()
            if versuch == max_retries:
                print(f"[FEHLER] Task {aufgaben_id} für Kapitel {kapitel_name} nach {max_retries} Versuchen fehlgeschlagen.")
                return None
            else:
                print(f"[INFO] Starte Task {aufgaben_id} für Kapitel {kapitel_name} erneut...")

def warte_auf_freien_cpukern_und_ram(
    max_auslastung_cpu: float = 50.0,
    max_auslastung_ram: float = 80.0,
    timeout: float = 30.0,
    sleep_intervall: float = 0.5,
    verbose: bool = True
) -> bool:
    """
    Warte, bis mindestens ein CPU-Kern unter max_auslastung_cpu ist und RAM-Auslastung unter max_auslastung_ram,
    oder bis timeout abgelaufen ist. Gibt True zurück, wenn freie Ressourcen gefunden, sonst False.
    """
    # Erster Aufruf für valide CPU-Werte (Datenbasis)
    psutil.cpu_percent(percpu=True, interval=0.1)

    start_time = time.perf_counter()
    while True:
        cpu_last_pro_kern = psutil.cpu_percent(percpu=True, interval=0.1)
        ram_auslastung = psutil.virtual_memory().percent

        cpu_ok = any(last < max_auslastung_cpu for last in cpu_last_pro_kern)
        ram_ok = ram_auslastung < max_auslastung_ram

        if cpu_ok and ram_ok:
            if verbose:
                print(f"[INFO] Ressourcen frei: CPU-Kerne {cpu_last_pro_kern}, RAM {ram_auslastung:.1f}%")
            return True

        elapsed = time.perf_counter() - start_time
        if elapsed > timeout:
            if verbose:
                print(f"[WARNUNG] Timeout nach {timeout}s: CPU<{max_auslastung_cpu}%, RAM<{max_auslastung_ram}%, starte trotzdem.")
            return False

        if verbose:
            print(f"[INFO] Warte... CPU pro Kern: {cpu_last_pro_kern}, RAM: {ram_auslastung:.1f}%, verstrichene Zeit: {elapsed:.1f}s")
        
        print(f"warte_auf_freien_cpukern_und_ram geht schlafen")
        time.sleep(sleep_intervall)

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
        self.inner_window = self.canvas.create_window((0,0), window=self.inner_frame, anchor="nw")

        self.inner_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind('<Configure>', self._on_canvas_configure)

        self.inner_frame.columnconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.update_errors()  # Starte Updates

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.inner_window, width=event.width)

    def update_errors(self):
        try:
            with open(self.logfile_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            lines = []

        errors = []
        current_error = []
        collecting = False

        for line in lines:
            if any(keyword in line for keyword in ["ERROR", "Error", "FEHLER", "Fehler"]):
                if collecting and current_error:
                    errors.append("".join(current_error))
                    current_error = []
                collecting = True
                current_error.append(line)
            elif collecting:
                if line.strip() == "":
                    errors.append("".join(current_error))
                    current_error = []
                    collecting = False
                else:
                    current_error.append(line)

        if collecting and current_error:
            errors.append("".join(current_error))

        if errors != self.error_entries:
            self.error_entries = errors
            self._refresh_widgets()

        self.after(self.refresh_interval, self.update_errors)

    def _refresh_widgets(self):
        for w in self.widgets:
            w.destroy()
        self.widgets.clear()
        self.expanded.clear()

        for idx, err_text in enumerate(self.error_entries):
            first_line = err_text.splitlines()[0] if err_text else "Fehler"

            btn = ttk.Button(self.inner_frame, text=first_line)
            btn.grid(row=2*idx, column=0, sticky="ew", pady=2)
            btn.bind("<1>", lambda e, i=idx: self._toggle(i))
            self.widgets.append(btn)

            lbl = tk.Label(self.inner_frame, text=err_text, justify="left", bg="white")
            lbl.grid(row=2*idx+1, column=0, sticky="ew")
            lbl.grid_remove()
            self.widgets.append(lbl)
            self.expanded[idx] = False

    def _toggle(self, idx):
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
     
        # manager = Manager()
        # self.progress_queue = manager.Queue()  # Queue wird zwischen Prozessen geteilt
        # self.progress_queue_active =
        self.thread_queue = queue.Queue()
        self.tasks_running = False
        self.tasks_lock = threading.Lock()

        self.max_workers = psutil.cpu_count(logical=False) or 1  # Fallback 1, falls None [erstmal nur pyhsische und nicht logische]
      
        self.master = parent  # Zugriff auf die Hauptanwendung
        
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
       # self.force_var = tk.BooleanVar(value=False)  # Checkbox für --force
        
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

        self.kapitel_tasks = {}  # Struktur: {kapitel_name: {task_id: wert}}
        self._progress_lock = threading.Lock()
                # UI-Elemente bauen (muss als Methode definiert sein)
        self._build_widgets()

        self.lade_docx_aus_globalordner()
        
        # Grid-Konfiguration für dynamisches Layout
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        for i in range(8):
            self.rowconfigure(i, weight=0)
        self.rowconfigure(7, weight=1)  # Fehleranzeige wächst mit

        if config.FehlerAnzeigen:
            logfile ='meinLog_letzterDurchlauf.log'  # Beispiel-Logpfad anpassen
            self.fehlermonitor = FehlerAnzeige(self, logfile)
            self.fehlermonitor.grid(row=7, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)


    def toggle_tab(self, tab_text):
        for tab_id in self.notebook.tabs():
            if self.notebook.tab(tab_id, "text") == tab_text:
                state = self.notebook.tab(tab_id, "state")
                current = self.notebook.select()

                if state == "hidden":
                    # Tab ist versteckt, also sichtbar machen
                    self.notebook.tab(tab_id, state="normal")
                    # Falls Tab gerade nicht aktiv ist, aktiviere ihn
                    if current != tab_id:
                        self.notebook.select(tab_id)
                    else:
                        # Tab ist bereits aktiv, Event wird nicht gefeuert,
                        # deshalb eigene Logik manuell ausführen
                        self.lade_aufgaben_checkboxes()
                else:
                    # Tab ist sichtbar, also verstecken
                    if current == tab_id:
                        # Wenn der gerade aktive Tab versteckt wird,
                        # aktiviere stattdessen die "Hauptseite"
                        for t in self.notebook.tabs():
                            if self.notebook.tab(t, "text") == "Hauptseite":
                                self.notebook.select(t)
                                break
                    self.notebook.hide(tab_id)
                break


    def kapitel_annotation_editor_starten(self):
        ausgewaehlte_kapitel = [k for k, v in self.chapter_vars.items() if v.get()]
        if not ausgewaehlte_kapitel:
            messagebox.showwarning("Hinweis", "Keine Kapitel ausgewählt!")
            return

        fehlende_kapitel = []

        for kapitel in ausgewaehlte_kapitel:
            dateipfad = os.path.join(config.GLOBALORDNER["merge"], f"{kapitel}_gesamt.json")

            # Prüfung: existiert die Datei?
            if not os.path.exists(dateipfad):
                fehlende_kapitel.append(kapitel)
                continue

            tab_frame = ttk.Frame(self.notebook)
            editor = AnnotationenEditor(tab_frame, self.notebook, dateipfad, self.master.config_editor)
            editor.pack(expand=True, fill="both")
            self.notebook.add(tab_frame, text=kapitel)

            # Falls Kapitel fehlen, Hinweis anzeigen
        if fehlende_kapitel:
            messagebox.showwarning(
                "Fehlende Dateien",
                "Für folgende Kapitel wurden keine JSON-Dateien gefunden:\n\n" +
                "\n".join(fehlende_kapitel)
            )
        else:
            # Optional: ersten neuen Tab aktivieren
            if ausgewaehlte_kapitel:
                self.notebook.select(len(self.notebook.tabs()) - len(ausgewaehlte_kapitel))

    def _build_widgets(self):
        # Haupt-Grid: 2 Spalten (Buttons rechts, Hauptinhalt links)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)  # Hauptbereich wächst vertikal mit

        # --- Obere Buttons rechts ---
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=0, column=1, sticky="ne", padx=5, pady=5)
        btn_frame.columnconfigure(0, weight=0)
        btn_frame.columnconfigure(1, weight=0)

        ttk.Button(btn_frame, text="🔧", command=lambda: self.toggle_tab("🔧 Installation und Modellwahl"), width=3).grid(row=0, column=0, sticky="e", padx=(0,5))
        ttk.Button(btn_frame, text="⚙️", command=lambda: self.toggle_tab("⚙️ Einstellungen"), width=3).grid(row=0, column=1, sticky="e")

        # --- Quelle (.docx) Frame ---
        frm_file = ttk.Labelframe(self, text="Quelle (.docx)")
        frm_file.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        frm_file.columnconfigure(1, weight=1)  # Label darf wachsen

        ttk.Button(frm_file, text="Datei wählen", command=self.select_word_file).grid(row=0, column=0, padx=5, pady=5)
        ttk.Label(frm_file, textvariable=self.selected_file).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ttk.Button(frm_file, text="📖 Kapitel‑Konfiguration öffnen", command=self.open_kapitel_config).grid(row=0, column=2, padx=5, pady=5)

        # --- Hauptbereich mit 2 Spalten: Aufgaben | Kapitel ---
        pan = ttk.Frame(self)
        pan.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        pan.columnconfigure(0, weight=2)
        pan.columnconfigure(1, weight=3)
        pan.rowconfigure(0, weight=1)

        # Aufgaben-Frame links
        self.aufg_frame = ttk.LabelFrame(pan, text="Aufgaben und Modelle")
        self.aufg_frame.grid(row=0, column=0, sticky="nsew", padx=(0,10))
        self.aufg_frame.columnconfigure(1, weight=1)  # Spinner-Label kann wachsen

        # Aufgaben-Checkboxen laden (muss Kapitel-Checkboxen initialisieren)
        self.lade_aufgaben_checkboxes()

        # Kapitel-Frame rechts mit Scrollbar
        chap_container = ttk.Frame(pan)
        chap_container.grid(row=0, column=1, sticky="nsew")
        chap_container.columnconfigure(0, weight=1)
        chap_container.rowconfigure(0, weight=1)

        self.chapter_canvas = tk.Canvas(chap_container, borderwidth=0, highlightthickness=0)
        self.chapter_canvas.grid(row=0, column=0, sticky="nsew")

        chap_scroll = ttk.Scrollbar(chap_container, orient="vertical", command=self.chapter_canvas.yview)
        chap_scroll.grid(row=0, column=1, sticky="ns")
        self.chapter_canvas.configure(yscrollcommand=chap_scroll.set)

        self.chapter_frame = ttk.LabelFrame(self.chapter_canvas, text="Kapitel")
        self.chapter_canvas.create_window((0,0), window=self.chapter_frame, anchor="nw")

        # Scrollregion anpassen, wenn Inhalt sich ändert
        self.chapter_frame.bind(
            "<Configure>",
            lambda e: self.chapter_canvas.configure(scrollregion=self.chapter_canvas.bbox("all"))
        )

        # --- Start- und Stop-Buttons unten ---
        self.start_stop_button_frame = ttk.Frame(self)
        self.start_stop_button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        self.start_button = ttk.Button(self.start_stop_button_frame, text="Ausgewählte Aufgaben starten", command=self.start_tasks)
        self.start_button.grid(row=0, column=0, padx=10)

        self.stop_button = ttk.Button(self.start_stop_button_frame, text="Stoppen", command=self.stop_tasks)
        self.stop_button.grid(row=0, column=1, padx=10)

        # --- Info-Zeile mit aktiver Aufgabe und globalem Spinner ---
        info_zeile = ttk.Frame(self)
        info_zeile.grid(row=5, column=0, columnspan=2, sticky="ew", pady=5, padx=10)
        info_zeile.columnconfigure(0, weight=1)
        info_zeile.columnconfigure(1, weight=1)

        self.aktive_aufgabe_label.grid(in_=info_zeile, row=0, column=0, sticky="w")
        self._spinner_label.grid(in_=info_zeile, row=0, column=1, sticky="e")

        # --- Spinner-Animation starten ---
        self._active_task_spinners = {}
        self._spinner_index = 0
        self.after(200, self._animate_task_spinners)

        # --- Automatisches Herunterfahren (optional) ---
        if self.shutdown_controller._is_shutdown_supported():
            shutdown_options = ["Nein", "5 min", "10 min", "15 min", "30 min", "45 min", "1h"]
            self.shutdown_var = tk.StringVar(value="Nein")

            lbl_shutdown = ttk.Label(self, text="Automatisches Herunterfahren bei Inaktivität nach Fertigstellung:")
            cb_shutdown = ttk.Combobox(self, values=shutdown_options, textvariable=self.shutdown_var, state="readonly", width=10)

            lbl_shutdown.grid(row=5, column=0, columnspan=2, pady=(10,5), sticky="n")
            cb_shutdown.grid(row=6, column=0, columnspan=2, pady=(0,10), sticky="n")

            def on_shutdown_changed(event=None):
                auswahl = self.shutdown_var.get()
                if auswahl == "Nein":
                    self.shutdown_controller.disabled()
                else:
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

    # def _start_systemressourcen_thread(self):
    #     thread = threading.Thread(target=self._systemressourcen_worker, daemon=True)
    #     thread.start()

    # def _systemressourcen_worker(self):
    #     import time
    #     while True:
    #         if self.systemressourcen_anzeigen.get():
    #             ram = Systemressourcen.get_ram_info()
    #             swap = Systemressourcen.get_swap_info()
    #             cpu = Systemressourcen.get_cpu_info()
    #             disk = Systemressourcen.get_disk_info()
    #             net = Systemressourcen.get_network_stats()
    #             self.after(0, self._update_labels, ram, swap, cpu, disk, net)
    #         time.sleep(2)

    # def _update_labels(self, ram, swap, cpu, disk, net):
    #     self.sys_labels["RAM Genutzt"].config(text=f"{ram['used'] / (1024**3):.2f} GB")
    #     self.sys_labels["RAM Gesamt"].config(text=f"{ram['total'] / (1024**3):.2f} GB")
    #     self.sys_labels["RAM Prozent"].config(text=f"{ram['percent']} %")

    #     self.sys_labels["Swap Genutzt"].config(text=f"{swap['used'] / (1024**3):.2f} GB")
    #     self.sys_labels["Swap Gesamt"].config(text=f"{swap['total'] / (1024**3):.2f} GB")
    #     self.sys_labels["Swap Prozent"].config(text=f"{swap['percent']} %")
    #     self.sys_labels["Swap Bytes In"].config(text=f"{swap['sin'] / (1024**2):.2f} MB")
    #     self.sys_labels["Swap Bytes Out"].config(text=f"{swap['sout'] / (1024**2):.2f} MB")

    #     self.sys_labels["Logische CPU-Kerne"].config(text=str(cpu['logical_cores']))
    #     self.sys_labels["Physische CPU-Kerne"].config(text=str(cpu['physical_cores']))
    #     self.sys_labels["CPU Auslastung gesamt"].config(text=f"{cpu['cpu_percent_total']} %")
    #     self.sys_labels["CPU Auslastung pro Kern"].config(text=", ".join(f"{p}%" for p in cpu['cpu_percent_per_core']))

    #     self.sys_labels["Festplatte Genutzt"].config(text=f"{disk['used'] / (1024**3):.2f} GB")
    #     self.sys_labels["Festplatte Gesamt"].config(text=f"{disk['total'] / (1024**3):.2f} GB")
    #     self.sys_labels["Festplatte Prozent"].config(text=f"{disk['percent']} %")

    #     self.sys_labels["Netzwerk Gesendet (MB)"].config(text=f"{net['bytes_sent'] / (1024**2):.2f} MB")
    #     self.sys_labels["Netzwerk Empfangen (MB)"].config(text=f"{net['bytes_recv'] / (1024**2):.2f} MB")





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

        for task_id, label in list(self.task_spinner_labels.items()):
            if not label.winfo_exists():
                del self.task_spinner_labels[task_id]
                continue
            
            # Prüfen, ob Aufgabe aktiviert ist (existiert und True)
            if self.task_vars.get(task_id) and self.task_vars[task_id].get():
                # Spinner nur anzeigen, wenn auch aktiviert
                if getattr(self, "_active_task_spinners", {}).get(task_id, False):
                    label.config(text=frame)
                else:
                    label.config(text="")
            else:
                label.config(text="")

        if self.task_spinner_labels:
            self.after(200, self._animate_task_spinners)


    def aktualisiere_progressbar(self, kapitel_name, task_id=None, wert=0, mehrere=False):
        pb = self.kapitel_progressbars.get(kapitel_name)
        lbl = self.kapitel_task_labels.get(kapitel_name)

        if pb and lbl:
            try:
                progress_wert = float(wert)
            except (ValueError, TypeError):
                progress_wert = 0
            
            pb["value"] = progress_wert

            if progress_wert == 0:
                pb.grid_remove()
                lbl.grid_remove()
            else:
                if task_id is None:
                    label_text = "Aufgabe: -"
                else:
                    label_text = f"Aufgaben: {task_id}" if mehrere else f"Aufgabe: {task_id}"
                lbl.config(text=label_text)
                lbl.grid()
                pb.grid()

        # Gesamtfortschritt aktualisieren
        if not hasattr(self, "kapitel_fortschritte"):
            self.kapitel_fortschritte = {}
        self.kapitel_fortschritte[kapitel_name] = wert

        # Durchschnitt berechnen
        if self.kapitel_fortschritte:
            gesamt = sum(self.kapitel_fortschritte.values()) / len(self.kapitel_fortschritte)
        else:
            gesamt = 0

        # Gesamt-Progressbar aktualisieren (wenn vorhanden)
        if hasattr(self, "gesamt_progressbar") and self.gesamt_progressbar:
            self.gesamt_progressbar["value"] = gesamt

        # Gesamtstatus-Label aktualisieren
        if hasattr(self, "gesamt_status_label") and self.gesamt_status_label:
            self.gesamt_status_label["text"] = f"Gesamtfortschritt: {int(gesamt)} %"

    def melde_KI_Tasks_fortschritt(self, kapitel_name, task_id, wert):
        """Wird von parallelen Tasks aufgerufen, um Fortschritt zu melden."""
        with self._progress_lock:
            if kapitel_name not in self.kapitel_tasks:
                self.kapitel_tasks[kapitel_name] = {}

            tasks = self.kapitel_tasks[kapitel_name]

            if wert == 0:
                tasks.pop(task_id, None)
                self._set_task_spinner(task_id,False)
            else:
                tasks[task_id] = wert
                self._set_task_spinner(task_id,True)

            task_ids = list(tasks.keys())
            durchschnitt = sum(tasks.values()) / len(tasks) if tasks else 0
            mehrere = len(task_ids) > 1

        # Für Label die Task-IDs als String mit Semikolon getrennt
        task_ids_str = "; ".join(task_ids) if mehrere else (task_ids[0] if task_ids else "")

        self.aktualisiere_progressbar(kapitel_name, task_ids_str, durchschnitt, mehrere)
    

    def InhaltsverzeichnisAuslesenMitDialog(self):
        """Dialog zur Auswahl des Kapitelstils und weiterer Optionen beim Einlesen aus Word."""

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

        ttk.Label(dialog, text="Kapitelstil:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        style_var = tk.StringVar()
        combo_style = ttk.Combobox(dialog, textvariable=style_var, values=styles, state="readonly")
        combo_style.grid(row=0, column=1, sticky="ew", padx=10, pady=5)

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

        aufst_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog, text="Nummerierung muss aufsteigend sein", variable=aufst_var)\
            .grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        praefix_frame = ttk.Frame(dialog)
        praefix_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        praefix_frame.columnconfigure(1, weight=1)

        ttk.Label(praefix_frame, text="Präfix:").grid(row=0, column=0, sticky="w")
        praefix_var = tk.StringVar(value="Kapitel")
        ttk.Entry(praefix_frame, textvariable=praefix_var).grid(row=0, column=1, sticky="ew", padx=5)
        nur_pref_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(praefix_frame, text="nur Präfix berücksichtigen", variable=nur_pref_var)\
            .grid(row=0, column=2, sticky="w", padx=(5, 0))

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

            try:
                self.kapitel_config._create_from_word(stil, self.selected_file.get(), nummer, praefix, aufsteigend)
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim Laden der Kapitel:\n{e}")

        btn_ok = ttk.Button(dialog, text="Kapitel übernehmen", command=auswahl_bestaetigen)
        btn_ok.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 15))
        btn_ok.focus_set()
        dialog.bind("<Return>", lambda e: auswahl_bestaetigen())

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
        
        # Vorherige Widgets löschen
        for widget in self.aufg_frame.winfo_children():
            widget.destroy()

        self.task_vars = {}
        self.selected_models = {}  # Speichert pro Aufgabe das ausgewählte Modell

        # Checkbox-Variable für "Alle Aufgaben"
        self.all_tasks_var = tk.BooleanVar(value=True)  # Standard: alle aktiv

        def toggle_all_tasks():
            wert = self.all_tasks_var.get()
            for var in self.task_vars.values():
                var.set(wert)

        def update_all_tasks_var(*args):
            alle = all(var.get() for var in self.task_vars.values())
            if self.all_tasks_var.get() != alle:
                self.all_tasks_var.set(alle)

        style = ttk.Style()
        style.configure("HervorgehobeneCheckbutton.TCheckbutton",
                        font=("Segoe UI", 10, "bold"),
                        foreground="blue")

        rahmen = ttk.Frame(self.aufg_frame, padding=5, style="HervorhebungsFrame.TFrame")
        rahmen.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 10))
        rahmen.grid_columnconfigure(0, weight=1)

        cb_all = ttk.Checkbutton(
            rahmen,
            text="★ Alle Aufgaben",
            variable=self.all_tasks_var,
            command=toggle_all_tasks,
            style="HervorgehobeneCheckbutton.TCheckbutton"
        )
        cb_all.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 10))

        # Feste Einträge 1 und 2
        self.aufgaben_input = {
            1: "Text nach Kapiteln aufteilen",
            2: "Kapitel für KI vorbereiten",
        }

        if getattr(config, "NUTZE_KI", True):
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
            messagebox.showwarning("Warnung", f"Modelle konnten nicht geladen werden:\n{e}\nWechsle zum Modellwahl-Tab.")
            for tab_id in self.notebook.tabs():
                if self.notebook.tab(tab_id, "text") == "InstallationModellwahl":
                    self.notebook.select(tab_id)
                    break
            return

        self.model_selection_boxes = {}

        # Tooltip-Funktion (einfacher Tooltip mit Label)
        def create_tooltip(widget, text):
            tooltip = None
            def enter(event):
                nonlocal tooltip
                if tooltip or not text:
                    return
                x = widget.winfo_rootx() + 20
                y = widget.winfo_rooty() + 20
                tooltip = tk.Toplevel(widget)
                tooltip.wm_overrideredirect(True)
                tooltip.wm_geometry(f"+{x}+{y}")
                label = tk.Label(tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1, font=("Segoe UI", 9))
                label.pack()
            def leave(event):
                nonlocal tooltip
                if tooltip:
                    tooltip.destroy()
                    tooltip = None
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)

        # Ab Zeile 1, da row=0 vom Rahmen und "Alle Aufgaben"-Checkbox belegt
        for i, (schritt_nr, beschreibung) in enumerate(self.aufgaben_input.items(), start=1):
            var = tk.BooleanVar(value=True)  # Standard alle aktiv

            var.trace_add("write", lambda *args: update_all_tasks_var())

            frame = ttk.Frame(self.aufg_frame)
            frame.grid(row=i, column=0, sticky="ew", pady=2)
            frame.columnconfigure(0, weight=3)
            frame.columnconfigure(1, weight=1)
            frame.columnconfigure(2, weight=0)

            cb = tk.Checkbutton(frame, text=beschreibung, variable=var)
            cb.grid(row=0, column=0, sticky="w")

            # Tooltip zum Checkbox-Text
            create_tooltip(cb, f"Aufgabe {schritt_nr}: {beschreibung}")

            spinner_lbl = ttk.Label(frame, text="", font=("Consolas", 12))
            spinner_lbl.grid(row=0, column=1, sticky="w", padx=5)

            self.task_vars[schritt_nr] = var
            self.task_spinner_labels[schritt_nr] = spinner_lbl

            if "(mit ki)" in beschreibung.lower() and modelle:
                combo = ttk.Combobox(frame, values=modelle, state="readonly", width=40)
                combo.set(modelle[0])
                combo.grid(row=0, column=2, padx=5, sticky="w")
                self.model_selection_boxes[schritt_nr] = combo

                # Speichere initial ausgewähltes Modell
                self.selected_models[schritt_nr] = modelle[0]

                # Callback zum Speichern der Auswahl
                def on_model_selected(event, sn=schritt_nr):
                    self.selected_models[sn] = self.model_selection_boxes[sn].get()
                combo.bind("<<ComboboxSelected>>", on_model_selected)

        # Synchronisation: Initial alle Aufgaben aktivieren
        toggle_all_tasks()

        # Button außerhalb der Loop in eigenem Frame
        btn_frame = ttk.Frame(self.aufg_frame)
        btn_frame.grid(row=len(self.aufgaben_input) + 1, column=0, sticky="w", pady=5)
        btn_kapitel_bearbeiten = ttk.Button(
            btn_frame,
            text="Annotationen manuell optimieren",
            command=self.kapitel_annotation_editor_starten
        )
        btn_kapitel_bearbeiten.grid(row=0, column=0, sticky="w")


    def lade_docx_aus_globalordner(self):
        ordner = config.GLOBALORDNER
        if not ordner or "Eingabe" not in ordner:
            print(f"GLOBALORDNER ist nicht korrekt gesetzt oder unvollständig.")
        else:    
            self.ordner = ordner
            # Versuche, Pfad zur .docx-Datei aus Eingabe-Ordner zu rekonstruieren
            eingabe_ordner = Path(ordner["Eingabe"])
        
            # Leite .docx-Dateiname aus dem Ordnernamen ab
            try:
                ergebnisse_ordner = eingabe_ordner.parent  # .../Annotationstoolergebnisse/<dateiname_ohne_endung>
                docx_name = ergebnisse_ordner.name + ".docx"
                original_docx = ergebnisse_ordner.parent.parent / docx_name  # gehe zwei Ebenen nach oben

                if not original_docx.is_file():
                    messagebox.showwarning("Datei nicht gefunden", f"Die ursprüngliche .docx-Datei konnte nicht gefunden werden:\n{original_docx}")
                    return

                self.selected_file.set(str(Path(original_docx)))
                print(f"[DEBUG] Rekonstruierte .docx-Datei: {repr(original_docx)}")

                self.output_folder = ergebnisse_ordner
                self.kapitel_config.output_folder = str(self.output_folder)

                self.kapitel_config_datei = self.output_folder / "kapitel_config.json"
                if self.kapitel_config_datei.is_file():
                    try:
                        self.kapitel_config.load_from_file(str(self.kapitel_config_datei))
                        print(f"[INFO] Kapitel-Konfiguration geladen aus {self.kapitel_config_datei}")
                    except Exception as e:
                        messagebox.showerror("Fehler", f"Konnte Kapitel-Konfiguration nicht laden: {e}")
                        self.kapitel_config_datei = None
                else:
                    messagebox.showwarning("Keine Kapitel-Konfiguration", f"Die Datei {self.kapitel_config_datei} wurde nicht gefunden.")
                    self.kapitel_config_datei = None

                # Optional: Textbox aktualisieren
                if hasattr(self, "textbox"):
                    self.textbox.delete("1.0", "end")
                    self.textbox.insert("end", f"Geladenes Projekt: {original_docx.name}\nPfad: {original_docx.parent}")

                # Kapitel-Checkboxen laden
                self.lade_kapitel_checkboxes()

            except Exception as e:
                messagebox.showerror("Fehler", f"Beim Laden des Projekts ist ein Fehler aufgetreten:\n{e}")


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
            "absatz" : ergebnisse_ordner / "absatz",
            "ki":     ergebnisse_ordner / "ki",
            "merge":  ergebnisse_ordner / "merge",
            "pdf":    ergebnisse_ordner / "pdf",
            "manuell": ergebnisse_ordner / "manuell",
            "pdf2" : ergebnisse_ordner / "pdf2",
        }
        
        for pfad in self.ordner.values():
            pfad.mkdir(parents=True, exist_ok=True)
            print(f"[DEBUG] Ordner erstellt: {repr(pfad)}")
 
        self.update_globalordner_in_config(self.ordner)
       
        self.lade_kapitel_checkboxes()
      
    def lade_kapitel_checkboxes(self):

        if not self.kapitel_config.kapitel_liste and self.kapitel_config.kapitel_daten:
            self.kapitel_config.kapitel_liste = list(self.kapitel_config.kapitel_daten.keys())

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
   
        def alle_auswaehlen_toggle():
            wert = self.all_var.get()
            for var in self.chapter_vars.values():
                var.set(wert)
                
        self.all_var = tk.BooleanVar(value=True)
        alle_auswaehlen_toggle()
     

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
            frame.grid_columnconfigure(3, weight=0)

            cb = ttk.Checkbutton(frame, text=name, variable=var)
            cb.grid(row=0, column=0, sticky="w")

            pb = ttk.Progressbar(frame, orient="horizontal", length=150, mode="determinate")
            pb.grid(row=0, column=1, sticky="e", padx=5)
            pb.grid_remove()
            self.kapitel_progressbars[name] = pb

            lbl_task = ttk.Label(frame, text="", width=20, anchor="w")
            lbl_task.grid(row=0, column=2, sticky="w", padx=(5, 0))
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
        # Leere eventuell verbliebene Aufgaben aus früheren Läufen
        while not self.thread_queue.empty():
            try:
                self.thread_queue.get_nowait()
                self.thread_queue.task_done()
            except queue.Empty:
                break

        with self.tasks_lock:
            if self.tasks_running:
                print("[WARNUNG] Aufgabenverarbeitung läuft bereits.", flush=True)
                return
            self.tasks_running = True

        self.disable_controls() 

        print("[DEBUG] Starte Aufgabenverarbeitung", flush=True)
        self.abort_flag.clear()
        self.task_flags = {key: var.get() for key, var in self.task_vars.items()}

        if not self.kapitel_config.kapitel_liste and self.kapitel_config.kapitel_daten:
            self.kapitel_config.kapitel_liste = list(self.kapitel_config.kapitel_daten.keys())

        ausgewaehlte_kapitel = [name for name, var in self.chapter_vars.items() if var.get()]
        selected_file_path = self.selected_file.get()
        task_flags = {key: var.get() for key, var in self.task_vars.items()}
        model_selection_boxes = getattr(self, "model_selection_boxes", None)
        kapitel_liste = list(self.kapitel_config.kapitel_liste)
        kapitel_daten = copy.deepcopy(self.kapitel_config.kapitel_daten)
        ordner_nur_str = {k: str(v) for k, v in self.ordner.items()}
        max_workers = self.max_workers
        abort_flag = self.abort_flag
        progress_queue = self.master.progress_queue
        mp_progress_queue = self.master.mp_progress_queue 

        modelle_für_tasks = {}
        if model_selection_boxes:
            for aid, combobox in model_selection_boxes.items():
                try:
                    modelle_für_tasks[aid] = combobox.get()
                except Exception as e:
                    print(f"[WARNUNG] Fehler beim Auslesen des Modells für Aufgabe {aid}: {e}")

        print(f"[DEBUG] Ausgewählte Kapitel: {ausgewaehlte_kapitel}", flush=True)
        bereits_in_queue = set()
        for kapitel in ausgewaehlte_kapitel:
            if kapitel in bereits_in_queue:
                print(f"[WARNUNG] Kapitel mehrfach in Queue eingefügt: {kapitel}", flush=True)
            bereits_in_queue.add(kapitel)
            self.thread_queue.put(kapitel)
        
        kapitel_anzahl = len(ausgewaehlte_kapitel)
        max_threads = min(self.max_workers, kapitel_anzahl)

        try:
            with ThreadPoolExecutor(max_workers=max_threads) as thread_executor:
                futures = []
                for _ in range(max_threads):
                    futures.append(thread_executor.submit(
                        self._thread_worker,
                        selected_file_path,
                        kapitel_liste,
                        ordner_nur_str,
                        task_flags,
                        progress_queue,
                        mp_progress_queue, 
                        abort_flag,
                        kapitel_daten,
                        modelle_für_tasks,
                        max_workers
                    ))

                concurrent.futures.wait(futures, return_when=concurrent.futures.ALL_COMPLETED)

                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        print(f"[ERROR] Fehler im Thread-Worker: {e}", flush=True)
                        traceback.print_exc()
        finally:
            self.enable_controls()
            with self.tasks_lock:
                self.tasks_running = False
            self.progress_queue_active = False
            self.master.stoppe_progress_pruefung()
            print("[DEBUG] Aufgabenverarbeitung abgeschlossen", flush=True)


    def _thread_worker(self,
                    selected_file_path,
                    kapitel_liste,
                    ordner_nur_str,
                    task_flags,
                    progress_queue,
                    mp_progress_queue,
                    abort_flag,
                    kapitel_daten,
                    modelle_für_tasks,
                    max_workers):
        print("[DEBUG] Thread Worker gestartet", flush=True)

        while True:
            try:
                kapitel = self.thread_queue.get_nowait()
            except queue.Empty:
                break

            print(f"starte Verarbeitung {kapitel}")

            self.verarbeite_kapitel(
                kapitel,
                selected_file_path,
                kapitel_liste,
                ordner_nur_str,
                task_flags,
                progress_queue,
                mp_progress_queue,
                abort_flag,
                kapitel_daten,
                modelle_für_tasks,
                max_workers
            )

            self.thread_queue.task_done()

    def verarbeite_kapitel(self, kapitel_name,
                        selected_file_path,
                        kapitel_liste,                        
                        ordner_nur_str,
                        task_flags,
                        progress_queue,
                        mp_progress_queue,
                        abort_flag,
                        kapitel_daten,
                        modelle_für_tasks,
                        max_workers
                        ):
        
        print(f"[DEBUG] Starte Verarbeitung für Kapitel: {kapitel_name}", flush=True)

        warte_auf_freien_cpukern_und_ram(max_auslastung_cpu=95.0, max_auslastung_ram=80.0, timeout=30.0)
        print(f"[DEBUG] Ressourcen-Check abgeschlossen für Kapitel: {kapitel_name}", flush=True)

        try:
            if abort_flag.is_set():
                print(f"[INFO] Verarbeitung von Kapitel {kapitel_name} abgebrochen (Abort-Flag gesetzt).", flush=True)
                return

            print(f"[DEBUG] Verwende Ordnerstruktur: {ordner_nur_str}", flush=True)

            if task_flags.get(1, False):
                print(f"[DEBUG] Starte Aufgabe 1: Extraktion für Kapitel: {kapitel_name}", flush=True)
                progress_queue.put((kapitel_name, "1", 0.1))

                extrahiere_kapitel_mit_config(
                    selected_file_path,
                    kapitel_liste,
                    ordner_nur_str["txt"],
                    [kapitel_name],
                    lambda k, w: progress_queue.put((k, "1", w))
                )
                print(f"[DEBUG] Aufgabe 1 abgeschlossen für Kapitel: {kapitel_name}", flush=True)
               
                if abort_flag.is_set():
                    print(f"[INFO] Verarbeitung von Kapitel {kapitel_name} abgebrochen vor Aufgabe 1.2.", flush=True)
                    return

                print(f"[DEBUG] Starte Aufgabe 1.2: Vorverarbeitung für Kapitel: {kapitel_name}", flush=True)
                progress_queue.put((kapitel_name, "Vorverarbeitung", 0.1))

                verarbeite_kapitel_und_speichere_json(
                    ordner_nur_str["txt"],
                    ordner_nur_str["json"],
                    [kapitel_name],
                    lambda kapitel, fortschritt: progress_queue.put((kapitel, "2.1", fortschritt))
                )
                print(f"[DEBUG] Aufgabe 1.2 abgeschlossen für Kapitel: {kapitel_name}", flush=True)
             
            if task_flags.get(2, False):
                if abort_flag.is_set():
                    print(f"[INFO] Verarbeitung von Kapitel {kapitel_name} abgebrochen vor Aufgabe 2.", flush=True)
                    return

                print(f"[DEBUG] Starte Aufgabe 2: Satzaufteilung für Kapitel: {kapitel_name}", flush=True)
                progress_queue.put((kapitel_name, "Satzbildung", 0.1))

                dateien_aufteilen(
                    kapitel_name,
                    ordner_nur_str["json"],
                    ordner_nur_str["satz"],
                    lambda kapitel, fortschritt: progress_queue.put((kapitel, "2.2", fortschritt))
                )
                print(f"[DEBUG] Aufgabe 2 abgeschlossen für Kapitel: {kapitel_name}", flush=True)
             

            next_key = None

            if getattr(config, "NUTZE_KI", True):
                    if abort_flag.is_set():
                        print(f"[INFO] KI-Verarbeitung für Kapitel {kapitel_name} abgebrochen (Abort-Flag gesetzt).", flush=True)
                        return

                    aktive_tasks = [aid for aid in config.KI_AUFGABEN if task_flags.get(aid, False)]
                    print(f"[DEBUG] Aktive KI-Tasks für Kapitel {kapitel_name}: {aktive_tasks}", flush=True)

                    if not aktive_tasks:
                        print(f"[INFO] Keine aktiven KI-Aufgaben für Kapitel {kapitel_name}.", flush=True)
                    else:
                        print(f"[INFO] Starte parallele KI-Aufgaben für Kapitel {kapitel_name}", flush=True)

                        max_workers = min(len(aktive_tasks), os.cpu_count() or 1)
                        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                            futures = []

                            for aufgaben_id in aktive_tasks:
                                aufgaben_key = config.KI_AUFGABEN[aufgaben_id]
                                task_name = f"Aufgabe {aufgaben_id}: {aufgaben_key}"
                                print(f"[DEBUG] Plane {task_name} für Kapitel {kapitel_name}", flush=True)

                                try:
                                    prompt_datei_text = lade_prompt_datei(aufgaben_id)
                                except Exception as e:
                                    print(f"[FEHLER] Laden der Prompt-Datei für Aufgabe {aufgaben_id} fehlgeschlagen: {e}", flush=True)
                                    traceback.print_exc()
                                    continue

                                zusatz_info = kapitel_daten.get(kapitel_name, {}).get(f"ZusatzInfo_{aufgaben_id}", "")
                                prompt = prompt_datei_text + "\n" + zusatz_info
                                print(f"[DEBUG] Prompt-Text für {task_name}: {prompt[:200]}...", flush=True)

                                modell_name = modelle_für_tasks.get(aufgaben_id, None)

                                warte_auf_freien_cpukern_und_ram(max_auslastung_cpu=95.0, max_auslastung_ram=80.0, timeout=30.0)

                                future = executor.submit(
                                    ki_task_process,
                                    kapitel_name,
                                    aufgaben_id,
                                    prompt,
                                    modell_name,
                                    {"satz": ordner_nur_str["satz"], "ki": ordner_nur_str["ki"]},
                                    mp_progress_queue 
                                )
                                futures.append(future)

                            for future in concurrent.futures.as_completed(futures):
                                try:
                                    future.result()
                                    print(f"[DEBUG] KI-Task abgeschlossen für Kapitel {kapitel_name}", flush=True)
                                except Exception as e:
                                    print(f"[ERROR] Fehler bei KI-Aufgabe: {e}", flush=True)
                                    traceback.print_exc()

                        print(f"[INFO] KI-Verarbeitung abgeschlossen für Kapitel {kapitel_name}", flush=True)
            else:
                next_key = 3 # falls keine KI-Aufgaben genutzt werden , defaultwert

            if task_flags.get(next_key, False):
                if abort_flag.is_set():
                    print(f"[INFO] Verarbeitung von Kapitel {kapitel_name} abgebrochen vor Merge.", flush=True)
                    return

                print(f"[DEBUG] Starte Zusammenführung für Kapitel {kapitel_name}", flush=True)
                progress_queue.put((kapitel_name, next_key, 0.1))

                Merge_annotationen(
                    ordner_nur_str["json"],
                    ordner_nur_str["ki"],
                    ordner_nur_str["merge"],
                    [kapitel_name],
                    lambda w: progress_queue.put((kapitel_name, next_key + ".1", w))
                )

                if abort_flag.is_set():
                    print(f"[INFO] Verarbeitung von Kapitel {kapitel_name} abgebrochen vor Visualisierung.", flush=True)
                    return

                print(f"[DEBUG] Starte Visualisierung für Kapitel {kapitel_name}", flush=True)
                progress_queue.put((kapitel_name, next_key + ".2", 0.1))

                visualisiere_annotationen(
                    ordner_nur_str["merge"],
                    ordner_nur_str["pdf"],
                    [kapitel_name],
                    lambda w: progress_queue.put((kapitel_name, "final 2", w))
                )

            progress_queue.put((kapitel_name, "Fertig", 1.0))
            print(f"[INFO] Kapitel abgeschlossen: {kapitel_name}", flush=True)

        except Exception as e:
            print(f"[FEHLER] Verarbeitung für Kapitel '{kapitel_name}' fehlgeschlagen:", str(e), flush=True)
            traceback.print_exc()

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
    def update_globalordner_in_config(self, neue_ordner: dict):
            config.GLOBALORDNER.clear()
            config.GLOBALORDNER.update({
                k: str(v).replace("\\", "/") for k, v in neue_ordner.items()
            })

            editor = getattr(self.master, "config_editor", None)
            if editor is not None and hasattr(editor, "_save"):
                editor._save()
                print("[INFO] GLOBALORDNER wurde über config_editor._save() gespeichert.")
            else:
                print("[WARNUNG] Kein config_editor verfügbar – Änderungen nicht automatisch gespeichert.")
                

# if __name__ == "__main__":
#     from pathlib import Path
#     import Eingabe.config as config

#     ordner_nur_str = {
#         "satz": config.GLOBALORDNER["satz"],
#         "ki": config.GLOBALORDNER["ki"],
#     }

#     kapitel_name = "Prolog – Finis post portam"
#     aufgaben_id =4
#     prompt = lade_prompt_datei(4)
#     modell_name = "leoLM/leo-mistral-hessianai-7b"

#     ki_task_process(kapitel_name, aufgaben_id, prompt, modell_name, ordner_nur_str, None)



  