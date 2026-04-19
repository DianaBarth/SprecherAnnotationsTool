import os
import re
import gc
from pathlib import Path
import unicodedata
import Eingabe.config as config  # Importiere das komplette config-Modul

MODEL_NAME = ""  # Wird später durch GUI gesetzt/überschrieben

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
        result_file_name = f"{aufgaben_name}_{os.path.basename(dateipfad)}"
        result_file_path = os.path.join(ki_ordner, result_file_name)

        if os.path.exists(result_file_path) and not force:
            print(f"[INFO] Ergebnisdatei {result_file_path} existiert bereits. KI-Analyse wird übersprungen.")
        else:
            with open(dateipfad, 'r', encoding='utf-8') as f:
                eingabetext = f.read()

            messages_Chat = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": eingabetext}
            ]
            messages_Flat = f"Anweisung:\n{prompt}\n{eingabetext}"

            # Daten an Modell übergeben
            if client.check_chat_model():
                ki_ergebnis = KI_Analyse_Chat(
                    client, messages_Chat,
                    dateiname=os.path.basename(dateipfad),
                    wortnr_bereich=""
                )
            else:
                ki_ergebnis = KI_Analyse_Flat(
                    client, messages_Flat,
                    dateiname=os.path.basename(dateipfad),
                    wortnr_bereich=""
                )

            if ki_ergebnis:
                print("KI Roh-Ausgabe:\n", ki_ergebnis)
                antwort_log_datei = os.path.join(ki_ordner, f"{aufgaben_name}_KIAntwort.txt")
                with open(antwort_log_datei, 'a', encoding='utf-8') as f:
                    f.write(ki_ergebnis + "\n\n")  # mit Abstand anhängen

                with open(result_file_path, 'w', encoding='utf-8') as result_file:
                    result_file.write(ki_ergebnis)

                print(f"[INFO] Ergebnis gespeichert unter: {result_file_path}")

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


def extrahiere_ig_woerter_aus_json(
    json_ordner,
    ausgabe_datei,
    lowercase=True,
    sort_case_insensitive=True,
    min_len=1,
    verwende_tokenInklZahlwoerter=True,
    ignoriere_spezialtokens=True,
):
    """
    Extrahiert eindeutige IG-Wörter aus *_annotierungen.json-Dateien,
    entfernt Duplikate und speichert alphabetisch sortiert als TXT.

    Parameter:
    ----------
    json_ordner : str | Path
        Ordner mit JSON-Dateien
    ausgabe_datei : str | Path
        Zieldatei für Wortliste
    lowercase : bool
        Alles klein schreiben
    sort_case_insensitive : bool
        Alphabetisch ohne Groß-/Kleinschreibung sortieren
    min_len : int
        Minimale Tokenlänge
    verwende_tokenInklZahlwoerter : bool
        Bevorzugt tokenInklZahlwoerter statt token
    ignoriere_spezialtokens : bool
        Ignoriert Dinge wie |BREAK| oder Tag-Tokens
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

    print(f"[INFO] Starte IG-Extraktion aus {len(json_dateien)} JSON-Dateien ...")

    einzigartige_tokens = set()

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

                if not token:
                    continue

                if len(token) < min_len:
                    continue

                if ignoriere_spezialtokens:
                    # Tags wie |BREAK|, |ZentriertStart| etc.
                    if token.startswith("|") and token.endswith("|"):
                        continue

                    # leere / technische Marker
                    if token in {"", "_", "__"}:
                        continue

                einzigartige_tokens.add(token)

        except Exception as e:
            print(f"[FEHLER] Fehler beim Lesen von {datei.name}: {e}")

    if sort_case_insensitive:
        sortierte_tokens = sorted(einzigartige_tokens, key=lambda x: x.lower())
    else:
        sortierte_tokens = sorted(einzigartige_tokens)

    ausgabe_datei.parent.mkdir(parents=True, exist_ok=True)

    with open(ausgabe_datei, "w", encoding="utf-8") as f:
        for token in sortierte_tokens:
            f.write(token + "\n")

    print(f"[INFO] IG-Wörter extrahiert: {len(sortierte_tokens)}")
    print(f"[✓] IG-Wortliste gespeichert: {ausgabe_datei}")


if __name__ == "__main__":
    extrahiere_ig_woerter_aus_json(
        json_ordner=config.GLOBALORDNER["json"],
        ausgabe_datei=Path(config.GLOBALORDNER["ki"]) / "ig_woerter.txt",
        lowercase=True,
        sort_case_insensitive=True,
        min_len=2,
        verwende_tokenInklZahlwoerter=True,
        ignoriere_spezialtokens=True,
    )