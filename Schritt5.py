import json
import re
import traceback
from collections import defaultdict
from pathlib import Path

import Eingabe.config as config


def parse_bereich(bereich):
    if bereich in (None, ""):
        return []

    bereich = str(bereich).strip()

    if ":" in bereich:
        try:
            start, ende = map(int, bereich.split(":"))
            if start > ende:
                start, ende = ende, start
            return list(range(start, ende + 1))
        except ValueError:
            print(f"[FEHLER] Ungültiger Bereich: {bereich}")
            return []

    try:
        return [int(bereich)]
    except ValueError:
        print(f"[FEHLER] Ungültiger Einzelwert für WortNr: {bereich}")
        return []


def ist_abschnittsdatei(dateiname):
    return re.fullmatch(r".+_\d+_annotierungen\.json", dateiname) is not None


def extrahiere_hauptkapitel_und_index(dateiname_ohne_endung):
    match = re.fullmatch(r"(.+)_(\d+)_annotierungen", dateiname_ohne_endung)
    if not match:
        return None, None

    hauptkapitel = match.group(1)
    idx = int(match.group(2))
    return hauptkapitel, idx


def ermittle_abschnittsdateien(quellordner_kapitel, ausgewaehlte_kapitel=None):
    quellordner_kapitel = Path(quellordner_kapitel)

    dateien = sorted(quellordner_kapitel.glob("*_annotierungen.json"))
    if not dateien:
        print("[FEHLER] Keine '_annotierungen.json'-Dateien im Quellordner gefunden.")
        return []

    gefundene = []

    for datei in dateien:
        if not ist_abschnittsdatei(datei.name):
            print(f"[DEBUG] Überspringe Nicht-Abschnittsdatei: {datei.name}")
            continue

        hauptkapitel, idx = extrahiere_hauptkapitel_und_index(datei.stem)

        if hauptkapitel is None:
            print(f"[WARNUNG] Dateiname konnte nicht ausgewertet werden: {datei.name}")
            continue

        if ausgewaehlte_kapitel is not None and hauptkapitel not in ausgewaehlte_kapitel:
            continue

        gefundene.append({
            "pfad": datei,
            "dateiname": datei.name,
            "stem": datei.stem,
            "hauptkapitel": hauptkapitel,
            "index": idx,
        })

    print(f"[DEBUG] Erkannte Abschnittsdateien: {[d['dateiname'] for d in gefundene]}")
    return gefundene


def finde_annotationsdateien_fuer_abschnitt(quellordner_annotationen, abschnitts_dateiname):
    """
    Erwartete KI-Dateien z. B.:

    betonung_I.Scelus sapiens matris_010_annotierungen_001.json
    pause_I.Scelus sapiens matris_010_annotierungen_001.json
    person_I.Scelus sapiens matris_010_annotierungen_001.json

    Allgemein:
    <typ>_<abschnitts_stem>_*.json
    """

    quellordner_annotationen = Path(quellordner_annotationen)
    abschnitts_stem = Path(abschnitts_dateiname).stem

    muster = f"*_{abschnitts_stem}_*.json"
    dateien = sorted(quellordner_annotationen.glob(muster))

    print(f"[DEBUG] Suche KI-Dateien mit Muster: {muster}")
    print(f"[DEBUG] Gefundene KI-Dateien: {[d.name for d in dateien]}")

    return dateien


def extrahiere_typ_aus_ki_dateiname(dateiname, abschnitts_dateiname):
    abschnitts_stem = Path(abschnitts_dateiname).stem
    suffix = f"_{abschnitts_stem}_"

    if suffix not in dateiname:
        return None

    typ = dateiname.split(suffix, 1)[0].lower().strip("_")
    return typ or None


def ermittle_feldname_fuer_typ(typ):
    """
    typ aus Dateiname -> Feldname im Token-JSON.

    Beispiel:
    typ='pause' -> config.KI_AUFGABEN enthält 'pause' -> Feld 'pause'
    """

    typ = str(typ).lower().strip()

    for _, aufgabenname in config.KI_AUFGABEN.items():
        if str(aufgabenname).lower() == typ:
            return aufgabenname

    return None


def normalisiere_ki_daten(typ, daten, feldname):
    """
    Wandelt verschiedene KI-Ausgabeformate in ein einheitliches Format:

    [
        {"WortNr": 12, feldname: "hauptbetonung"}
    ]

    Unterstützt:

    1. Neues Kategorie-Dict:
       {
         "hauptbetonung": [12],
         "nebenbetonung": [8, 15]
       }

    2. Sprecher-Format:
       [
         {
           "Sprecher": "Anna",
           "RedeStart": 5,
           "RedeEnde": 8,
           "Rede": "..."
         }
       ]

    3. Altes Listenformat:
       [
         {"WortNr": 12, "pause": "atempause"}
       ]
    """

     # ----------------------------------------------------
    # Kombinationsformat:
    # {
    #   "pause": {...},
    #   "gedanken": {...},
    #   "betonung": {...},
    #   "spannung": {...}
    # }
    # ----------------------------------------------------
    if typ == "kombination" and isinstance(daten, dict):
        kombi_mapping = {
            "pause": "pause",
            "gedanken": "gedanken",
            "betonung": "betonung",
            "spannung": "spannung",
        }

        for untertyp, feld in kombi_mapping.items():
            teil = daten.get(untertyp)

            if not isinstance(teil, dict):
                continue

            for kategorie, wortnrs in teil.items():
                if not isinstance(wortnrs, list):
                    continue

                for wortnr in wortnrs:
                    try:
                        wortnr = int(wortnr)
                    except (ValueError, TypeError):
                        continue

                    normalisiert.append({
                        "WortNr": wortnr,
                        feld: str(kategorie)
                    })

        return normalisiert

    typ = str(typ).lower().strip()
    feldname = str(feldname).strip()
    normalisiert = []

    # ----------------------------------------------------
    # Sprecher / Person Spezialformat
    # ----------------------------------------------------
    if typ in {"person", "sprecher"} and isinstance(daten, list):
        for eintrag in daten:
            if not isinstance(eintrag, dict):
                continue

            sprecher = (
                eintrag.get("Sprecher")
                or eintrag.get("sprecher")
                or eintrag.get("Person")
                or eintrag.get("person")
                or ""
            )

            start = eintrag.get("RedeStart")
            ende = eintrag.get("RedeEnde")

            if not sprecher or start is None or ende is None:
                continue

            try:
                start = int(start)
                ende = int(ende)
            except (ValueError, TypeError):
                continue

            if start > ende:
                start, ende = ende, start

            for wortnr in range(start, ende + 1):
                normalisiert.append({
                    "WortNr": wortnr,
                    feldname: sprecher
                })

        return normalisiert

    # ----------------------------------------------------
    # Neues Dict-Format:
    # {"atempause": [5], "staupause": [11]}
    # ----------------------------------------------------
    if isinstance(daten, dict):
        for kategorie, wortnrs in daten.items():
            if not isinstance(wortnrs, list):
                continue

            for wortnr in wortnrs:
                try:
                    wortnr = int(wortnr)
                except (ValueError, TypeError):
                    continue

                normalisiert.append({
                    "WortNr": wortnr,
                    feldname: str(kategorie)
                })

        return normalisiert

    # ----------------------------------------------------
    # Altes Listenformat
    # ----------------------------------------------------
    if isinstance(daten, list):
        for eintrag in daten:
            if not isinstance(eintrag, dict):
                continue

            wortnrs = parse_bereich(eintrag.get("WortNr"))
            if not wortnrs:
                continue

            wert = (
                eintrag.get(feldname)
                or eintrag.get(feldname.lower())
                or eintrag.get(feldname.capitalize())
                or eintrag.get(typ)
                or eintrag.get(typ.capitalize())
                or ""
            )

            if wert in ("", None, []):
                continue

            for wortnr in wortnrs:
                normalisiert.append({
                    "WortNr": wortnr,
                    feldname: wert
                })

    return normalisiert


def baue_index(liste, feldname=None):
    """
    Baut:
    {
      feldname: {
        WortNr: [wert1, wert2]
      }
    }

    Unterstützt normale Einträge:
      {"WortNr": 12, "pause": "atempause"}

    und Kombi-Einträge:
      {"WortNr": 12, "pause": "atempause"}
      {"WortNr": 15, "betonung": "hauptbetonung"}
    """

    index = defaultdict(dict)

    for eintrag in liste:
        if not isinstance(eintrag, dict):
            continue

        wortnrs = parse_bereich(eintrag.get("WortNr"))
        if not wortnrs:
            continue

        # Normalfall: bestimmtes Feld
        if feldname:
            feldnamen = [feldname]
        else:
            feldnamen = [
                k for k in eintrag.keys()
                if k != "WortNr" and eintrag.get(k) not in ("", None, [])
            ]

        for feld in feldnamen:
            wert = eintrag.get(feld, "")

            if wert in ("", None, []):
                continue

            for nr in wortnrs:
                index.setdefault(feld, {}).setdefault(nr, []).append(wert)

    return index

def bereinige_werte(werte):
    bereinigt = []

    for wert in werte:
        if isinstance(wert, list):
            for v in wert:
                if v not in ("", None) and v not in bereinigt:
                    bereinigt.append(v)
        else:
            if wert not in ("", None) and wert not in bereinigt:
                bereinigt.append(wert)

    return bereinigt


def merge_einen_abschnitt(
    original_daten,
    annotationsdateien,
    abschnitts_dateiname,
):
    annotationen_daten = defaultdict(list)
    feldnamen_pro_typ = {}

    for dateipfad in annotationsdateien:
        dateiname = dateipfad.name
        typ = extrahiere_typ_aus_ki_dateiname(dateiname, abschnitts_dateiname)

        print(f"[DEBUG] Prüfe KI-Datei: {dateiname}")
        print(f"[DEBUG] Erkannter Typ: {typ}")

        if not typ:
            print(f"[WARNUNG] Konnte Typ nicht aus Dateiname ableiten: {dateiname}")
            continue

        feldname = ermittle_feldname_fuer_typ(typ)

        if not feldname:
            print(f"[WARNUNG] Typ '{typ}' ist nicht in config.KI_AUFGABEN enthalten.")
            continue

        try:
            with open(dateipfad, encoding="utf-8") as f:
                daten = json.load(f)

            normalisiert = normalisiere_ki_daten(
                typ=typ,
                daten=daten,
                feldname=feldname,
            )

            if not normalisiert:
                print(f"[WARNUNG] Keine verwertbaren Daten in: {dateiname}")
                continue

            annotationen_daten[typ].extend(normalisiert)
            feldnamen_pro_typ[typ] = feldname

        except Exception as e:
            print(f"[FEHLER] Fehler beim Laden der Datei {dateiname}: {e}")
            traceback.print_exc()
            continue

    indizes = defaultdict(dict)

    for typ, daten in annotationen_daten.items():
        feldname = feldnamen_pro_typ.get(typ)

        if typ == "kombination":
            print(f"[DEBUG] Erstelle Kombi-Index für Typ '{typ}'")
            teilindizes = baue_index(daten, feldname=None)

            for feld, nr_index in teilindizes.items():
                for nr, werte in nr_index.items():
                    indizes[feld].setdefault(nr, []).extend(werte)

        else:
            if not feldname:
                continue

            print(f"[DEBUG] Erstelle Index für Typ '{typ}' -> Feld '{feldname}'")
            teilindizes = baue_index(daten, feldname)

            for feld, nr_index in teilindizes.items():
                for nr, werte in nr_index.items():
                    indizes[feld].setdefault(nr, []).extend(werte)

        zusammengefuehrt = []

    for eintrag in original_daten:
        wortnr = eintrag.get("WortNr")

        if wortnr is None:
            continue

        try:
            wortnr_int = int(wortnr)
        except (ValueError, TypeError):
            continue

        neuer_eintrag = dict(eintrag)

        for feldname, index in indizes.items():
            werte = index.get(wortnr_int, [])

            if not werte:
                if feldname not in neuer_eintrag:
                    neuer_eintrag[feldname] = ""
                continue

            bereinigt = bereinige_werte(werte)

            if len(bereinigt) == 0:
                neuer_eintrag[feldname] = ""
            elif len(bereinigt) == 1:
                neuer_eintrag[feldname] = bereinigt[0]
            else:
                neuer_eintrag[feldname] = bereinigt

        zusammengefuehrt.append(neuer_eintrag)

    print(f"[INFO] Merge Abschnitt abgeschlossen: {abschnitts_dateiname}")
    return zusammengefuehrt


def Merge_annotationen(
    quellordner_kapitel,
    quellordner_annotationen,
    ziel_ordner,
    ausgewaehlte_kapitel=None,
    progress_callback=None,
):
    print("[DEBUG] Starte Merge_annotationen")
    print(f"[DEBUG] quellordner_kapitel: {quellordner_kapitel}")
    print(f"[DEBUG] quellordner_annotationen: {quellordner_annotationen}")
    print(f"[DEBUG] ziel_ordner: {ziel_ordner}")
    print(f"[DEBUG] ausgewaehlte_kapitel: {ausgewaehlte_kapitel}")

    quellordner_kapitel = Path(quellordner_kapitel)
    quellordner_annotationen = Path(quellordner_annotationen)
    ziel_ordner = Path(ziel_ordner)
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    try:
        abschnittsdateien = ermittle_abschnittsdateien(
            quellordner_kapitel,
            ausgewaehlte_kapitel,
        )

        if not abschnittsdateien:
            print("[WARNUNG] Keine passenden Abschnittsdateien gefunden.")
            return

        gesamt = len(abschnittsdateien)

        for pos, info in enumerate(abschnittsdateien, start=1):
            abschnittspfad = info["pfad"]
            dateiname = info["dateiname"]

            print(f"[DEBUG] Verarbeite Abschnitt {pos}/{gesamt}: {dateiname}")

            if progress_callback:
                progress_callback(round(((pos - 1) / max(gesamt, 1)) * 100, 1))

            with open(abschnittspfad, encoding="utf-8") as f:
                original_daten = json.load(f)

            if not isinstance(original_daten, list):
                print(f"[FEHLER] Originaldatei ist keine Liste: {dateiname}")
                continue

            annotationsdateien = finde_annotationsdateien_fuer_abschnitt(
                quellordner_annotationen,
                dateiname,
            )

            if not annotationsdateien:
                print(f"[INFO] Keine KI-Annotationen gefunden für: {dateiname}")

            zusammengefuehrt = merge_einen_abschnitt(
                original_daten=original_daten,
                annotationsdateien=annotationsdateien,
                abschnitts_dateiname=dateiname,
            )

            zielpfad = ziel_ordner / dateiname

            with open(zielpfad, "w", encoding="utf-8") as f:
                json.dump(zusammengefuehrt, f, ensure_ascii=False, indent=2)

            print(f"[✓] Datei erfolgreich gespeichert: {zielpfad}")

            if progress_callback:
                progress_callback(round((pos / max(gesamt, 1)) * 100, 1))

    except Exception as e:
        print(f"[FEHLER] Merge_annotationen fehlgeschlagen: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    Merge_annotationen(
        quellordner_kapitel=config.GLOBALORDNER["json"],
        quellordner_annotationen=config.GLOBALORDNER["ki"],
        ziel_ordner=config.GLOBALORDNER["merge"],
    )