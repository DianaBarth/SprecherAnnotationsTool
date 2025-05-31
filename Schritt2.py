
import os
import regex
import re
import json
import pandas as pd

from pathlib import Path
from num2words import num2words

import Eingabe.config as config # Importiere das komplette config-Modul

def roemisch_zu_int(roemisch):
    roemisch = roemisch.upper()
    roem_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    ergebnis = 0
    vorher = 0
    for buchstabe in reversed(roemisch):
        wert = roem_map.get(buchstabe, 0)
        if wert < vorher:
            ergebnis -= wert
        else:
            ergebnis += wert
        vorher = wert
    return ergebnis

def ist_roemisch(token):
    # Regex für römische Zahlen (grob)
    return re.fullmatch(r'M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})', token.upper()) is not None

def ersetze_zahl_in_token(token):
    # Falls am Ende ein Punkt (oder anderes Satzzeichen) steht, für die Prüfung und Umwandlung ignorieren
    token_clean = token.rstrip('.:,;!?')

    if ist_roemisch(token_clean):
        zahl = roemisch_zu_int(token_clean)
        if zahl > 0:
            wort = num2words(zahl, lang='de')
            # Original token: Ersetze nur den römischen Teil durch das Wort, rest (z.B. Punkt) bleibt
            return token.replace(token_clean, wort)

    zahlen = re.findall(r'\d+', token)
    if not zahlen:
        return token  # Keine Zahl gefunden
    
    if token.isdigit():
        return num2words(int(token), lang='de')
    
    for zahl_str in zahlen:
        wort = num2words(int(zahl_str), lang='de')
        token = token.replace(zahl_str, "_" + wort)
    return token

def extrahiere_kapitelname(kapitelname):
    # Suche nach führender arabischer Zahl (z.B. 12)
    match_arabisch = regex.match(r"^(\d+)", kapitelname)
    if match_arabisch:
        return match_arabisch.group(1)

    # Suche nach führender römischer Zahl (z.B. XII)
    match_roemisch = regex.match(r"^(M{0,4}(CM)?(CD)?(D)?(C{0,3})(XC)?(XL)?(L)?(X{0,3})(IX)?(IV)?(V)?(I{0,3}))", kapitelname, flags=re.IGNORECASE)
    if match_roemisch and match_roemisch.group(1):
        return str(roemisch_zu_int(match_roemisch.group(1)))

    # Falls nichts gefunden, gib original zurück
    
    if "Prolog" in kapitelname:
        return 0
    
    return kapitelname

def verarbeite_kapitel_und_speichere_json(eingabeordner, ausgabeordner, ausgewaehlte_kapitel=None, progress_callback=None):

    print(f"[DEBUG -------------------------STARTE Schritt 2 für {ausgewaehlte_kapitel}]")

    eingabeordner = Path(eingabeordner)
    ausgabeordner = Path(ausgabeordner)
    
    ausgabeordner.mkdir(parents=True, exist_ok=True)

    if ausgewaehlte_kapitel is not None:
        ausgewaehlte_kapitel = set(ausgewaehlte_kapitel)

    textdateien = list(eingabeordner.glob("*.txt"))

    if ausgewaehlte_kapitel is not None:
        textdateien = [datei for datei in textdateien if datei.stem in ausgewaehlte_kapitel]

    anzahl_ueberschriften = config.ANZAHL_ÜBERSCHRIFTENZEILEN

    for i, datei in enumerate(textdateien):
        kapitelname_original = datei.stem
        kapitelname = extrahiere_kapitelname(kapitelname_original)
        step_count = 6  # Anzahl der logischen Verarbeitungsschritte
        current_step = 0

        def report_step():
            if progress_callback:
                progress = round((current_step + 1) / step_count, 3)
                progress_callback(kapitelname_original, progress)

        # Schritt 1: Einlesen der Datei
        with open(datei, "r", encoding="utf-8") as f:
            text = f.read()
        current_step += 1
        report_step()

        # Schritt 2: Zeilenumbrüche durch Platzhalter ersetzen
        text = regex.sub(r"\r\n|\r|\n", " _BREAK_BREAKY ", text)
        text = regex.sub(r"(_BREAK__BREAKY)+", " _BREAK__BREAKY ", text)
        current_step += 1
        report_step()

        # Schritt 3: Tokenisierung (inkl. _BREAK_ erhalten)
        woerter_und_satzzeichen = regex.split(r"\s+|(?<=\p{P})|(?=\p{P})|_BREAK_", text, flags=re.UNICODE)
        woerter_und_satzzeichen = [token for token in woerter_und_satzzeichen if token.strip()]
        current_step += 1
        report_step()

        # Schritt 4: Annotation
        annotationen = []
        zeilen_nr = 0

        for idx, token in enumerate(woerter_und_satzzeichen):
            token_annotationen = []

            if zeilen_nr < anzahl_ueberschriften:
                token_annotationen.append("Überschrift")

            if token == "BREAKY":
                woerter_und_satzzeichen[idx] = ""
                token_annotationen.append("zeilenumbruch")
                zeilen_nr += 1
            else:
                if regex.match(r"[\p{P}]", token):
                    if token == '–' or token in ['(', ')', '{', '}', '[', ']']:
                        token_annotationen.append("satzzeichenMitSpace")
                    elif token in ['.', '!', '?', ':', ';']:
                        token_annotationen.append("satzzeichenOhneSpace")
                    else:
                        token_annotationen.append("satzzeichenOhneSpace")

            annotationen.append(",".join(token_annotationen))

        current_step += 1
        report_step()

        if len(woerter_und_satzzeichen) != len(annotationen):
            raise ValueError(f"Längen von Tokens und Annotationen stimmen nicht überein.")

        tokenInklZahlwoerter = [ersetze_zahl_in_token(t) for t in woerter_und_satzzeichen]

        # Schritt 5: DataFrame und Speichern als JSON
        df = pd.DataFrame({
            "KapitelNummer": kapitelname,
            "WortNr": range(1, len(woerter_und_satzzeichen) + 1),
            "token": woerter_und_satzzeichen,
            "tokenInklZahlwoerter": tokenInklZahlwoerter,
            "annotation": annotationen,
        })

        for typ_name in config.KI_AUFGABEN.values():
            df[typ_name] = ""  # oder z.B. None, je nach Bedarf

        json_filename = ausgabeordner / f"{kapitelname_original}_annotierungen.json"
        with open(json_filename, "w", encoding="utf-8") as out_f:
            json.dump(json.loads(df.to_json(orient="records", force_ascii=False)), out_f, indent=2, ensure_ascii=False)

        current_step += 1
        report_step()

        print(f"[DEBUG -------------------------Schritt 2 abgeschlossen un datei erzeugt: {json_filename }")
