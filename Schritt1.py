import os
from docx import Document
from pathlib import Path
import Eingabe.config as config  # Importiere das komplette config-Modul

def extrahiere_kapitel_mit_config(docx_datei, kapitel_namen, kapitel_trenner, ausgabe_ordner, ausgewaehlte_kapitel=None, progress_callback=None):

    ausgabe_ordner = Path(ausgabe_ordner)

    print(f"[DEBUG] Starte Kapitel-Extraktion mit Datei: {docx_datei}")
    print(f"[DEBUG] Zielordner: {ausgabe_ordner}")
    print(f"[DEBUG] kapitel_namen: {kapitel_namen}")
    print(f"[DEBUG -------------------------STARTE Schritt 1 für {ausgewaehlte_kapitel}]")

    if not os.path.isfile(docx_datei):
        print(f"[FEHLER] Docx-Datei existiert nicht: {docx_datei}")
        return

    if not os.path.exists(ausgabe_ordner):
        os.makedirs(ausgabe_ordner, exist_ok=True)
        print(f"[DEBUG] Zielordner wurde angelegt.")

    dateiname_gesamt = os.path.splitext(os.path.basename(docx_datei))[0] + "_Gesamt.txt"
    dateipfad_gesamt = os.path.join(ausgabe_ordner, dateiname_gesamt)

    doc = Document(docx_datei)
    alle_texte = [p.text for p in doc.paragraphs]
    print(f"[DEBUG] Anzahl Paragraphen in Dokument: {len(alle_texte)}")

    def kapitel_startet_mit(text, kapitel):
        # Ignoriere Groß-/Kleinschreibung und Leerzeichen vorne/hinten
        return text.strip().lower().startswith(kapitel.strip().lower())

    if kapitel_namen:
        for i, kapitel_name in enumerate(kapitel_namen):
            print(f"[DEBUG] Verarbeite Kapitel {i+1}/{len(kapitel_namen)}: '{kapitel_name}'")

            steps = 3  # Anzahl Teilschritte pro Kapitel
            def melde_fortschritt(teil):
                if progress_callback:
                    progress_callback(kapitel_name, round((teil / steps), 3))

            # Schritt 1: Kapitelstart finden
            start_index = next(
                (idx for idx, text in enumerate(alle_texte) if kapitel_startet_mit(text, kapitel_name)),
                None)
            if start_index is None:
                print(f"[WARN] Kapitel '{kapitel_name}' nicht gefunden.")
                continue
            print(f"[DEBUG] Gefundener Startindex für '{kapitel_name}': {start_index}")
            melde_fortschritt(1)

            # Schritt 2: Nächsten Kapitelstart finden
            if i + 1 < len(kapitel_namen):
                naechster_start = next(
                    (idx for idx, text in enumerate(alle_texte) if kapitel_startet_mit(text, kapitel_namen[i + 1])),
                    len(alle_texte))
            else:
                naechster_start = len(alle_texte)
            print(f"[DEBUG] Nächster Startindex: {naechster_start}")

            kapitel_text = alle_texte[start_index:naechster_start]
            print(f"[DEBUG] Extrahierter Text für '{kapitel_name}', Länge: {len(kapitel_text)} Absätze")
            melde_fortschritt(2)

            if ausgewaehlte_kapitel is None or kapitel_name in ausgewaehlte_kapitel:
                # Kompakte Logik für Unterteilung nach kapitel_trenner
                if kapitel_trenner:
                    text_gesamt = "\n".join(kapitel_text)
                    teile = text_gesamt.split(kapitel_trenner) if kapitel_trenner in text_gesamt else [text_gesamt]
                else:
                    teile = ["\n".join(kapitel_text)]

                for idx, teil in enumerate(teile, start=1):
                    dateipfad = os.path.join(ausgabe_ordner, f"{kapitel_name}_{idx}.txt")
                    print(f"[DEBUG] Speichere Teil {idx} von Kapitel '{kapitel_name}' in Datei: {dateipfad}")
                    with open(dateipfad, "w", encoding="utf-8") as f:
                        f.write(teil)

                melde_fortschritt(3)
                print("[INFO] Kapitel wurden anhand der Konfiguration extrahiert.")

    else:
        print(f"[DEBUG] Speichere Gesamttext in: {dateipfad_gesamt}")
        with open(dateipfad_gesamt, "w", encoding="utf-8") as f:
            f.write("\n".join(alle_texte))
        print("[INFO] Gesamttext wurde gespeichert.")

        if progress_callback:
            progress_callback("Gesamttext", 1.0)
