import os
import re
import gc
import json
import traceback
import regex
from collections import Counter
from pathlib import Path
import unicodedata
import Eingabe.config as config
from KI_Analyse_Flat import baue_ki_prompt, lade_json_zu_txt_datei, splitte_in_abschnitte_nach_zeilenumbruch  
import personen_resolver

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
        ist_ig_aufgabe = str(aufgaben_name).lower() == "ig"
        
        ist_person_aufgabe = str(aufgaben_name).lower() == "person"

        if ist_person_aufgabe and "{SPRECHER_LISTE_HIER_EINFÜGEN}" in prompt:
            try:

                json_datei_fuer_personen = lade_json_zu_txt_datei(dateipfad)

                personen = personen_resolver.lade_personen_fuer_datei_ohne_kapitel_config(
                    dateipfad=str(json_datei_fuer_personen or dateipfad)
                )
                sprecher_liste_text = personen_resolver.formatiere_personen_fuer_prompt(personen)

                prompt = prompt.replace(
                    "{SPRECHER_LISTE_HIER_EINFÜGEN}",
                    sprecher_liste_text
                )

                print(f"[INFO] Sprecherliste injiziert: {sprecher_liste_text}")

            except Exception as e:
                print(f"[WARNUNG] Sprecherliste konnte nicht injiziert werden: {e}")
                prompt = prompt.replace(
                    "{SPRECHER_LISTE_HIER_EINFÜGEN}",
                    "Keine bekannten Sprecher"
                )
                # ----------------------------------------------------
        # Ergebnisdatei bestimmen
        # ----------------------------------------------------
        if ist_ig_aufgabe:
            result_file_name = "ig_wortliste.txt"
        else:
            result_file_name = f"{aufgaben_name}_{os.path.basename(dateipfad)}"

        result_file_path = ki_ordner / result_file_name

        # ----------------------------------------------------
        # IG: Wortliste IMMER zuerst erzeugen
        # ----------------------------------------------------
        if ist_ig_aufgabe:
            ig_woerter_datei = ki_ordner / "ig_woerter.txt"

            print("[INFO] Erzeuge IG-Wortliste aus JSON-Dateien ...")

            extrahiere_ig_woerter_aus_json(
                json_ordner=config.GLOBALORDNER["json"],
                ausgabe_datei=ig_woerter_datei,
                lowercase=True,             
                min_len=2,
                verwende_tokenInklZahlwoerter=True,
            )

            if not ig_woerter_datei.exists():
                print(f"[FEHLER] IG-Wortliste wurde nicht erzeugt: {ig_woerter_datei}")
                return

        # ----------------------------------------------------
        # Wenn Ergebnis schon existiert, überspringen
        # ----------------------------------------------------
        if result_file_path.exists() and not force:
            print(f"[INFO] Ergebnisdatei {result_file_path} existiert bereits. KI-Analyse wird übersprungen.")

            if ist_ig_aufgabe:
                splitte_ig_klassen(result_file_path, ki_ordner)

            return

        # ----------------------------------------------------
        # Eingabetext laden
        # ----------------------------------------------------
        if ist_ig_aufgabe:
            with open(ig_woerter_datei, "r", encoding="utf-8") as f:
                eingabetext = f.read()

            if not eingabetext.strip():
                print("[WARNUNG] IG-Wortliste ist leer. IG-Analyse wird übersprungen.")
                return

            print(f"[INFO] Verwende IG-Wortliste statt Kapiteltext: {ig_woerter_datei}")

            # ------------------------------------------------
            # IG: Chunkweise verarbeiten
            # ------------------------------------------------
            zeilen = [z for z in eingabetext.splitlines() if z.strip()]
            chunk_groesse = 100
            chunks = [zeilen[i:i + chunk_groesse] for i in range(0, len(zeilen), chunk_groesse)]

            print(f"[INFO] IG-Wortliste enthält {len(zeilen)} Zeilen.")
            print(f"[INFO] Verarbeite IG in {len(chunks)} Chunk(s) à maximal {chunk_groesse} Wörter.")

            alle_antworten = []

            for chunk_nr, chunk in enumerate(chunks, start=1):
                chunk_text = "\n".join(chunk)

                print(f"[INFO] IG-Chunk {chunk_nr}/{len(chunks)} mit {len(chunk)} Zeilen")

                messages_Chat = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": chunk_text}
                ]

                messages_Flat = f"Anweisung:\n{prompt}\n{chunk_text}"

                if client.check_chat_model():
                    antwort = KI_Analyse_Chat(
                        client,
                        messages_Chat,
                        dateiname="ig_woerter.txt",
                        wortnr_bereich=f"chunk_{chunk_nr:03}"
                    )
                else:
                    antwort = KI_Analyse_Flat(
                        client,
                        messages_Flat,
                        dateiname="ig_woerter.txt",
                        wortnr_bereich=f"chunk_{chunk_nr:03}"
                    )

                if antwort:
                    alle_antworten.append(antwort.strip())
              
                else:
                    print(f"[WARNUNG] Keine Antwort für IG-Chunk {chunk_nr}")

            ki_ergebnis = "\n".join(alle_antworten).strip()

        else:
            json_datei = lade_json_zu_txt_datei(dateipfad)

            if not json_datei or not json_datei.exists():
                print(f"[WARNUNG] Keine passende JSON-Datei gefunden. Fallback auf TXT: {dateipfad}")

                with open(dateipfad, "r", encoding="utf-8") as f:
                    eingabetext = f.read()

                messages_Chat = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": eingabetext}
                ]

                messages_Flat = f"Anweisung:\n{prompt}\n\n{eingabetext}"

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

            else:
                print(f"[INFO] Verwende JSON + Plaintext-Kontext: {json_datei}")

                with open(json_datei, "r", encoding="utf-8") as f:
                    json_daten = json.load(f)

                if not isinstance(json_daten, list):
                    print(f"[WARNUNG] JSON ist keine Liste. Fallback auf TXT: {json_datei}")

                    with open(dateipfad, "r", encoding="utf-8") as f:
                        eingabetext = f.read()

                    messages_Chat = [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": eingabetext}
                    ]

                    messages_Flat = f"Anweisung:\n{prompt}\n\n{eingabetext}"

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

                else:
                    abschnitte = splitte_in_abschnitte_nach_zeilenumbruch(json_daten)

                    print(f"[INFO] Verarbeite {len(abschnitte)} Abschnitt(e) mit Plaintext + WortNr-Mapping.")

                    alle_antworten = []

                    for abschnitt_nr, abschnitt in enumerate(abschnitte, start=1):
                        abschnitt_prompt = baue_ki_prompt(
                            abschnitt_text=abschnitt["text"],
                            tokens=abschnitt["tokens"],
                            aufgabe_prompt=None
                        )

                        wortnr_bereich = f"{abschnitt.get('start_wortnr', '')}-{abschnitt.get('end_wortnr', '')}"

                        print(
                            f"[INFO] Abschnitt {abschnitt_nr}/{len(abschnitte)} "
                            f"WortNr {wortnr_bereich}"
                        )

                        messages_Chat = [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": abschnitt_prompt}
                        ]

                        messages_Flat = (
                            f"Anweisung:\n{prompt}\n\n"
                            f"{abschnitt_prompt}"
                        )

                        if client.check_chat_model():
                            antwort = KI_Analyse_Chat(
                                client,
                                messages_Chat,
                                dateiname=os.path.basename(dateipfad),
                                wortnr_bereich=wortnr_bereich
                            )
                        else:
                            antwort = KI_Analyse_Flat(
                                client,
                                messages_Flat,
                                dateiname=os.path.basename(dateipfad),
                                wortnr_bereich=wortnr_bereich
                            )

                        if antwort:
                            alle_antworten.append(antwort.strip())
                        else:
                            print(f"[WARNUNG] Keine Antwort für Abschnitt {abschnitt_nr}")

                    ki_ergebnis = "\n".join(alle_antworten).strip()

        # ----------------------------------------------------
        # Ergebnis speichern
        # ----------------------------------------------------
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
        else:
            print("[WARNUNG] Kein KI-Ergebnis erhalten.")

    except Exception as e:
        print(f"[FEHLER] Fehler bei der Verarbeitung von {dateipfad}: {e}")
        traceback.print_exc()
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

import re
from pathlib import Path

def splitte_ig_klassen(eingabe_datei, ki_ordner):
    ik_set = set()
    ich_set = set()
    kein_set = set()
    sonder_set = set()

    def ist_mehrfach_klasse(klasse):
        return re.fullmatch(r"(ik|ich)(-(ik|ich))+", klasse) is not None

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

            # Normalisieren
            klasse = (
                klasse
                .replace("ig_ich", "ig-ich")
                .replace("ig/ich", "ig-ich")
                .replace("ig ich", "ig-ich")
            )

            # 🔥 NEUE LOGIK
            if ist_mehrfach_klasse(klasse):
                sonder_set.add(f"{wort}\t{klasse}")
                continue

            if klasse == "ik":
                ik_set.add(wort)
            elif klasse == "ich":
                ich_set.add(wort)
            elif klasse == "kein":
                kein_set.add(wort)
            else:
                kein_set.add(wort)

    # Dateien schreiben
    with open(Path(ki_ordner) / "ik_aussprache.txt", "w", encoding="utf-8") as f:
        for w in sorted(ik_set):
            f.write(w + "\n")

    with open(Path(ki_ordner) / "ich_aussprache.txt", "w", encoding="utf-8") as f:
        for w in sorted(ich_set):
            f.write(w + "\n")

    with open(Path(ki_ordner) / "kein_ig.txt", "w", encoding="utf-8") as f:
        for w in sorted(kein_set):
            f.write(w + "\n")

    with open(Path(ki_ordner) / "ig_sonderfälle.txt", "w", encoding="utf-8") as f:
        for eintrag in sorted(sonder_set):
            f.write(eintrag + "\n")

    print(f"[INFO] ik-Wörter: {len(ik_set)}")
    print(f"[INFO] ich-Wörter: {len(ich_set)}")
    print(f"[INFO] kein-ig-Wörter: {len(kein_set)}")
    print(f"[INFO] Sonderfälle (mehrere ig): {len(sonder_set)}")

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
    ignoriere_spezialtokens=True,
    nur_tokens_mit_ig=True,
):
    """
    Extrahiert IG-Wörter aus *_annotierungen.json-Dateien.

    Ausgabeformat:
        ein Wort pro Zeile

    Keine Häufigkeit.
    Keine Flexionsbündelung.
    Keine Basisformen.
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

    woerter_set = set()

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

                if ignoriere_spezialtokens:
                    if token.startswith("|") and token.endswith("|"):
                        continue
                    if token in {"", "_", "__"}:
                        continue

                clean_token = re.sub(r"[^\wäöüÄÖÜß]", "", token).strip()

                if not clean_token:
                    continue

                if len(clean_token) < min_len:
                    continue

                if nur_tokens_mit_ig and "ig" not in clean_token.lower():
                    continue

                woerter_set.add(clean_token)

        except Exception as e:
            print(f"[FEHLER] Fehler beim Lesen von {datei.name}: {e}")

    sortierte_woerter = sorted(
        woerter_set,
        key=lambda x: x.lower() if sort_case_insensitive else x
    )

    ausgabe_datei.parent.mkdir(parents=True, exist_ok=True)

    with open(ausgabe_datei, "w", encoding="utf-8") as f:
        for wort in sortierte_woerter:
            f.write(wort + "\n")

    print(f"[INFO] IG-Wörter extrahiert: {len(sortierte_woerter)}")
    print(f"[✓] IG-Wortliste gespeichert: {ausgabe_datei}")


if __name__ == "__main__":
    extrahiere_ig_woerter_aus_json(
        json_ordner=config.GLOBALORDNER["json"],
        ausgabe_datei=Path(config.GLOBALORDNER["ki"]) / "ig_woerter.txt",
        lowercase=True,    
        min_len=2,
        verwende_tokenInklZahlwoerter=True,
    )