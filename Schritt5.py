import json
import re
import traceback
from pathlib import Path


SATZENDE_TOKENS = {".", "!", "?", "…"}
KOMMA_TOKENS = {","}
GEDANKEN_PAUSE_TOKENS = {"–", "—", "...", "…"}
KONNEKTOREN = {"und", "aber", "doch", "denn"}
SPANNUNG_STARTER = {"plötzlich", "dann"}

STOPWOERTER = {
    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einer", "einem", "einen", "eines",
    "und", "oder", "aber", "doch", "denn",
    "ich", "du", "er", "sie", "es", "wir", "ihr",
    "mich", "dich", "sich", "uns", "euch",
    "mein", "dein", "sein", "ihr", "unser", "euer",
    "ist", "war", "bin", "bist", "sind", "seid", "waren",
    "hat", "habe", "hast", "haben", "hatte", "hatten",
    "zu", "in", "im", "am", "an", "auf", "mit", "von", "für",
    "nicht", "nur", "noch", "schon", "so", "da", "dort",
}


def leeres_kombi_json():
    return {
        "pause": {
            "atempause": [],
            "staupause": []
        },
        "gedanken": {
            "gedanken_weiter": [],
            "gedanken_ende": [],
            "pause_gedanken": []
        },
        "betonung": {
            "hauptbetonung": [],
            "nebenbetonung": []
        },
        "spannung": {
            "Starten": [],
            "Halten": [],
            "Stoppen": []
        }
    }


def token_text(eintrag):
    return str(
        eintrag.get("tokenInklZahlwoerter")
        or eintrag.get("token")
        or ""
    ).strip()


def token_norm(eintrag):
    return token_text(eintrag).lower().strip()


def wortnr(eintrag):
    try:
        nr = eintrag.get("WortNr")
        if nr is None or nr == "":
            return None
        return int(nr)
    except Exception:
        return None


def ist_satzzeichen_ohne_space_davor(eintrag):
    annotation = str(eintrag.get("annotation", "") or "")
    return "satzzeichenOhneSpaceDavor" in annotation


def ist_satzende(eintrag):
    return (
        ist_satzzeichen_ohne_space_davor(eintrag)
        and token_text(eintrag) in SATZENDE_TOKENS
    )


def ist_wort(eintrag):
    tok = token_text(eintrag)
    return bool(re.fullmatch(r"[A-Za-zÄÖÜäöüß]+", tok))


def ist_stopwort(eintrag):
    return token_norm(eintrag) in STOPWOERTER


def ist_inhaltswort(eintrag):
    return ist_wort(eintrag) and not ist_stopwort(eintrag)


def splitte_saetze(tokens):
    saetze = []
    aktueller_satz = []

    for eintrag in tokens:
        if not isinstance(eintrag, dict):
            continue

        aktueller_satz.append(eintrag)

        if ist_satzende(eintrag):
            saetze.append(aktueller_satz)
            aktueller_satz = []

    if aktueller_satz:
        saetze.append(aktueller_satz)

    return saetze


def gueltige_wortnr_set(tokens):
    return {
        wortnr(t)
        for t in tokens
        if isinstance(t, dict) and wortnr(t) is not None
    }


def erste_inhaltswort_nr(satz):
    for t in satz:
        if ist_inhaltswort(t):
            return wortnr(t)
    return None


def letzte_wortnr(satz):
    for t in reversed(satz):
        nr = wortnr(t)
        if nr is not None:
            return nr
    return None


def wort_tokens(satz):
    return [
        t for t in satz
        if ist_wort(t) and wortnr(t) is not None
    ]


def inhaltswort_tokens(satz):
    return [
        t for t in satz
        if ist_inhaltswort(t) and wortnr(t) is not None
    ]


def satz_wortanzahl(satz):
    return len(wort_tokens(satz))


def erstes_wort_norm(satz):
    for t in satz:
        if ist_wort(t):
            return token_norm(t)
    return ""


def satz_beginnt_mit_auf_einmal(satz):
    woerter = [token_norm(t) for t in satz if ist_wort(t)]
    return len(woerter) >= 2 and woerter[0] == "auf" and woerter[1] == "einmal"


def finde_vorherige_wortnr(tokens, index):
    for i in range(index - 1, -1, -1):
        if not isinstance(tokens[i], dict):
            continue

        if ist_wort(tokens[i]):
            nr = wortnr(tokens[i])
            if nr is not None:
                return nr

    return None


def fuege_eindeutig(ziel_liste, nr, gueltige_nr):
    if nr is None:
        return

    try:
        nr = int(nr)
    except Exception:
        return

    if nr not in gueltige_nr:
        return

    if nr not in ziel_liste:
        ziel_liste.append(nr)


def regelbasierte_kombination(tokens):
    result = leeres_kombi_json()

    if not isinstance(tokens, list) or not tokens:
        return result

    gueltige_nr = gueltige_wortnr_set(tokens)
    saetze = splitte_saetze(tokens)

    spannung_aktiv = False

    for satz_index, satz in enumerate(saetze, start=1):
        if not satz:
            continue

        wortanzahl = satz_wortanzahl(satz)
        erstes_wort = erstes_wort_norm(satz)
        endet_mit_satzende = any(ist_satzende(t) for t in satz)

        # ----------------------------------------------------
        # PAUSEN
        # ----------------------------------------------------
        komma_kandidaten = [
            t for t in satz
            if ist_satzzeichen_ohne_space_davor(t)
            and token_text(t) in KOMMA_TOKENS
            and wortnr(t) is not None
        ]

        if komma_kandidaten:
            satz_start_nr = erste_inhaltswort_nr(satz) or wortnr(satz[0]) or 0

            bestes_komma = max(
                komma_kandidaten,
                key=lambda t: abs((wortnr(t) or 0) - satz_start_nr)
            )

            fuege_eindeutig(
                result["pause"]["atempause"],
                wortnr(bestes_komma),
                gueltige_nr
            )

        if endet_mit_satzende and wortanzahl > 6:
            fuege_eindeutig(
                result["pause"]["staupause"],
                letzte_wortnr(satz),
                gueltige_nr
            )

        # ----------------------------------------------------
        # GEDANKEN
        # ----------------------------------------------------
        if erstes_wort in KONNEKTOREN:
            fuege_eindeutig(
                result["gedanken"]["gedanken_weiter"],
                erste_inhaltswort_nr(satz),
                gueltige_nr
            )

        if endet_mit_satzende and satz_index % 3 == 0:
            fuege_eindeutig(
                result["gedanken"]["gedanken_ende"],
                letzte_wortnr(satz),
                gueltige_nr
            )

        # ----------------------------------------------------
        # BETONUNG
        # ----------------------------------------------------
        betonungs_kandidaten = inhaltswort_tokens(satz)

        if betonungs_kandidaten:
            sortiert = sorted(
                betonungs_kandidaten,
                key=lambda t: (
                    len(token_text(t)),
                    -(wortnr(t) or 0)
                ),
                reverse=True
            )

            fuege_eindeutig(
                result["betonung"]["hauptbetonung"],
                wortnr(sortiert[0]),
                gueltige_nr
            )

            if wortanzahl > 6 and len(sortiert) > 1:
                fuege_eindeutig(
                    result["betonung"]["nebenbetonung"],
                    wortnr(sortiert[1]),
                    gueltige_nr
                )

        # ----------------------------------------------------
        # SPANNUNG
        # ----------------------------------------------------
        startet_spannung = (
            erstes_wort in SPANNUNG_STARTER
            or satz_beginnt_mit_auf_einmal(satz)
        )

        if startet_spannung:
            fuege_eindeutig(
                result["spannung"]["Starten"],
                erste_inhaltswort_nr(satz),
                gueltige_nr
            )
            spannung_aktiv = True

        if wortanzahl > 12:
            woerter = wort_tokens(satz)
            if woerter:
                mitte = woerter[len(woerter) // 2]
                fuege_eindeutig(
                    result["spannung"]["Halten"],
                    wortnr(mitte),
                    gueltige_nr
                )

        if endet_mit_satzende and spannung_aktiv:
            fuege_eindeutig(
                result["spannung"]["Stoppen"],
                letzte_wortnr(satz),
                gueltige_nr
            )
            spannung_aktiv = False

    # --------------------------------------------------------
    # GEDANKENPAUSEN BEI GEDANKENSTRICH / ELLIPSE
    # --------------------------------------------------------
    for idx, t in enumerate(tokens):
        if not isinstance(t, dict):
            continue

        if token_text(t) in GEDANKEN_PAUSE_TOKENS:
            nr_davor = finde_vorherige_wortnr(tokens, idx)

            fuege_eindeutig(
                result["gedanken"]["pause_gedanken"],
                nr_davor,
                gueltige_nr
            )

    # --------------------------------------------------------
    # FINAL: sortieren, Duplikate entfernen
    # --------------------------------------------------------
    for hauptkey in result:
        for subkey in result[hauptkey]:
            result[hauptkey][subkey] = sorted(set(result[hauptkey][subkey]))

    return result


def ermittle_kapitel_abschnitt_id(json_datei):
    json_datei = Path(json_datei)

    with open(json_datei, "r", encoding="utf-8") as f:
        daten = json.load(f)

    kapitelnummer = None

    if isinstance(daten, list):
        for eintrag in daten:
            if (
                isinstance(eintrag, dict)
                and eintrag.get("KapitelNummer") not in (None, "")
            ):
                kapitelnummer = eintrag.get("KapitelNummer")
                break

    if kapitelnummer is None:
        raise ValueError(f"Keine KapitelNummer in Datei gefunden: {json_datei.name}")

    kapitel_id = f"{int(kapitelnummer):03d}"

    match = re.search(r"_(\d+)_annotierungen\.json$", json_datei.name)

    if match:
        abschnitt_id = f"{int(match.group(1)):03d}"
    else:
        abschnitt_id = "001"

    return kapitel_id, abschnitt_id


def speichere_regel_json(ki_ordner, json_datei, daten, laufende_nr=1):
    ki_ordner = Path(ki_ordner)
    ki_ordner.mkdir(parents=True, exist_ok=True)

    kapitel_id, abschnitt_id = ermittle_kapitel_abschnitt_id(json_datei)

    ausgabe_datei = ki_ordner / (
        f"KI_KOMBINATION_{kapitel_id}_{abschnitt_id}_{laufende_nr:03}.json"
    )

    with open(ausgabe_datei, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Regelbasierte Kombinationsdatei gespeichert: {ausgabe_datei}")

    return ausgabe_datei


def verarbeite_regelbasiert(dateipfad, ki_ordner, force=False):
    print(f"[DEBUG] Schritt5_regelbasiert gestartet für {dateipfad}")

    try:
        json_datei = Path(dateipfad)

        if not json_datei.exists():
            print(f"[WARNUNG] JSON-Datei existiert nicht: {json_datei}")
            return None

        if not json_datei.name.endswith("_annotierungen.json"):
            print(f"[WARNUNG] Keine Annotierungsdatei, überspringe: {json_datei.name}")
            return None

        ki_ordner = Path(ki_ordner)
        ki_ordner.mkdir(parents=True, exist_ok=True)

        kapitel_id, abschnitt_id = ermittle_kapitel_abschnitt_id(json_datei)

        ziel_datei = ki_ordner / (
            f"KI_KOMBINATION_{kapitel_id}_{abschnitt_id}_001.json"
        )

        if ziel_datei.exists() and not force:
            print(f"[INFO] Regel-Datei existiert bereits, überspringe: {ziel_datei}")
            return ziel_datei

        with open(json_datei, "r", encoding="utf-8") as f:
            tokens = json.load(f)

        if not isinstance(tokens, list):
            print(f"[WARNUNG] JSON ist keine Tokenliste: {json_datei}")
            return None

        daten = regelbasierte_kombination(tokens)

        ausgabe_datei = speichere_regel_json(
            ki_ordner=ki_ordner,
            json_datei=json_datei,
            daten=daten,
            laufende_nr=1
        )

        print(f"[INFO] Regelbasierte Annotation abgeschlossen: {json_datei.name}")

        return ausgabe_datei

    except Exception as e:
        print(f"[FEHLER] Fehler in Schritt5_regelbasiert bei {dateipfad}: {e}")
        traceback.print_exc()
        return None


def verarbeite_ordner_regelbasiert(json_ordner, ki_ordner, force=False):
    json_ordner = Path(json_ordner)
    ki_ordner = Path(ki_ordner)

    if not json_ordner.exists():
        print(f"[FEHLER] JSON-Ordner existiert nicht: {json_ordner}")
        return []

    json_dateien = sorted(json_ordner.glob("*_annotierungen.json"))

    if not json_dateien:
        print(f"[WARNUNG] Keine *_annotierungen.json-Dateien gefunden in: {json_ordner}")
        return []

    print(f"[INFO] Starte regelbasierte Annotation für {len(json_dateien)} Datei(en).")

    erzeugte_dateien = []

    for json_datei in json_dateien:
        result = verarbeite_regelbasiert(
            dateipfad=json_datei,
            ki_ordner=ki_ordner,
            force=force
        )

        if result:
            erzeugte_dateien.append(result)

    print(f"[INFO] Schritt5 regelbasiert abgeschlossen. Dateien: {len(erzeugte_dateien)}")

    return erzeugte_dateien