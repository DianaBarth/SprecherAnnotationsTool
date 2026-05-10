from __future__ import annotations

import re
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional
from audioanalyse_service import AudioAnalyseService, AudioAnalyseResult


class AudioAnalyseTab(ttk.Frame):
    MAX_SEGMENTE_IM_UI = 1000
    MAX_DIFFS_IM_UI = 500

    def __init__(
        self,
        parent,
        notebook=None,
        kapitel_config=None,
        ordner: Optional[dict] = None,
    ):
        super().__init__(parent)

        self.notebook = notebook
        self.kapitel_config = kapitel_config
        self.ordner = ordner or {}

        self.service = AudioAnalyseService(
            model_size="small",
            device="cpu",
            compute_type="int8",
        )

        self._worker_running = False
        self._run_id = 0

        self.selected_kapitel = tk.StringVar()
        self.audio_path_var = tk.StringVar()
        self.ref_path_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Bereit")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.sprache_var = tk.StringVar(value="de")
        self.model_var = tk.StringVar(value="small")

        self.lbl_wpm_var = tk.StringVar(value="-")
        self.lbl_dauer_var = tk.StringVar(value="-")
        self.lbl_woerter_var = tk.StringVar(value="-")
        self.lbl_pausen_var = tk.StringVar(value="-")
        self.lbl_laengste_pause_var = tk.StringVar(value="-")

        self.current_result: Optional[AudioAnalyseResult] = None

        self.abschnitt_var = tk.StringVar()
        self.abschnitt_pfade: dict[int, Path] = {}

        self._build_widgets()
        self.set_project_context(kapitel_config=self.kapitel_config, ordner=self.ordner)

    # ---------------------------------------------------------
    # Öffentliche API
    # ---------------------------------------------------------

    def set_project_context(self, kapitel_config=None, ordner=None):
        if kapitel_config is not None:
            self.kapitel_config = kapitel_config
        if ordner is not None:
            self.ordner = ordner

        self._load_chapter_values()
        self._auto_fill_paths_for_selected_chapter()

    # ---------------------------------------------------------
    # UI Aufbau
    # ---------------------------------------------------------

    def _build_widgets(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        frm_top = ttk.LabelFrame(self, text="Audioanalyse")
        frm_top.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        frm_top.columnconfigure(1, weight=1)

        ttk.Label(frm_top, text="Kapitel:").grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.kapitel_combo = ttk.Combobox(
            frm_top,
            textvariable=self.selected_kapitel,
            state="readonly",
        )
        self.kapitel_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.kapitel_combo.bind("<<ComboboxSelected>>", self._on_kapitel_changed)

        ttk.Label(frm_top, text="Abschnitt:").grid(row=1, column=0, sticky="w", padx=5, pady=5)

        self.abschnitt_combo = ttk.Combobox(
            frm_top,
            textvariable=self.abschnitt_var,
            state="readonly",
            width=18,
        )
        self.abschnitt_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        self.abschnitt_combo.bind("<<ComboboxSelected>>", self._on_abschnitt_changed)

        self.btn_rescan = ttk.Button(
            frm_top,
            text="Pfade neu suchen",
            command=self._auto_fill_paths_for_selected_chapter,
        )
        self.btn_rescan.grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(frm_top, text="Audio-Datei:").grid(row=1, column=0, sticky="w", padx=5, pady=5)

        self.entry_audio = ttk.Entry(frm_top, textvariable=self.audio_path_var)
        self.entry_audio.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        self.btn_audio = ttk.Button(frm_top, text="Audio wählen", command=self._select_audio_file)
        self.btn_audio.grid(row=1, column=2, padx=5, pady=5)

        ttk.Label(frm_top, text="Referenz-JSON/TXT:").grid(row=2, column=0, sticky="w", padx=5, pady=5)

        self.entry_ref = ttk.Entry(frm_top, textvariable=self.ref_path_var)
        self.entry_ref.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        self.btn_ref = ttk.Button(frm_top, text="Referenz wählen", command=self._select_ref_file)
        self.btn_ref.grid(row=2, column=2, padx=5, pady=5)

        ttk.Label(frm_top, text="Sprache:").grid(row=3, column=0, sticky="w", padx=5, pady=5)

        self.cmb_sprache = ttk.Combobox(
            frm_top,
            textvariable=self.sprache_var,
            state="readonly",
            values=["de", "en", "auto"],
            width=12,
        )
        self.cmb_sprache.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(frm_top, text="Whisper-Modell:").grid(row=4, column=0, sticky="w", padx=5, pady=5)

        self.cmb_model = ttk.Combobox(
            frm_top,
            textvariable=self.model_var,
            state="readonly",
            values=["tiny", "base", "small", "medium", "large-v3"],
            width=18,
        )
        self.cmb_model.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        self.cmb_model.bind("<<ComboboxSelected>>", self._on_model_changed)

        btn_frame = ttk.Frame(frm_top)
        btn_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=5, pady=(10, 5))

        self.btn_start = ttk.Button(btn_frame, text="Analyse starten", command=self.start_analysis)
        self.btn_start.grid(row=0, column=0, padx=(0, 5))

        self.btn_export = ttk.Button(
            btn_frame,
            text="Aktuelles Ergebnis exportieren",
            command=self._export_current_result,
        )
        self.btn_export.grid(row=0, column=1, padx=5)

        # Status
        frm_status = ttk.LabelFrame(self, text="Status")
        frm_status.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        frm_status.columnconfigure(0, weight=1)

        ttk.Label(frm_status, textvariable=self.status_var).grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.progressbar = ttk.Progressbar(frm_status, variable=self.progress_var, maximum=100)
        self.progressbar.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        # Kennzahlen
        frm_metrics = ttk.LabelFrame(self, text="Kennzahlen")
        frm_metrics.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))

        pairs = [
            ("Dauer (s):", self.lbl_dauer_var),
            ("Wörter:", self.lbl_woerter_var),
            ("WPM:", self.lbl_wpm_var),
            ("Pausen:", self.lbl_pausen_var),
            ("Längste Pause (s):", self.lbl_laengste_pause_var),
        ]

        for idx, (label_text, var) in enumerate(pairs):
            ttk.Label(frm_metrics, text=label_text).grid(
                row=0,
                column=idx * 2,
                sticky="w",
                padx=(8, 2),
                pady=5,
            )
            ttk.Label(frm_metrics, textvariable=var).grid(
                row=0,
                column=idx * 2 + 1,
                sticky="w",
                padx=(0, 12),
                pady=5,
            )

        # Ergebnis-Tabs
        self.result_notebook = ttk.Notebook(self)
        self.result_notebook.grid(row=4, column=0, sticky="nsew", padx=8, pady=(0, 8))

        self._build_diff_tab()
        self._build_pausen_tab()
        self._build_tempo_tab()
        self._build_segment_tab()
        self._build_transkript_tab()

    def _on_kapitel_changed(self, event=None):
        self._load_abschnitt_values_for_selected_chapter()
        self._auto_fill_paths_for_selected_chapter()


    def _on_abschnitt_changed(self, event=None):
        self._auto_fill_paths_for_selected_chapter()


    def _kapitel_id_aus_name(self, kapitel_name: str) -> Optional[str]:
        if not self.kapitel_config:
            return None

        kapitel_liste = getattr(self.kapitel_config, "kapitel_liste", []) or []

        try:
            idx = list(kapitel_liste).index(kapitel_name)
            return f"{idx:03d}"
        except ValueError:
            return None
        
    def _finde_abschnitt_jsons(self, kapitel_name: str) -> dict[int, Path]:
        kapitel_id = self._kapitel_id_aus_name(kapitel_name)
        if not kapitel_id:
            return {}

        result: dict[int, Path] = {}

        pattern = re.compile(rf"^{kapitel_id}_(\d{{3}})\.json$")

        def scan(ordner_key: str, overwrite: bool):
            ordner = self.ordner.get(ordner_key) if self.ordner else None
            if not ordner:
                return

            ordner = Path(ordner)
            if not ordner.exists():
                return

            for pfad in sorted(ordner.glob("*.json")):
                m = pattern.match(pfad.name)
                if not m:
                    continue

                abschnitt_nr = int(m.group(1))

                if overwrite or abschnitt_nr not in result:
                    result[abschnitt_nr] = pfad

        scan("merge", overwrite=False)
        scan("manuell", overwrite=True)

        return dict(sorted(result.items()))
                
    def _load_abschnitt_values_for_selected_chapter(self):
        kapitel_name = self.selected_kapitel.get().strip()
        if not kapitel_name:
            self.abschnitt_pfade = {}
            self.abschnitt_combo["values"] = []
            self.abschnitt_var.set("")
            return

        self.abschnitt_pfade = self._finde_abschnitt_jsons(kapitel_name)

        values = [
            f"Abschnitt {nr:03d}"
            for nr in self.abschnitt_pfade.keys()
        ]

        self.abschnitt_combo["values"] = values

        if values:
            if self.abschnitt_var.get() not in values:
                self.abschnitt_var.set(values[0])
        else:
            self.abschnitt_var.set("")


    def _build_diff_tab(self):
        self.tab_diffs = ttk.Frame(self.result_notebook)
        self.tab_diffs.columnconfigure(0, weight=1)
        self.tab_diffs.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_diffs, text="Problemstellen")

        self.diff_tree = ttk.Treeview(
            self.tab_diffs,
            columns=("typ", "score", "summary", "referenz", "gesprochen"),
            show="headings",
        )

        self.diff_tree.heading("typ", text="Typ")
        self.diff_tree.heading("score", text="Score")
        self.diff_tree.heading("summary", text="Unterschied")
        self.diff_tree.heading("referenz", text="Referenz")
        self.diff_tree.heading("gesprochen", text="Gesprochen")

        self.diff_tree.column("typ", width=120, anchor="w")
        self.diff_tree.column("score", width=80, anchor="center")
        self.diff_tree.column("summary", width=420, anchor="w")
        self.diff_tree.column("referenz", width=360, anchor="w")
        self.diff_tree.column("gesprochen", width=360, anchor="w")

        diff_scroll_y = ttk.Scrollbar(self.tab_diffs, orient="vertical", command=self.diff_tree.yview)
        diff_scroll_x = ttk.Scrollbar(self.tab_diffs, orient="horizontal", command=self.diff_tree.xview)

        self.diff_tree.configure(
            yscrollcommand=diff_scroll_y.set,
            xscrollcommand=diff_scroll_x.set,
        )

        self.diff_tree.grid(row=0, column=0, sticky="nsew")
        diff_scroll_y.grid(row=0, column=1, sticky="ns")
        diff_scroll_x.grid(row=1, column=0, sticky="ew")

    def _build_pausen_tab(self):
        self.tab_pausen = ttk.Frame(self.result_notebook)
        self.tab_pausen.columnconfigure(0, weight=1)
        self.tab_pausen.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_pausen, text="Pausen")

        self.pause_tree = ttk.Treeview(
            self.tab_pausen,
            columns=("start", "end", "duration", "kategorie", "davor", "danach"),
            show="headings",
        )

        self.pause_tree.heading("start", text="Start")
        self.pause_tree.heading("end", text="Ende")
        self.pause_tree.heading("duration", text="Dauer")
        self.pause_tree.heading("kategorie", text="Kategorie")
        self.pause_tree.column("kategorie", width=140, anchor="center")
        self.pause_tree.heading("davor", text="Text davor")
        self.pause_tree.heading("danach", text="Text danach")

        self.pause_tree.column("start", width=120, anchor="center")
        self.pause_tree.column("end", width=120, anchor="center")
        self.pause_tree.column("duration", width=120, anchor="center")
        self.pause_tree.column("davor", width=350, anchor="w")
        self.pause_tree.column("danach", width=350, anchor="w")
        

        pause_scroll_y = ttk.Scrollbar(self.tab_pausen, orient="vertical", command=self.pause_tree.yview)
        self.pause_tree.configure(yscrollcommand=pause_scroll_y.set)

        self.pause_tree.grid(row=0, column=0, sticky="nsew")
        pause_scroll_y.grid(row=0, column=1, sticky="ns")

        self.pause_tree.tag_configure("kurz", background="#eeeeee")
        self.pause_tree.tag_configure("normal", background="#ffffff")
        self.pause_tree.tag_configure("lang", background="#fff3cd")        # gelb
        self.pause_tree.tag_configure("sehr_lang", background="#ffe5b4")   # orange
        self.pause_tree.tag_configure("problematisch", background="#f8d7da")  # rot

    def _build_segment_tab(self):
        self.tab_segmente = ttk.Frame(self.result_notebook)
        self.tab_segmente.columnconfigure(0, weight=1)
        self.tab_segmente.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_segmente, text="Segmente")

        self.segment_text = tk.Text(
            self.tab_segmente,
            wrap="word",
            height=20,
            font=("Arial", 10),
        )

        self.segment_text.tag_configure("bold", font=("Arial", 10, "bold"))
        self.segment_text.tag_configure("meta", foreground="gray")
        self.segment_text.tag_configure("ok", foreground="green")
        self.segment_text.tag_configure("bad", foreground="red", font=("Arial", 10, "bold"))
        self.segment_text.tag_configure("label", foreground="gray", font=("Arial", 10, "bold"))

        seg_scroll_y = ttk.Scrollbar(
            self.tab_segmente,
            orient="vertical",
            command=self.segment_text.yview,
        )

        self.segment_text.configure(yscrollcommand=seg_scroll_y.set)

        self.segment_text.grid(row=0, column=0, sticky="nsew")
        seg_scroll_y.grid(row=0, column=1, sticky="ns")

    def _build_transkript_tab(self):
        self.tab_transkript = ttk.Frame(self.result_notebook)
        self.tab_transkript.columnconfigure(0, weight=1)
        self.tab_transkript.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_transkript, text="Transkript")

        self.transkript_text = tk.Text(self.tab_transkript, wrap="word", height=15)

        trans_scroll = ttk.Scrollbar(
            self.tab_transkript,
            orient="vertical",
            command=self.transkript_text.yview,
        )

        self.transkript_text.configure(yscrollcommand=trans_scroll.set)

        self.transkript_text.grid(row=0, column=0, sticky="nsew")
        trans_scroll.grid(row=0, column=1, sticky="ns")

    # ---------------------------------------------------------
    # UI Events
    # ---------------------------------------------------------

    def _on_model_changed(self, event=None):
        neuer_wert = self.model_var.get().strip()
        if not neuer_wert:
            return

        self.service.model_size = neuer_wert
        self.service._model = None

    def _on_kapitel_changed(self, event=None):
        self._auto_fill_paths_for_selected_chapter()

    def _select_audio_file(self):
        initial_dir = self._get_audio_dir()

        path = filedialog.askopenfilename(
            title="Audio-Datei auswählen",
            initialdir=str(initial_dir) if initial_dir else None,
            filetypes=[("Audio-Dateien", "*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma")],
        )

        if not path:
            return

        src_path = Path(path)

        # -----------------------------
        # Zielpfad bestimmen
        # -----------------------------
        target_path = self._build_audio_target_path(src_path)

        if not target_path:
            # fallback: einfach setzen
            self.audio_path_var.set(str(src_path))
            return

        try:
            import shutil

            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Konvertieren nur wenn nicht .wav
            if src_path.suffix.lower() != ".wav":
                target_path = target_path.with_suffix(".wav")
                self._convert_to_wav(src_path, target_path)
            else:
                shutil.copy2(src_path, target_path)

            self.audio_path_var.set(str(target_path))

        except Exception as e:
            messagebox.showerror("Fehler beim Kopieren", str(e))
            self.audio_path_var.set(str(src_path))

    def _build_audio_target_path(self, src_path: Path) -> Optional[Path]:
        audio_dir = self._get_audio_dir()
        if not audio_dir:
            return None

        # Abschnitt basiert
        abschnitt_nr = self._get_selected_abschnitt_nr()

        if abschnitt_nr and abschnitt_nr in self.abschnitt_pfade:
            json_path = self.abschnitt_pfade[abschnitt_nr]
            base_name = json_path.stem  # 002_001
        else:
            # fallback: Kapitelname
            kapitel_name = self.selected_kapitel.get().strip()
            base_name = self.service.normalisiere_dateinamen(kapitel_name)

        return Path(audio_dir) / f"{base_name}.wav"

    def _convert_to_wav(self, src: Path, dst: Path):
        try:
            import subprocess

            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", str(src),
                    "-ar", "16000",
                    "-ac", "1",
                    str(dst),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except Exception as e:
            raise RuntimeError(f"FFmpeg-Konvertierung fehlgeschlagen: {e}")

    def _select_ref_file(self):
        initial_dir = self._get_ref_dir()

        path = filedialog.askopenfilename(
            title="Referenzdatei auswählen",
            initialdir=str(initial_dir) if initial_dir else None,
            filetypes=[
                ("Referenzdateien", "*.json *.txt"),
                ("JSON-Dateien", "*.json"),
                ("Textdateien", "*.txt"),
            ],
        )

        if path:
            self.ref_path_var.set(path)

    # ---------------------------------------------------------
    # Analyse
    # ---------------------------------------------------------

    def start_analysis(self):
        if self._worker_running:
            messagebox.showinfo("Audioanalyse", "Es läuft bereits eine Analyse.")
            return

        kapitel_name = self.selected_kapitel.get().strip()
        audio_path = Path(self.audio_path_var.get().strip()) if self.audio_path_var.get().strip() else None
        ref_path = Path(self.ref_path_var.get().strip()) if self.ref_path_var.get().strip() else None
        sprache = self.sprache_var.get().strip() or "de"

        if not kapitel_name:
            messagebox.showwarning("Fehlende Auswahl", "Bitte zuerst ein Kapitel auswählen.")
            return

        if not audio_path or not audio_path.is_file():
            messagebox.showwarning("Fehlende Audio-Datei", "Bitte eine gültige Audio-Datei auswählen.")
            return

        if not ref_path or not ref_path.is_file():
            messagebox.showwarning("Fehlende Referenz", "Bitte eine gültige Referenz-JSON/TXT auswählen.")
            return

        output_paths = self._get_output_paths(kapitel_name)

        use_cache = False  # Default = neu analysieren

        if output_paths["json"].is_file():
            try:
                cached = self.service.lade_json_result(output_paths["json"])

                if self.service.ist_cache_gueltig(cached, audio_path, ref_path, sprache):
                    antwort = messagebox.askyesnocancel(
                        "Analyse vorhanden",
                        "Für dieses Kapitel existiert bereits eine Analyse.\n\n"
                        "JA = vorhandene Daten verwenden\n"
                        "NEIN = neu analysieren\n"
                        "ABBRECHEN = nichts tun"
                    )

                    if antwort is None:
                        return  # Abbruch

                    elif antwort is True:
                        use_cache = True   # JA → Cache verwenden

                    else:
                        use_cache = False  # NEIN → neu analysieren

            except Exception:
                use_cache = False

        self._run_id += 1
        run_id = self._run_id

        self._worker_running = True
        self._set_busy_state(True)
        self._reset_result_views()
        self.status_var.set("Analyse gestartet ...")
        self.progress_var.set(0)

        worker = threading.Thread(
            target=self._analysis_worker,
            args=(run_id, kapitel_name, audio_path, ref_path, sprache, use_cache),
            daemon=True,
        )
        worker.start()


    def _analysis_worker(self, run_id, kapitel_name, audio_path, ref_path, sprache, use_cache: bool):
        try:
            output_paths = self._get_output_paths(kapitel_name)

            result: Optional[AudioAnalyseResult] = None
            cache_hit = False

            if use_cache and output_paths["json"].is_file():
                try:
                    cached = self.service.lade_json_result(output_paths["json"])
                    if self.service.ist_cache_gueltig(cached, audio_path, ref_path, sprache):
                        result = cached
                        cache_hit = True
                        self._threadsafe_progress_update(
                            "Cache-Treffer: vorhandenes Ergebnis geladen", 100, run_id
                        )
                except Exception:
                    result = None

            if result is None:
                self._threadsafe_progress_update("Starte NEUE Analyse (Whisper)...", 5, run_id)

                result = self.service.analysiere_kapitel(
                    kapitel_name=kapitel_name,
                    audio_path=audio_path,
                    referenz_path=ref_path,
                    sprache=sprache,
                    progress_callback=lambda status, prog: self._threadsafe_progress_update(status, prog, run_id),
                )

                self.service.speichere_json(result, output_paths["json"])
                self.service.speichere_diff_csv(result, output_paths["diff_csv"])
                self.service.speichere_pausen_csv(result, output_paths["pausen_csv"])
                self.service.speichere_segmente_csv(result, output_paths["segmente_csv"])

            # Wichtig: erst HIER, nachdem result sicher gesetzt ist
            self.service.speichere_satzanalyse_json(
                result,
                output_paths["satzanalyse_json"]
            )

            self._safe_after(
                lambda rid=run_id, res=result, paths=output_paths, hit=cache_hit:
                    self._handle_analysis_success_if_current(rid, res, paths, hit)
            )

        except Exception as e:
            traceback.print_exc()
            self._safe_after(
                lambda err=e, rid=run_id:
                    self._handle_analysis_error_if_current(rid, err)
            )


    def _threadsafe_progress_update(self, status: str, progress: float, run_id: Optional[int] = None):
        if run_id is None:
            self._safe_after(lambda: self._update_progress(status, progress))
            return

        self._safe_after(
            lambda rid=run_id:
                self._update_progress_if_current(rid, status, progress)
        )

    def _update_progress_if_current(self, run_id: int, status: str, progress: float):
        if run_id != self._run_id:
            return

        self._update_progress(status, progress)

    def _update_progress(self, status: str, progress: float):
        self.status_var.set(status)
        self.progress_var.set(progress)

    def _handle_analysis_success_if_current(
        self,
        run_id: int,
        result: AudioAnalyseResult,
        output_paths: dict[str, Path],
        cache_hit: bool,
    ):
        if run_id != self._run_id:
            return

        self._handle_analysis_success(result, output_paths, cache_hit)

    def _handle_analysis_success(
        self,
        result: AudioAnalyseResult,
        output_paths: dict[str, Path],
        cache_hit: bool = False,
    ):
        self.current_result = result
        self._fill_result_views(result)
        self._fill_metric_labels(result)

        prefix = "Cache" if cache_hit else "Fertig"

        self.status_var.set(
            f"{prefix} | JSON: {output_paths['json'].name} | CSV: {output_paths['diff_csv'].name}"
        )
        self.progress_var.set(100)

        self._worker_running = False
        self._set_busy_state(False)

    def _handle_analysis_error_if_current(self, run_id: int, error: Exception):
        if run_id != self._run_id:
            return

        self._handle_analysis_error(error)

    def _handle_analysis_error(self, error: Exception):
        self.status_var.set("Fehler")
        self._worker_running = False
        self._set_busy_state(False)
        messagebox.showerror("Audioanalyse-Fehler", str(error))

    def _safe_after(self, func):
        try:
            if self.winfo_exists():
                self.after(0, func)
        except tk.TclError:
            pass

    # ---------------------------------------------------------
    # Ergebnisdarstellung
    # ---------------------------------------------------------

    def _reset_result_views(self):
        self.current_result = None

        for tree in (self.diff_tree, self.pause_tree, self.tempo_tree):
            for item in tree.get_children():
                tree.delete(item)

        self.segment_text.delete("1.0", "end")
        self.transkript_text.delete("1.0", "end")

        self.lbl_dauer_var.set("-")
        self.lbl_woerter_var.set("-")
        self.lbl_wpm_var.set("-")
        self.lbl_pausen_var.set("-")
        self.lbl_laengste_pause_var.set("-")

    def _fill_metric_labels(self, result: AudioAnalyseResult):
        self.lbl_dauer_var.set(str(result.audio_dauer_sekunden))
        self.lbl_woerter_var.set(str(result.wortanzahl))
        self.lbl_wpm_var.set(str(result.wpm))
        self.lbl_pausen_var.set(str(result.pausen_anzahl))
        self.lbl_laengste_pause_var.set(str(result.laengste_pause))

    def _fill_result_views(self, result: AudioAnalyseResult):
        self._fill_diff_view(result)     
        self._fill_segment_view(result)
        self._fill_transcript_view(result)
        self._fill_tempo_view(result)

        for p in self._sortiere_pausen(result.pausen):
            kategorie = getattr(p, "kategorie", "normal")

            self.pause_tree.insert(
                "",
                "end",
                values=(
                    f"{p.start:.3f}",
                    f"{p.end:.3f}",
                    f"{p.duration:.3f}",
                    kategorie,
                    getattr(p, "text_davor", ""),
                    getattr(p, "text_danach", ""),
                 ),
                tags=(kategorie,)
            )

    def _sortiere_pausen(self, pausen):
        gewicht = {
            "problematisch": 5,
            "sehr_lang": 4,
            "lang": 3,
            "normal": 2,
            "kurz": 1,
        }

        return sorted(
            pausen,
            key=lambda p: (
                -gewicht.get(getattr(p, "kategorie", "normal"), 2),
                -p.duration,
            )
        )

    def _fill_diff_view(self, result: AudioAnalyseResult):
        for entry in result.diff_entries[:self.MAX_DIFFS_IM_UI]:
            summary = getattr(entry, "summary", "") or entry.ref_text

            self.diff_tree.insert(
                "",
                "end",
                values=(
                    entry.typ,
                    f"{entry.score:.4f}",
                    summary,
                    getattr(entry, "ref_diff", "") or entry.ref_text,
                    getattr(entry, "spoken_diff", "") or entry.spoken_text,
                ),
            )



    def _fill_segment_view(self, result: AudioAnalyseResult):
        take_infos = []

        ref_path = Path(result.referenz_path)
        if ref_path.suffix.lower() == ".json" and ref_path.is_file():
            take_infos = self._berechne_take_infos_aus_json(ref_path)

        take_by_start_satz = {
            int(t["start_satz_nr"]): t
            for t in take_infos
        }
        bereits_gezeigte_takes = set()

        self.segment_text.delete("1.0", "end")

        for idx, seg in enumerate(result.segmente[:self.MAX_SEGMENTE_IM_UI], start=1):
            status = getattr(seg, "status", "OK")
            status_tag = "ok" if status == "OK" else "bad"

            match_score = getattr(seg, "match_score", 0.0)
            ref_satz_nr = getattr(seg, "ref_satz_nr", 0)
    
            for start_satz, take_info in sorted(take_by_start_satz.items()):
                if start_satz <= ref_satz_nr and take_info["take_nr"] not in bereits_gezeigte_takes:
                    bereits_gezeigte_takes.add(take_info["take_nr"])

                    self.segment_text.insert(
                        "end",
                        f"\n──────── Take {take_info['take_nr']} · "
                        f"ab Referenzsatz {take_info['start_satz_nr']} · "
                        f"{take_info.get('wortanzahl', '?')} Wörter ────────\n\n",
                        ("label",),
                    )



            self.segment_text.insert(
                "end",
                f"Segment {idx} | {seg.start:.3f}–{seg.end:.3f}s | "
                f"{seg.word_count} Wörter | {seg.local_wpm:.2f} WPM | "
                f"Ref-Satz {ref_satz_nr} | Score {match_score:.4f} | ",
                ("meta",),
            )
            self.segment_text.insert("end", f"{status}\n", (status_tag,))

            self.segment_text.insert("end", "Original: ", ("label",))
            self._insert_marked_text(
                self.segment_text,
                getattr(seg, "ref_marked", "") or getattr(seg, "ref_text", ""),
            )
            self.segment_text.insert("end", "\n")

            self.segment_text.insert("end", "Gesprochen: ", ("label",))
            self._insert_marked_text(
                self.segment_text,
                getattr(seg, "spoken_marked", "") or getattr(seg, "text", ""),
            )
            self.segment_text.insert("end", "\n")

            diff_summary = getattr(seg, "diff_summary", "")
            if diff_summary:
                self.segment_text.insert("end", "Differenz: ", ("label",))
                self.segment_text.insert("end", f"{diff_summary}\n", ("bad",))

            self.segment_text.insert("end", "\n")

        self.segment_text.configure(state="normal")

    def _fill_transcript_view(self, result: AudioAnalyseResult):
        self.transkript_text.delete("1.0", "end")
        self.transkript_text.insert("1.0", result.transcript_text)

    def _insert_marked_text(self, text_widget: tk.Text, text: str):
        parts = re.split(r"(\*\*.*?\*\*)", text or "")

        for part in parts:
            if not part:
                continue

            if part.startswith("**") and part.endswith("**"):
                text_widget.insert("end", part[2:-2], ("bold",))
            else:
                text_widget.insert("end", part)

    # ---------------------------------------------------------
    # Export
    # ---------------------------------------------------------

    def _export_current_result(self):
        if not self.current_result:
            messagebox.showinfo("Audioanalyse", "Es liegt noch kein Analyseergebnis vor.")
            return

        kapitel_name = self.current_result.kapitel_name
        output_paths = self._get_output_paths(kapitel_name)

        try:
            self.service.speichere_json(self.current_result, output_paths["json"])
            self.service.speichere_diff_csv(self.current_result, output_paths["diff_csv"])
            self.service.speichere_pausen_csv(self.current_result, output_paths["pausen_csv"])
            self.service.speichere_segmente_csv(self.current_result, output_paths["segmente_csv"])
        except Exception as e:
            messagebox.showerror("Exportfehler", str(e))
            return

        messagebox.showinfo(
            "Export abgeschlossen",
            f"Dateien gespeichert in:\n{output_paths['json'].parent}",
        )
        
        basis = Path(self.current_result.referenz_path).stem
        satzanalyse_pfad = output_paths["json"].parent / f"{basis}_satzanalyse.json"

        self.service.speichere_satzanalyse_json(
            self.current_result,
            output_paths["satzanalyse_json"]
        )
    # ---------------------------------------------------------
    # Dateifindung / Projektkontext
    # ---------------------------------------------------------

    def _load_chapter_values(self):
        kapitel_liste = []

        if self.kapitel_config is not None:
            kapitel_liste = getattr(self.kapitel_config, "kapitel_liste", []) or []

            if not kapitel_liste:
                kapitel_daten = getattr(self.kapitel_config, "kapitel_daten", {}) or {}
                kapitel_liste = list(kapitel_daten.keys())

        self.kapitel_combo["values"] = kapitel_liste

        if kapitel_liste:
            aktuelles = self.selected_kapitel.get().strip()

            if aktuelles not in kapitel_liste:
                self.selected_kapitel.set(kapitel_liste[0])
        else:
            self.selected_kapitel.set("")

        self._load_abschnitt_values_for_selected_chapter()

    def _auto_fill_paths_for_selected_chapter(self):
        kapitel_name = self.selected_kapitel.get().strip()
        if not kapitel_name:
            self.audio_path_var.set("")
            self.ref_path_var.set("")
            return

        # -----------------------------
        # Audio-Datei automatisch suchen
        # Priorität:
        # 1. passend zur ausgewählten JSON: 002_001.json -> audio/002_001.wav
        # 2. allgemeine Audiosuche nach Kapitelname
        # -----------------------------
        audio_dir = self._get_audio_dir()

        if audio_dir and audio_dir.exists():
            audio_match = None

            abschnitt_nr = self._get_selected_abschnitt_nr()

            if abschnitt_nr and abschnitt_nr in self.abschnitt_pfade:
                json_path = self.abschnitt_pfade[abschnitt_nr]
                expected_audio = audio_dir / f"{json_path.stem}.wav"

                if expected_audio.is_file():
                    audio_match = expected_audio

            if audio_match is None:
                audio_match = self.service.finde_audiodatei(kapitel_name, audio_dir)

            self.audio_path_var.set(str(audio_match) if audio_match else "")
        else:
            self.audio_path_var.set("")

        # -----------------------------
        # Referenz-JSON automatisch setzen
        # Priorität:
        # 1. ausgewählter Abschnitt aus manuell/merge
        # 2. allgemeine Referenzsuche
        # -----------------------------
        abschnitt_nr = self._get_selected_abschnitt_nr()

        if abschnitt_nr and abschnitt_nr in self.abschnitt_pfade:
            self.ref_path_var.set(str(self.abschnitt_pfade[abschnitt_nr]))
            return

        ref_dir = self._get_ref_dir()

        if ref_dir and ref_dir.exists():
            ref_match = self.service.finde_referenztext(kapitel_name, ref_dir)
            self.ref_path_var.set(str(ref_match) if ref_match else "")
        else:
            self.ref_path_var.set("")
        
    def _get_audio_dir(self) -> Optional[Path]:
        if not self.ordner:
            return None

        value = self.ordner.get("audio")
        return Path(value) if value else None

    def _get_ref_dir(self) -> Optional[Path]:
        if not self.ordner:
            return None

        for key in ("manuell", "merge", "txt"):
            value = self.ordner.get(key)
            if value:
                return Path(value)

        return None

    def _get_txt_dir(self) -> Optional[Path]:
        # Kompatibilitäts-Fallback, falls an anderer Stelle noch genutzt.
        return self._get_ref_dir()

    def _get_audioanalyse_dir(self) -> Path:
        if self.ordner and self.ordner.get("audioanalyse"):
            path = Path(self.ordner["audioanalyse"])
            path.mkdir(parents=True, exist_ok=True)
            return path

        fallback = Path.cwd() / "audioanalyse"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _get_output_paths(self, kapitel_name: str) -> dict[str, Path]:
        audioanalyse_dir = self._get_audioanalyse_dir()

        ref_text = self.ref_path_var.get().strip()
        if ref_text:
            key = Path(ref_text).stem  # z.B. 002_001
        else:
            key = self.service.make_output_key(kapitel_name)

        return {
            "json": audioanalyse_dir / f"{key}_analyse.json",
            "diff_csv": audioanalyse_dir / f"{key}_problemstellen.csv",
            "pausen_csv": audioanalyse_dir / f"{key}_pausen.csv",
            "segmente_csv": audioanalyse_dir / f"{key}_segmente.csv",
            "satzanalyse_json": audioanalyse_dir / f"{key}_satzanalyse.json",
        }

    def _get_selected_abschnitt_nr(self) -> Optional[int]:
        text = self.abschnitt_var.get().strip()
        m = re.search(r"(\d+)", text)
        if not m:
            return None
        return int(m.group(1))
    # ---------------------------------------------------------
    # Busy State
    # ---------------------------------------------------------

    def _set_busy_state(self, busy: bool):
        state = "disabled" if busy else "normal"
        readonly_state = "disabled" if busy else "readonly"

        self.btn_start.config(state=state)
        self.btn_export.config(state=state)
        self.btn_rescan.config(state=state)

        self.kapitel_combo.config(state=readonly_state)
        self.cmb_sprache.config(state=readonly_state)
        self.cmb_model.config(state=readonly_state)

        self.entry_audio.config(state=state)
        self.entry_ref.config(state=state)
        self.btn_audio.config(state=state)
        self.btn_ref.config(state=state)

    def _berechne_take_infos_aus_json(self, json_path: Path) -> list[dict]:
        try:
            daten = json.loads(Path(json_path).read_text(encoding="utf-8"))
        except Exception:
            return []

        if not isinstance(daten, list):
            return []

        MIN_WOERTER = 50
        OPTIMAL_MIN = 70
        OPTIMAL_MAX = 120
        MAX_WOERTER = 170

        take_infos = [{
            "take_nr": 1,
            "start_satz_nr": 1,
            "wortanzahl": 0,
        }]

        take_nr = 1
        take_woerter = 0
        satz_nr = 0
        kandidat_satz_nr = None
        kandidat_wortzahl = None

        for eintrag in daten:
            if not isinstance(eintrag, dict):
                continue

            token = str(eintrag.get("token", "") or "").strip()
            if not token:
                continue

            if self._json_eintrag_ist_wort(eintrag):
                take_woerter += 1

            if not self._json_eintrag_ist_satzende(eintrag):
                continue

            satz_nr += 1

            if OPTIMAL_MIN <= take_woerter <= OPTIMAL_MAX:
                take_infos[-1]["wortanzahl"] = take_woerter

                take_nr += 1
                take_infos.append({
                    "take_nr": take_nr,
                    "start_satz_nr": satz_nr + 1,
                    "wortanzahl": 0,
                })

                take_woerter = 0
                kandidat_satz_nr = None
                kandidat_wortzahl = None
                continue

            if MIN_WOERTER <= take_woerter < OPTIMAL_MIN:
                kandidat_satz_nr = satz_nr
                kandidat_wortzahl = take_woerter

            if take_woerter >= MAX_WOERTER:
                take_infos[-1]["wortanzahl"] = kandidat_wortzahl or take_woerter

                take_nr += 1
                take_infos.append({
                    "take_nr": take_nr,
                    "start_satz_nr": (kandidat_satz_nr or satz_nr) + 1,
                    "wortanzahl": 0,
                })

                take_woerter = 0
                kandidat_satz_nr = None
                kandidat_wortzahl = None

        if take_infos:
            take_infos[-1]["wortanzahl"] = take_infos[-1].get("wortanzahl") or take_woerter

        return [t for t in take_infos if t.get("start_satz_nr", 0) > 0]


    def _json_eintrag_ist_wort(self, eintrag: dict) -> bool:
        token = str(eintrag.get("token", "") or "").strip()
        return bool(token) and re.search(r"\w", token, re.UNICODE) is not None


    def _json_eintrag_ist_satzende(self, eintrag: dict) -> bool:
        token = str(eintrag.get("token", "") or "").strip()
        annotation = eintrag.get("annotation", "")

        if isinstance(annotation, dict):
            hat_zeilenumbruch = "zeilenumbruch" in {
                str(k).lower() for k in annotation.keys()
            }
        elif isinstance(annotation, list):
            hat_zeilenumbruch = any(
                str(a).lower() == "zeilenumbruch"
                for a in annotation
            )
        else:
            hat_zeilenumbruch = "zeilenumbruch" in str(annotation).lower()

        return (
            token in {".", "!", "?", "…"}
            or token.endswith((".", "!", "?", "…"))
            or hat_zeilenumbruch
        )
    
    def _build_tempo_tab(self):
        self.tab_tempo = ttk.Frame(self.result_notebook)
        self.tab_tempo.columnconfigure(0, weight=1)
        self.tab_tempo.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_tempo, text="Tempoanalyse")

        self.tempo_tree = ttk.Treeview(
            self.tab_tempo,
            columns=("bewertung", "start", "end", "wpm", "woerter", "text"),
            show="headings",
        )

        self.tempo_tree.heading("bewertung", text="Bewertung")
        self.tempo_tree.heading("start", text="Start")
        self.tempo_tree.heading("end", text="Ende")
        self.tempo_tree.heading("wpm", text="WPM")
        self.tempo_tree.heading("woerter", text="Wörter")
        self.tempo_tree.heading("text", text="Text")

        self.tempo_tree.column("bewertung", width=120, anchor="center")
        self.tempo_tree.column("start", width=90, anchor="center")
        self.tempo_tree.column("end", width=90, anchor="center")
        self.tempo_tree.column("wpm", width=90, anchor="center")
        self.tempo_tree.column("woerter", width=80, anchor="center")
        self.tempo_tree.column("text", width=900, anchor="w")

        self.tempo_tree.tag_configure("sehr_langsam", background="#d1ecf1")
        self.tempo_tree.tag_configure("langsam", background="#e2f3f5")
        self.tempo_tree.tag_configure("normal", background="#ffffff")
        self.tempo_tree.tag_configure("schnell", background="#fff3cd")
        self.tempo_tree.tag_configure("sehr_schnell", background="#f8d7da", foreground="#721c24")

        scroll_y = ttk.Scrollbar(self.tab_tempo, orient="vertical", command=self.tempo_tree.yview)
        scroll_x = ttk.Scrollbar(self.tab_tempo, orient="horizontal", command=self.tempo_tree.xview)

        self.tempo_tree.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )

        self.tempo_tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    def _klassifiziere_tempo(self, wpm: float) -> str:
        if wpm < 90:
            return "sehr_langsam"
        if wpm < 120:
            return "langsam"
        if wpm <= 165:
            return "normal"
        if wpm <= 190:
            return "schnell"
        return "sehr_schnell"


    def _tempo_label(self, kategorie: str) -> str:
        labels = {
            "sehr_langsam": "sehr langsam",
            "langsam": "langsam",
            "normal": "normal",
            "schnell": "schnell",
            "sehr_schnell": "sehr schnell",
        }
        return labels.get(kategorie, kategorie)
    
    def _fill_tempo_view(self, result: AudioAnalyseResult):
        self.tempo_tree.delete(*self.tempo_tree.get_children())

        segmente = list(result.segmente)

        # Auffällige zuerst: sehr schnell, schnell, sehr langsam, langsam, normal
        gewicht = {
            "sehr_schnell": 5,
            "schnell": 4,
            "sehr_langsam": 3,
            "langsam": 2,
            "normal": 1,
        }

        eintraege = []

        for seg in segmente:
            wpm = float(getattr(seg, "local_wpm", 0.0) or 0.0)
            kat = self._klassifiziere_tempo(wpm)
            eintraege.append((kat, seg))

        eintraege.sort(
            key=lambda x: (
                -gewicht.get(x[0], 0),
                -float(getattr(x[1], "local_wpm", 0.0) or 0.0),
            )
        )

        for kat, seg in eintraege:
            self.tempo_tree.insert(
                "",
                "end",
                values=(
                    self._tempo_label(kat),
                    f"{seg.start:.3f}",
                    f"{seg.end:.3f}",
                    f"{seg.local_wpm:.2f}",
                    seg.word_count,
                    seg.text,
                ),
                tags=(kat,),
            )
