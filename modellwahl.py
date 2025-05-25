import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.simpledialog as simpledialog
import threading
import Eingabe.config as config # Importiere das komplette config-Modul

class InstallationModellwahl(ttk.Frame):
    """Seite zur Auswahl und Laden von HuggingFace-Modellen."""
    def __init__(self, parent, notebook, client):
        super().__init__(parent)
        self.client = client
        self.notebook = notebook  # <-- hier speichern
        # Tab dem Notebook hinzufügen:
        self.notebook.add(self, text="🔧 Installation und Modellwahl")
        
        self.inst_label = None
        self.inst_button = None
        self.inst_progress = None
        self._loading = False


        if self.client.is_huggingface_installed():
            # HF installiert, normale GUI aufbauen
            self._build_widgets()
            self.update_model_list()
            self._loading = False
        else:
            # Installation nötig, Installation UI anzeigen
            self._build_install_widgets()

        self.notebook.hide(self)  # Versteckt den Tab

    def _build_install_widgets(self):
        self.inst_label = ttk.Label(self, text="HuggingFace ist nicht installiert.")
        self.inst_label.pack(pady=10)
        
        self.inst_button = ttk.Button(self, text="HuggingFace installieren", command=self.start_install)
        self.inst_button.pack(pady=10)
        
        self.inst_progress = ttk.Progressbar(self, mode='indeterminate')
        self.inst_progress.pack(pady=10, fill='x', padx=20)

    def start_install(self):
        self.inst_button.config(state='disabled')
        self.inst_label.config(text="Installation läuft...")
        self.inst_progress.start()
        threading.Thread(target=self.install_in_thread, daemon=True).start()

    def install_in_thread(self):
        try:
            self.client.install_huggingface()
            self.after(0, self.install_success)
        except Exception as e:
            print(f"Installationsfehler: {e}")  # Debug-Log
            self.after(0, lambda: self.install_fail(str(e)))

    def install_success(self):
        self.inst_progress.stop()
        self.inst_label.config(text="Installation erfolgreich!")
        messagebox.showinfo("Erfolg", "HuggingFace wurde installiert.")
        # Installations-Widgets entfernen
        self.inst_label.pack_forget()
        self.inst_button.pack_forget()
        self.inst_progress.pack_forget()
        # Vollständige GUI aufbauen
        self._build_widgets()
        self.update_model_list()
        self._loading = False

    def install_fail(self, err_msg):
        self.inst_progress.stop()
        self.inst_label.config(text="Installation fehlgeschlagen.")
        messagebox.showerror("Fehler", f"Installation fehlgeschlagen:\n{err_msg}")
        self.inst_button.config(state='normal')

    def _build_widgets(self):
        self.columnconfigure(0, weight=1)  # Damit der Hauptframe selbst in der Breite wächst

        frm = ttk.Frame(self)
        frm.grid(row=0, column=0, sticky="ew", pady=5, padx=10)
        frm.columnconfigure(1, weight=1)  # Combobox wächst mit
        frm.columnconfigure(3, weight=0)  # X-Button ganz rechts

        # Sprache Label + Combobox + +Button + Close-Button rechts oben
        ttk.Label(frm, text="Sprache:").grid(row=0, column=0, sticky="w")

        self.language_var = tk.StringVar(value="Deutsch / German")
        self.language_cb = ttk.Combobox(
            frm, textvariable=self.language_var,
            values=[
                "Deutsch / German", "English / English", "Français / French",
                # ... weitere Sprachen ...
                "multi / Multilingual"
            ],
            state="readonly", width=25
        )
        self.language_cb.grid(row=0, column=1, sticky="ew", padx=(5,0))
        self.language_cb.bind("<<ComboboxSelected>>", lambda _: self.update_model_list())

        self.add_language_btn = ttk.Button(frm, text="+", width=3, command=self._add_language)
        self.add_language_btn.grid(row=0, column=2, padx=5)

        btn_close = ttk.Button(frm, text="✖️", width=3, command=self.hide_tab)
        btn_close.grid(row=0, column=3, sticky="e")

        # Model-Filter (zweite Zeile)
        ttk.Label(frm, text="Model-Filter:").grid(row=1, column=0, sticky="w")
        self.filter_var = tk.StringVar(value="t5")
        self.filter_cb = ttk.Combobox(
            frm, textvariable=self.filter_var,
            values=["t5", "bert", "gpt2", "summarization", "classification", "translation"],
            width=25
        )
        self.filter_cb.grid(row=1, column=1, sticky="ew", padx=5)
        self.filter_cb.bind("<<ComboboxSelected>>", lambda _: self.update_model_list())
        self.filter_cb.bind("<Return>", lambda e: self.update_model_list())

        # Modell wählen Frame (zweite Gruppe, neue Zeile unter frm)
        frm_model = ttk.Frame(self)
        frm_model.grid(row=1, column=0, sticky="ew", pady=10, padx=10)
        frm_model.columnconfigure(1, weight=1)

        ttk.Label(frm_model, text="Modell wählen:").grid(row=0, column=0, sticky="w")

        self.model_var = tk.StringVar()
        self.model_cb = ttk.Combobox(
            frm_model, textvariable=self.model_var,
            state="readonly", width=40
        )
        self.model_cb.grid(row=0, column=1, sticky="ew", padx=5)
        self.model_cb.bind("<<ComboboxSelected>>", lambda _: self.update_model_info())

        # Info Label
        self.info_lbl = ttk.Label(self, text="", justify="left", foreground="blue")
        self.info_lbl.grid(row=2, column=0, sticky="ew", pady=5, padx=10)

        # Button Frame (Laden + Progressbar)
        self.btn_frame = ttk.Frame(self)
        self.btn_frame.grid(row=3, column=0, pady=10, sticky="ew", padx=10)
        self.btn_frame.columnconfigure(1, weight=1)

        self.load_btn = ttk.Button(self.btn_frame, text="Modell laden", command=self.lade_huggingface_modell)
        self.load_btn.grid(row=0, column=0, padx=5)

        self.progress = ttk.Progressbar(self.btn_frame, orient="horizontal", length=200, mode="determinate")
        self.progress.grid(row=0, column=1, padx=5, sticky="ew")

        # Status Label
        self.status_lbl = ttk.Label(self, text="Bereit.")
        self.status_lbl.grid(row=4, column=0, sticky="ew", padx=10)

        self._update_training_widgets()  # Initialer Aufruf


    def hide_tab(self):
        # Beispiel zum Ausblenden des Tabs
        if hasattr(self, "notebook"):
            self.notebook.hide(self)


    def _add_language(self):
        import tkinter.simpledialog as simpledialog

        new_lang = simpledialog.askstring("Sprache hinzufügen",
                                          "Gib die Sprache ein im Format 'Landessprache / Englisch',\nz.B. 'Ελληνικά / Greek':")
        if new_lang and " / " in new_lang:
            values = list(self.language_cb['values'])
            if new_lang not in values:
                values.append(new_lang)
                self.language_cb['values'] = values
                self.language_var.set(new_lang)
                self.update_model_list()

    def update_model_list(self):
        if self._loading:
            return
        langs = [p.strip().lower() for p in self.language_var.get().split("/")]
        filt = self.filter_var.get().lower()
        models = self.client.get_available_models(model_filter=filt, language_keywords=langs)
        self.model_cb["values"] = models
        if models:
            self.model_var.set(models[0])
            self.load_btn.state(["!disabled"])
            self.update_model_info()
        else:
            self.model_var.set("")
            self.info_lbl.config(text="Keine Modelle gefunden.")
            self.load_btn.state(["disabled"])

    def _update_training_widgets(self):
        if not hasattr(self, "train_btn"):
            self.train_btn = ttk.Button(self.btn_frame, text="Modell trainieren", command=self.train_model)
        if not hasattr(self, "train_progress"):
            self.train_progress = ttk.Progressbar(self.btn_frame, orient="horizontal", length=200, mode="determinate")

        self.train_btn.pack_forget()
        self.train_progress.pack_forget()

        if self.client.model is not None:
            self.train_btn.pack(side=tk.LEFT, padx=5)
            self.train_progress.pack(side=tk.LEFT, padx=5)

    def train_model(self):
        file_path = filedialog.askopenfilename(
            title="Trainingsdatei wählen",
            filetypes=[("Textdateien", "*.txt"), ("JSON Dateien", "*.json"), ("Alle Dateien", "*.*")]
        )
        if not file_path:
            self.status_lbl.config(text="Training abgebrochen: keine Datei gewählt.")
            return

        def progress_update(fraction):
            self.train_progress.config(mode="determinate", value=fraction * 100)
            self.train_progress.update_idletasks()

        def training_task():
            try:
                self.status_lbl.config(text=f"Training mit Datei: {file_path} gestartet...")
                self.train_progress.config(mode="determinate", value=0)

                self.client.train_model_from_file(
                    train_file_path=file_path,
                    epochs=3,
                    batch_size=8,
                    learning_rate=5e-5,
                    progress_callback=progress_update
                )

                self.status_lbl.config(text="Training erfolgreich beendet.")
            except Exception as e:
                print(f"Training fehlgeschlagen: {e}")  # Debug-Log
                self.status_lbl.config(text=f"Training fehlgeschlagen: {e}")
            finally:
                self.train_progress.config(value=0)

        threading.Thread(target=training_task, daemon=True).start()

    def update_model_info(self):
        name = self.model_var.get()
        if not name:
            self.info_lbl.config(text="")
            return
        info = self.client.get_model_info(name)
        if info.get("Error"):
            self.info_lbl.config(text=f"Fehler: {info['Error']}")
        else:
            txt = (
                f"Größe: {info['Model Size (MB)']} MB\n"
                f"Parameter: {info['Number of Parameters']}\n"
                f"Architektur: {info['Architecture']}\n"
                f"Tokenizer: {info['Tokenizer Class']}"
            )
            self.info_lbl.config(text=txt)

    def lade_huggingface_modell(self):
        if self._loading:
            return
        name = self.model_var.get()
        if not name:
            return
        self._loading = True
        self.load_btn.state(["disabled"])
        self.status_lbl.config(text="Lade Modell…")
        self.progress.config(mode="indeterminate")
        self.progress.start(10)
        threading.Thread(target=self._load_thread, args=(name,), daemon=True).start()

    def _load_thread(self, name: str):
        try:
            self.client.set_model(name)
            self.after(0, lambda: self._on_loaded(name))
        except Exception as e:
            print(f"Laden fehlgeschlagen: {e}")  # Debug-Log
            self.after(0, lambda e=e: self._on_load_fail(e))

    def _on_loaded(self, name: str):
        self._loading = False
        self.progress.stop()
        self.progress.config(mode="determinate", value=100)
        self.status_lbl.config(text=f"'{name}' geladen ✔")
        self.load_btn.state(["!disabled"])
        self._update_training_widgets()

    def _on_load_fail(self, err: Exception):
        self._loading = False
        self.progress.stop()
        self.progress.config(mode="determinate", value=0)
        self.status_lbl.config(text=f"Laden fehlgeschlagen: {err}")
        self.load_btn.state(["!disabled"])

