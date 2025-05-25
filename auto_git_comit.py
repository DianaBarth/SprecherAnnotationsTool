
import subprocess
import os
import tkinter as tk
from tkinter import simpledialog, messagebox

from sprecher_annotationstool import SprecherAnnotationsTool
from log_manager import LogManager


def auto_git_commit():
    repo_path = os.path.dirname(os.path.abspath(__file__))
    os.chdir(repo_path)

    subprocess.run(["git", "add", "."], check=False)

    # Tkinter-Fenster verstecken, damit nur Dialog erscheint
    root = tk.Tk()
    root.withdraw()

    try:
        message = simpledialog.askstring("Commit-Nachricht", "🟡 Commit-Nachricht eingeben (leer lassen zum Überspringen):")
        if message and message.strip():
            subprocess.run(["git", "commit", "-m", message.strip()], check=False)
            subprocess.run(["git", "push"], check=False)
            messagebox.showinfo("Erfolg", "Änderungen wurden erfolgreich committet und gepusht.")
        else:
            messagebox.showinfo("Übersprungen", "Commit wurde übersprungen.")
    except Exception as e:
        messagebox.showerror("Fehler", f"Git-Auto-Commit fehlgeschlagen:\n{e}")
    finally:
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