import os
from docx import Document
import Eingabe.config as config # Importiere das komplette config-Modul

def extrahiere_kapitel_mit_config(docx_datei, kapitel_namen, ausgabe_ordner, ausgewaehlte_kapitel=None, progress_callback=None):
    print(f"[DEBUG] Starte Kapitel-Extraktion mit Datei: {docx_datei}")
    print(f"[DEBUG] Zielordner: {ausgabe_ordner}")
    print(f"[DEBUG] kapitel_namen: {kapitel_namen}")

    print(f"[DEBUG -------------------------STARTE Schritt 1 für {ausgewaehlte_kapitel}]")


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
# '        if ausgewaehlte_kapitel is not None:
#             kapitel_namen = [k for k in kapitel_namen if k in ausgewaehlte_kapitel]
#             print(f"[DEBUG] Extrahiere nur ausgewählte Kapitel: {kapitel_namen}")'

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
                # Schritt 3: Datei schreiben
                dateipfad = os.path.join(ausgabe_ordner, f"{kapitel_name}.txt")
                print(f"[DEBUG] Speichere Kapitel '{kapitel_name}' in Datei: {dateipfad}")
                with open(dateipfad, "w", encoding="utf-8") as f:
                    f.write("\n".join(kapitel_text))
                melde_fortschritt(3)
                print("[INFO] Kapitel wurden anhand der Konfiguration extrahiert.")

    else:
        print(f"[DEBUG] Speichere Gesamttext in: {dateipfad_gesamt}")
        with open(dateipfad_gesamt, "w", encoding="utf-8") as f:
            f.write("\n".join(alle_texte))
        print("[INFO] Gesamttext wurde gespeichert.")

        if progress_callback:
            progress_callback("Gesamttext", 1.0)
