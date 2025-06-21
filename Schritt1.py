import os
from pathlib import Path
from docx import Document
from Eingabe.config import ANZAHL_ÜBERSCHRIFTENZEILEN

def extrahiere_kapitel_mit_config(docx_datei, kapitel_namen, kapitel_trenner, ausgabe_ordner, ausgewaehlte_kapitel=None, progress_callback=None):
    ausgabe_ordner = Path(ausgabe_ordner)
    ausgabe_ordner.mkdir(parents=True, exist_ok=True)

    if not os.path.isfile(docx_datei):
        print(f"[FEHLER] Docx-Datei existiert nicht: {docx_datei}")
        return

    doc = Document(docx_datei)
    alle_paragraphen = doc.paragraphs

    def get_formatierung(paragraph):
        indent = paragraph.paragraph_format.left_indent
        einrueckung = indent and indent.pt > 0
        ausrichtung = paragraph.alignment
        ist_zentriert = ausrichtung == 1
        ist_rechtsbuendig = ausrichtung == 2
        return {
            "Einrueckung": einrueckung,
            "Zentriert": ist_zentriert,
            "Rechtsbuendig": ist_rechtsbuendig,
        }

    START_TAGS = {
        "Einrueckung": "|EinrueckungsStart| ",
        "Zentriert": "|ZentriertStart| ",
        "Rechtsbuendig": "|RechtsbuendigStart| ",
    }
    END_TAGS = {
        "Einrueckung": "|EinrueckungsEnde| ",
        "Zentriert": "|ZentriertEnde| ",
        "Rechtsbuendig": "|RechtsbuendigEnde| ",
    }

    def kapitel_startet_mit(text, kapitel):
        return text.strip().lower().startswith(kapitel.strip().lower())

    def ermittle_offene_tags(text):
        offene = set()
        for fmt in ["Einrueckung", "Zentriert", "Rechtsbuendig"]:
            start_count = text.count(START_TAGS[fmt])
            end_count = text.count(END_TAGS[fmt])
            if start_count > end_count:
                offene.add(fmt)
        return offene

    if kapitel_namen:
        for i, kapitel_name in enumerate(kapitel_namen):
            print(f"[INFO] Verarbeite Kapitel {i+1}/{len(kapitel_namen)}: '{kapitel_name}'")

            start_index = next((idx for idx, p in enumerate(alle_paragraphen) if kapitel_startet_mit(p.text, kapitel_name)), None)
            if start_index is None:
                print(f"[WARN] Kapitel '{kapitel_name}' nicht gefunden.")
                continue

            if i + 1 < len(kapitel_namen):
                naechster_start = next((idx for idx, p in enumerate(alle_paragraphen) if kapitel_startet_mit(p.text, kapitel_namen[i+1])), len(alle_paragraphen))
            else:
                naechster_start = len(alle_paragraphen)

            kapitel_paragraphs = alle_paragraphen[start_index:naechster_start]

            if ausgewaehlte_kapitel and kapitel_name not in ausgewaehlte_kapitel:
                continue

            abschnitts_liste = []
            aktueller_abschnitt = []
            offene_formatierungen = set()

            def format_tags_vor_text(format_status, offene_formatierungen):
                end_tags = []
                start_tags = []

                # Beende alles, was nicht mehr gebraucht wird
                for fmt in list(offene_formatierungen):
                    if not format_status.get(fmt, False):
                        end_tags.append(f"\n{END_TAGS[fmt].strip()}")
                        offene_formatierungen.remove(fmt)

                # Starte neue Tags (mit Zeilenumbruch danach!)
                for fmt in format_status:
                    if format_status[fmt] and fmt not in offene_formatierungen:
                        start_tags.append(f"\n{START_TAGS[fmt].strip()}\n")
                        offene_formatierungen.add(fmt)

                return "".join(end_tags + start_tags)


            def format_tags_nach_text(format_status, offene_formatierungen):
                tags_mit_newline = []
                for fmt in list(offene_formatierungen):
                    if not format_status.get(fmt, False):
                        tags_mit_newline.append(f"\n{END_TAGS[fmt].strip()}")
                return "".join(tags_mit_newline)
            
            for para in kapitel_paragraphs:
                text = para.text.strip()
                if kapitel_trenner and text == kapitel_trenner.strip():
                    # Trenner gefunden → Abschnitt beenden
                    if aktueller_abschnitt:
                        abschnitts_liste.append(aktueller_abschnitt)
                        aktueller_abschnitt = []
                    continue

                format_status = get_formatierung(para)
                start_tags = format_tags_vor_text(format_status, offene_formatierungen)
                end_tags = format_tags_nach_text(format_status, offene_formatierungen)

                # Update offene Formatierungen
                beendete = {fmt for fmt in offene_formatierungen if not format_status[fmt]}
                offene_formatierungen.difference_update(beendete)
                neu_geoeffnete = {fmt for fmt in format_status if format_status[fmt] and fmt not in offene_formatierungen}
                offene_formatierungen.update(neu_geoeffnete)

                text_mit_tags = f"{start_tags}{text}{end_tags}" if text else f"{start_tags}{end_tags}"
                aktueller_abschnitt.append(text_mit_tags)

            # letzten Abschnitt hinzufügen
            if aktueller_abschnitt:
                abschnitts_liste.append(aktueller_abschnitt)

            # Teile speichern mit korrektem Tag-Handling
            offene_tags_vorher = set()

            for idx, teil_abschnitt in enumerate(abschnitts_liste, start=1):               

                if idx == 1:
                    # Nur beim ersten Abschnitt des Kapitels
                    kopfzeilen = teil_abschnitt[:ANZAHL_ÜBERSCHRIFTENZEILEN]
                    rest = teil_abschnitt[ANZAHL_ÜBERSCHRIFTENZEILEN:]

                    if kopfzeilen:
                        kopftext = "\n".join(kopfzeilen)
                        kopftext = f"|UeberschriftStart|\n{kopftext}\n|UeberschriftEnde|"
                    else:
                        kopftext = ""

                    text = kopftext + ("\n" + "\n".join(rest) if rest else "")
                    print("[DEBUG] Überschrift für Kapitel", kapitel_name, "gesetzt.")
                else:
                    text = "\n".join(teil_abschnitt)

                # Am Anfang: evtl. offene Tags vom vorherigen Teil einfügen
                if offene_tags_vorher:
                    start_tags = "".join(START_TAGS[fmt] for fmt in offene_tags_vorher)
                    text = start_tags + text

                # Alle noch offenen Formatierungen explizit schließen
                end_tags = "".join(f"\n{END_TAGS[fmt].strip()}" for fmt in offene_formatierungen)
                text = text + end_tags

                # leere offene_formatierungen zurücksetzen für nächste Datei
                offene_tags_vorher = set()

                # Speichern
                dateipfad = ausgabe_ordner / f"{kapitel_name}_{idx:03}.txt"
                with open(dateipfad, "w", encoding="utf-8") as f:
                    f.write(text)

                print(f"[INFO] Gespeichert Teil {idx} von Kapitel '{kapitel_name}' als {dateipfad}")
                
                offene_tags_vorher = set()
    else:
        text_gesamt = "\n".join([p.text for p in alle_paragraphen])
        dateiname_gesamt = os.path.splitext(os.path.basename(docx_datei))[0] + "_Gesamt.txt"
        dateipfad_gesamt = ausgabe_ordner / dateiname_gesamt
        with open(dateipfad_gesamt, "w", encoding="utf-8") as f:
            f.write(text_gesamt)
        print(f"[INFO] Gesamttext gespeichert: {dateipfad_gesamt}")

    if progress_callback:
        progress_callback("Fertig", 100)
