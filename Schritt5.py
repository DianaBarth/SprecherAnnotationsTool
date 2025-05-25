import os
import json
import glob
import traceback
import shutil
from collections import defaultdict
import Eingabe.config as config # Importiere das komplette config-Modul

# Personen aus ZusatzInfo_2 der kapitel_config.json extrahieren
def lade_personen(kapitel_name):
    config_datei = "Eingabe/kapitel_config.json"
    try:
        with open(config_datei, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        # Annahme: ZusatzInfo_2 enthält eine Liste von Personen
        zusatzinfo_2 = config_data.get(kapitel_name, {}).get("ZusatzInfo_2", [])
        return zusatzinfo_2
    except Exception as e:
        print(f"[FEHLER] Personen aus ZusatzInfo_2 konnten nicht geladen werden: {e}")
        return []

def baue_annotationstypen(kapitel_name):
    personen = lade_personen(kapitel_name)

    annotationstypen = {}
    for aufgaben_nr, typ_name in config.KI_AUFGABEN.items():
        if typ_name == "person":
            annotationstypen[typ_name] = personen
        else:
            eintraege = config.AUFGABEN_ANNOTATIONEN.get(aufgaben_nr, [])
            namen = [eintrag["name"] for eintrag in eintraege if "name" in eintrag]
            annotationstypen[typ_name] = namen

    return annotationstypen

schluessel_mapping = {wert: wert.capitalize() for wert in config.KI_AUFGABEN.values()}

def parse_bereich(bereich):
    if not bereich:
        print("[WARNUNG] 'WortNr' fehlt oder ist leer – Eintrag wird übersprungen.")
        return []
    bereich = str(bereich)
    if ":" in bereich:
        try:
            start, ende = map(int, bereich.split(":"))
            return list(range(start, ende + 1))
        except ValueError:
            print(f"[FEHLER] Ungültiger Bereich: {bereich}")
            return []
    else:
        try:
            return [int(bereich)]
        except ValueError:
            print(f"[FEHLER] Ungültiger Einzelwert für WortNr: {bereich}")
            return []

def baue_index(liste, schluessel):
    index = {}
    for eintrag in liste:
        wortnrs = parse_bereich(eintrag.get("WortNr"))
        for nr in wortnrs:
            index.setdefault(nr, []).append(eintrag.get(schluessel, ""))
    return index

def ermittele_kapitel_namen(quellordner_kapitel):
    dateien = glob.glob(os.path.join(quellordner_kapitel, "*_annotierungen.json"))
    if not dateien:
        print("[FEHLER] Keine '_annotierungen.json'-Dateien im Quellordner gefunden.")
        return []
    kapitel_namen = [os.path.basename(datei).replace("_annotierungen.json", "") for datei in dateien]
    return kapitel_namen


def Merge_annotationen(quellordner_kapitel, quellordner_annotationen, ziel_ordner, ausgewaehlte_kapitel=None, progress_callback=None):
    print("[DEBUG] Starte Merge_annotationen")
    print(f"[DEBUG] quellordner_kapitel: {quellordner_kapitel}")
    print(f"[DEBUG] quellordner_annotationen: {quellordner_annotationen}")
    print(f"[DEBUG] ziel_ordner: {ziel_ordner}")
    print(f"[DEBUG] ausgewaehlte_kapitel: {ausgewaehlte_kapitel}")

    try:
        kapitel_namen = ermittele_kapitel_namen(quellordner_kapitel)
        print(f"[DEBUG] Erkannte Kapitel: {kapitel_namen}")
        if not kapitel_namen:
            print("[WARNUNG] Keine Kapitel erkannt.")
            return

        if ausgewaehlte_kapitel is not None:
            kapitel_namen = [k for k in kapitel_namen if k in ausgewaehlte_kapitel]
            print(f"[DEBUG] Gefilterte Kapitel: {kapitel_namen}")

        for kapitel_name in kapitel_namen:
            print(f"[DEBUG] Verarbeite Kapitel: {kapitel_name}")
            if progress_callback:
                progress_callback(0)

            datei_original = os.path.join(quellordner_kapitel, f"{kapitel_name}_annotierungen.json")
            print(f"[DEBUG] Lade Originaldatei: {datei_original}")
            with open(datei_original, encoding="utf-8") as f:
                original_daten = json.load(f)

            muster = os.path.join(quellordner_annotationen, f"*{kapitel_name}_annotierungen_*.json")
            dateien = glob.glob(muster)
            print(f"[DEBUG] Gefundene Annotationsdateien ({len(dateien)}): {dateien}")

            if not dateien:
                os.makedirs(ziel_ordner, exist_ok=True)
                datei_ziel = os.path.join(ziel_ordner, f"{kapitel_name}_gesamt.json")
                with open(datei_ziel, "w", encoding="utf-8") as f:
                    json.dump(original_daten, f, ensure_ascii=False, indent=2)
                print(f"[INFO] Keine Annotationen gefunden – Originaldatei kopiert: {datei_ziel}")
                if progress_callback:
                    progress_callback(100)
                continue

            annotationen_daten = defaultdict(list)
            anzahl = len(dateien)

            for i, dateipfad in enumerate(dateien):
                dateiname = os.path.basename(dateipfad)
                teile = dateiname.split("_")
                print(f"[DEBUG] Prüfe Datei: {dateiname}")
                if len(teile) < 3:
                    print(f"[WARNUNG] Datei übersprungen (ungültiger Name): {dateiname}")
                    continue

                typ = teile[0].lower()
                print(f"[DEBUG] Annotations-Typ erkannt: {typ}")
                try:
                    with open(dateipfad, encoding="utf-8") as f:
                        daten = json.load(f)
                    if not isinstance(daten, list) or not all(isinstance(e, dict) for e in daten):
                        print(f"[FEHLER] Datei hat ungültiges Format: {dateipfad}")
                        continue
                    annotationen_daten[typ].extend(daten)
                except Exception as e:
                    print(f"[FEHLER] Fehler beim Laden der Datei {dateiname}: {e}")
                    continue

                if progress_callback:
                    progress_callback(round((i + 1) / (anzahl + 3), 3) * 100)

            schluessel_mapping = {wert: wert.capitalize() for wert in config.KI_AUFGABEN.values()}
            print(f"[DEBUG] Schlüssel-Mapping: {schluessel_mapping}")

            indizes = {}
            for typ, daten in annotationen_daten.items():
                if typ in schluessel_mapping:
                    print(f"[DEBUG] Erstelle Index für Typ: {typ}")
                    indizes[typ] = baue_index(daten, schluessel_mapping[typ])

            if progress_callback:
                progress_callback(round((anzahl + 1) / (anzahl + 3), 3) * 100)

            zusammengeführt = []
            for eintrag in original_daten:
                wortnr = eintrag.get("WortNr")
                if wortnr is None:
                    continue
                try:
                    wortnr = int(wortnr)
                except ValueError:
                    continue

                neuer_eintrag = {
                    "KapitelName": eintrag.get("KapitelName"),
                    "WortNr": wortnr,
                    "token": eintrag.get("token"),
                    "annotation": eintrag.get("annotation", [])
                }

                for typ, index in indizes.items():
                    schluessel = schluessel_mapping[typ]
                    neuer_eintrag[schluessel] = index.get(wortnr, "")

                zusammengeführt.append(neuer_eintrag)

            os.makedirs(ziel_ordner, exist_ok=True)
            datei_ziel = os.path.join(ziel_ordner, f"{kapitel_name}_gesamt.json")
            with open(datei_ziel, "w", encoding="utf-8") as f:
                json.dump(zusammengeführt, f, ensure_ascii=False, indent=2)

            print(f"[✓] Datei erfolgreich gespeichert: {datei_ziel}")

            if progress_callback:
                progress_callback(100)

    except Exception as e:
        print(f"[FEHLER] Schritt 8.1 fehlgeschlagen: {e}")
        traceback.print_exc()

    
    try:
        kapitel_namen = ermittele_kapitel_namen(quellordner_kapitel)
        if not kapitel_namen:
            return

        if ausgewaehlte_kapitel is not None:
            kapitel_namen = [k for k in kapitel_namen if k in ausgewaehlte_kapitel]

        for kapitel_name in kapitel_namen:
            if progress_callback:
                progress_callback(0)

            # Originaltext laden
            datei_original = os.path.join(quellordner_kapitel, f"{kapitel_name}_annotierungen.json")
            with open(datei_original, encoding="utf-8") as f:
                original_daten = json.load(f)

            # Alle passenden Annotationen-Dateien
            muster = os.path.join(quellordner_annotationen, f"*{kapitel_name}_annotierungen_*.json")
            dateien = glob.glob(muster)

            # NEU: Wenn keine Annotationen vorhanden -> Originaldatei kopieren
            if not dateien:
                os.makedirs(ziel_ordner, exist_ok=True)
                datei_ziel = os.path.join(ziel_ordner, f"{kapitel_name}_gesamt.json")
                with open(datei_ziel, "w", encoding="utf-8") as f:
                    json.dump(original_daten, f, ensure_ascii=False, indent=2)
                print(f"[INFO] Keine Annotationen gefunden – Originaldatei kopiert: {datei_ziel}")
                if progress_callback:
                    progress_callback(100)
                continue

            anzahl = len(dateien)
            annotationen_daten = defaultdict(list)

            for i, dateipfad in enumerate(dateien):
                dateiname = os.path.basename(dateipfad)
                teile = dateiname.split("_")
                if len(teile) < 3:
                    print(f"[WARNUNG] Datei übersprungen (ungültiger Name): {dateiname}")
                    continue

                typ = teile[0].lower()
                with open(dateipfad, encoding="utf-8") as f:
                    daten = json.load(f)
                    if not isinstance(daten, list) or not all(isinstance(e, dict) for e in daten):
                        print(f"[FEHLER] Datei hat ungültiges Format: {dateipfad}")
                        continue
                    annotationen_daten[typ].extend(daten)

                if progress_callback:
                    progress_callback(round((i + 1) / (anzahl + 3), 3)*100)

            schluessel_mapping = {wert: wert.capitalize() for wert in config.KI_AUFGABEN.values()}
            indizes = {}
            for typ, daten in annotationen_daten.items():
                if typ in schluessel_mapping:
                    indizes[typ] = baue_index(daten, schluessel_mapping[typ])
            if progress_callback:
                progress_callback(round((anzahl + 1) / (anzahl + 3), 3)*100)

            zusammengeführt = []
            for eintrag in original_daten:
                wortnr = eintrag.get("WortNr")
                if wortnr is None:
                    continue
                try:
                    wortnr = int(wortnr)
                except ValueError:
                    continue

                neuer_eintrag = {
                    "KapitelName": eintrag.get("KapitelName"),
                    "WortNr": wortnr,
                    "token": eintrag.get("token"),
                    "annotation": eintrag.get("annotation", [])
                }

                for typ, index in indizes.items():
                    schluessel = schluessel_mapping[typ]
                    neuer_eintrag[schluessel] = index.get(wortnr, "")

                zusammengeführt.append(neuer_eintrag)

            os.makedirs(ziel_ordner, exist_ok=True)
            datei_ziel = os.path.join(ziel_ordner, f"{kapitel_name}_gesamt.json")
            with open(datei_ziel, "w", encoding="utf-8") as f:
                json.dump(zusammengeführt, f, ensure_ascii=False, indent=2)

            print(f"[✓] Datei erfolgreich gespeichert: {datei_ziel}")

            if progress_callback:
                progress_callback(100)

    except Exception as e:
        print(f"[FEHLER] Schritt 8.1 fehlgeschlagen: {e}")
        traceback.print_exc()