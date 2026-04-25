import os
import re
import gc
import json
import regex
from collections import Counter
from pathlib import Path
import unicodedata
import Eingabe.config as config  # Importiere das komplette config-Modul

MODEL_NAME = ""  # Wird später durch GUI gesetzt/überschrieben
IG_ANALYSE_IN_DIESEM_LAUF_ERLEDIGT = False

def KI_Analyse_Chat(client, messages, dateiname="", wortnr_bereich=""):
    try:
        # Kombiniere Messages zu Prompt-String
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"<SYSTEM>\n{msg['content']}\n</SYSTEM>\n"
            elif msg["role"] == "user":
                prompt += f"<USER>\n{msg['content']}\n</USER>\n"

        print("[INFO] Anfrage an lokales Modell über HuggingFaceClient …")
        content = client.generate(prompt)

        print("[DEBUG] Prompt an Modell:")
        print(prompt)
        print("[DEBUG] KI-Ergebnis vom Modell:")
        print(content)

        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        if dateiname and wortnr_bereich:
            log_antwort(dateiname, wortnr_bereich, content)

        return content
    except Exception as e:
        print(f"[FEHLER] KI-Anfrage fehlgeschlagen: {e}")
        return None

def KI_Analyse_Flat(client, prompt_text, dateiname="", wortnr_bereich=""):
    try:
        print("[INFO] Anfrage an lokales Modell über HuggingFaceClient …")
        content = client.generate(prompt_text)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        if dateiname and wortnr_bereich:
            log_antwort(dateiname, wortnr_bereich, content)

        return content
    except Exception as e:
        print(f"[FEHLER] KI-Anfrage fehlgeschlagen: {e}")
        return None


def daten_verarbeiten(client, prompt, dateipfad, ki_ordner, aufgabe, force=False):
    print(f"[DEBUG] schritt4.daten_verarbeiten gestartet für {dateipfad} und {aufgabe}")
    ki_ordner = Path(ki_ordner)

 
    try:
        if not isinstance(dateipfad, str):
            raise ValueError(f"Unerwarteter Dateipfad: {dateipfad}")

        aufgaben_name = config.KI_AUFGABEN.get(aufgabe, f"unbekannt{aufgabe}")
        ist_ig_aufgabe = aufgaben_name.lower() == "ig"


        global IG_ANALYSE_IN_DIESEM_LAUF_ERLEDIGT

        if ist_ig_aufgabe and IG_ANALYSE_IN_DIESEM_LAUF_ERLEDIGT:
            print("[INFO] IG-Analyse wurde in diesem Lauf bereits ausgeführt – überspringe.")
            return
        
        if ist_ig_aufgabe:
            result_file_name = "ig_wortliste.txt"
        else:
            result_file_name = f"{aufgaben_name}_{os.path.basename(dateipfad)}"

        result_file_path = ki_ordner / result_file_name

        if result_file_path.exists() and not force:
            print(f"[INFO] Ergebnisdatei {result_file_path} existiert bereits. KI-Analyse wird übersprungen.")
            return

        if ist_ig_aufgabe:
            ig_woerter_datei = ki_ordner / "ig_woerter.txt"

            print("[INFO] Erzeuge IG-Wortliste aus JSON-Dateien ...")

            extrahiere_ig_woerter_aus_json(
                json_ordner=config.GLOBALORDNER["json"],
                ausgabe_datei=ig_woerter_datei,
                lowercase=True,
                sort_case_insensitive=True,
                min_len=2,
                verwende_tokenInklZahlwoerter=True,
            )

            if not ig_woerter_datei.exists():
                print(f"[FEHLER] IG-Wortliste wurde nicht erzeugt: {ig_woerter_datei}")
                return

            with open(ig_woerter_datei, "r", encoding="utf-8") as f:
                eingabetext = f.read()

            if not eingabetext.strip():
                print("[WARNUNG] IG-Wortliste ist leer. IG-Analyse wird übersprungen.")
                return

            print(f"[INFO] Verwende IG-Wortliste statt Kapiteltext: {ig_woerter_datei}")

        else:
            with open(dateipfad, "r", encoding="utf-8") as f:
                eingabetext = f.read()

        messages_Chat = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": eingabetext}
        ]

        messages_Flat = f"Anweisung:\n{prompt}\n{eingabetext}"

        if client.check_chat_model():
            ki_ergebnis = KI_Analyse_Chat(
                client,
                messages_Chat,
                dateiname=os.path.basename(dateipfad),
                wortnr_bereich=""
            )
        else:
            ki_ergebnis = KI_Analyse_Flat(
                client,
                messages_Flat,
                dateiname=os.path.basename(dateipfad),
                wortnr_bereich=""
            )

        if ki_ergebnis:
            print("KI Roh-Ausgabe:\n", ki_ergebnis)

            antwort_log_datei = ki_ordner / f"{aufgaben_name}_KIAntwort.txt"
            with open(antwort_log_datei, "a", encoding="utf-8") as f:
                f.write(ki_ergebnis + "\n\n")

            with open(result_file_path, "w", encoding="utf-8") as result_file:
                result_file.write(ki_ergebnis)

            print(f"[INFO] Ergebnis gespeichert unter: {result_file_path}")

            if ist_ig_aufgabe:
                splitte_ig_klassen(result_file_path, ki_ordner)
                IG_ANALYSE_IN_DIESEM_LAUF_ERLEDIGT = True

    except Exception as e:
        print(f"[FEHLER] Fehler bei der Verarbeitung von {dateipfad}: {e}")
    finally:
        gc.collect()

def log_antwort(dateiname, wortnr_bereich, content):
    log_datei = f"log_{dateiname}.txt"
    with open(log_datei, 'a', encoding='utf-8') as log_file:
        log_file.write(f"Bereich: {wortnr_bereich}, Antwort: {content}\n")

def normalisiere_ig_token(token, lowercase=True):
    """
    Vereinheitlicht Token für IG-Listen:
    - trimmt Leerzeichen
    - optional alles klein
    - Unicode normalisieren
    """
    token = (token or "").strip()
    token = unicodedata.normalize("NFC", token)

    if lowercase:
        token = token.lower()

    return token

def splitte_ig_klassen(eingabe_datei, ki_ordner):
    ik_set = set()
    kein_set = set()

    with open(eingabe_datei, "r", encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile:
                continue

            teile = zeile.split("\t")
            if len(teile) < 2:
                continue

            wort = teile[0].strip().lower()
            klasse = teile[1].strip().lower()

            if klasse == "ik":
                ik_set.add(wort)
            elif klasse == "kein":
                kein_set.add(wort)
            # "ich" wird bewusst ignoriert

    # speichern
    ik_datei = Path(ki_ordner) / "ik_aussprache.txt"
    kein_datei = Path(ki_ordner) / "kein_ig.txt"

    with open(ik_datei, "w", encoding="utf-8") as f:
        for w in sorted(ik_set):
            f.write(w + "\n")

    with open(kein_datei, "w", encoding="utf-8") as f:
        for w in sorted(kein_set):
            f.write(w + "\n")

    print(f"[INFO] ik-Wörter: {len(ik_set)} → {ik_datei}")
    print(f"[INFO] kein-ig-Wörter: {len(kein_set)} → {kein_datei}")


def ist_echtes_wort(token):
    """
    True nur für echte Wörter.
    Erlaubt Buchstaben inkl. Umlaute, Bindestrich und Apostroph.
    Keine Zahlen, keine Satzzeichen-only, keine Tags.
    """
    token = (token or "").strip()

    if not token:
        return False

    if token.startswith("|") and token.endswith("|"):
        return False

    # Mindestens ein Buchstabe
    if not regex.search(r"\p{L}", token):
        return False

    # Nur Buchstaben, kombinierende Zeichen, Bindestrich, Apostroph
    return regex.fullmatch(r"[\p{L}\p{M}'’\-]+", token) is not None


def extrahiere_ig_woerter_aus_json(
    json_ordner,
    ausgabe_datei,
    lowercase=True,
    sort_case_insensitive=True,
    min_len=1,
    verwende_tokenInklZahlwoerter=True,
):
    """
    Extrahiert alle tatsächlichen Wörter aus *_annotierungen.json-Dateien
    und speichert sie mit Häufigkeit.

    Ausgabeformat:
        wort<TAB>anzahl
    """
    json_ordner = Path(json_ordner)
    ausgabe_datei = Path(ausgabe_datei)

    if not json_ordner.exists():
        print(f"[FEHLER] JSON-Ordner existiert nicht: {json_ordner}")
        return

    json_dateien = sorted(json_ordner.glob("*_annotierungen.json"))

    if not json_dateien:
        print(f"[WARNUNG] Keine *_annotierungen.json-Dateien gefunden in: {json_ordner}")
        return

    print(f"[INFO] Starte Wortextraktion aus {len(json_dateien)} JSON-Dateien ...")

    zaehler = Counter()

    for datei in json_dateien:
        try:
            with open(datei, "r", encoding="utf-8") as f:
                daten = json.load(f)

            if not isinstance(daten, list):
                print(f"[WARNUNG] Datei hat kein Listenformat, überspringe: {datei.name}")
                continue

            for eintrag in daten:
                if not isinstance(eintrag, dict):
                    continue

                if verwende_tokenInklZahlwoerter:
                    token = eintrag.get("tokenInklZahlwoerter") or eintrag.get("token") or ""
                else:
                    token = eintrag.get("token") or ""

                token = normalisiere_ig_token(token, lowercase=lowercase)

                if len(token) < min_len:
                    continue

                if not ist_echtes_wort(token):
                    continue

                # Nur Wörter mit "ig"
                if "ig" not in token:
                    continue

                zaehler[token] += 1

        except Exception as e:
            print(f"[FEHLER] Fehler beim Lesen von {datei.name}: {e}")

    if sort_case_insensitive:
        sortierte_tokens = sorted(zaehler.items(), key=lambda x: x[0].lower())
    else:
        sortierte_tokens = sorted(zaehler.items())

    ausgabe_datei.parent.mkdir(parents=True, exist_ok=True)

    with open(ausgabe_datei, "w", encoding="utf-8") as f:
        for token, anzahl in sortierte_tokens:
            f.write(f"{token}\t{anzahl}\n")

    print(f"[INFO] Echte Wörter extrahiert: {len(sortierte_tokens)}")
    print(f"[INFO] Gesamtvorkommen: {sum(zaehler.values())}")
    print(f"[✓] Wortliste gespeichert: {ausgabe_datei}")

if __name__ == "__main__":
    extrahiere_ig_woerter_aus_json(
        json_ordner=config.GLOBALORDNER["json"],
        ausgabe_datei=Path(config.GLOBALORDNER["ki"]) / "ig_woerter.txt",
        lowercase=True,
        sort_case_insensitive=True,
        min_len=2,
        verwende_tokenInklZahlwoerter=True,
    )