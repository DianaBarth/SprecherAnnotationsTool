import os
import re
import ast
import yaml
import unicodedata
from datetime import date
from pathlib import Path

import Eingabe.config as config


# ------------------------------------------------------------
# Basis-Utils
# ------------------------------------------------------------

def lade_yaml_datei(pfad):

    print(f"[PersonenResolver] Lade YAML: {pfad}")

    if not pfad or not os.path.exists(pfad):
        print("[PersonenResolver] YAML-Datei nicht gefunden.")
        return {}

    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[PersonenResolver] Fehler beim Laden YAML: {e}")
        return {}


def hole_personen_mapping():
    mapping = getattr(config, "PERSONEN_YAML_MAPPING", {})

    if isinstance(mapping, dict):
        return mapping

    try:
        return ast.literal_eval(mapping)
    except Exception:
        print("[PersonenResolver] Mapping konnte nicht geparst werden.")
        return {}


def parse_iso_date(value):
    try:
        return date.fromisoformat(str(value)) if value else None
    except Exception:
        return None


def datum_in_perioden(stichtag, perioden):
    if not stichtag or not perioden:
        return False

    for p in perioden:
        start = parse_iso_date(p.get("entry"))
        ende = parse_iso_date(p.get("exit"))

        if start and stichtag < start:
            continue
        if ende and stichtag > ende:
            continue

        return True

    return False


def normalisiere_kapitel_titel(text):
    if not text:
        return ""

    text = str(text).strip().lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    text = text.replace("–", "-").replace("—", "-")
    text = text.replace(":", " ")
    text = text.replace(".", " ")
    text = text.replace("_", " ")
    text = text.replace("-", " ")

    text = re.sub(r"^\s*[ivxlcdm]+[\.\s]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ------------------------------------------------------------
# 🔥 Dateiname → Kapitel + Abschnitt
# ------------------------------------------------------------

def parse_kapitel_und_abschnitt_aus_dateiname(dateipfad):
    name = Path(dateipfad).stem

    match = re.match(r"^(.*?)_(\d+)_annotierungen$", name)

    if not match:
        print(f"[PersonenResolver] Dateiname nicht erkannt: {name}")
        return None

    return {
        "kapitelname": match.group(1),
        "abschnitt_nummer": int(match.group(2)),
    }


# ------------------------------------------------------------
# 🔥 Kapitel + Subchapter via ID (K01_10)
# ------------------------------------------------------------

def finde_chapter_obj(chapters_data, kapitelname_norm):
    for chapter in chapters_data:
        yaml_titel = chapter.get("title", "")
        yaml_norm = normalisiere_kapitel_titel(yaml_titel)

        if yaml_norm == kapitelname_norm:
            return chapter

    return None


def finde_subchapter_ueber_id(chapter, abschnitt_nummer):
    chapter_id = chapter.get("chapter_id")

    if not chapter_id:
        return None

    gesuchte_id = f"{chapter_id}_{abschnitt_nummer:02d}"

    for sub in chapter.get("subchapters", []):
        if sub.get("sub_id") == gesuchte_id:
            return sub

    print(f"[PersonenResolver] Subchapter nicht gefunden: {gesuchte_id}")
    return None


# ------------------------------------------------------------
# 🔥 Anchor-Date über Datei bestimmen
# ------------------------------------------------------------

def hole_anchor_date_fuer_datei(dateipfad):
    info = parse_kapitel_und_abschnitt_aus_dateiname(dateipfad)
    if not info:
        return None

    chapters_pfad = getattr(config, "PERSONEN_CHAPTERS_DATEI", "")
    chapters_data = lade_yaml_datei(chapters_pfad)

    mapping = hole_personen_mapping()
    subchapter_datum_key = mapping.get("subchapter_datum_feld", "anchor_date")

    kapitelname_norm = normalisiere_kapitel_titel(info["kapitelname"])

    chapter = finde_chapter_obj(chapters_data.get("chapters", []), kapitelname_norm)

    if not chapter:
        print(f"[PersonenResolver] Kapitel nicht gefunden: {info['kapitelname']}")
        return None

    sub = finde_subchapter_ueber_id(chapter, info["abschnitt_nummer"])

    if not sub:
        return None

    anchor = sub.get(subchapter_datum_key)

    print(
        f"[PersonenResolver] Anchor via ID: "
        f"{chapter.get('chapter_id')} -> {sub.get('sub_id')} -> {anchor}"
    )

    return anchor


# ------------------------------------------------------------
# 🔥 Personen aus YAML (für KI + Editor nutzbar)
# ------------------------------------------------------------

def lade_personen_aus_yaml_fuer_datei(dateipfad):
    chars_pfad = getattr(config, "PERSONEN_CHARAKTERE_DATEI", "")
    chars_data = lade_yaml_datei(chars_pfad)

    mapping = hole_personen_mapping()

    relevante_perioden = mapping.get(
        "relevante_perioden",
        ["group_periods", "external_periods"]
    )

    charakter_gruppen = mapping.get(
        "charakter_gruppen",
        [
            "children",
            "internal_children",
            "external_children",
            "external_adults",
            "internal_adults",
        ]
    )

    id_feld = mapping.get("id_feld", "id")
    name_feld = mapping.get("name_feld", "name")

    anchor_date_str = hole_anchor_date_fuer_datei(dateipfad)
    stichtag = parse_iso_date(anchor_date_str)

    print(f"[PersonenResolver] anchor_date={anchor_date_str} | parsed={stichtag}")

    if not stichtag:
        return []

    kandidaten = []

    for gruppenname in charakter_gruppen:
        for char_data in chars_data.get(gruppenname, []):
            aktiv = any(
                datum_in_perioden(stichtag, char_data.get(p, []))
                for p in relevante_perioden
            )

            if not aktiv:
                continue

            name = char_data.get(name_feld) or char_data.get(id_feld)

            if name:
                kandidaten.append(str(name).strip())

    # Duplikate entfernen
    eindeutig = []
    gesehen = set()

    for k in kandidaten:
        key = k.casefold()
        if key not in gesehen:
            gesehen.add(key)
            eindeutig.append(k)

    print(f"[PersonenResolver] Personen: {eindeutig}")
    return eindeutig


# ------------------------------------------------------------
# Fallback (kapitel_config)
# ------------------------------------------------------------

def lade_personen_aus_kapitel_config(kapitel_config, kapitelname):
    zusatzinfo = kapitel_config.kapitel_daten.get(kapitelname, {}).get("ZusatzInfo_3", "")

    if not zusatzinfo:
        return []

    if isinstance(zusatzinfo, list):
        return [str(x).strip() for x in zusatzinfo if str(x).strip()]

    if isinstance(zusatzinfo, str):
        werte = re.findall(r"'(.*?)'", zusatzinfo)
        if werte:
            return werte

        return [t.strip() for t in re.split(r"[;,]", zusatzinfo) if t.strip()]

    return []


# ------------------------------------------------------------
# 🔥 Hauptfunktion für KI-Pipeline
# ------------------------------------------------------------

def lade_personen_fuer_datei(kapitel_config, dateipfad):
    quelle = getattr(config, "PERSONEN_QUELLE", "yaml")

    if quelle == "yaml":
        personen = lade_personen_aus_yaml_fuer_datei(dateipfad)

        if personen:
            return personen

        print("[PersonenResolver] YAML leer → fallback")

    info = parse_kapitel_und_abschnitt_aus_dateiname(dateipfad)
    if not info:
        return []

    return lade_personen_aus_kapitel_config(
        kapitel_config,
        info["kapitelname"]
    )


# ------------------------------------------------------------
# Für KI-Prompt
# ------------------------------------------------------------

def formatiere_personen_fuer_prompt(personen):
    if not personen:
        return "Keine bekannten Sprecher"

    return "\n".join(f"- {p}" for p in personen)

def lade_personen_fuer_datei_ohne_kapitel_config(dateipfad):
    quelle = getattr(config, "PERSONEN_QUELLE", "yaml")

    if quelle == "yaml":
        personen = lade_personen_aus_yaml_fuer_datei(dateipfad)

        if personen:
            return personen

    return []