from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional, Iterable, Any
import csv
import difflib
import json
import re
import unicodedata


from text_builder import baue_text_aus_tokens

@dataclass
class PauseInfo:
    start: float
    end: float
    duration: float
    kategorie: str = ""
    text_davor: str = ""
    text_danach: str = ""

@dataclass
class DiffEntry:
    typ: str
    score: float
    ref_text: str
    spoken_text: str
    ref_diff: str = ""
    spoken_diff: str = ""
    summary: str = ""


@dataclass
class SegmentInfo:
    start: float
    end: float
    text: str
    word_count: int
    local_wpm: float

    ref_text: str = ""
    ref_marked: str = ""
    spoken_marked: str = ""
    diff_summary: str = ""
    status: str = "OK"
    match_score: float = 0.0
    ref_satz_nr: int = 0


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


class AudioAnalyseService:
    AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma")

    def __init__(
        self,
        model_size: str = "small",
         device: str = "auto",
        compute_type: str = "auto",
        pause_threshold: float = 0.7,
        diff_threshold: float = 0.85,
        use_number_words: bool = False,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.pause_threshold = pause_threshold
        self.diff_threshold = diff_threshold
        self.use_number_words = use_number_words
        self._model = None
   

    def lade_json_tokens(self, json_path: Path) -> list[dict]:
        with open(json_path, "r", encoding="utf-8") as f:
            daten = json.load(f)

        if not isinstance(daten, list):
            raise ValueError(f"JSON enthält keine Liste: {json_path}")

        return daten


    @staticmethod
    def klassifiziere_pause(duration: float) -> str:
        if duration < 0.5:
            return "kurz"
        elif duration < 1.0:
            return "normal"
        elif duration < 1.8:
            return "lang"
        elif duration < 2.5:
            return "sehr_lang"
        return "problematisch"

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
        audio_path = Path(audio_path)
        referenz_path = Path(referenz_path)

        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio-Datei nicht gefunden: {audio_path}")
        if not referenz_path.is_file():
            raise FileNotFoundError(f"Referenzdatei nicht gefunden: {referenz_path}")

        self._report(progress_callback, "Referenz laden", 5)
        json_daten = self.lade_json_tokens(referenz_path)

        referenz_text = baue_text_aus_tokens(
            json_daten,
            use_number_words=False
        )

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
        pausen = self.extrahiere_pausen(segments, self.pause_threshold, segments)

        self._report(progress_callback, "Segmente mit Originaltext vergleichen", 88)
        segmente = self.baue_segment_infos_mit_referenz(segments, referenz_text)

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

    def finde_referenztext(self, kapitel_name: str, ref_ordner: Path) -> Optional[Path]:
        ref_ordner = Path(ref_ordner)
        if not ref_ordner.exists():
            return None

        key = self.normalisiere_dateinamen(kapitel_name)

        kandidaten = sorted(ref_ordner.glob("*.json"))
        if not kandidaten:
            kandidaten = sorted(ref_ordner.glob("*.txt"))

        return self._finde_besten_dateitreffer(key, kandidaten)

    def finde_audiodatei(self, kapitel_name: str, audio_ordner: Path) -> Optional[Path]:
        audio_ordner = Path(audio_ordner)
        if not audio_ordner.exists():
            return None

        key = self.normalisiere_dateinamen(kapitel_name)
        kandidaten = [
            p for p in sorted(audio_ordner.iterdir())
            if p.is_file() and p.suffix.lower() in self.AUDIO_EXTENSIONS
        ]

        # exakter Treffer bevorzugt (neu!)
        for p in kandidaten:
            if p.stem == key:
                return p
    
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

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    def speichere_diff_csv(self, result: AudioAnalyseResult, ziel_datei: Path) -> None:
        ziel_datei = Path(ziel_datei)
        ziel_datei.parent.mkdir(parents=True, exist_ok=True)

        with open(ziel_datei, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                "typ",
                "score",
                "referenz",
                "gesprochen",
                "referenz_markiert",
                "gesprochen_markiert",
                "summary",
            ])
            for entry in result.diff_entries:
                writer.writerow([
                    entry.typ,
                    f"{entry.score:.4f}",
                    entry.ref_text,
                    entry.spoken_text,
                    entry.ref_diff,
                    entry.spoken_diff,
                    entry.summary,
                ])

    def speichere_pausen_csv(self, result: AudioAnalyseResult, ziel_datei: Path) -> None:
        ziel_datei = Path(ziel_datei)
        ziel_datei.parent.mkdir(parents=True, exist_ok=True)

        with open(ziel_datei, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["start", "end", "duration", "kategorie"])
            for p in result.pausen:
                writer.writerow([
                    f"{p.start:.3f}",
                    f"{p.end:.3f}",
                    f"{p.duration:.3f}",
                    p.kategorie,
                ])

    def speichere_segmente_csv(self, result: AudioAnalyseResult, ziel_datei: Path) -> None:
        ziel_datei = Path(ziel_datei)
        ziel_datei.parent.mkdir(parents=True, exist_ok=True)

        with open(ziel_datei, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                "start",
                "end",
                "word_count",
                "local_wpm",
                "status",
                "match_score",
                "ref_satz_nr",
                "original",
                "gesprochen",
                "differenz",
            ])
            for s in result.segmente:
                writer.writerow([
                    f"{s.start:.3f}",
                    f"{s.end:.3f}",
                    s.word_count,
                    f"{s.local_wpm:.2f}",
                    s.status,
                    f"{s.match_score:.4f}",
                    s.ref_satz_nr,
                    s.ref_text,
                    s.text,
                    s.diff_summary,
                ])

    # --------------------------------------------------------
    # Referenz aus TXT oder JSON
    # --------------------------------------------------------

    @staticmethod
    def lade_referenz(datei: Path, use_number_words: bool = True) -> str:
        datei = Path(datei)

        if datei.suffix.lower() == ".json":
            daten = json.loads(datei.read_text(encoding="utf-8"))
            return AudioAnalyseService.rekonstruiere_text_aus_json(
                daten,
                use_number_words=use_number_words,
            )

        return datei.read_text(encoding="utf-8").strip()

    @staticmethod
    def rekonstruiere_text_aus_json(daten: Any, use_number_words: bool = False) -> str:
        if isinstance(daten, dict):
            if isinstance(daten.get("tokens"), list):
                daten = daten["tokens"]
            elif isinstance(daten.get("daten"), list):
                daten = daten["daten"]
            else:
                daten = list(daten.values())

        tokens: list[str] = []

        for eintrag in daten:
            if not isinstance(eintrag, dict):
                continue

            token = (
                eintrag.get("tokenInklZahlwoerter")
                if use_number_words and eintrag.get("tokenInklZahlwoerter")
                else eintrag.get("token")
            )

            token = str(token or "").strip()

            if not token:
                continue

            if token.startswith("|") and token.endswith("|"):
                continue

            tokens.append(token)

        return AudioAnalyseService.tokens_zu_text_mit_annotationen(tokens)

    @staticmethod
    def tokens_zu_text_mit_annotationen(eintraege: list[dict]) -> str:
        text = ""

        for i, eintrag in enumerate(eintraege):
            token = str(eintrag.get("token", "")).strip()
            if not token:
                continue

            annotation = eintrag.get("annotation", "")

            # Normalisieren (egal ob dict / list / string)
            if isinstance(annotation, dict):
                annot_set = {str(k).lower() for k in annotation.keys()}
            elif isinstance(annotation, list):
                annot_set = {str(a).lower() for a in annotation}
            else:
                annot_set = {str(annotation).lower()}

            if not text:
                text = token
                continue

            if "satzzeichenohnespacedavor" in annot_set:
                text += token

            elif "satzzeichenohnespacedanach" in annot_set:
                text += " " + token  # kein Space danach → davor normal

            elif "satzzeichenmitspace" in annot_set:
                text += " " + token

            else:
                text += " " + token

        return text.strip()
    # --------------------------------------------------------
    # Analyse-Helfer
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
    segments_list: Optional[list] = None,
) -> list[PauseInfo]:
        segments_list = list(segments_list or segments)
        threshold = self.pause_threshold if pause_threshold is None else pause_threshold

        pausen: list[PauseInfo] = []

        for i in range(len(segments_list) - 1):
            current_seg = segments_list[i]
            next_seg = segments_list[i + 1]

            end = float(getattr(current_seg, "end", 0.0) or 0.0)
            start = float(getattr(next_seg, "start", 0.0) or 0.0)

            delta = start - end

            if delta >= threshold:
                text_davor = (getattr(current_seg, "text", "") or "").strip()
                text_danach = (getattr(next_seg, "text", "") or "").strip()

                pausen.append(
                    PauseInfo(
                        start=round(end, 3),
                        end=round(start, 3),
                        duration=round(delta, 3),
                        kategorie=self.klassifiziere_pause(delta),
                        text_davor=text_davor[:200],
                        text_danach=text_danach[:200],
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

    def baue_segment_infos_mit_referenz(
        self,
        segments: Iterable[Any],
        referenz_text: str,
    ) -> list[SegmentInfo]:
        infos: list[SegmentInfo] = []

        ref_saetze = self._split_saetze(referenz_text)
        ref_pool = [
            {
                "satz_nr": idx + 1,
                "text": satz,
                "norm": self._normalisiere_fuer_vergleich(satz),
                "used": False,
            }
            for idx, satz in enumerate(ref_saetze)
        ]

        for seg in segments:
            start = float(getattr(seg, "start", 0.0) or 0.0)
            end = float(getattr(seg, "end", 0.0) or 0.0)
            hyp_text = (getattr(seg, "text", "") or "").strip()

            ref_match = self._finde_besten_referenzsatz(
                hyp_text=hyp_text,
                ref_pool=ref_pool,
            )

            if ref_match:
                ref_match["used"] = True
                ref_text = ref_match["text"]
                ref_satz_nr = int(ref_match["satz_nr"])
                match_score = float(ref_match["score"])
            else:
                ref_text = ""
                ref_satz_nr = 0
                match_score = 0.0

            ref_marked, hyp_marked, summary = self.markiere_wort_diffs(ref_text, hyp_text)

            dauer = max(end - start, 0.0)
            word_count = self.zaehle_woerter(hyp_text)
            local_wpm = round((word_count / dauer * 60.0), 2) if dauer > 0 else 0.0

            status = "OK" if match_score >= self.diff_threshold and not summary else "Abweichung"
            if match_score >= 0.96 and not summary:
                status = "OK"

            infos.append(
                SegmentInfo(
                    start=round(start, 3),
                    end=round(end, 3),
                    text=hyp_text,
                    word_count=word_count,
                    local_wpm=local_wpm,
                    ref_text=ref_text,
                    ref_marked=ref_marked,
                    spoken_marked=hyp_marked,
                    diff_summary=summary,
                    status=status,
                    match_score=round(match_score, 4),
                    ref_satz_nr=ref_satz_nr,
                )
            )

        return infos

    def _finde_besten_referenzsatz(
        self,
        hyp_text: str,
        ref_pool: list[dict[str, Any]],
        window_unused_bonus: float = 0.03,
    ) -> Optional[dict[str, Any]]:
        hyp_norm = self._normalisiere_fuer_vergleich(hyp_text)

        if not hyp_norm:
            return None

        best: Optional[dict[str, Any]] = None
        best_score = -1.0

        for ref in ref_pool:
            ref_norm = ref["norm"]

            if not ref_norm:
                continue

            score = difflib.SequenceMatcher(None, ref_norm, hyp_norm).ratio()

            # Noch nicht verwendete Referenzsätze leicht bevorzugen.
            if not ref.get("used"):
                score += window_unused_bonus

            # Grober Längenabgleich verhindert sehr absurde Matches.
            ref_wc = self.zaehle_woerter(ref["text"])
            hyp_wc = self.zaehle_woerter(hyp_text)
            if ref_wc and hyp_wc:
                ratio = min(ref_wc, hyp_wc) / max(ref_wc, hyp_wc)
                score += ratio * 0.08

            if score > best_score:
                best_score = score
                best = ref

        if best is None:
            return None

        result = dict(best)
        result["score"] = max(0.0, min(1.0, best_score))
        return result

    # --------------------------------------------------------
    # Diff-Logik
    # --------------------------------------------------------

    def simple_diff(
        self,
        referenz_text: str,
        transcript_text: str,
        threshold: float = 0.85,
        max_entries: int = 50,
    ) -> list[DiffEntry]:
        ref_saetze = self._split_saetze(referenz_text)
        hyp_saetze = self._split_saetze(transcript_text)

        ref_pool = [
            {
                "satz_nr": idx + 1,
                "text": satz,
                "norm": self._normalisiere_fuer_vergleich(satz),
                "used": False,
            }
            for idx, satz in enumerate(ref_saetze)
        ]

        diffs: list[DiffEntry] = []

        for hyp in hyp_saetze:
            match = self._finde_besten_referenzsatz(hyp, ref_pool)

            if not match:
                diffs.append(
                    DiffEntry(
                        typ="kein_match",
                        score=0.0,
                        ref_text="",
                        spoken_text=hyp,
                        summary=f"zusätzlich/unklar: '{hyp[:200]}'",
                    )
                )
                continue

            for ref in ref_pool:
                if ref["satz_nr"] == match["satz_nr"]:
                    ref["used"] = True
                    break

            ref_text = match["text"]
            score = float(match["score"])

            ref_marked, hyp_marked, summary = self.markiere_wort_diffs(ref_text, hyp)

            if score < threshold or summary:
                diffs.append(
                    DiffEntry(
                        typ="abweichung",
                        score=round(score, 4),
                        ref_text=ref_text,
                        spoken_text=hyp,
                        ref_diff=ref_marked,
                        spoken_diff=hyp_marked,
                        summary=summary,
                    )
                )

            if len(diffs) >= max_entries:
                break

        if len(diffs) < max_entries:
            for ref in ref_pool:
                if not ref.get("used"):
                    diffs.append(
                        DiffEntry(
                            typ="fehlt",
                            score=0.0,
                            ref_text=ref["text"],
                            spoken_text="",
                            ref_diff=f"**{ref['text']}**",
                            spoken_diff="",
                            summary=f"fehlt: '{ref['text'][:200]}'",
                        )
                    )
                    if len(diffs) >= max_entries:
                        break

        return diffs[:max_entries]

    @staticmethod
    def _wort_liste(text: str) -> list[str]:
        return re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)

    @staticmethod
    def _normalisiere_wort(w: str) -> str:
        w = w.casefold()
        w = re.sub(r"[^\wäöüß]+", "", w, flags=re.UNICODE)
        return w

    @staticmethod
    def _normalisiere_fuer_vergleich(text: str) -> str:
        text = text.casefold()
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("„", '"').replace("“", '"').replace("”", '"')
        text = text.replace("‚", "'").replace("‘", "'").replace("’", "'")
        text = re.sub(r"[^\wäöüß ]+", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    
    @staticmethod
    def tokens_zu_text(tokens: list[str]) -> str:
        text = ""

        ohne_space_davor = {
            ".", ",", ":", ";", "!", "?", "…",
            ")", "]", "}", "”", "“", "’", "»",
        }
        ohne_space_danach = {"(", "[", "{", "„", "‚", "«"}

        for token in tokens:
            token = str(token or "").strip()
            if not token:
                continue

            if not text:
                text = token
            elif token in ohne_space_davor:
                text += token
            elif text[-1] in ohne_space_danach:
                text += token
            else:
                text += " " + token

        return text.strip()

    def markiere_wort_diffs(self, ref: str, hyp: str) -> tuple[str, str, str]:
        ref_tokens = self._wort_liste(ref)
        hyp_tokens = self._wort_liste(hyp)

        ref_norm = [self._normalisiere_wort(t) for t in ref_tokens]
        hyp_norm = [self._normalisiere_wort(t) for t in hyp_tokens]

        sm = difflib.SequenceMatcher(None, ref_norm, hyp_norm)

        ref_out: list[str] = []
        hyp_out: list[str] = []
        summary: list[str] = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            ref_part = ref_tokens[i1:i2]
            hyp_part = hyp_tokens[j1:j2]

            if tag == "equal":
                ref_out.extend(ref_part)
                hyp_out.extend(hyp_part)
                continue

            ref_text = self.tokens_zu_text(ref_part)
            hyp_text = self.tokens_zu_text(hyp_part)

            if ref_part:
                ref_out.append(f"**{ref_text}**")
            if hyp_part:
                hyp_out.append(f"**{hyp_text}**")

            if tag == "replace":
                summary.append(f"anders: '{ref_text}' → '{hyp_text}'")
            elif tag == "delete":
                summary.append(f"fehlt: '{ref_text}'")
            elif tag == "insert":
                summary.append(f"zusätzlich: '{hyp_text}'")

        return (
            self.tokens_zu_text(ref_out),
            self.tokens_zu_text(hyp_out),
            "; ".join(summary),
        )

    # --------------------------------------------------------
    # Dateien / Kapitel
    # --------------------------------------------------------

    @staticmethod
    def normalisiere_dateinamen(text: str) -> str:
        text = text.strip().lower()

        text = (
            text.replace("ä", "ae")
                .replace("ö", "oe")
                .replace("ü", "ue")
                .replace("ß", "ss")
        )

        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))

        text = text.replace("–", "_").replace("—", "_").replace("-", "_")
        text = re.sub(r"[^a-z0-9_ ]+", "", text)
        text = re.sub(r"\s+", "_", text)
        text = re.sub(r"_+", "_", text)

        return text.strip("_")

    def make_output_key(self, kapitel_name: str) -> str:
        return self.normalisiere_dateinamen(kapitel_name)

    def standard_output_paths(self, kapitel_name: str, audioanalyse_ordner: Path) -> dict[str, Path]:
        audioanalyse_ordner = Path(audioanalyse_ordner)
        key = self.make_output_key(kapitel_name)

        return {
            "json": audioanalyse_ordner / f"{key}_analyse.json",
            "diff_csv": audioanalyse_ordner / f"{key}_problemstellen.csv",
            "pausen_csv": audioanalyse_ordner / f"{key}_pausen.csv",
            "segmente_csv": audioanalyse_ordner / f"{key}_segmente.csv",
        }

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

        saetze = re.split(r"(?<=[.!?…])\s+", text)
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

            if key_num is not None and stem_num is not None and key_num == stem_num:
                score += 0.25

            if key_tokens and stem_tokens:
                overlap = len(key_tokens & stem_tokens) / max(len(key_tokens), 1)
                score += overlap * 0.25

            if key in stem_key or stem_key in key:
                score += 0.15

            if score > best_score:
                best_score = score
                best_path = p

        return best_path if best_score >= 0.55 else None