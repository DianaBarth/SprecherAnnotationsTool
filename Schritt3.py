import re
import regex
import json
import os
from pathlib import Path
import tiktoken
import Eingabe.config as config

tokenizer = tiktoken.get_encoding("cl100k_base")  # GPT-4/3.5 Tokenizer
satzzeichen = {".", "!", "?"}
satzzeichen_pattern = re.compile(r'([.!?])')  # Satzzeichen als Trenner
zeilenumbruch_marker = "_BREAK*BREAKY"


def zähle_gpt_tokens(text: str) -> int:
    return len(tokenizer.encode(text))

def ist_satzende(token):
    return token in satzzeichen or token == zeilenumbruch_marker

def daten_aufteilen(kapitelname, txt_ordner, json_ordner, ausgabe_ordner, progress_callback=None):
    
    print(f"config.MAX_PROMPT_TOKENS: {config.MAX_PROMPT_TOKENS}")
    txt_dateien_aufteilen(kapitelname,txt_ordner, ausgabe_ordner, progress_callback)

    extrahiere_ig_tokens(kapitelname,json_ordner, ausgabe_ordner, progress_callback,True)
 
    print(f"[INFO] Daten aufteilen abgeschlossen für Kapitel '{kapitelname}'")

def split_text_in_saetze(text):
    # Splitte Text so, dass Satzzeichen am Ende erhalten bleiben
    parts = satzzeichen_pattern.split(text)
    saetze = []
    for i in range(0, len(parts)-1, 2):
        satz = parts[i].strip() + parts[i+1].strip()
        saetze.append(satz)
    if len(parts) % 2 != 0:
        letzter_satz = parts[-1].strip()
        if letzter_satz:
            saetze.append(letzter_satz)
    return saetze

def txt_dateien_aufteilen(kapitelname, eingabe_ordner, ausgabe_ordner, progress_callback=None):
    print(f"[DEBUG -------------------------STARTE Schritt 3 für {kapitelname}")
    eingabe_ordner = Path(eingabe_ordner)
    ausgabe_ordner = Path(ausgabe_ordner)
    os.makedirs(ausgabe_ordner, exist_ok=True)

    # Alte Regex für Annotationen entfernen, da neue Tags anders sind
    # annotation_pattern = re.compile(r"\[[^\]]*Start\]|\[[^\]]*Ende\]")  # NICHT MEHR NÖTIG

    dateien = sorted([f for f in eingabe_ordner.glob(f"{kapitelname}_*.txt")])
    if not dateien:
        print(f"[WARNUNG] Keine TXT-Dateien für Kapitel '{kapitelname}' gefunden.")
        return

    for datei in dateien:
        print(f"[DEBUG] Verarbeite Datei: {datei.name}")
        with open(datei, "r", encoding="utf-8") as f:
            text = f.read()

        # Keine Annotationen mit Regex entfernen! Stattdessen die neuen Tags ignorieren später beim Verarbeiten.

        # Falls gewünscht: Entferne die neuen Formatierungs-Tags (optional)
        for tag in ["|UeberschriftStart|","|UeberschriftEnde|",
                    "|EinrückungsStart|", "|EinrückungsEnde|",
                    "|ZentriertStart|", "|ZentriertEnde|",
                    "|RechtsbuendigStart|", "|RechtsbuendigEnde|"]:
            text = text.replace(tag, "")  # falls du Tags aus dem reinen Text entfernen willst

        saetze = split_text_in_saetze(text)
        abschnitt = ""
        token_counter = 0
        abschnitt_counter = 1

        for i, satz in enumerate(saetze, 1):
            satz_tokens = len(tokenizer.encode(satz))
            # Wenn wir mit aktuellem Satz die Grenze überschreiten, abschnitt speichern und neu starten
            if token_counter + satz_tokens > config.MAX_PROMPT_TOKENS:
                if abschnitt:
                    token_anzahl = len(tokenizer.encode(abschnitt))
                    dateiname = ausgabe_ordner / f"{datei.stem}_abschnitt_{abschnitt_counter:03}.txt"
                    with open(dateiname, "w", encoding="utf-8") as out_f:
                        out_f.write(abschnitt.strip())
                    print(f"[DEBUG] Gespeichert Abschnitt {abschnitt_counter} mit {token_anzahl} Tokens in {dateiname}")
                    abschnitt_counter += 1
                abschnitt = satz
                token_counter = satz_tokens
            else:
                abschnitt = abschnitt + " " + satz if abschnitt else satz
                token_counter += satz_tokens

            if progress_callback:
                fortschritt = int((i / len(saetze)) * 100)
                progress_callback(kapitelname, fortschritt)

        if abschnitt:
            token_anzahl = len(tokenizer.encode(abschnitt))
            dateiname = ausgabe_ordner / f"{datei.stem}_abschnitt_{abschnitt_counter:03}_annotierungen.txt"
            with open(dateiname, "w", encoding="utf-8") as out_f:
                out_f.write(abschnitt.strip())
            print(f"[DEBUG] Gespeichert letzter Abschnitt {abschnitt_counter} mit {token_anzahl} Tokens in {dateiname}")

    if progress_callback:
        progress_callback(kapitelname, 100)

    print(f"[DEBUG -------------------------Schritt 3 abgeschlossen für Kapitel {kapitelname}]")


#-----------------------
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

    abschnittsnummer = 1
    aktueller_abschnitt = []
    aktueller_token_text = ""

    def speichere_abschnitt(abschnitt_tokens, abschnitt_nr):
        abschnitt_text = ";".join(abschnitt_tokens) if semikolon_format else "\n".join(abschnitt_tokens)
        token_count = zähle_gpt_tokens(abschnitt_text)
        dateiname = f"{kapitelname}_ig_abschnitt_{abschnitt_nr:03}.txt"
        ausgabe_datei = ausgabe_ordner / dateiname
        with open(ausgabe_datei, "w", encoding="utf-8") as f_out:
            f_out.write(abschnitt_text)
        print(f"[DEBUG] Gespeichert IG-Abschnitt {abschnitt_nr} mit {token_count} GPT-Tokens in {ausgabe_datei}")

    for token in tokens_sortiert:
        # Baue Teststring für Token-Zähler
        test_abschnitt = aktueller_abschnitt + [token]
        if semikolon_format:
            test_text = ";".join(test_abschnitt)
        else:
            test_text = "\n".join(test_abschnitt)

        token_anzahl = zähle_gpt_tokens(test_text)

        if token_anzahl > max_tokens:
            # Aktuellen Abschnitt speichern und neuen starten
            if aktueller_abschnitt:
                speichere_abschnitt(aktueller_abschnitt, abschnittsnummer)
                abschnittsnummer += 1
            aktueller_abschnitt = [token]
        else:
            aktueller_abschnitt.append(token)

    # Letzten Abschnitt speichern
    if aktueller_abschnitt:
        speichere_abschnitt(aktueller_abschnitt, abschnittsnummer)

    if progress_callback:
        progress_callback(kapitelname, 100)

    print(f"[INFO] IG-Token Extraktion abgeschlossen für: {kapitelname}")