
import subprocess
import os
import tkinter as tk
from tkinter import simpledialog, messagebox

from sprecher_annotationstool import SprecherAnnotationsTool
from log_manager import LogManager
import subprocess
import os
import tkinter as tk
from tkinter import messagebox, scrolledtext


class CommitDialog(tk.Toplevel):
    def __init__(self, parent, changed_files):
        super().__init__(parent)
        self.title("Commit-Nachricht")
        self.resizable(False, False)
        self.result = None

        label = tk.Label(self, text="🟡 Commit-Nachricht eingeben:")
        label.pack(padx=10, pady=(10,0))

        self.entry = tk.Entry(self, width=50)
        self.entry.pack(padx=10, pady=5)
        self.entry.focus_set()

        label_files = tk.Label(self, text="Geänderte Dateien:")
        label_files.pack(padx=10, pady=(10,0))

        # Scrollbares Textfeld für geänderte Dateien
        self.text_area = scrolledtext.ScrolledText(self, width=60, height=10, state='normal')
        self.text_area.pack(padx=10, pady=5)
        self.text_area.insert(tk.END, "\n".join(changed_files))
        self.text_area.config(state='disabled')  # Nur lesen

        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)

        commit_btn = tk.Button(button_frame, text="Commit", command=self.on_commit)
        commit_btn.pack(side=tk.LEFT, padx=5)
        cancel_btn = tk.Button(button_frame, text="Abbrechen", command=self.on_cancel)
        cancel_btn.pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self.on_commit())
        self.bind("<Escape>", lambda e: self.on_cancel())

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

    def on_commit(self):
        msg = self.entry.get().strip()
        if msg == "":
            messagebox.showwarning("Warnung", "Bitte eine Commit-Nachricht eingeben oder Abbrechen klicken.")
            return
        self.result = msg
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()

def auto_git_commit():
    repo_path = os.path.dirname(os.path.abspath(__file__))
    os.chdir(repo_path)

    # Nur geänderte Dateien ohne Status ausgeben
    result = subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True)
    changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]

    if not changed_files:
        print("Auto-Commit: Keine Änderungen gefunden, übersprungen.")
        return

    # Commit-Dialog öffnen
    root = tk.Tk()
    root.withdraw()
    dialog = CommitDialog(root, changed_files)
    root.wait_window(dialog)
    root.destroy()

    if dialog.result is None:
        print("Auto-Commit abgebrochen.")
        return

    try:
        subprocess.run(["git", "add"] + changed_files, check=True)
        subprocess.run(["git", "commit", "-m", dialog.result], check=True)
       # Versuch, einfach zu pushen
        proc = subprocess.run(["git", "push"], capture_output=True, text=True)
        if proc.returncode != 0:
            # Beim ersten Mal möglicherweise Upstream noch nicht gesetzt
            print("Erster Push; Upstream wird jetzt gesetzt …")
            proc2 = subprocess.run(["git", "push", "-u", "origin", "main"], capture_output=True, text=True)
            if proc2.returncode != 0:
                print("❌ Erster Push fehlgeschlagen:")
                print(proc2.stderr.strip())
            else:
                print("✅ Erster Push mit Upstream erfolgreich.")
        else:
            print("✅ Auto-Commit erfolgreich gepusht.")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Git-Auto-Commit fehlgeschlagen: {e}")

if __name__ == "__main__":
    # Haupttool
    logger = LogManager('meinlog_Komplett.log', extra_logfile='meinLog_letzterDurchlauf.log')

    print("-------------------------------------------------------------------------------------------")
    print("NEUSTART Sprecher-Annotationen-Tool")
    print("-------------------------------------------------------------------------------------------")

    try:
        app = SprecherAnnotationsTool(logger)
        app.mainloop()
    except Exception as e:
        print(f"Fehler im Haupttool: {e}")
    else:
        # Nur wenn kein Fehler im Log (Zeile mit "Error") vorhanden ist, committen
        def log_enthaelt_error(logdatei):
            if not os.path.exists(logdatei):
                return False
            with open(logdatei, "r", encoding="utf-8") as f:
                for zeile in f:
                    if "Error" in zeile:
                        return True
            return False

        if not log_enthaelt_error('meinLog_lezterDurchlauf.log'):
            auto_git_commit()
        else:
            print("Commit übersprungen: 'Error' im Log gefunden.")