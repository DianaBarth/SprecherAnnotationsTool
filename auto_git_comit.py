
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
        # Keine Änderungen
        return

    # Änderungen hinzufügen
    subprocess.run(["git", "add"] + changed_files, check=False)

    root = tk.Tk()
    root.withdraw()

    dialog = CommitDialog(root, changed_files)
    root.wait_window(dialog)

    if dialog.result is None:
        messagebox.showinfo("Abgebrochen", "Commit wurde abgebrochen.")
    else:
        try:
            subprocess.run(["git", "commit", "-m", dialog.result], check=False)
            subprocess.run(["git", "push"], check=False)
            messagebox.showinfo("Erfolg", "Änderungen wurden erfolgreich committet und gepusht.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Git-Auto-Commit fehlgeschlagen:\n{e}")
    root.destroy()

if __name__ == "__main__":
    #Haupttool
    logger = LogManager('meinlog.log')

    print("-------------------------------------------------------------------------------------------")
    print("NEUSTART Sprecher-Annotationen-Tool")
    print("-------------------------------------------------------------------------------------------")

    try:
        app = SprecherAnnotationsTool()
        app.mainloop()
    except Exception as e:
        print(f"Fehler im Haupttool: {e}")
    else:
        # Nur wenn kein Fehler
        auto_git_commit()