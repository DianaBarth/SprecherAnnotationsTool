import regex
import re
import json
import pandas as pd
from pathlib import Path
from num2words import num2words

import Eingabe.config as config

def verarbeite_kapitel_und_speichere_json(eingabeordner, ausgabeordner, ausgewaehlte_kapitel=None, progress_callback=None):

    # Annotation-Strings
    START_TAGS = {
        "Einrückung": "|EinrückungsStart|",
        "Zentriert": "|ZentriertStart|",
        "Rechtsbuendig": "|RechtsbuendigStart|",
    }
    END_TAGS = {
        "Einrückung": "|EinrückungsEnde|",
        "Zentriert": "|ZentriertEnde|",
        "Rechtsbuendig": "|RechtsbuendigEnde|",
    }

    def roemisch_zu_int(roemisch):
        roem_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        ergebnis = 0
        vorher = 0
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
        match_roemisch = regex.match(r"^(M{0,4}(CM)?(CD)?(D)?(C{0,3})(XC)?(XL)?(L)?(X{0,3})(IX)?(IV)?(V)?(I{0,3}))", kapitelname, flags=re.IGNORECASE)
        if match_roemisch and match_roemisch.group(1):
            return str(roemisch_zu_int(match_roemisch.group(1)))
        if "Prolog" in kapitelname:
            return 0
        return kapitelname

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
        textdateien = [datei for datei in textdateien if datei.stem in erweiterte_kapitel]

    for i, datei in enumerate(textdateien):
        kapitelname_original = datei.stem
        kapitelname = extrahiere_kapitelname(kapitelname_original)

        step_count = 6
        current_step = 0
        def report_step():
            if progress_callback:
                progress = round((current_step + 1) / step_count, 3)
                progress_callback(kapitelname_original, progress)

        with open(datei, "r", encoding="utf-8") as f:
            text = f.read()
        current_step += 1
        report_step()

        # Tags vor Tokenisierung durch Leerzeichen abtrennen
        alle_tags = list(START_TAGS.values()) + list(END_TAGS.values())
        for tag in alle_tags:
            text = text.replace(tag, f" {tag} ")

        # Zeilenumbrüche durch speziellen Token ersetzen
        text = regex.sub(r"\r\n|\r|\n", " _BREAK_BREAKY ", text)
        text = regex.sub(r"(_BREAK__BREAKY)+", " _BREAK__BREAKY ", text)

        current_step += 1
        report_step()

        # Tokenisierung
        raw_tokens = regex.split(r"\s+|(?<=\p{P})|(?=\p{P})|_BREAK_", text, flags=regex.UNICODE)
        raw_tokens = [t for t in raw_tokens if t.strip()]

        cleaned_tokens = []
        cleaned_annotations = []
        positions = []

        aktive_formate = []
        position_status = None  # Aktive Formatierung (z.B. "Zentriert")

        i = 0
        while i < len(raw_tokens):
            token = raw_tokens[i]

            if token in START_TAGS.values():
                typ = [k for k, v in START_TAGS.items() if v == token][0]
                aktive_formate.append(typ)
                position_status = aktive_formate[-1]  # Immer der zuletzt aktivierte Typ
                i += 1
                continue  # Tag nicht als Token speichern

            if token in END_TAGS.values():
                typ = [k for k, v in END_TAGS.items() if v == token][0]
                if aktive_formate and typ in aktive_formate:
                    # Schließe den zuletzt geöffneten dieses Typs
                    for idx in range(len(aktive_formate) - 1, -1, -1):
                        if aktive_formate[idx] == typ:
                            del aktive_formate[idx]
                            break
                    # Positionen der letzten Tokens mit Start-Tag auf Ende setzen
                    for j in range(len(cleaned_tokens) - 1, -1, -1):
                        if positions[j] == f"{typ}Start":
                            positions[j] = f"{typ}Ende"
                            break
                    # Aktualisiere position_status auf zuletzt aktiven Typ oder None
                    position_status = aktive_formate[-1] if aktive_formate else None
                i += 1
                continue  # Tag nicht als Token speichern

            if token == "BREAKY":
                cleaned_tokens.append("")
                cleaned_annotations.append("zeilenumbruch")
                positions.append("")
                i += 1
                continue

            # Normale Tokens verarbeiten
            annotationen = []
            if regex.match(r"[\p{P}]", token):
                if token in ['–', '(', ')', '{', '}', '[', ']', '“', '„']:
                    annotationen.append("satzzeichenMitSpace")
                else:
                    annotationen.append("satzzeichenOhneSpace")

            cleaned_tokens.append(token)
            cleaned_annotations.append(",".join(annotationen))

            if position_status:
                positions.append(f"{position_status}Start")
            else:
                positions.append("")

            i += 1

        current_step += 1
        report_step()

        if len(cleaned_tokens) != len(cleaned_annotations) or len(cleaned_tokens) != len(positions):
            raise ValueError("Längen von Tokens, Annotationen und Positionen stimmen nicht überein.")

        tokenInklZahlwoerter = [ersetze_zahl_in_token(t) for t in cleaned_tokens]

        df = pd.DataFrame({
            "KapitelNummer": kapitelname,
            "WortNr": range(1, len(cleaned_tokens) + 1),
            "token": cleaned_tokens,
            "tokenInklZahlwoerter": tokenInklZahlwoerter,
            "annotation": cleaned_annotations,
            "person": "",
            "betonung": "",
            "pause": "",
            "gedanken": "",
            "spannung": "",
            "ig": "",
            "position": positions,
        })

        for typ_name in config.KI_AUFGABEN.values():
            df[typ_name] = ""

        json_filename = ausgabeordner / f"{kapitelname_original}_annotierungen.json"
        with open(json_filename, "w", encoding="utf-8") as out_f:
            json.dump(json.loads(df.to_json(orient="records", force_ascii=False)), out_f, indent=2, ensure_ascii=False)

        current_step += 1
        report_step()
