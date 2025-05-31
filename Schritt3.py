import re
import os
import json
import regex
from pathlib import Path
import Eingabe.config as config  # Importiere das komplette config-Modul

satzzeichen = {".", "!", "?"}
zeilenumbruch_marker = "_BREAK__BREAKY"  # Wie in deinem bisherigen Code für Zeilenumbruch-Annotation

def daten_aufteilen(kapitelname, txt_ordner, json_ordner, ausgabe_ordner, progress_callback=None):
      
    txt_dateien_aufteilen(kapitelname,txt_ordner, ausgabe_ordner, progress_callback)

    extrahiere_ig_tokens(kapitelname,json_ordner, ausgabe_ordner, progress_callback,True)
 
    print(f"[INFO] Daten aufteilen abgeschlossen für Kapitel '{kapitelname}'")

def txt_dateien_aufteilen(kapitelname, txt_ordner, ausgabe_ordner, progress_callback=None):
    print(f"[DEBUG ------------------------- STARTE TXT-Aufteilung für Kapitel: {kapitelname}]")
    txt_ordner = Path(txt_ordner)
    ausgabe_ordner = Path(ausgabe_ordner)
    ausgabe_ordner.mkdir(parents=True, exist_ok=True)

    # Filtere alle passenden txt-Dateien: kapitelname + _{idx}.txt
    dateien = [f for f in txt_ordner.glob(f"{kapitelname}_*.txt")]
    if not dateien:
        print(f"[WARNUNG] Keine passenden TXT-Dateien gefunden für Kapitel: {kapitelname}")
        return

    for datei in sorted(dateien):
        print(f"[DEBUG] Verarbeite Datei: {datei.name}")

        with open(datei, "r", encoding="utf-8") as f:
            text = f.read()

        # Tokenisiere text grob nach Leerzeichen, behalte Satzzeichen etc.
        tokens = regex.findall(r"\S+|\n", text)

        saetze = []
        aktueller_satz = []
        token_counter = 0

        def ist_satzende(token):
            # Satzende, wenn token ein Satzzeichen ist oder Zeilenumbruch Marker
            if token in satzzeichen:
                return True
            if token == zeilenumbruch_marker:
                return True
            return False

        abschnittsnummer = 1
        abschnitt_tokens = []
        abschnitt_token_count = 0

        for token in tokens:
            aktueller_satz.append(token)
            token_counter += 1

            if ist_satzende(token):
                # Satz abgeschlossen, prüfe, ob Abschnitt zu groß wird
                satz_laenge = len(aktueller_satz)

                if abschnitt_token_count + satz_laenge > config.MAX_PROMPT_TOKENS:
                    # Speichere aktuellen Abschnitt als Datei
                    dateiname = ausgabe_ordner / f"{datei.stem}_abschnitt_{abschnittsnummer:03}.txt"
                    with open(dateiname, "w", encoding="utf-8") as out_f:
                        out_f.write(" ".join(abschnitt_tokens).replace(zeilenumbruch_marker, "\n"))
                    print(f"[DEBUG] Gespeichert Abschnitt {abschnittsnummer} mit {abschnitt_token_count} Tokens in {dateiname}")
                    abschnittsnummer += 1
                    abschnitt_tokens = aktueller_satz.copy()
                    abschnitt_token_count = satz_laenge
                else:
                    abschnitt_tokens.extend(aktueller_satz)
                    abschnitt_token_count += satz_laenge

                aktueller_satz = []

            # Wenn Satz endet nicht, warte weiter

        # Falls am Ende noch Tokens übrig sind im Satz und/oder Abschnitt, speichere
        if aktueller_satz:
            abschnitt_tokens.extend(aktueller_satz)
        if abschnitt_tokens:
            dateiname = ausgabe_ordner / f"{datei.stem}_abschnitt_{abschnittsnummer:03}.txt"
            with open(dateiname, "w", encoding="utf-8") as out_f:
                out_f.write(" ".join(abschnitt_tokens).replace(zeilenumbruch_marker, "\n"))
            print(f"[DEBUG] Gespeichert letzter Abschnitt {abschnittsnummer} mit {abschnitt_token_count} Tokens in {dateiname}")

        if progress_callback:
            progress_callback(kapitelname, 100)

    print(f"[DEBUG ------------------------- TXT-Aufteilung abgeschlossen für Kapitel: {kapitelname}]")

def extrahiere_ig_tokens(kapitelname, json_ordner, ausgabe_ordner, progress_callback=None, semikolon_format=True):
    json_ordner = Path(json_ordner)
    ausgabe_ordner = Path(ausgabe_ordner)
    ausgabe_ordner.mkdir(parents=True, exist_ok=True)

    pattern = re.compile(re.escape(kapitelname) + r"(_\d+)_annotierungen\.json$")
    gefundene_dateien = [f for f in json_ordner.iterdir() if pattern.match(f.name)]

    if not gefundene_dateien:
        print(f"[FEHLER] Keine passenden JSON-Dateien für '{kapitelname}' gefunden im Ordner: {json_ordner}")
        return

    tokens_mit_ig = set()

    for json_datei in gefundene_dateien:
        print(f"[INFO] Lese JSON-Datei: {json_datei}")
        with open(json_datei, "r", encoding="utf-8") as f:
            daten = json.load(f)

        for eintrag in daten:
            token = eintrag.get("tokenInklZahlwoerter", "")
            if "ig" in token:
                tokens_mit_ig.add(token)

    print(f"[INFO] Gefundene eindeutige Tokens mit 'ig' insgesamt: {len(tokens_mit_ig)}")

    tokens_sortiert = sorted(tokens_mit_ig, key=lambda x: x.lower())
    max_tokens = config.MAX_PROMPT_TOKENS

    if semikolon_format:
        abschnittsnummer = 1
        for i in range(0, len(tokens_sortiert), max_tokens):
            teil_tokens = tokens_sortiert[i:i + max_tokens]
            ausgabe_datei = ausgabe_ordner / f"{kapitelname}_ig_abschnitt_{abschnittsnummer:03}.txt"
            with open(ausgabe_datei, "w", encoding="utf-8") as f_out:
                f_out.write(";".join(teil_tokens))
            print(f"[DEBUG] Gespeichert IG-Abschnitt {abschnittsnummer} mit {len(teil_tokens)} Tokens in {ausgabe_datei}")
            abschnittsnummer += 1
    else:
        ausgabe_datei = ausgabe_ordner / f"{kapitelname}_ig.txt"
        with open(ausgabe_datei, "w", encoding="utf-8") as f_out:
            for token in tokens_sortiert:
                f_out.write(token + "\n")
        print(f"[DEBUG] Gespeichert IG-Tokens zeilenweise in: {ausgabe_datei}")

    if progress_callback:
        progress_callback(kapitelname, 100)

    print(f"[INFO] IG-Token Extraktion abgeschlossen für: {kapitelname}")
