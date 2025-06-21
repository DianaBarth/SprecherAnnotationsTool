import regex
import re
import json
import pandas as pd

from pathlib import Path
from num2words import num2words

import Eingabe.config as config  # Importiere das komplette config-Modul

def roemisch_zu_int(roemisch):
    roem_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    ergebnis, vorher = 0, 0
    for buchstabe in reversed(roemisch.upper()):
        wert = roem_map.get(buchstabe, 0)
        ergebnis = ergebnis - wert if wert < vorher else ergebnis + wert
        vorher = wert
    return ergebnis

def ist_roemisch(token):
    return re.fullmatch(r'M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})', token.upper()) is not None

def ersetze_zahl_in_token(token):
    token_clean = token.rstrip('.:,;!?')
    if ist_roemisch(token_clean):
        zahl = roemisch_zu_int(token_clean)
        if zahl > 0:
            return token.replace(token_clean, num2words(zahl, lang='de'))
    zahlen = re.findall(r'\d+', token)
    if not zahlen:
        return token
    if token.isdigit():
        return num2words(int(token), lang='de')
    for zahl_str in zahlen:
        wort = num2words(int(zahl_str), lang='de')
        token = token.replace(zahl_str, "_" + wort)
    return token

def extrahiere_kapitelname(kapitelname):
    match_arabisch = regex.match(r"^(\d+)", kapitelname)
    if match_arabisch:
        return match_arabisch.group(1)
    match_roemisch = regex.match(
        r"^(M{0,4}(CM)?(CD)?(D)?(C{0,3})(XC)?(XL)?(L)?(X{0,3})(IX)?(IV)?(V)?(I{0,3}))",
        kapitelname,
        flags=re.IGNORECASE,
    )
    if match_roemisch and match_roemisch.group(1):
        return str(roemisch_zu_int(match_roemisch.group(1)))
    if "Prolog" in kapitelname:
        return "0"
    return kapitelname

def verarbeite_kapitel_und_speichere_json(eingabeordner, ausgabeordner, ausgewaehlte_kapitel=None, progress_callback=None):
    START_TAGS = {
        "Ueberschrift": "|UeberschriftStart|",
        "Einrückung": "|EinrückungsStart|",
        "Zentriert": "|ZentriertStart|",
        "Rechtsbuendig": "|RechtsbuendigStart|",
    }
    END_TAGS = {
        "Ueberschrift": "|UeberschriftEnde|",
        "Einrückung": "|EinrückungsEnde|",
        "Zentriert": "|ZentriertEnde|",
        "Rechtsbuendig": "|RechtsbuendigEnde|",
    }

    eingabeordner = Path(eingabeordner)
    ausgabeordner = Path(ausgabeordner)
    ausgabeordner.mkdir(parents=True, exist_ok=True)
    textdateien = list(eingabeordner.glob("*.txt"))

    if ausgewaehlte_kapitel is not None:
        erweiterte_kapitel = set()
        for kapitel in ausgewaehlte_kapitel:
            erweiterte_kapitel.add(kapitel)
            for idx in range(0, 1000):
                erweiterte_kapitel.add(f"{kapitel}_{idx:03d}")
        textdateien = [d for d in textdateien if d.stem in erweiterte_kapitel]

    for datei in textdateien:
        kapitelname_original = datei.stem
        kapitelname = extrahiere_kapitelname(kapitelname_original)

        with open(datei, "r", encoding="utf-8") as f:
            text = f.read()

        for tag in list(START_TAGS.values()) + list(END_TAGS.values()):
            text = text.replace(tag, f" {tag} ")

        text = regex.sub(r"\r\n|\r|\n", " |BREAK| ", text)
        text = regex.sub(r"(_BREAK_)+", " |BREAK| ", text)

        woerter_und_satzzeichen = regex.split(r"\s+|(?<=\p{P})|(?=\p{P})", text, flags=regex.UNICODE)
        woerter_und_satzzeichen = [w for w in woerter_und_satzzeichen if w.strip()]

        cleaned_tokens = []
        cleaned_annotations = []
        positions = []

        pending_position_start = None  # Typ, z.B. "Zentriert"
        last_token_idx = {}            # Dict für letzte Token-Position je Typ
        in_ueberschrift = False

        i = 0
        while i < len(woerter_und_satzzeichen):
            token = woerter_und_satzzeichen[i]

            # START-TAG erkennen
            if token in START_TAGS.values():
                typ = [k for k, v in START_TAGS.items() if v == token][0]
                print(f"DEBUG: START-TAG '{token}' erkannt, pending_position_start gesetzt auf '{typ}'")
                if typ == "Ueberschrift":
                    in_ueberschrift = True
                    typ = "Zentriert"
                pending_position_start = typ
                i += 1
                continue

            # END-TAG erkennen
            elif token in END_TAGS.values():
                typ = [k for k, v in END_TAGS.items() if v == token][0]
                print(f"DEBUG: END-TAG '{token}' erkannt")
                if typ == "Ueberschrift":
                    in_ueberschrift = False
                    typ = "Zentriert"

                # Position des letzten echten Tokens vor dem End-Tag mit Ende-Annotation versehen
                if typ in last_token_idx and last_token_idx[typ] is not None:
                    idx = last_token_idx[typ]
                    if positions[idx]:
                        positions[idx] += f",{typ}Ende"
                    else:
                        positions[idx] = f"{typ}Ende"
                    print(f"DEBUG: Position an Index {idx} ergänzt mit '{typ}Ende'")
                    last_token_idx[typ] = None  # Reset

                i += 1
                continue

            # Zeilenumbruch |BREAK|
            elif token == "|BREAK|":
                print(f"DEBUG: Zeilenumbruch erkannt an Position {len(positions)}")
                cleaned_tokens.append("")
                cleaned_annotations.append("zeilenumbruch")
                positions.append("")
                i += 1
                continue

            # Annotationen und Position bestimmen
            annotationen = []
            position_wert = ""

            # Satzzeichen erkennen und annotieren
            if regex.match(r"[\p{P}]", token):
                if token in ['–', '(', ')', '{', '}', '[', ']']:
                    annotationen.append("satzzeichenMitSpace")
                elif token in ['„']:
                    annotationen.append("satzzeichenOhneSpaceDanach")
                else:
                    annotationen.append("satzzeichenOhneSpaceDavor")

            # Überschrift-Annotation hinzufügen, wenn aktiv
            if in_ueberschrift:
                annotationen.append("Überschrift")

            if token.strip():  # nur wenn echtes Token
                if pending_position_start:
                    position_wert = f"{pending_position_start}Start"
                    last_token_idx[pending_position_start] = len(positions)
                    print(f"DEBUG: Token '{token}' bekommt Position '{position_wert}' (pending_position_start='{pending_position_start}')")
                    pending_position_start = None
                else:
                    for typ in last_token_idx:
                        last_token_idx[typ] = len(positions)
                    print(f"DEBUG: Token '{token}' aktualisiert letzte Positionen: {last_token_idx}")

            else:
                print(f"DEBUG: Leer-Token an Position {len(positions)}")
            
            
            print(f"DEBUG: Token '{token}': Annotationen = {annotationen}, position_wert = {position_wert}")

            cleaned_tokens.append(token)
            cleaned_annotations.append(",".join(annotationen))
            positions.append(position_wert)
            
        

     
            i += 1

        print(f"DEBUG: Anzahl Tokens: {len(cleaned_tokens)}")
        print(f"DEBUG: Anzahl Annotationen: {len(cleaned_annotations)}")
        print(f"DEBUG: Beispiel Annotationen (erste 40): {cleaned_annotations[:40]}")
        print(f"DEBUG: Beispiel Positions (erste 40): {positions[:40]}")

        if not (len(cleaned_tokens) == len(cleaned_annotations) == len(positions)):
            raise ValueError("Längen von Tokens, Annotationen und Positionen stimmen nicht überein.")

        tokenInklZahlwoerter = [ersetze_zahl_in_token(t) for t in cleaned_tokens]

        df = pd.DataFrame({
            "KapitelNummer": kapitelname,
            "WortNr": range(1, len(cleaned_tokens) + 1),
            "token": cleaned_tokens,
            "tokenInklZahlwoerter": tokenInklZahlwoerter,
            "annotation": cleaned_annotations,
            "position": positions,
        })

        for typ_name in config.KI_AUFGABEN.values():
            if typ_name not in df.columns:
                df[typ_name] = ""

        json_filename = ausgabeordner / f"{kapitelname_original}_annotierungen.json"
        with open(json_filename, "w", encoding="utf-8") as out_f:
            json.dump(json.loads(df.to_json(orient="records", force_ascii=False)), out_f, indent=2, ensure_ascii=False)
