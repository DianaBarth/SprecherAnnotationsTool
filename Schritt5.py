import os
import json
import glob
import traceback
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import Eingabe.config as config


def lade_personen(kapitel_name):
    config_datei = "Eingabe/kapitel_config.json"
    try:
        with open(config_datei, "r", encoding="utf-8") as f:
            config_data = json.load(f)

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
            wert = eintrag.get(schluessel, "")
            if wert not in (None, "", []):
                index.setdefault(nr, []).append(wert)
    return index


def ist_abschnittsdatei(dateiname):
    """
    Erwartet z. B.:
    Prolog_001_annotierungen.json
    Kapitel 1_002_annotierungen.json
    """
    return re.fullmatch(r".+_\d+_annotierungen\.json", dateiname) is not None


def extrahiere_hauptkapitel_und_index(dateiname_ohne_endung):
    """
    Aus 'Kapitel 1_001_annotierungen' -> ('Kapitel 1', 1)
    """
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
    Sucht KI-Dateien passend zu einem Abschnitt.
    Erwartete Muster z. B.:
    sprecher_Kapitel 1_001_annotierungen_001.json
    emotion_Kapitel 1_001_annotierungen_002.json

    Also allgemein:
    <typ>_<abschnittsdatei ohne .json>_*.json
    """
    quellordner_annotationen = Path(quellordner_annotationen)
    abschnitts_stem = Path(abschnitts_dateiname).stem

    muster = f"*_{abschnitts_stem}_*.json"
    dateien = sorted(quellordner_annotationen.glob(muster))

    print(f"[DEBUG] Suche KI-Dateien mit Muster: {muster}")
    print(f"[DEBUG] Gefundene KI-Dateien: {[d.name for d in dateien]}")
    return dateien


def extrahiere_typ_aus_ki_dateiname(dateiname, abschnitts_dateiname):
    """
    Extrahiert aus z. B.
    'sprecher_Kapitel 1_001_annotierungen_001.json'
    den Typ 'sprecher'
    """
    abschnitts_stem = Path(abschnitts_dateiname).stem
    suffix = f"_{abschnitts_stem}_"

    if suffix not in dateiname:
        return None

    typ = dateiname.split(suffix, 1)[0].lower().strip("_")
    return typ or None

def merge_einen_abschnitt(original_daten, annotationsdateien, abschnitts_dateiname, kein_ig_set=None):
    annotationen_daten = defaultdict(list)
    schluessel_mapping = {wert: wert.capitalize() for wert in config.KI_AUFGABEN.values()}

    print(f"[DEBUG] Schlüssel-Mapping: {schluessel_mapping}")

    for dateipfad in annotationsdateien:
        dateiname = dateipfad.name
        typ = extrahiere_typ_aus_ki_dateiname(dateiname, abschnitts_dateiname)

        print(f"[DEBUG] Prüfe KI-Datei: {dateiname}")
        print(f"[DEBUG] Erkannter Typ: {typ}")

        if not typ:
            print(f"[WARNUNG] Konnte Typ nicht aus Dateiname ableiten: {dateiname}")
            continue

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

    indizes = {}
    for typ, daten in annotationen_daten.items():
        if typ in schluessel_mapping:
            schluessel = schluessel_mapping[typ]
            print(f"[DEBUG] Erstelle Index für Typ '{typ}' -> Schlüssel '{schluessel}'")
            indizes[typ] = baue_index(daten, schluessel)
        else:
            print(f"[WARNUNG] Typ '{typ}' ist nicht in KI_AUFGABEN enthalten und wird ignoriert.")

    zusammengefuehrt = []

    anzahl_ig_ich = 0
    anzahl_ig_leer = 0

    for eintrag in original_daten:
        wortnr = eintrag.get("WortNr")
        if wortnr is None:
            continue

        try:
            wortnr = int(wortnr)
        except (ValueError, TypeError):
            continue

        neuer_eintrag = dict(eintrag)

        # IG immer direkt im Merge setzen
        ig_wert = bestimme_ig_wert_fuer_eintrag(
            neuer_eintrag,
            kein_ig_set or set()
        )
        neuer_eintrag["ig"] = ig_wert

        if ig_wert == "ich":
            anzahl_ig_ich += 1
        else:
            anzahl_ig_leer += 1

        # Andere KI-Annotationen zusätzlich mergen
        for typ, index in indizes.items():
            schluessel = schluessel_mapping[typ]
            werte = index.get(wortnr, [])

            if not werte:
                if schluessel not in neuer_eintrag:
                    neuer_eintrag[schluessel] = ""
            else:
                bereinigt = []
                for wert in werte:
                    if isinstance(wert, list):
                        for v in wert:
                            if v not in ("", None) and v not in bereinigt:
                                bereinigt.append(v)
                    else:
                        if wert not in ("", None) and wert not in bereinigt:
                            bereinigt.append(wert)

                if len(bereinigt) == 0:
                    neuer_eintrag[schluessel] = ""
                elif len(bereinigt) == 1:
                    neuer_eintrag[schluessel] = bereinigt[0]
                else:
                    neuer_eintrag[schluessel] = bereinigt

        zusammengefuehrt.append(neuer_eintrag)

    print(f"[INFO] Merge Abschnitt abgeschlossen: {abschnitts_dateiname}")
    print(f"[INFO]   ig='ich': {anzahl_ig_ich}")
    print(f"[INFO]   ig='':   {anzahl_ig_leer}")

    return zusammengefuehrt


def Merge_annotationen(quellordner_kapitel, quellordner_annotationen, ziel_ordner, ausgewaehlte_kapitel=None, progress_callback=None):
    print("[DEBUG] Starte Merge_annotationen")
    print(f"[DEBUG] quellordner_kapitel: {quellordner_kapitel}")
    print(f"[DEBUG] quellordner_annotationen: {quellordner_annotationen}")
    print(f"[DEBUG] ziel_ordner: {ziel_ordner}")
    print(f"[DEBUG] ausgewaehlte_kapitel: {ausgewaehlte_kapitel}")

    quellordner_kapitel = Path(quellordner_kapitel)
    quellordner_annotationen = Path(quellordner_annotationen)
    ziel_ordner = Path(ziel_ordner)
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    kein_ig_set = lade_kein_ig_liste(quellordner_annotationen)

    try:
        abschnittsdateien = ermittle_abschnittsdateien(quellordner_kapitel, ausgewaehlte_kapitel)

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

            annotationsdateien = finde_annotationsdateien_fuer_abschnitt(
                quellordner_annotationen,
                dateiname
            )

            if not annotationsdateien:
                print(f"[INFO] Keine KI-Annotationen gefunden – setze nur IG automatisch für: {dateiname}")
            else:
                print(f"[INFO] {len(annotationsdateien)} KI-Dateien gefunden für: {dateiname}")

            zusammengefuehrt = merge_einen_abschnitt(
                original_daten=original_daten,
                annotationsdateien=annotationsdateien,
                abschnitts_dateiname=dateiname,
                kein_ig_set=kein_ig_set,
            )

            zielpfad = ziel_ordner / dateiname
            with open(zielpfad, "w", encoding="utf-8") as f:
                json.dump(zusammengefuehrt, f, ensure_ascii=False, indent=2)

            print(f"[✓] Datei erfolgreich gespeichert: {zielpfad}")

            # Optional: kurzer IG-Check
            anzahl_ich = sum(1 for e in zusammengefuehrt if e.get("ig") == "ich")
            print(f"[INFO]   ig='ich': {anzahl_ich}")

            if progress_callback:
                progress_callback(round((pos / max(gesamt, 1)) * 100, 1))

    except Exception as e:
        print(f"[FEHLER] Merge_annotationen fehlgeschlagen: {e}")
        traceback.print_exc()
        # ----------------------------------------------------
# IG-Update
# ----------------------------------------------------

def lade_ig_mapping_aus_ordner(satz_ordner, ig_ordner, kapitelname):
    satz_ordner = Path(satz_ordner)
    ig_ordner = Path(ig_ordner)

    pattern = re.compile(re.escape(kapitelname) + r"_ig_abschnitt_\d{3}\.txt$")
    ig_mapping = {}

    satz_dateien = sorted([f for f in satz_ordner.iterdir() if pattern.match(f.name)])

    for satz_datei in satz_dateien:
        ig_datei = ig_ordner / satz_datei.name
        if not ig_datei.exists():
            print(f"[WARNUNG] Keine IG-Datei gefunden für {satz_datei.name}, überspringe.")
            continue

        with open(satz_datei, "r", encoding="utf-8") as f:
            tokens = [t.strip() for t in f.read().split(";") if t.strip()]

        with open(ig_datei, "r", encoding="utf-8") as f:
            ig_werte = [i.strip() for i in f.read().split(";") if i.strip()]

        if len(tokens) != len(ig_werte):
            print(
                f"[WARNUNG] Ungleiche Anzahl Tokens ({len(tokens)}) und IG-Werte ({len(ig_werte)}) "
                f"in Datei {satz_datei.name}"
            )

        for token, ig_wert in zip(tokens, ig_werte):
            ig_mapping[token] = ig_wert

    print(f"[INFO] {len(ig_mapping)} Token-IG-Paare geladen für Kapitel {kapitelname}")
    return ig_mapping


def lade_kein_ig_liste(ig_ordner):
    ig_ordner = Path(ig_ordner)
    datei = ig_ordner / "keinIG.txt"

    if not datei.exists():
        print(f"[WARNUNG] keine keinIG.txt gefunden: {datei}")
        return set()

    kein_ig = set()

    with open(datei, "r", encoding="utf-8") as f:
        for zeile in f:
            wort = zeile.strip().lower()
            if wort:
                kein_ig.add(wort)

    print(f"[INFO] {len(kein_ig)} Einträge aus keinIG.txt geladen.")
    return kein_ig


def bereinige_token_fuer_ig(token):
    token = normalisiere_ig_token(token, lowercase=True)
    token = re.sub(r"[^\wäöüß]", "", token).strip()
    return token


def update_json_with_ig_annotations(json_ordner, ausgabe_ordner, satz_ordner, ig_ordner, kapitelname):
    """
    Neues, vereinfachtes IG-System:
    - alles mit 'ig' bekommt standardmäßig 'ich'
    - Ausnahmen aus keinIG.txt bleiben leer
    """
    json_ordner = Path(json_ordner)
    ausgabe_ordner = Path(ausgabe_ordner)
    ausgabe_ordner.mkdir(parents=True, exist_ok=True)

    kein_ig_set = lade_kein_ig_liste(ig_ordner)

    dateien = sorted(json_ordner.glob(f"{kapitelname}_*_annotierungen.json"))
    if not dateien:
        print(f"[WARNUNG] Keine JSON-Dateien gefunden für Kapitel {kapitelname}")
        return

    for json_datei in dateien:
        with open(json_datei, "r", encoding="utf-8") as f:
            daten = json.load(f)

        anzahl_ich = 0
        anzahl_leer = 0

        for eintrag in daten:
            token = (
                eintrag.get("tokenInklZahlwoerter")
                or eintrag.get("token")
                or ""
            )

            token_clean = bereinige_token_fuer_ig(token)

            if not token_clean:
                eintrag["ig"] = ""
                anzahl_leer += 1
                continue

            if "ig" in token_clean and token_clean not in kein_ig_set:
                eintrag["ig"] = "ich"
                anzahl_ich += 1
            else:
                eintrag["ig"] = ""
                anzahl_leer += 1

        ausgabe_datei = ausgabe_ordner / json_datei.name
        with open(ausgabe_datei, "w", encoding="utf-8") as f_out:
            json.dump(daten, f_out, ensure_ascii=False, indent=2)

        print(f"[INFO] Aktualisierte Datei gespeichert: {ausgabe_datei}")
        print(f"[INFO]   ig='ich': {anzahl_ich}")
        print(f"[INFO]   ig='':   {anzahl_leer}")

def bestimme_ig_wert_fuer_eintrag(eintrag, kein_ig_set):
    """
    Bestimmt den IG-Wert für einen JSON-Eintrag.
    Standard:
    - enthält das Token 'ig'
    - und steht nicht in keinIG.txt
    => 'ich'
    Sonst leer.
    """
    token = (
        eintrag.get("tokenInklZahlwoerter")
        or eintrag.get("token")
        or ""
    )

    token_clean = bereinige_token_fuer_ig(token)

    if not token_clean:
        return ""

    if "ig" in token_clean and token_clean not in kein_ig_set:
        return "ich"

    return ""

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
    nur_tokens_mit_ig=True,
):
    """
    Extrahiert IG-Wörter aus *_annotierungen.json-Dateien,
    zählt Häufigkeiten und bündelt einfache Flexionen.

    Ausgabeformat pro Zeile:
        basiswort | haeufigkeit | flexion1, flexion2, ...

    Beispiel:
        wichtig | 37 | wichtige, wichtigem, wichtigen, wichtiger, wichtiges
    """
    from collections import defaultdict, Counter

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

    # basis -> Counter aller konkreten Formen
    basis_zu_formen = defaultdict(Counter)

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

                # Satzzeichen entfernen
                clean_token = re.sub(r"[^\wäöüÄÖÜß]", "", token).strip()

                if not clean_token:
                    continue

                if len(clean_token) < min_len:
                    continue

                if nur_tokens_mit_ig and "ig" not in clean_token.lower():
                    continue

                basis = bestimme_flexions_basis(clean_token)
                basis_zu_formen[basis][clean_token] += 1

        except Exception as e:
            print(f"[FEHLER] Fehler beim Lesen von {datei.name}: {e}")

    if not basis_zu_formen:
        print("[WARNUNG] Keine passenden IG-Wörter gefunden.")
        return

    # Sortierung: zuerst nach Häufigkeit absteigend, dann alphabetisch
    basiswoerter = list(basis_zu_formen.keys())

    def sortierschluessel(basis):
        gesamt = sum(basis_zu_formen[basis].values())
        if sort_case_insensitive:
            return (-gesamt, basis.lower())
        return (-gesamt, basis)

    basiswoerter = sorted(basiswoerter, key=sortierschluessel)

    ausgabe_datei.parent.mkdir(parents=True, exist_ok=True)

    anzahl_basiswoerter = 0
    anzahl_token_vorkommen = 0

    with open(ausgabe_datei, "w", encoding="utf-8") as f:
        for basis in basiswoerter:
            formen_counter = basis_zu_formen[basis]
            gesamt = sum(formen_counter.values())
            anzahl_token_vorkommen += gesamt
            anzahl_basiswoerter += 1

            # Varianten außer der Basis
            flexionen = sorted(
                [form for form in formen_counter.keys() if form != basis],
                key=lambda x: x.lower()
            )

            flexionen_text = ", ".join(flexionen)

            # Format: basis | anzahl | flexionen
            f.write(f"{basis} | {gesamt} | {flexionen_text}\n")

    print(f"[INFO] IG-Basiswörter extrahiert: {anzahl_basiswoerter}")
    print(f"[INFO] Gesamte IG-Vorkommen: {anzahl_token_vorkommen}")
    print(f"[✓] IG-Wortliste gespeichert: {ausgabe_datei}")

def bestimme_flexions_basis(token: str) -> str:
    """
    Heuristische Basisform für einfache Flexionsbündelung.
    Beispiel:
    wichtig, wichtige, wichtigem, wichtigen -> wichtig
    König, Könige, Königen -> könig

    Achtung: bewusst einfach gehalten, kein echtes Lemmatizing.
    """
    token = token.strip().lower()

    # Nur einfache, häufige Flexionsendungen
    endungen = [
        "eren", "erem", "erer", "eres",
        "sten", "stem", "ster", "stes",
        "ern",
        "en", "em", "er", "es", "e", "n", "s"
    ]

    for endung in endungen:
        if token.endswith(endung) and len(token) > len(endung) + 2:
            kandidat = token[:-len(endung)]

            # Nur dann kürzen, wenn die gekürzte Form noch sinnvoll wirkt
            if "ig" in kandidat:
                return kandidat

    return token







if __name__ == "__main__":
    print("[DEBUG] Starte IG-Extraktion...")

    extrahiere_ig_woerter_aus_json(
        json_ordner=config.GLOBALORDNER["json"],
        ausgabe_datei=Path(config.GLOBALORDNER["ki"]) / "ig_woerter.txt",
        lowercase=True,
        sort_case_insensitive=True,
        min_len=2,
        verwende_tokenInklZahlwoerter=True,
        ignoriere_spezialtokens=True,
        nur_tokens_mit_ig=True,
    )

    print("[DEBUG] IG-Extraktion beendet.")
 