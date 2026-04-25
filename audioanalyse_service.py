from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional, Iterable, Any
import csv
import difflib
import json
import re
import unicodedata


# ------------------------------------------------------------
# Datamodelle
# ------------------------------------------------------------

@dataclass
class PauseInfo:
    start: float
    end: float
    duration: float


@dataclass
class DiffEntry:
    typ: str
    score: float
    ref_text: str
    spoken_text: str


@dataclass
class SegmentInfo:
    start: float
    end: float
    text: str
    word_count: int
    local_wpm: float


@dataclass
class AudioAnalyseResult:
    kapitel_name: str
    audio_path: str
    referenz_path: str
    sprache: str

    model_size: str
    pause_threshold: float
    diff_threshold: float

    audio_mtime: float
    audio_size: int
    referenz_mtime: float
    referenz_size: int

    audio_dauer_sekunden: float
    wortanzahl: int
    wpm: float

    pausen_anzahl: int
    laengste_pause: float

    pausen: list[PauseInfo]
    diff_entries: list[DiffEntry]
    segmente: list[SegmentInfo]

    transcript_text: str


# ------------------------------------------------------------
# Service
# ------------------------------------------------------------

class AudioAnalyseService:
    """
    Reine Fachlogik für Kapitel-Audioanalyse.

    Aufgaben:
    - Referenztexte finden
    - Audiodateien finden
    - faster-whisper lazy laden
    - Audio transkribieren
    - Kennzahlen berechnen
    - grobe Textabweichungen ermitteln
    - Ergebnisse speichern / laden
    - Cache-Validierung
    """

    AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma")

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
        pause_threshold: float = 0.7,
        diff_threshold: float = 0.85,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.pause_threshold = pause_threshold
        self.diff_threshold = diff_threshold

        self._model = None

    # --------------------------------------------------------
    # Öffentliche API
    # --------------------------------------------------------

    def analysiere_kapitel(
        self,
        kapitel_name: str,
        audio_path: Path,
        referenz_path: Path,
        sprache: str = "de",
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> AudioAnalyseResult:
        """
        Führt die Analyse für genau ein Kapitel aus.
        """
        audio_path = Path(audio_path)
        referenz_path = Path(referenz_path)

        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio-Datei nicht gefunden: {audio_path}")
        if not referenz_path.is_file():
            raise FileNotFoundError(f"Referenztext nicht gefunden: {referenz_path}")

        self._report(progress_callback, "Referenztext laden", 5)
        referenz_text = self.lade_text(referenz_path)

        self._report(progress_callback, "Whisper-Modell initialisieren", 15)
        model = self._get_model()

        whisper_language = None if sprache == "auto" else sprache

        self._report(progress_callback, "Audio transkribieren", 30)
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=whisper_language,
            word_timestamps=False,
        )
        segments = list(segments_iter)

        self._report(progress_callback, "Transkript aufbereiten", 70)
        transcript_text = self.baue_transcript_text(segments)
        wortanzahl = self.zaehle_woerter(transcript_text)
        audio_dauer = float(getattr(info, "duration", 0.0) or 0.0)
        wpm = round((wortanzahl / audio_dauer * 60.0), 2) if audio_dauer > 0 else 0.0

        self._report(progress_callback, "Pausen analysieren", 80)
        pausen = self.extrahiere_pausen(segments, self.pause_threshold)

        self._report(progress_callback, "Segmente auswerten", 88)
        segmente = self.baue_segment_infos(segments)

        self._report(progress_callback, "Textabweichungen vergleichen", 94)
        diffs = self.simple_diff(
            referenz_text,
            transcript_text,
            threshold=self.diff_threshold,
        )

        audio_mtime, audio_size = self._datei_signatur(audio_path)
        referenz_mtime, referenz_size = self._datei_signatur(referenz_path)

        result = AudioAnalyseResult(
            kapitel_name=kapitel_name,
            audio_path=str(audio_path),
            referenz_path=str(referenz_path),
            sprache=sprache,

            model_size=self.model_size,
            pause_threshold=self.pause_threshold,
            diff_threshold=self.diff_threshold,

            audio_mtime=audio_mtime,
            audio_size=audio_size,
            referenz_mtime=referenz_mtime,
            referenz_size=referenz_size,

            audio_dauer_sekunden=round(audio_dauer, 2),
            wortanzahl=wortanzahl,
            wpm=wpm,

            pausen_anzahl=len(pausen),
            laengste_pause=round(max((p.duration for p in pausen), default=0.0), 2),

            pausen=pausen,
            diff_entries=diffs,
            segmente=segmente,

            transcript_text=transcript_text,
        )

        self._report(progress_callback, "Fertig", 100)
        return result

    def finde_referenztext(self, kapitel_name: str, txt_ordner: Path) -> Optional[Path]:
        """
        Sucht eine passende Referenz-TXT für ein Kapitel.
        """
        txt_ordner = Path(txt_ordner)
        if not txt_ordner.exists():
            return None

        key = self.normalisiere_dateinamen(kapitel_name)
        kandidaten = sorted(txt_ordner.glob("*.txt"))
        return self._finde_besten_dateitreffer(key, kandidaten)

    def finde_audiodatei(self, kapitel_name: str, audio_ordner: Path) -> Optional[Path]:
        """
        Sucht eine passende Audiodatei für ein Kapitel.
        """
        audio_ordner = Path(audio_ordner)
        if not audio_ordner.exists():
            return None

        key = self.normalisiere_dateinamen(kapitel_name)
        kandidaten = [
            p for p in sorted(audio_ordner.iterdir())
            if p.is_file() and p.suffix.lower() in self.AUDIO_EXTENSIONS
        ]
        return self._finde_besten_dateitreffer(key, kandidaten)

    def speichere_json(self, result: AudioAnalyseResult, ziel_datei: Path) -> None:
        ziel_datei = Path(ziel_datei)
        ziel_datei.parent.mkdir(parents=True, exist_ok=True)
        ziel_datei.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def lade_json_result(self, datei: Path) -> AudioAnalyseResult:
        data = json.loads(Path(datei).read_text(encoding="utf-8"))

        return AudioAnalyseResult(
            kapitel_name=data["kapitel_name"],
            audio_path=data["audio_path"],
            referenz_path=data["referenz_path"],
            sprache=data["sprache"],

            model_size=data.get("model_size", ""),
            pause_threshold=data.get("pause_threshold", self.pause_threshold),
            diff_threshold=data.get("diff_threshold", self.diff_threshold),

            audio_mtime=data.get("audio_mtime", 0.0),
            audio_size=data.get("audio_size", 0),
            referenz_mtime=data.get("referenz_mtime", 0.0),
            referenz_size=data.get("referenz_size", 0),

            audio_dauer_sekunden=data["audio_dauer_sekunden"],
            wortanzahl=data["wortanzahl"],
            wpm=data["wpm"],

            pausen_anzahl=data["pausen_anzahl"],
            laengste_pause=data["laengste_pause"],

            pausen=[PauseInfo(**x) for x in data.get("pausen", [])],
            diff_entries=[DiffEntry(**x) for x in data.get("diff_entries", [])],
            segmente=[SegmentInfo(**x) for x in data.get("segmente", [])],

            transcript_text=data.get("transcript_text", ""),
        )

    def ist_cache_gueltig(
        self,
        result: AudioAnalyseResult,
        audio_path: Path,
        referenz_path: Path,
        sprache: str,
    ) -> bool:
        audio_path = Path(audio_path)
        referenz_path = Path(referenz_path)

        if not audio_path.is_file() or not referenz_path.is_file():
            return False

        audio_mtime, audio_size = self._datei_signatur(audio_path)
        ref_mtime, ref_size = self._datei_signatur(referenz_path)

        return (
            Path(result.audio_path) == audio_path
            and Path(result.referenz_path) == referenz_path
            and result.sprache == sprache
            and result.model_size == self.model_size
            and float(result.pause_threshold) == float(self.pause_threshold)
            and float(result.diff_threshold) == float(self.diff_threshold)
            and float(result.audio_mtime) == float(audio_mtime)
            and int(result.audio_size) == int(audio_size)
            and float(result.referenz_mtime) == float(ref_mtime)
            and int(result.referenz_size) == int(ref_size)
        )

    def speichere_diff_csv(self, result: AudioAnalyseResult, ziel_datei: Path) -> None:
        ziel_datei = Path(ziel_datei)
        ziel_datei.parent.mkdir(parents=True, exist_ok=True)

        with open(ziel_datei, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["typ", "score", "referenz", "gesprochen"])
            for entry in result.diff_entries:
                writer.writerow([
                    entry.typ,
                    f"{entry.score:.4f}",
                    entry.ref_text,
                    entry.spoken_text,
                ])

    def speichere_pausen_csv(self, result: AudioAnalyseResult, ziel_datei: Path) -> None:
        ziel_datei = Path(ziel_datei)
        ziel_datei.parent.mkdir(parents=True, exist_ok=True)

        with open(ziel_datei, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["start", "end", "duration"])
            for p in result.pausen:
                writer.writerow([
                    f"{p.start:.3f}",
                    f"{p.end:.3f}",
                    f"{p.duration:.3f}",
                ])

    def speichere_segmente_csv(self, result: AudioAnalyseResult, ziel_datei: Path) -> None:
        ziel_datei = Path(ziel_datei)
        ziel_datei.parent.mkdir(parents=True, exist_ok=True)

        with open(ziel_datei, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["start", "end", "word_count", "local_wpm", "text"])
            for s in result.segmente:
                writer.writerow([
                    f"{s.start:.3f}",
                    f"{s.end:.3f}",
                    s.word_count,
                    f"{s.local_wpm:.2f}",
                    s.text,
                ])

    # --------------------------------------------------------
    # Hilfsfunktionen: Dateien / Kapitel
    # --------------------------------------------------------

    @staticmethod
    def lade_text(datei: Path) -> str:
        return Path(datei).read_text(encoding="utf-8").strip()

    @staticmethod
    def normalisiere_dateinamen(text: str) -> str:
        """
        Macht aus Kapitel-/Dateinamen einen stabilen Vergleichsschlüssel.
        """
        text = text.strip().lower()

        # Deutsche Sonderfälle zuerst
        text = (
            text.replace("ä", "ae")
                .replace("ö", "oe")
                .replace("ü", "ue")
                .replace("ß", "ss")
        )

        # Unicode normalisieren und Akzente entfernen
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))

        # typische Trenner vereinheitlichen
        text = text.replace("–", "_").replace("—", "_").replace("-", "_")

        # alles außer a-z0-9 und _/Leerzeichen raus
        text = re.sub(r"[^a-z0-9_ ]+", "", text)
        text = re.sub(r"\s+", "_", text)
        text = re.sub(r"_+", "_", text)

        return text.strip("_")

    def make_output_key(self, kapitel_name: str) -> str:
        return self.normalisiere_dateinamen(kapitel_name)

    def standard_output_paths(self, kapitel_name: str, audioanalyse_ordner: Path) -> dict[str, Path]:
        """
        Liefert Standard-Ausgabepfade für ein Kapitel.
        """
        audioanalyse_ordner = Path(audioanalyse_ordner)
        key = self.make_output_key(kapitel_name)

        return {
            "json": audioanalyse_ordner / f"{key}_analyse.json",
            "diff_csv": audioanalyse_ordner / f"{key}_problemstellen.csv",
            "pausen_csv": audioanalyse_ordner / f"{key}_pausen.csv",
            "segmente_csv": audioanalyse_ordner / f"{key}_segmente.csv",
        }

    # --------------------------------------------------------
    # Hilfsfunktionen: Analyse
    # --------------------------------------------------------

    @staticmethod
    def zaehle_woerter(text: str) -> int:
        return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))

    @staticmethod
    def baue_transcript_text(segments: Iterable[Any]) -> str:
        teile: list[str] = []
        for seg in segments:
            text = getattr(seg, "text", "") or ""
            text = text.strip()
            if text:
                teile.append(text)
        return " ".join(teile).strip()

    def extrahiere_pausen(
        self,
        segments: Iterable[Any],
        pause_threshold: Optional[float] = None,
    ) -> list[PauseInfo]:
        threshold = self.pause_threshold if pause_threshold is None else pause_threshold

        pausen: list[PauseInfo] = []
        prev_end: Optional[float] = None

        for seg in segments:
            start = float(getattr(seg, "start", 0.0) or 0.0)
            end = float(getattr(seg, "end", 0.0) or 0.0)

            if prev_end is not None:
                delta = start - prev_end
                if delta >= threshold:
                    pausen.append(
                        PauseInfo(
                            start=round(prev_end, 3),
                            end=round(start, 3),
                            duration=round(delta, 3),
                        )
                    )
            prev_end = end

        return pausen

    def baue_segment_infos(self, segments: Iterable[Any]) -> list[SegmentInfo]:
        infos: list[SegmentInfo] = []

        for seg in segments:
            start = float(getattr(seg, "start", 0.0) or 0.0)
            end = float(getattr(seg, "end", 0.0) or 0.0)
            text = (getattr(seg, "text", "") or "").strip()

            dauer = max(end - start, 0.0)
            word_count = self.zaehle_woerter(text)
            local_wpm = round((word_count / dauer * 60.0), 2) if dauer > 0 else 0.0

            infos.append(
                SegmentInfo(
                    start=round(start, 3),
                    end=round(end, 3),
                    text=text,
                    word_count=word_count,
                    local_wpm=local_wpm,
                )
            )

        return infos

    def simple_diff(
        self,
        referenz_text: str,
        transcript_text: str,
        threshold: float = 0.85,
        max_entries: int = 50,
    ) -> list[DiffEntry]:
        """
        Robusteres MVP-Alignment auf Satzebene:
        - Satzlisten via SequenceMatcher vergleichen
        - replace / insert / delete Blöcke melden
        - bei equal-Blöcken zusätzlich Near-Matches prüfen
        """
        ref_saetze = self._split_saetze(referenz_text)
        hyp_saetze = self._split_saetze(transcript_text)

        diffs: list[DiffEntry] = []
        sm = difflib.SequenceMatcher(None, ref_saetze, hyp_saetze)

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if len(diffs) >= max_entries:
                break

            if tag == "equal":
                for ref, hyp in zip(ref_saetze[i1:i2], hyp_saetze[j1:j2]):
                    score = difflib.SequenceMatcher(None, ref, hyp).ratio()
                    if score < threshold:
                        diffs.append(
                            DiffEntry(
                                typ="abweichung",
                                score=round(score, 4),
                                ref_text=ref[:500],
                                spoken_text=hyp[:500],
                            )
                        )
                        if len(diffs) >= max_entries:
                            break
                continue

            ref_block = " ".join(ref_saetze[i1:i2]).strip()[:500]
            hyp_block = " ".join(hyp_saetze[j1:j2]).strip()[:500]

            diffs.append(
                DiffEntry(
                    typ=tag,  # replace / delete / insert
                    score=0.0,
                    ref_text=ref_block,
                    spoken_text=hyp_block,
                )
            )

        if len(diffs) < max_entries and len(ref_saetze) != len(hyp_saetze):
            diffs.append(
                DiffEntry(
                    typ="satzanzahl_unterschiedlich",
                    score=0.0,
                    ref_text=f"{len(ref_saetze)} Referenz-Sätze",
                    spoken_text=f"{len(hyp_saetze)} gesprochene Sätze",
                )
            )

        return diffs[:max_entries]

    # --------------------------------------------------------
    # Private Helfer
    # --------------------------------------------------------

    def _get_model(self):
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ImportError(
                "faster-whisper ist nicht installiert. "
                "Installiere es z. B. mit: pip install faster-whisper"
            ) from e

        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        return self._model

    @staticmethod
    def _split_saetze(text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

        saetze = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in saetze if s.strip()]

    @staticmethod
    def _report(
        progress_callback: Optional[Callable[[str, float], None]],
        status: str,
        value: float,
    ) -> None:
        if progress_callback:
            progress_callback(status, value)

    @staticmethod
    def _datei_signatur(datei: Path) -> tuple[float, int]:
        stat = Path(datei).stat()
        return stat.st_mtime, stat.st_size

    @staticmethod
    def _extrahiere_kapitelnummer(text: str) -> Optional[int]:
        m = re.search(r"(?:kapitel_?)?0*([0-9]{1,4})", text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
        return None

    def _finde_besten_dateitreffer(self, key: str, kandidaten: list[Path]) -> Optional[Path]:
        if not kandidaten:
            return None

        best_path: Optional[Path] = None
        best_score = -1.0

        key_num = self._extrahiere_kapitelnummer(key)
        key_tokens = {t for t in key.split("_") if t}

        for p in kandidaten:
            stem_key = self.normalisiere_dateinamen(p.stem)
            stem_num = self._extrahiere_kapitelnummer(stem_key)
            stem_tokens = {t for t in stem_key.split("_") if t}

            score = difflib.SequenceMatcher(None, key, stem_key).ratio()

            # Nummernbonus
            if key_num is not None and stem_num is not None and key_num == stem_num:
                score += 0.25

            # Token-Overlap
            if key_tokens and stem_tokens:
                overlap = len(key_tokens & stem_tokens) / max(len(key_tokens), 1)
                score += overlap * 0.25

            # Teiltrefferbonus
            if key in stem_key or stem_key in key:
                score += 0.15

            if score > best_score:
                best_score = score
                best_path = p

        return best_path if best_score >= 0.55 else None