import tkinter as tk
import re
from tkinter import ttk
import queue
from multiprocessing import Manager
import multiprocessing
import importlib
from huggingface_client import HuggingFaceClient
from log_manager import LogManager
from kapitel_config import KapitelConfig
from dashboard import DashBoard
from modellwahl import InstallationModellwahl
from config_editor import ConfigEditor
import Eingabe.config as config # Importiere das komplette config-Modul

class SprecherAnnotationsTool(tk.Tk):
    """Hauptanwendung mit Tab-Notebook"""

    def __init__(self, logger):
        super().__init__()
        self.title("Sprecher-Annotationen-Tool")

        # Queue und Flag initialisieren
        self.progress_queue = queue.Queue()
        manager = Manager()
        self.mp_progress_queue =manager.Queue()
        self.progress_queue_active = False

        # HuggingFace Client initialisieren
        self.client = HuggingFaceClient()

        # Notebook anlegen, mit grid platzieren
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # Layout-Gewichtung für automatisches Vergrößern
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.starte_progress_pruefung()
        # KapitelConfig, Dashboard etc. anlegen
        self.kapitel_config = KapitelConfig(self, self.notebook)
        self.dashboard = DashBoard(self, self.notebook, self.kapitel_config, self.client)
        InstallationModellwahl(self, self.notebook, self.client)
        self.kapitel_config.dashboard = self.dashboard
        self.config_editor = ConfigEditor(self, self.notebook, self.dashboard)        

        # Anfangs den Dashboard-Tab auswählen (Achtung: Attributname ist klein)
        
        importlib.reload(config)
        print(config.__file__)
        print(f"MAX_PROMPT_TOKENS: {config.MAX_PROMPT_TOKENS}")

    
    def starte_progress_pruefung(self):
        print("[INFO] Starte Fortschrittsprüfung")
        if not self.progress_queue_active:
            self.progress_queue_active = True
            self.after(0, self.pruefe_progress_queue)
            self.after(0, self.pruefe_mp_progress_queue)  # <--- MP-Queue auch prüfen

    def stoppe_progress_pruefung(self):
        print("[INFO] Stoppe Fortschrittsprüfung")
        self.progress_queue_active = False

    def pruefe_progress_queue(self):
    
            try:
                if self.progress_queue_active:
                    while not self.progress_queue.empty():
                        kapitel_name, aufgaben_id, wert = self.progress_queue.get_nowait()
                        print(f"melde_KI_Tasks_fortschritt für {kapitel_name} id {aufgaben_id} mit wert {wert}", flush=True)
                        self.dashboard.melde_KI_Tasks_fortschritt(kapitel_name, aufgaben_id, wert)  # deine GUI-Update-Funktion
            except Exception as e:
                print(f"[FEHLER bei Queue-Check] {e}")

            if self.progress_queue_active:
                self.after(200, self.pruefe_progress_queue)  # alle 200 ms prüfen
                
    def pruefe_mp_progress_queue(self):
        try:
            if self.progress_queue_active:                   
                while not self.mp_progress_queue.empty():
                    item = self.mp_progress_queue.get_nowait()

                    if isinstance(item, tuple) and len(item) == 3:
                        kapitel_name, aufgaben_id, wert = item
                        print(f"[MP] melde_KI_Tasks_fortschritt für {kapitel_name} id {aufgaben_id} mit wert {wert}", flush=True)
                        self.dashboard.melde_KI_Tasks_fortschritt(kapitel_name, aufgaben_id, wert)
                    else:
                        print(f"[WARNUNG] Unerwartetes Format in mp_progress_queue: {item}", flush=True)
        except Exception as e:
            print(f"[FEHLER bei MP-Queue-Check] {e}", flush=True)

        if self.progress_queue_active:
            self.after(200, self.pruefe_mp_progress_queue)

if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    logger = LogManager('meinlog_Komplett.log', extra_logfile='meinLog_letzterDurchlauf.log')

    print("-------------------------------------------------------------------------------------------")
    print("NEUSTART Sprecher-Annotationen-Tool")
    print("-------------------------------------------------------------------------------------------")

    app = SprecherAnnotationsTool(logger)
    app.mainloop()
