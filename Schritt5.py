import json
import re
import traceback
from pathlib import Path
from collections import defaultdict


# ------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------

ERLAUBTE_FELDER_PRO_PASS = {
    "prosodie": {"betonung", "pause", "gedanken", "spannung"},
    "sprecher": {"person"},
    "person": {"person"},
    "ig": {"ig"},
}

NIEMALS_KI_UEBERSCHREIBEN = {
    "token",
    "tokenInklZahlwoerter",
    "annotation",
    "position",
    "kombination",
}


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

def parse_bereich(wert):
    if wert in (None, ""):
        return []

    wert = str(wert).strip()

    if ":" in wert:
        try:
            start, ende = map(int, wert.split(":", 1))
            if start > ende:
                start, ende = ende, start
            return list(range(start, ende + 1))
        except ValueError:
            return []

    try:
        return [int(wert)]
    except ValueError:
        return []


def lade_json_robust(dateipfad):
    text = Path(dateipfad).read_text(encoding="utf-8").strip()

    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Erstes JSON-Objekt extrahieren
    start = text.find("{")
    if start == -1:
        raise ValueError("Kein JSON-Objekt gefunden.")

    tiefe = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            tiefe += 1
        elif ch == "}":
            tiefe -= 1
            if tiefe == 0:
                return json.loads(text[start:i + 1])

    raise ValueError("Kein vollständiges JSON-Objekt gefunden.")


def key_fuer_wort(eintrag):
    try:
        return str(eintrag["KapitelNummer"]), int(eintrag["WortNr"])
    except Exception:
        return None


# ------------------------------------------------------------
# KI-Output normalisieren
# ------------------------------------------------------------

def normalisiere_ki_output(daten, pass_typ, default_kapitelnummer=None):
    """
    Gibt eine flache Update-Liste zurück:

    [
      {
        "KapitelNummer": "1",
        "WortNr": 874,
        "feld": "betonung",
        "wert": "hauptbetonung"
      }
    ]
    """

    pass_typ = str(pass_typ).lower().strip()
    erlaubte_felder = ERLAUBTE_FELDER_PRO_PASS.get(pass_typ)

    if not erlaubte_felder:
        raise ValueError(f"Unbekannter KI-Pass: {pass_typ}")

    updates = []
    warnungen = []

    # --------------------------------------------------------
    # Format:
    # {
    #   "pause": {"atempause": [1, 2]},
    #   "betonung": {"hauptbetonung": [3]}
    # }
    # --------------------------------------------------------
    if isinstance(daten, dict):
        for feld, kategorien in daten.items():
            feld = str(feld).strip()

            if feld not in erlaubte_felder:
                warnungen.append(f"Ungültiges Feld für Pass '{pass_typ}': {feld}")
                continue

            if not isinstance(kategorien, dict):
                warnungen.append(f"Feld '{feld}' enthält kein Kategorie-Dict.")
                continue

            for wert, wortnrs in kategorien.items():
                if not isinstance(wortnrs, list):
                    warnungen.append(f"'{feld}.{wert}' ist keine Liste.")
                    continue

                for wortnr in wortnrs:
                    try:
                        wortnr = int(wortnr)
                    except Exception:
                        warnungen.append(f"Ungültige WortNr bei '{feld}.{wert}': {wortnr}")
                        continue

                    updates.append({
                        "KapitelNummer": str(default_kapitelnummer) if default_kapitelnummer is not None else None,
                        "WortNr": wortnr,
                        "feld": feld,
                        "wert": str(wert),
                    })

        return updates, warnungen

    # --------------------------------------------------------
    # Sprecherformat:
    # [
    #   {"Sprecher": "Anna", "RedeStart": 5, "RedeEnde": 8}
    # ]
    # --------------------------------------------------------
    if pass_typ in {"sprecher", "person"} and isinstance(daten, list):
        for eintrag in daten:
            if not isinstance(eintrag, dict):
                warnungen.append("Sprecher-Eintrag ist kein Dict.")
                continue

            sprecher = (
                eintrag.get("Sprecher")
                or eintrag.get("sprecher")
                or eintrag.get("Person")
                or eintrag.get("person")
            )

            start = eintrag.get("RedeStart")
            ende = eintrag.get("RedeEnde")

            if not sprecher or start is None or ende is None:
                warnungen.append(f"Unvollständiger Sprecher-Eintrag: {eintrag}")
                continue

            try:
                start = int(start)
                ende = int(ende)
            except Exception:
                warnungen.append(f"Ungültiger Sprecher-Bereich: {eintrag}")
                continue

            if start > ende:
                start, ende = ende, start

            kapitelnummer = eintrag.get("KapitelNummer", default_kapitelnummer)

            for wortnr in range(start, ende + 1):
                updates.append({
                    "KapitelNummer": str(kapitelnummer) if kapitelnummer is not None else None,
                    "WortNr": wortnr,
                    "feld": "person",
                    "wert": str(sprecher),
                })

        return updates, warnungen

    # --------------------------------------------------------
    # Altes Listenformat:
    # [
    #   {"KapitelNummer": "1", "WortNr": 12, "ig": "ich"}
    # ]
    # --------------------------------------------------------
    if isinstance(daten, list):
        for eintrag in daten:
            if not isinstance(eintrag, dict):
                warnungen.append("Listen-Eintrag ist kein Dict.")
                continue

            wortnrs = parse_bereich(eintrag.get("WortNr"))
            if not wortnrs:
                warnungen.append(f"Fehlende/ungültige WortNr: {eintrag}")
                continue

            kapitelnummer = eintrag.get("KapitelNummer", default_kapitelnummer)

            for feld, wert in eintrag.items():
                if feld in {"KapitelNummer", "WortNr"}:
                    continue

                if feld not in erlaubte_felder:
                    warnungen.append(f"Ungültiges Feld für Pass '{pass_typ}': {feld}")
                    continue

                if wert in ("", None, []):
                    continue

                for wortnr in wortnrs:
                    updates.append({
                        "KapitelNummer": str(kapitelnummer) if kapitelnummer is not None else None,
                        "WortNr": wortnr,
                        "feld": feld,
                        "wert": wert,
                    })

        return updates, warnungen

    raise ValueError(f"Nicht unterstütztes KI-Format für Pass '{pass_typ}'.")


# ------------------------------------------------------------
# Robuster feldbasierter Merge
# ------------------------------------------------------------

def merge_ki_updates(
    original_daten,
    ki_updates,
    pass_typ,
    default_kapitelnummer=None,
    schuetze_manuelle_aenderungen=True,
    source_suffix="_source",
    ki_source_name="ki",
):
    """
    original_daten:
        Liste deiner Wortobjekte.

    ki_updates:
        Bereits normalisierte Updates ODER roher KI-Output.

    pass_typ:
        "prosodie", "sprecher", "person" oder "ig".

    schuetze_manuelle_aenderungen:
        Wenn True, werden Felder mit z.B. pause_source == "manual"
        nicht durch KI überschrieben.
    """

    pass_typ = str(pass_typ).lower().strip()
    erlaubte_felder = ERLAUBTE_FELDER_PRO_PASS.get(pass_typ)

    if not erlaubte_felder:
        raise ValueError(f"Unbekannter KI-Pass: {pass_typ}")

    report = {
        "geschrieben": 0,
        "uebersprungen_manual": 0,
        "unbekannte_wortnr": [],
        "doppelte_updates": [],
        "fehlende_felder": [],
        "ungueltige_felder": [],
        "doppelte_original_keys": [],
        "warnungen": [],
    }

    # Original indexieren
    index = {}

    for eintrag in original_daten:
        if not isinstance(eintrag, dict):
            continue

        key = key_fuer_wort(eintrag)

        if key is None:
            report["fehlende_felder"].append(f"Original ohne gültige KapitelNummer/WortNr: {eintrag}")
            continue

        if key in index:
            report["doppelte_original_keys"].append(key)
            continue

        index[key] = eintrag

    # Falls roher KI-Output übergeben wurde: normalisieren
    if not (
        isinstance(ki_updates, list)
        and all(isinstance(x, dict) and {"WortNr", "feld", "wert"} <= set(x.keys()) for x in ki_updates)
    ):
        ki_updates, warnungen = normalisiere_ki_output(
            ki_updates,
            pass_typ=pass_typ,
            default_kapitelnummer=default_kapitelnummer,
        )
        report["warnungen"].extend(warnungen)

    # Doppelte Updates erkennen
    gesehen = {}

    for upd in ki_updates:
        feld = upd.get("feld")
        wert = upd.get("wert")
        wortnr = upd.get("WortNr")
        kapitelnummer = upd.get("KapitelNummer", default_kapitelnummer)

        if feld not in erlaubte_felder:
            report["ungueltige_felder"].append(upd)
            continue

        if feld in NIEMALS_KI_UEBERSCHREIBEN:
            report["ungueltige_felder"].append(upd)
            continue

        if wortnr is None:
            report["fehlende_felder"].append(upd)
            continue

        try:
            wortnr = int(wortnr)
        except Exception:
            report["fehlende_felder"].append(upd)
            continue

        if kapitelnummer is None:
            # Fallback: Wenn es nur ein Kapitel im Original gibt
            kapitel_set = {k[0] for k in index.keys()}
            if len(kapitel_set) == 1:
                kapitelnummer = next(iter(kapitel_set))
            else:
                report["fehlende_felder"].append(f"KapitelNummer fehlt bei Update: {upd}")
                continue

        key = (str(kapitelnummer), wortnr)
        update_key = (str(kapitelnummer), wortnr, feld)

        if update_key in gesehen:
            alter_wert = gesehen[update_key]

            if alter_wert != wert:
                report["doppelte_updates"].append({
                    "KapitelNummer": str(kapitelnummer),
                    "WortNr": wortnr,
                    "feld": feld,
                    "werte": [alter_wert, wert],
                })

            # Bei Duplikaten gewinnt hier der letzte Wert.
            # Falls du lieber den ersten behalten willst: continue
        gesehen[update_key] = wert

        if key not in index:
            report["unbekannte_wortnr"].append({
                "KapitelNummer": str(kapitelnummer),
                "WortNr": wortnr,
                "feld": feld,
                "wert": wert,
            })
            continue

        ziel = index[key]

        source_feld = f"{feld}{source_suffix}"

        if (
            schuetze_manuelle_aenderungen
            and ziel.get(source_feld) == "manual"
            and ziel.get(feld) not in ("", None, [])
        ):
            report["uebersprungen_manual"] += 1
            continue

        ziel[feld] = wert
        ziel[source_feld] = ki_source_name
        report["geschrieben"] += 1

    return original_daten, report


# ------------------------------------------------------------
# Beispielaufrufe
# ------------------------------------------------------------

def merge_prosodie(original_daten, prosodie_json, kapitelnummer=None):
    return merge_ki_updates(
        original_daten=original_daten,
        ki_updates=prosodie_json,
        pass_typ="prosodie",
        default_kapitelnummer=kapitelnummer,
        schuetze_manuelle_aenderungen=True,
        ki_source_name="ki_prosodie",
    )


def merge_sprecher(original_daten, sprecher_json, kapitelnummer=None):
    return merge_ki_updates(
        original_daten=original_daten,
        ki_updates=sprecher_json,
        pass_typ="sprecher",
        default_kapitelnummer=kapitelnummer,
        schuetze_manuelle_aenderungen=True,
        ki_source_name="ki_sprecher",
    )


def merge_ig(original_daten, ig_json, kapitelnummer=None):
    return merge_ki_updates(
        original_daten=original_daten,
        ki_updates=ig_json,
        pass_typ="ig",
        default_kapitelnummer=kapitelnummer,
        schuetze_manuelle_aenderungen=True,
        ki_source_name="ki_ig",
    )

def Merge_annotationen(
    quellordner_kapitel,
    quellordner_annotationen,
    ziel_ordner,
    ausgewaehlte_kapitel=None,
    progress_callback=None,
):
    from pathlib import Path
    import json

    quellordner_kapitel = Path(quellordner_kapitel)
    quellordner_annotationen = Path(quellordner_annotationen)
    ziel_ordner = Path(ziel_ordner)
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    dateien = sorted(quellordner_kapitel.glob("*_annotierungen.json"))

    gesamt = len(dateien)

    for i, pfad in enumerate(dateien, start=1):
        if progress_callback:
            progress_callback(round((i - 1) / max(gesamt, 1) * 100, 1))

        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)

        kapitelnummer = None
        if daten:
            kapitelnummer = daten[0].get("KapitelNummer")

        # --------------------------------------------------
        # KI-Dateien finden (sehr simpel gehalten)
        # --------------------------------------------------
        stem = pfad.stem

        ki_dateien = list(quellordner_annotationen.glob(f"*_{stem}_*.json"))

        for ki_pfad in ki_dateien:
            name = ki_pfad.name.lower()

            try:
                ki_json = lade_json_robust(ki_pfad)

                if "betonung" in name or "pause" in name or "spannung" in name:
                    daten, _ = merge_prosodie(daten, ki_json, kapitelnummer)

                elif "person" in name:
                    daten, _ = merge_sprecher(daten, ki_json, kapitelnummer)

                elif "ig" in name:
                    daten, _ = merge_ig(daten, ki_json, kapitelnummer)

            except Exception as e:
                print(f"[FEHLER] {ki_pfad.name}: {e}")
                continue

        zielpfad = ziel_ordner / pfad.name

        with open(zielpfad, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)

        if progress_callback:
            progress_callback(round(i / max(gesamt, 1) * 100, 1))

    print("[✓] Merge abgeschlossen")