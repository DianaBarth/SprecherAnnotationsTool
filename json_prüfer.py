import json
import os


def prüfe_json_ordner(ordnerpfad):
    """Prüft alle JSON-Dateien im angegebenen Ordner auf Gültigkeit."""
    if not os.path.isdir(ordnerpfad):
        print(f"Ordner nicht gefunden: {ordnerpfad}")
        return

    for dateiname in os.listdir(ordnerpfad):
        if not dateiname.endswith(".json"):
            continue

        pfad = os.path.join(ordnerpfad, dateiname)
        try:
            with open(pfad, "r", encoding="utf-8") as f:
                json.load(f)
            print(f"{dateiname}: ✅ Gültiges JSON")
        except json.JSONDecodeError as e:
            print(f"{dateiname}: ❌ Ungültiges JSON – {e}")
        except Exception as e:
            print(f"{dateiname}: ⚠️ Fehler beim Öffnen – {e}")

prüfe_json_ordner(r"G:\Dokumente\DianaBuch_FinisPostPortam\Buch\VersionBuch2025\testdaten annotationstool\Annotationstoolergebnisse\die Organisation_FinisPostPortam_mod\satz")