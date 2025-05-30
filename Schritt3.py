import os
import json
from pathlib import Path
import Eingabe.config as config # Importiere das komplette config-Modul

satzzeichen = {".", "!", "?"}
annotation_trenner = "zeilenumbruch"


def bereinige_eintrag(eintrag):
    """Entfernt 'annotation' sowie alle Felder, deren Key in KI_AUFGABEN.values() vorkommt."""
    zu_entfernende_keys = set(config.KI_AUFGABEN.values())
    return {k: v for k, v in eintrag.items() if k != "annotation" and k not in zu_entfernende_keys}

def zaehle_woerter_in_eintrag(eintrag):
    zu_entfernende_keys = set(config.KI_AUFGABEN.values())
    wort_anzahl = 0
    for key, value in eintrag.items():
        if key == "annotation" or key in zu_entfernende_keys:
            continue
        wort_anzahl += len(str(key).split())
        wort_anzahl += len(str(value).split())
    return wort_anzahl



def dateien_aufteilen(kapitelname, eingabe_ordner, ausgabe_ordner, progress_callback=None):
    print(f"[DEBUG -------------------------STARTE Schritt 3 für {kapitelname}")
    print(f"[DEBUG] Durchsuche Ordner: {eingabe_ordner}")
    
    eingabe_ordner = Path(eingabe_ordner)
    ausgabe_ordner = Path(ausgabe_ordner)

    for root, _, files in os.walk(eingabe_ordner):
        for datei in files:
            if not datei.endswith(".json"):
                print(f"[DEBUG] Überspringe Datei (kein JSON): {datei}")
                continue

            datei_name_ohne_endung = os.path.splitext(datei)[0]
            if kapitelname and not datei_name_ohne_endung.startswith(f"{kapitelname}_"):
                continue

            dateipfad = os.path.join(root, datei)
            print(f"[DEBUG] Verarbeite Datei: {dateipfad} mit Kapitelname: {kapitelname}")

            try:
                with open(dateipfad, "r", encoding="utf-8") as f:
                    daten = json.load(f)
                print(f"[DEBUG] JSON geladen, Anzahl Einträge: {len(daten)}")
            except Exception as e:
                print(f"[FEHLER] Laden der Datei {dateipfad} fehlgeschlagen: {e}")
                continue

            saetze = []
            aktueller_satz = []
            gesamt_saetze = sum(
                1 for eintrag in daten if eintrag.get("token") in satzzeichen or annotation_trenner in eintrag.get("annotation", "")
            )
            gesamt_saetze = max(gesamt_saetze, 1)
            print(f"[DEBUG] Gesamtanzahl Sätze geschätzt: {gesamt_saetze}")
            satz_zaehler = 0

            zielverzeichnis = os.path.join(ausgabe_ordner, os.path.relpath(root, eingabe_ordner))
            os.makedirs(zielverzeichnis, exist_ok=True)
            print(f"[DEBUG] Zielverzeichnis erstellt: {zielverzeichnis}")
            basisname = os.path.splitext(datei)[0]

            for eintrag in daten:
                if eintrag.get("annotation") == "Überschrift":
                    ueberschrift_pfad = os.path.join(zielverzeichnis, f"{basisname}_{satz_zaehler + 1:03}.json")
                    print(f"[DEBUG] Schreibe Überschrift in Datei: {ueberschrift_pfad}")
                    try:
                        with open(ueberschrift_pfad, "w", encoding="utf-8") as f:
                            bereinigt = [bereinige_eintrag(eintrag)]
                            json.dump(bereinigt, f, indent=2, ensure_ascii=False)
                    except Exception as e:
                        print(f"[FEHLER] Speichern der Überschriftdatei {ueberschrift_pfad} fehlgeschlagen: {e}")
                    continue

                token = eintrag.get("token")
                if token is None:
                    print(f"[WARNUNG] Kein 'token' in Eintrag: {eintrag}. Überspringe diesen Eintrag.")
                    continue

                aktueller_satz.append(eintrag)
                annotation = eintrag.get("annotation", "")
                if token in satzzeichen or annotation_trenner in annotation:
                    saetze.append(aktueller_satz)
                    print(f"[DEBUG] Satz abgeschlossen mit {len(aktueller_satz)} Einträgen, Satznummer: {satz_zaehler + 1}")
                    aktueller_satz = []
                    satz_zaehler += 1
                    if progress_callback:
                        fortschritt = int((satz_zaehler / gesamt_saetze) * 50)
                        print(f"[DEBUG] Fortschritt Satzaufteilung: {fortschritt}%")
                        progress_callback(kapitelname, fortschritt)

            if aktueller_satz:
                saetze.append(aktueller_satz)
                print(f"[DEBUG] Letzter Satz hinzugefügt mit {len(aktueller_satz)} Einträgen")
                if progress_callback:
                    progress_callback(kapitelname, 50)

            abschnitt = []
            abschnitt_counter = 1
            wort_counter = 0
            anzahl_saetze = len(saetze)
            print(f"[DEBUG] Anzahl Sätze zum Verarbeiten in Abschnitten: {anzahl_saetze}")

            for i, satz in enumerate(saetze, 1):
                satz_woerter = sum(zaehle_woerter_in_eintrag(eintrag) for eintrag in satz)
                print(f"[DEBUG] Satz {i}: Wörter = {satz_woerter}, aktueller Wortzähler = {wort_counter}")
                if wort_counter + satz_woerter > config.MAX_PROMPT_TOKENS:
                    if abschnitt:
                        abschnitt_pfad = os.path.join(zielverzeichnis, f"{basisname}_{abschnitt_counter:03}.json")
                        print(f"[DEBUG] Speichere Abschnitt {abschnitt_counter} mit {len(abschnitt)} Einträgen in {abschnitt_pfad}")
                        try:
                            with open(abschnitt_pfad, "w", encoding="utf-8") as f:
                                bereinigt = [bereinige_eintrag(e) for e in abschnitt]
                                json.dump(bereinigt, f, indent=2, ensure_ascii=False)
                        except Exception as e:
                            print(f"[FEHLER] Speichern von Abschnitt {abschnitt_pfad} fehlgeschlagen: {e}")
                        abschnitt_counter += 1
                    abschnitt = satz.copy()
                    wort_counter = satz_woerter
                else:
                    abschnitt.extend(satz)
                    wort_counter += satz_woerter

                if progress_callback:
                    fortschritt = 50 + int((i / anzahl_saetze) * 50)
                    print(f"[DEBUG] Fortschritt Abschnitt speichern: {fortschritt}%")
                    progress_callback(kapitelname, fortschritt)

            if abschnitt:
                abschnitt_pfad = os.path.join(zielverzeichnis, f"{basisname}_{abschnitt_counter:03}.json")
                print(f"[DEBUG] Speichere letzten Abschnitt {abschnitt_counter} mit {len(abschnitt)} Einträgen in {abschnitt_pfad}")
                try:
                    with open(abschnitt_pfad, "w", encoding="utf-8") as f:
                        bereinigt = [bereinige_eintrag(e) for e in abschnitt]
                        json.dump(bereinigt, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"[FEHLER] Speichern von letztem Abschnitt {abschnitt_pfad} fehlgeschlagen: {e}")

            if progress_callback:
                print(f"[DEBUG] Fortschritt 100% für Kapitel {kapitelname}")
                progress_callback(kapitelname, 100)

            print(f"[DEBUG -------------------------Schritt 3 abgeschlossen für {datei}]")
