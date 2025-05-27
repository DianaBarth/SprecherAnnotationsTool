import tkinter as tk
from tkinter import ttk

from log_manager import LogManager
from kapitel_config import KapitelConfig
from dashboard import DashBoard
from modellwahl import InstallationModellwahl
from config_editor import ConfigEditor
from huggingface_client import HuggingFaceClient

import Eingabe.config as config # Importiere das komplette config-Modul

class SprecherAnnotationsTool(tk.Tk):
    """Hauptanwendung mit Tab-Notebook"""

    def __init__(self, logger):
        super().__init__()
        self.title("Sprecher-Annotationen-Tool")

        # HuggingFace Client initialisieren
        self.client = HuggingFaceClient()

        # Notebook anlegen, mit grid platzieren
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # Layout-Gewichtung für automatisches Vergrößern
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # KapitelConfig, Dashboard etc. anlegen
        self.kapitel_config = KapitelConfig(self, self.notebook)
        self.dashboard = DashBoard(self, self.notebook, self.kapitel_config, self.client)
        InstallationModellwahl(self, self.notebook, self.client)
        self.kapitel_config.dashboard = self.dashboard
        self.config_editor = ConfigEditor(self, self.notebook, self.dashboard)        

        # Anfangs den Dashboard-Tab auswählen (Achtung: Attributname ist klein)
        self.notebook.select(self.dashboard)


if __name__ == "__main__":
    logger = LogManager('meinlog_Komplett.log', extra_logfile='meinLog_letzterDurchlauf.log')

    print("-------------------------------------------------------------------------------------------")
    print("NEUSTART Sprecher-Annotationen-Tool")
    print("-------------------------------------------------------------------------------------------")

    app = SprecherAnnotationsTool(logger)
    app.mainloop()
