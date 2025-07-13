import json
import os

import json
import os
import regex  # ← wird für Unicode-Satzzeichen verwendet

def bestimme_satzzeichen_annotation(token):
    if regex.match(r"[\p{P}]", token):
        if token in ['–', '(', ')', '{', '}', '[', ']']:
            return "satzzeichenMitSpace"
        elif token in ['„']:
            return "satzzeichenOhneSpaceDanach"
        else:
            return "satzzeichenOhneSpaceDavor"
    return ""

def inkrementiere_wortnr(dateipfad_input, dateipfad_output, offset):
    with open(dateipfad_input, 'r', encoding='utf-8') as f:
        daten = json.load(f)

    for eintrag in daten:
        # WortNr erhöhen
        if "WortNr" in eintrag and isinstance(eintrag["WortNr"], (int, float)):
            eintrag["WortNr"] += offset

        # Annotation prüfen oder korrigieren
        token = eintrag.get("token", "")
        korrekt_annotation = bestimme_satzzeichen_annotation(token)

        vorhandene = eintrag.get("annotation", "").split(",") if eintrag.get("annotation") else []

        # Alte Satzzeichen-Tags entfernen
        bereinigte = [a for a in vorhandene if not a.startswith("satzzeichen")]

        # Neue ggf. ergänzen
        if korrekt_annotation:
            bereinigte.append(korrekt_annotation)

        eintrag["annotation"] = ",".join(bereinigte).strip(",")

    with open(dateipfad_output, 'w', encoding='utf-8') as f:
        json.dump(daten, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Erfolgreich! Alle 'WortNr'-Felder wurden um {offset} erhöht.")
    print(f"📁 Neue Datei gespeichert als: {dateipfad_output}")

def main():
    print("🔧 WortNr-Inkrementierer und Annoationen-Hinzufüger für JSON-Dateien\n")

    # 1. Ordnerpfad
    pfad = input("📁 Ordnerpfad (z. B. ./daten): ").strip()
    while not os.path.isdir(pfad):
        print("❌ Ordner nicht gefunden.")
        pfad = input("Bitte gültigen Ordnerpfad angeben: ").strip()

    # 2. Eingabedateiname
    eingabe_datei = input("📄 Eingabedateiname (z. B. eingabe.json): ").strip()
    eingabe_pfad = os.path.join(pfad, eingabe_datei)
    while not os.path.isfile(eingabe_pfad):
        print("❌ Eingabedatei nicht gefunden.")
        eingabe_datei = input("Bitte gültigen Eingabedateinamen angeben: ").strip()
        eingabe_pfad = os.path.join(pfad, eingabe_datei)

    # 3. Ausgabedateiname
    ausgabe_datei = input("💾 Ausgabedateiname (z. B. ausgabe.json): ").strip()
    ausgabe_pfad = os.path.join(pfad, ausgabe_datei)

    # 4. Offset
    offset_str = input("➕ Offset-Wert (z. B. 500): ").strip()
    try:
        offset = int(offset_str)
    except ValueError:
        print("❌ Ungültiger Offset. Bitte eine Ganzzahl eingeben.")
        return

    # Verarbeitung
    inkrementiere_wortnr(eingabe_pfad, ausgabe_pfad, offset)

if __name__ == "__main__":
    main()
