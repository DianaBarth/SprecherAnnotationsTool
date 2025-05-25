import threading
import time
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
import shutil
import os

import Eingabe.config as config # Importiere das komplette config-Modul

class ShutdownController:
    def __init__(self, root):
        self.root = root
        self.shutdown_after_idle = False
        self.idle_time_seconds = None
        self.shutdown_timer_thread = None
        self.popup_window = None
        self.idle_countdown = 0

        if not self._is_shutdown_supported():
            print("Shutdown-Funktion nicht unterstützt auf diesem System. Controller wird deaktiviert.")
            self.disabled = True
            return
        self.disabled = False

    def _is_shutdown_supported(self):
        if sys.platform == "win32":
            return True
        elif sys.platform.startswith("linux") or sys.platform == "darwin":
            return shutil.which("shutdown") is not None and os.geteuid() == 0
        return False

    def set_shutdown_timeout(self, seconds: int):
        """Setzt die Inaktivitätszeit bis zum Shutdown (0 = deaktiviert)."""
        self.shutdown_after_idle = seconds > 0
        self.idle_time_seconds = seconds

    def show_task_finished_popup(self, task_id, dauer_str):
        """Zeigt ein Fenster mit Taskabschluss-Info und optionalem Shutdown-Countdown."""
        if self.active_popup:
            self.active_popup.destroy()

        self.active_popup = tk.Toplevel(self.root)
        self.active_popup.title(f"Task {task_id} abgeschlossen")
        self.active_popup.geometry("400x200")
        self.active_popup.protocol("WM_DELETE_WINDOW", self.on_popup_closed)

        # Hauptcontainer mit grid
        container = tk.Frame(self.active_popup)
        container.grid(row=0, column=0, padx=20, pady=20)

        label = tk.Label(container, text=f"Task {task_id} wurde abgeschlossen.\nBenötigte Zeit: {dauer_str}")
        label.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="w")

        # Button-Frame
        btn_ok = tk.Button(container, text="OK", command=self.on_popup_ok)
        btn_ok.grid(row=1, column=0, padx=10, pady=5, sticky="e")

        btn_shutdown = tk.Button(container, text="Jetzt herunterfahren", command=self.on_popup_shutdown)
        btn_shutdown.grid(row=1, column=1, padx=10, pady=5, sticky="w")

        # Leeres Feld für Shutdown-Hinweis
        self.idle_label = tk.Label(container, text="", fg="red")
        self.idle_label.grid(row=2, column=0, columnspan=2, pady=(10, 0), sticky="w")

        if self.shutdown_after_idle:
            self.idle_countdown = self.idle_time_seconds
            self._update_idle_countdown_label()
            self.shutdown_timer_thread = threading.Thread(target=self._idle_shutdown_countdown, daemon=True)
            self.shutdown_timer_thread.start()

    def _update_idle_countdown_label(self):
        if self.active_popup:
            minutes = self.idle_countdown // 60
            seconds = self.idle_countdown % 60
            text = f"Automatischer Shutdown in {minutes} Minuten {seconds} Sekunden (wenn keine Aktion erfolgt)"
            self.idle_label.config(text=text)

    def _idle_shutdown_countdown(self):
        while self.idle_countdown > 0 and self.active_popup is not None:
            time.sleep(1)
            self.idle_countdown -= 1
            self.root.after(0, self._update_idle_countdown_label)

        if self.idle_countdown <= 0 and self.active_popup is not None:
            self.root.after(0, self.on_popup_shutdown)

    def on_popup_ok(self):
        self._cancel_shutdown()
        if self.active_popup:
            self.active_popup.destroy()
        self.active_popup = None

    def on_popup_shutdown(self):
        self._cancel_shutdown()
        if self.active_popup:
            self.active_popup.destroy()
        self.active_popup = None
        self.shutdown_pc()

    def on_popup_closed(self):
        self._cancel_shutdown()
        if self.active_popup:
            self.active_popup.destroy()
        self.active_popup = None

    def _cancel_shutdown(self):
        self.idle_countdown = 0

    def shutdown_pc(self):
        if not self._is_shutdown_supported():
            messagebox.showerror("Shutdown nicht unterstützt", "Automatisches Herunterfahren wird auf diesem System nicht unterstützt.")
            return

        try:
            if sys.platform == "win32":
                subprocess.run("shutdown /s /t 5", shell=True, check=True)
            elif sys.platform.startswith("linux") or sys.platform == "darwin":
                # Versuch: Nur wenn Benutzer root oder sudo-Rechte hat
                if os.geteuid() != 0:
                    messagebox.showwarning(
                        "Root-Rechte erforderlich",
                        "Shutdown unter Linux/macOS erfordert Root-Rechte.\nBitte Tool mit sudo ausführen."
                    )
                    return
                subprocess.run(["shutdown", "-h", "now"], check=True)
            else:
                messagebox.showerror("Nicht unterstütztes System", "Dein Betriebssystem wird nicht unterstützt.")
        except Exception as e:
            messagebox.showerror("Fehler beim Herunterfahren", f"Herunterfahren fehlgeschlagen:\n{e}")
