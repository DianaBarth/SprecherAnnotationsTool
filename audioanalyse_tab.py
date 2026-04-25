from __future__ import annotations

import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from audioanalyse_service import AudioAnalyseService, AudioAnalyseResult


class AudioAnalyseTab(ttk.Frame):
    """
    Tkinter-Tab für die Audioanalyse.

    Ziele:
    - Kapitel auswählen
    - passende Audio-/Referenzdatei automatisch finden
    - bei Bedarf manuell überschreiben
    - Analyse im Hintergrundthread starten
    - Kennzahlen + Problemstellen anzeigen
    - JSON/CSV in audioanalyse-Ordner schreiben
    """

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

        self._build_widgets()
        self.set_project_context(kapitel_config=self.kapitel_config, ordner=self.ordner)

    # ---------------------------------------------------------
    # Öffentliche API
    # ---------------------------------------------------------

    def set_project_context(self, kapitel_config=None, ordner=None):
        """
        Wird von außen aufgerufen, wenn Projekt / Kapitel / Ordner gewechselt haben.
        """
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

        # ---------------------------------------------
        # Eingabebereich
        # ---------------------------------------------
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

        self.btn_rescan = ttk.Button(
            frm_top,
            text="Pfade neu suchen",
            command=self._auto_fill_paths_for_selected_chapter
        )
        self.btn_rescan.grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(frm_top, text="Audio-Datei:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.entry_audio = ttk.Entry(frm_top, textvariable=self.audio_path_var)
        self.entry_audio.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.btn_audio = ttk.Button(frm_top, text="Audio wählen", command=self._select_audio_file)
        self.btn_audio.grid(row=1, column=2, padx=5, pady=5)

        ttk.Label(frm_top, text="Referenz-TXT:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.entry_ref = ttk.Entry(frm_top, textvariable=self.ref_path_var)
        self.entry_ref.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.btn_ref = ttk.Button(frm_top, text="TXT wählen", command=self._select_ref_file)
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
            command=self._export_current_result
        )
        self.btn_export.grid(row=0, column=1, padx=5)

        # ---------------------------------------------
        # Status / Fortschritt
        # ---------------------------------------------
        frm_status = ttk.LabelFrame(self, text="Status")
        frm_status.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        frm_status.columnconfigure(0, weight=1)

        ttk.Label(frm_status, textvariable=self.status_var).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.progressbar = ttk.Progressbar(frm_status, variable=self.progress_var, maximum=100)
        self.progressbar.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        # ---------------------------------------------
        # Kennzahlen
        # ---------------------------------------------
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
            ttk.Label(frm_metrics, text=label_text).grid(row=0, column=idx * 2, sticky="w", padx=(8, 2), pady=5)
            ttk.Label(frm_metrics, textvariable=var).grid(row=0, column=idx * 2 + 1, sticky="w", padx=(0, 12), pady=5)

        # ---------------------------------------------
        # Tabs für Ergebnisse
        # ---------------------------------------------
        self.result_notebook = ttk.Notebook(self)
        self.result_notebook.grid(row=4, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # Problemstellen
        self.tab_diffs = ttk.Frame(self.result_notebook)
        self.tab_diffs.columnconfigure(0, weight=1)
        self.tab_diffs.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_diffs, text="Problemstellen")

        self.diff_tree = ttk.Treeview(
            self.tab_diffs,
            columns=("typ", "score", "referenz", "gesprochen"),
            show="headings",
        )
        self.diff_tree.heading("typ", text="Typ")
        self.diff_tree.heading("score", text="Score")
        self.diff_tree.heading("referenz", text="Referenz")
        self.diff_tree.heading("gesprochen", text="Gesprochen")

        self.diff_tree.column("typ", width=140, anchor="w")
        self.diff_tree.column("score", width=80, anchor="center")
        self.diff_tree.column("referenz", width=420, anchor="w")
        self.diff_tree.column("gesprochen", width=420, anchor="w")

        diff_scroll_y = ttk.Scrollbar(self.tab_diffs, orient="vertical", command=self.diff_tree.yview)
        diff_scroll_x = ttk.Scrollbar(self.tab_diffs, orient="horizontal", command=self.diff_tree.xview)
        self.diff_tree.configure(yscrollcommand=diff_scroll_y.set, xscrollcommand=diff_scroll_x.set)

        self.diff_tree.grid(row=0, column=0, sticky="nsew")
        diff_scroll_y.grid(row=0, column=1, sticky="ns")
        diff_scroll_x.grid(row=1, column=0, sticky="ew")

        # Pausen
        self.tab_pausen = ttk.Frame(self.result_notebook)
        self.tab_pausen.columnconfigure(0, weight=1)
        self.tab_pausen.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_pausen, text="Pausen")

        self.pause_tree = ttk.Treeview(
            self.tab_pausen,
            columns=("start", "end", "duration"),
            show="headings",
        )
        self.pause_tree.heading("start", text="Start")
        self.pause_tree.heading("end", text="Ende")
        self.pause_tree.heading("duration", text="Dauer")

        self.pause_tree.column("start", width=120, anchor="center")
        self.pause_tree.column("end", width=120, anchor="center")
        self.pause_tree.column("duration", width=120, anchor="center")

        pause_scroll_y = ttk.Scrollbar(self.tab_pausen, orient="vertical", command=self.pause_tree.yview)
        self.pause_tree.configure(yscrollcommand=pause_scroll_y.set)

        self.pause_tree.grid(row=0, column=0, sticky="nsew")
        pause_scroll_y.grid(row=0, column=1, sticky="ns")

        # Segmente
        self.tab_segmente = ttk.Frame(self.result_notebook)
        self.tab_segmente.columnconfigure(0, weight=1)
        self.tab_segmente.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_segmente, text="Segmente")

        self.segment_tree = ttk.Treeview(
            self.tab_segmente,
            columns=("start", "end", "word_count", "local_wpm", "text"),
            show="headings",
        )
        self.segment_tree.heading("start", text="Start")
        self.segment_tree.heading("end", text="Ende")
        self.segment_tree.heading("word_count", text="Wörter")
        self.segment_tree.heading("local_wpm", text="lokale WPM")
        self.segment_tree.heading("text", text="Text")

        self.segment_tree.column("start", width=100, anchor="center")
        self.segment_tree.column("end", width=100, anchor="center")
        self.segment_tree.column("word_count", width=80, anchor="center")
        self.segment_tree.column("local_wpm", width=100, anchor="center")
        self.segment_tree.column("text", width=800, anchor="w")

        seg_scroll_y = ttk.Scrollbar(self.tab_segmente, orient="vertical", command=self.segment_tree.yview)
        seg_scroll_x = ttk.Scrollbar(self.tab_segmente, orient="horizontal", command=self.segment_tree.xview)
        self.segment_tree.configure(yscrollcommand=seg_scroll_y.set, xscrollcommand=seg_scroll_x.set)

        self.segment_tree.grid(row=0, column=0, sticky="nsew")
        seg_scroll_y.grid(row=0, column=1, sticky="ns")
        seg_scroll_x.grid(row=1, column=0, sticky="ew")

        # Transkript
        self.tab_transkript = ttk.Frame(self.result_notebook)
        self.tab_transkript.columnconfigure(0, weight=1)
        self.tab_transkript.rowconfigure(0, weight=1)
        self.result_notebook.add(self.tab_transkript, text="Transkript")

        self.transkript_text = tk.Text(self.tab_transkript, wrap="word", height=15)
        trans_scroll = ttk.Scrollbar(self.tab_transkript, orient="vertical", command=self.transkript_text.yview)
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
        self.service._model = None  # lazy neu laden beim nächsten Lauf

    def _on_kapitel_changed(self, event=None):
        self._auto_fill_paths_for_selected_chapter()

    def _select_audio_file(self):
        initial_dir = self._get_audio_dir()
        path = filedialog.askopenfilename(
            title="Audio-Datei auswählen",
            initialdir=str(initial_dir) if initial_dir else None,
            filetypes=[("Audio-Dateien", "*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma")],
        )
        if path:
            self.audio_path_var.set(path)

    def _select_ref_file(self):
        initial_dir = self._get_txt_dir()
        path = filedialog.askopenfilename(
            title="Referenz-TXT auswählen",
            initialdir=str(initial_dir) if initial_dir else None,
            filetypes=[("Textdateien", "*.txt")],
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
            messagebox.showwarning("Fehlende Referenz", "Bitte eine gültige Referenz-TXT auswählen.")
            return

        self._run_id += 1
        run_id = self._run_id

        self._worker_running = True
        self._set_busy_state(True)
        self._reset_result_views()
        self.status_var.set("Analyse gestartet ...")
        self.progress_var.set(0)

        worker = threading.Thread(
            target=self._analysis_worker,
            args=(run_id, kapitel_name, audio_path, ref_path, sprache),
            daemon=True,
        )
        worker.start()

    def _analysis_worker(self, run_id: int, kapitel_name: str, audio_path: Path, ref_path: Path, sprache: str):
        try:
            output_paths = self._get_output_paths(kapitel_name)
            result: Optional[AudioAnalyseResult] = None
            cache_hit = False

            if output_paths["json"].is_file():
                try:
                    cached = self.service.lade_json_result(output_paths["json"])
                    if self.service.ist_cache_gueltig(cached, audio_path, ref_path, sprache):
                        result = cached
                        cache_hit = True
                        self._threadsafe_progress_update("Cache-Treffer: vorhandenes Ergebnis geladen", 100, run_id)
                except Exception:
                    result = None

            if result is None:
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

            self._safe_after(
                lambda rid=run_id, res=result, paths=output_paths, hit=cache_hit:
                    self._handle_analysis_success_if_current(rid, res, paths, hit)
            )

        except Exception as e:
            traceback.print_exc()
            self._safe_after(lambda err=e, rid=run_id: self._handle_analysis_error_if_current(rid, err))

    def _threadsafe_progress_update(self, status: str, progress: float, run_id: Optional[int] = None):
        if run_id is None:
            self._safe_after(lambda: self._update_progress(status, progress))
            return

        self._safe_after(lambda rid=run_id: self._update_progress_if_current(rid, status, progress))

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

        for tree in (self.diff_tree, self.pause_tree, self.segment_tree):
            for item in tree.get_children():
                tree.delete(item)

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
        for entry in result.diff_entries[:self.MAX_DIFFS_IM_UI]:
            self.diff_tree.insert(
                "",
                "end",
                values=(
                    entry.typ,
                    f"{entry.score:.4f}",
                    entry.ref_text,
                    entry.spoken_text,
                )
            )

        for p in result.pausen:
            self.pause_tree.insert(
                "",
                "end",
                values=(
                    f"{p.start:.3f}",
                    f"{p.end:.3f}",
                    f"{p.duration:.3f}",
                )
            )

        for seg in result.segmente[:self.MAX_SEGMENTE_IM_UI]:
            self.segment_tree.insert(
                "",
                "end",
                values=(
                    f"{seg.start:.3f}",
                    f"{seg.end:.3f}",
                    seg.word_count,
                    f"{seg.local_wpm:.2f}",
                    seg.text,
                )
            )

        self.transkript_text.delete("1.0", "end")
        self.transkript_text.insert("1.0", result.transcript_text)

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
            f"Dateien gespeichert in:\n{output_paths['json'].parent}"
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

    def _auto_fill_paths_for_selected_chapter(self):
        kapitel_name = self.selected_kapitel.get().strip()
        if not kapitel_name:
            return

        audio_dir = self._get_audio_dir()
        txt_dir = self._get_txt_dir()

        if audio_dir and audio_dir.exists():
            audio_match = self.service.finde_audiodatei(kapitel_name, audio_dir)
            self.audio_path_var.set(str(audio_match) if audio_match else "")

        if txt_dir and txt_dir.exists():
            ref_match = self.service.finde_referenztext(kapitel_name, txt_dir)
            self.ref_path_var.set(str(ref_match) if ref_match else "")

    def _get_audio_dir(self) -> Optional[Path]:
        if not self.ordner:
            return None
        value = self.ordner.get("audio")
        return Path(value) if value else None

    def _get_txt_dir(self) -> Optional[Path]:
        if not self.ordner:
            return None
        value = self.ordner.get("txt")
        return Path(value) if value else None

    def _get_audioanalyse_dir(self) -> Path:
        if self.ordner and self.ordner.get("audioanalyse"):
            return Path(self.ordner["audioanalyse"])

        fallback = Path.cwd() / "audioanalyse"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _get_output_paths(self, kapitel_name: str) -> dict[str, Path]:
        return self.service.standard_output_paths(
            kapitel_name=kapitel_name,
            audioanalyse_ordner=self._get_audioanalyse_dir(),
        )

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