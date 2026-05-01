import regex
import re
import json
import pandas as pd

from pathlib import Path
from num2words import num2words
import locale
import calendar

import Eingabe.config as config  # Importiere das komplette config-Modul

def get_monatsnamen(sprache_code):
    """Gibt Monatsnamen gemäß Sprachcode via locale zurück."""
    try:
        # Mapping für Sprachcode zu Locale (falls nötig anpassen)
        locale_map = {
            "de": "de_DE.UTF-8",
            "en": "en_US.UTF-8",
            "fr": "fr_FR.UTF-8"
        }
        loc = locale_map.get(sprache_code, "de_DE.UTF-8")
        locale.setlocale(locale.LC_TIME, loc)
        return [calendar.month_name[i] for i in range(1, 13)]
    
    except Exception as e:
        print(f"Warnung: locale konnte nicht gesetzt werden ({e})")
        # Fallback auf deutsche Monatsnamen
        return ["Januar", "Februar", "März", "April", "Mai", "Juni",
                "Juli", "August", "September", "Oktober", "November", "Dezember"]

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

def ersetze_zahl_in_token(token, vorher_token=None, naechstes_token=None):
    print(f"DEBUG: Verarbeite Token='{token}', vorher_token='{vorher_token}', naechstes_token='{naechstes_token}'")
    
    match = re.match(r"([A-Za-z]?)(\d+)([.,:;!?\-]*)$", token)
    if not match:
        return token

    prefix, zahl_str, endzeichen = match.groups()
    zahl = int(zahl_str)
    print(f"DEBUG: Gefundene Zahl='{zahl}', Präfix='{prefix}', Endzeichen='{endzeichen}'")

    monate = get_monatsnamen(config.SPRACHE)

    # Sonderfall: Buchstabe + Zahl (z. B. "J1")
    if prefix and prefix.isalpha():
        wort = num2words(zahl, lang=config.SPRACHE)
        print(f"DEBUG: Sonderfall Buchstabe+Zahl -> '{prefix}_{wort}'")
        return f"{prefix}_{wort}"

    # Ordinalzahl-Kontext
    if endzeichen == '.' and (
        (vorher_token and vorher_token.lower() in ['am', 'zum']) or
        (naechstes_token and naechstes_token.lower() in monate)
    ):
        print("DEBUG: Kontext für Ordnungszahl erkannt.")
        wort = num2words(zahl, lang='de', to='ordinal')
        if wort.endswith('ste'):
            wort = wort[:-3] + 'sten'
        elif wort.endswith('te'):
            wort = wort[:-2] + 'ten'
        return wort
    else:
        wort = num2words(zahl, lang=config.SPRACHE)
        print(f"DEBUG: Normale Kardinalzahl='{wort}'")
        return wort

def lade_kapitel_reihenfolge():
    config_datei = Path("Eingabe/kapitel_config.json")

    with open(config_datei, "r", encoding="utf-8") as f:
        data = json.load(f)

    kapitel_liste = data.get("kapitel_liste", [])

    return {
        name: idx
        for idx, name in enumerate(kapitel_liste)
    }

def sort_key_kapiteldatei(pfad: Path, kapitel_reihenfolge=None):
    kapitel_reihenfolge = kapitel_reihenfolge or {}

    stem = pfad.stem

    # entfernt Abschnittsnummer, z.B.
    # "3. Erste Risse (Kapitel VII–VIII)_001"
    # -> "3. Erste Risse (Kapitel VII–VIII)"
    m = re.match(r"^(.*?)[_-](\d+)$", stem)
    if m:
        basis, teil = m.groups()
    else:
        basis, teil = stem, "0"

    if basis in kapitel_reihenfolge:
        return kapitel_reihenfolge[basis], int(teil), stem.lower()

    print(f"[WARNUNG] Kapitel nicht in kapitel_config.json gefunden: {basis!r}")
    return 999999, int(teil), stem.lower()

def verarbeite_kapitel_und_speichere_json(eingabeordner, ausgabeordner, ausgewaehlte_kapitel=None, progress_callback=None):
    START_TAGS = {
        "Ueberschrift": "|UeberschriftStart|",
        "Einrueckung": "|EinrueckungStart|",
        "Zentriert": "|ZentriertStart|",
        "Rechtsbuendig": "|RechtsbuendigStart|",
        "Fett": "|FettStart|",
        "Kursiv": "|KursivStart|",
    }

    END_TAGS = {
        "Ueberschrift": "|UeberschriftEnde|",
        "Einrueckung": "|EinrueckungEnde|",
        "Zentriert": "|ZentriertEnde|",
        "Rechtsbuendig": "|RechtsbuendigEnde|",
        "Fett": "|FettEnde|",
        "Kursiv": "|KursivEnde|",
    }

    eingabeordner = Path(eingabeordner)
    ausgabeordner = Path(ausgabeordner)
    ausgabeordner.mkdir(parents=True, exist_ok=True)

    kapitel_reihenfolge = lade_kapitel_reihenfolge()

    textdateien = sorted(
        eingabeordner.glob("*.txt"),
        key=lambda p: sort_key_kapiteldatei(p, kapitel_reihenfolge)
    )

    global_wortnr = 1

    for datei in textdateien:
        kapitelname_original = datei.stem
        kapitelname = kapitelnummer_aus_config_index(
            kapitelname_original,
            kapitel_reihenfolge
        )

        with open(datei, "r", encoding="utf-8") as f:
            text = f.read()

        # Tags trennen
        for tag in list(START_TAGS.values()) + list(END_TAGS.values()):
            text = text.replace(tag, f" {tag} ")

        text = regex.sub(r"\r\n|\r|\n", " |BREAK| ", text)

        pattern = r"[|]\w+[|]|\d+\.(?!\d)|\d+|[\w-]+|[^\w\s-]"
        tokens = regex.findall(pattern, text, flags=regex.UNICODE)
        tokens = [w for w in tokens if w.strip()]

        cleaned_tokens = []
        cleaned_annotations = []
        positions = []
        betonungen = []

        pending_position_start = None
        active_positions = set()
        last_token_idx = {
            "Einrueckung": None,
            "Zentriert": None,
            "Rechtsbuendig": None,
        }

        in_ueberschrift = False
        fett_aktiv = False
        kursiv_aktiv = False

        i = 0
        while i < len(tokens):
            token = tokens[i]

            # ------------------ START TAG ------------------
            if token in START_TAGS.values():
                typ = [k for k, v in START_TAGS.items() if v == token][0]

                if typ == "Fett":
                    fett_aktiv = True
                    i += 1
                    continue

                if typ == "Kursiv":
                    kursiv_aktiv = True
                    i += 1
                    continue

                if typ == "Ueberschrift":
                    in_ueberschrift = True
                    typ = "Zentriert"

                active_positions.add(typ)
                pending_position_start = typ

                i += 1
                continue

            # ------------------ END TAG ------------------
            elif token in END_TAGS.values():
                typ = [k for k, v in END_TAGS.items() if v == token][0]

                if typ == "Fett":
                    fett_aktiv = False
                    i += 1
                    continue

                if typ == "Kursiv":
                    kursiv_aktiv = False
                    i += 1
                    continue

                if typ == "Ueberschrift":
                    in_ueberschrift = False
                    typ = "Zentriert"

                if typ in last_token_idx and last_token_idx[typ] is not None:
                    idx = last_token_idx[typ]

                    teile = [p.strip() for p in str(positions[idx] or "").split(",") if p.strip()]
                    ende = f"{typ}Ende"

                    if ende not in teile:
                        teile.append(ende)

                    positions[idx] = ",".join(teile)

                last_token_idx[typ] = None
                active_positions.discard(typ)

                i += 1
                continue

            # ------------------ BREAK ------------------
            elif token == "|BREAK|":
                cleaned_tokens.append("")
                cleaned_annotations.append("zeilenumbruch")
                positions.append("")
                betonungen.append("")
                i += 1
                continue

            # ------------------ TOKEN ------------------
            annotationen = []
            position_wert = ""

            if regex.match(r"[\p{P}]", token):
                if token in ['–', '(', ')', '{', '}', '[', ']']:
                    annotationen.append("satzzeichenMitSpace")
                elif token == '„':
                    annotationen.append("satzzeichenOhneSpaceDanach")
                else:
                    annotationen.append("satzzeichenOhneSpaceDavor")

            if in_ueberschrift:
                annotationen.append("Überschrift")

            if token.strip():
                aktueller_idx = len(positions)

                if pending_position_start:
                    position_wert = f"{pending_position_start}Start"
                    pending_position_start = None

                # 🔥 WICHTIG: immer alle aktiven aktualisieren
                for aktiver_typ in active_positions:
                    last_token_idx[aktiver_typ] = aktueller_idx

            betonung_wert = ""
            if not in_ueberschrift:
                if fett_aktiv:
                    betonung_wert = "Hauptbetonung"
                elif kursiv_aktiv:
                    betonung_wert = "Nebenbetonung"

            cleaned_tokens.append(token)
            cleaned_annotations.append(",".join(annotationen))
            positions.append(position_wert)
            betonungen.append(betonung_wert)

            i += 1

        # ------------------ DATAFRAME ------------------
        df = pd.DataFrame({
            "KapitelNummer": kapitelname,
            "WortNr": range(global_wortnr, global_wortnr + len(cleaned_tokens)),
            "token": cleaned_tokens,
            "annotation": cleaned_annotations,
            "position": positions,
            "betonung": betonungen,
        })

        json_filename = ausgabeordner / f"{kapitelname_original}_annotierungen.json"

        with open(json_filename, "w", encoding="utf-8") as out_f:
            json.dump(json.loads(df.to_json(orient="records", force_ascii=False)), out_f, indent=2, ensure_ascii=False)

        global_wortnr += len(cleaned_tokens)

    if progress_callback:
        progress_callback("Fertig", 100)

def basisname_ohne_abschnitt(stem):
    """
    Entfernt Abschnittsnummer:
    'Vorwort_001' -> 'Vorwort'
    '2. Aufbau der Welt (Kapitel IV–VI)_001' -> '2. Aufbau der Welt (Kapitel IV–VI)'
    """
    m = re.match(r"^(.*?)[_-](\d+)$", stem)
    if m:
        return m.group(1)
    return stem


def kapitelnummer_aus_config_index(kapitelname_original, kapitel_reihenfolge):
    basis = basisname_ohne_abschnitt(kapitelname_original)

    if basis not in kapitel_reihenfolge:
        raise ValueError(
            f"Kapitel nicht in kapitel_config.json gefunden: {basis!r} "
            f"(aus Datei: {kapitelname_original!r})"
        )

    return str(kapitel_reihenfolge[basis])
