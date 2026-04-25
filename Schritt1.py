import os
import re
from pathlib import Path
from docx import Document
import Eingabe.config as config

ANZAHL_ÜBERSCHRIFTENZEILEN = getattr(config, "ANZAHL_ÜBERSCHRIFTENZEILEN", 1)
EINRUECKUNGSFORMAT = getattr(config, "EINRUECKUNGSFORMAT", [])


def normalisiere_text(text):
    text = (text or "").replace("\xa0", " ")
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def ist_kapitel_trenner(text, trenner_config):
    text = normalisiere_text(text)
    trenner_config = normalisiere_text(trenner_config)

    print(f"[DEBUG] Prüfe Trenner: text={text!r}, config={trenner_config!r}")

    if not trenner_config or not text:
        return False

    # Fester Trennertext
    if "{" not in trenner_config:
        match = text == trenner_config
        print(f"[DEBUG] Fester Trenner, Match={match}")
        if match:
            print(f"[DEBUG] Fester Kapiteltrenner erkannt: {text!r}")
        return match

    # Platzhalter-Template -> Regex
    regex = re.escape(trenner_config)

    # {Nr} = arabische oder römische Zahl
    regex = regex.replace(r"\{Nr\}", r"(?:[IVXLCDM]+|\d+)")

    # Punkte etwas toleranter machen, damit auch '1 . 1' erkannt wird
    regex = regex.replace(r"\.", r"\s*\.\s*")

    # Erlaubt zusätzlich:
    # 1.1
    # 1.1 Titel
    # 1.1: Titel
    # 1.1 - Titel
    # 1.1. Titel
    # IV.V Titel
    pattern = rf"^{regex}(?:[.:,-])?(?:\s+.*)?$"

    match = re.fullmatch(pattern, text, re.IGNORECASE) is not None
    print(f"[DEBUG] Pattern={pattern!r}, Match={match}")

    if match:
        print(f"[DEBUG] Kapiteltrenner erkannt: {text!r}")

    return match


def extrahiere_kapitel_mit_config(
    docx_datei,
    kapitel_namen,
    kapitel_trenner,
    ausgabe_ordner,
    ausgewaehlte_kapitel=None,
    progress_callback=None
):
    ausgabe_ordner = Path(ausgabe_ordner)
    ausgabe_ordner.mkdir(parents=True, exist_ok=True)

    print(f"[DEBUG] Starte Kapitel-Extraktion mit Datei: {docx_datei}")
    print(f"[DEBUG] Zielordner: {ausgabe_ordner}")
    print(f"[DEBUG] kapitel_namen: {kapitel_namen}")
    print(f"[DEBUG] kapitel_trenner: {kapitel_trenner!r}")
    print(f"[DEBUG] ausgewaehlte_kapitel: {ausgewaehlte_kapitel}")

    if not os.path.isfile(docx_datei):
        print(f"[FEHLER] Docx-Datei existiert nicht: {docx_datei}")
        return

    doc = Document(docx_datei)
    alle_paragraphen = doc.paragraphs
    print(f"[DEBUG] Anzahl Paragraphen im Dokument: {len(alle_paragraphen)}")

    def get_formatierung(paragraph):
        pf = paragraph.paragraph_format
        stilname = paragraph.style.name.strip().lower() if paragraph.style else ""

        ausrichtung = paragraph.alignment
        ist_zentriert = ausrichtung == 1
        ist_rechtsbuendig = ausrichtung == 2

        einrueckung = False
        if not ist_zentriert and not ist_rechtsbuendig:
            if pf.left_indent and abs(pf.left_indent.pt) > 0.1:
                einrueckung = True
            elif pf.first_line_indent and abs(pf.first_line_indent.pt) > 0.1:
                einrueckung = True
            elif pf.right_indent and abs(pf.right_indent.pt) > 0.1:
                einrueckung = True
            elif any(name.lower() in stilname for name in EINRUECKUNGSFORMAT):
                einrueckung = True

        format_status = {
            "Einrueckung": einrueckung,
            "Zentriert": ist_zentriert,
            "Rechtsbuendig": ist_rechtsbuendig,
        }

        print(f"[DEBUG] Format für Absatz: {paragraph.text[:60]!r} => {format_status}")
        return format_status

    START_TAGS = {
        "Einrueckung": "|EinrueckungStart| ",
        "Zentriert": "|ZentriertStart| ",
        "Rechtsbuendig": "|RechtsbuendigStart| ",
    }
    END_TAGS = {
        "Einrueckung": "|EinrueckungEnde| ",
        "Zentriert": "|ZentriertEnde| ",
        "Rechtsbuendig": "|RechtsbuendigEnde| ",
    }

    def run_ist_fett(run):
        if run.bold is True:
            return True
        if run.style and run.style.font and run.style.font.bold is True:
            return True
        return False


    def run_ist_kursiv(run):
        if run.italic is True:
            return True
        if run.style and run.style.font and run.style.font.italic is True:
            return True
        return False


    def paragraph_text_mit_inline_formatmarkern(paragraph):
        teile = []
        fett_aktiv = False
        kursiv_aktiv = False

        for run in paragraph.runs:
            text = run.text or ""
            if not text:
                continue

            text = text.replace("\xa0", " ").replace("\t", " ")

            ist_fett = run_ist_fett(run)
            ist_kursiv = run_ist_kursiv(run)

            if ist_fett and not fett_aktiv:
                teile.append("|FettStart|")
                fett_aktiv = True
            elif not ist_fett and fett_aktiv:
                teile.append("|FettEnde|")
                fett_aktiv = False

            if ist_kursiv and not kursiv_aktiv:
                teile.append("|KursivStart|")
                kursiv_aktiv = True
            elif not ist_kursiv and kursiv_aktiv:
                teile.append("|KursivEnde|")
                kursiv_aktiv = False

            teile.append(text)

        if kursiv_aktiv:
            teile.append("|KursivEnde|")
        if fett_aktiv:
            teile.append("|FettEnde|")

        return normalisiere_text("".join(teile))


    def kapitel_startet_mit(text, kapitel):
        text = normalisiere_text(text)
        kapitel = normalisiere_text(kapitel)
        return text.lower().startswith(kapitel.lower())

    def format_tags_vor_text(format_status, offene_formatierungen):
        end_tags = []
        start_tags = []

        for fmt in list(offene_formatierungen):
            if not format_status.get(fmt, False):
                end_tags.append(f"\n{END_TAGS[fmt].strip()}")
                offene_formatierungen.remove(fmt)

        for fmt, aktiv in format_status.items():
            if aktiv and fmt not in offene_formatierungen:
                start_tags.append(f"\n{START_TAGS[fmt].strip()}\n")
                offene_formatierungen.add(fmt)

        return "".join(end_tags + start_tags)

    def format_tags_nach_text(format_status, offene_formatierungen):
        tags_mit_newline = []
        for fmt in list(offene_formatierungen):
            if not format_status.get(fmt, False):
                tags_mit_newline.append(f"\n{END_TAGS[fmt].strip()}")
                offene_formatierungen.remove(fmt)
        return "".join(tags_mit_newline)

    if kapitel_namen:
        gesamt_kapitel = len(kapitel_namen)

        for i, kapitel_name in enumerate(kapitel_namen):
            print(f"[INFO] Verarbeite Kapitel {i + 1}/{gesamt_kapitel}: {kapitel_name!r}")

            if ausgewaehlte_kapitel and kapitel_name not in ausgewaehlte_kapitel:
                print(f"[DEBUG] Kapitel übersprungen: {kapitel_name!r}")
                continue

            steps = 3

            def melde_fortschritt(teil):
                if progress_callback:
                    progress_callback(kapitel_name, round(teil / steps, 3))

            start_index = next(
                (idx for idx, p in enumerate(alle_paragraphen) if kapitel_startet_mit(p.text, kapitel_name)),
                None
            )

            if start_index is None:
                print(f"[WARN] Kapitel nicht gefunden: {kapitel_name!r}")
                continue

            print(f"[DEBUG] Startindex für Kapitel {kapitel_name!r}: {start_index}")
            melde_fortschritt(1)

            if i + 1 < len(kapitel_namen):
                naechster_start = next(
                    (idx for idx, p in enumerate(alle_paragraphen) if kapitel_startet_mit(p.text, kapitel_namen[i + 1])),
                    len(alle_paragraphen)
                )
            else:
                naechster_start = len(alle_paragraphen)

            print(f"[DEBUG] Endindex für Kapitel {kapitel_name!r}: {naechster_start}")

            kapitel_paragraphs = alle_paragraphen[start_index:naechster_start]
            print(f"[DEBUG] Kapitel {kapitel_name!r} umfasst {len(kapitel_paragraphs)} Absätze")
            melde_fortschritt(2)

            abschnitts_liste = []
            aktueller_abschnitt = []
            offene_formatierungen = set()

            for para_idx, para in enumerate(kapitel_paragraphs, start=1):
                raw_text = para.text or ""
                text = paragraph_text_mit_inline_formatmarkern(para)

                print(f"[DEBUG] Absatz {para_idx}: roh={raw_text!r}")
                print(f"[DEBUG] Absatz {para_idx}: normalisiert={text!r}")
                
                text_fuer_trenner = normalisiere_text(raw_text)
                
                if ist_kapitel_trenner(text_fuer_trenner, kapitel_trenner):
                    print(f"[DEBUG] >>> TRENNER GEFUNDEN in Kapitel {kapitel_name!r}: {text!r}")

                    if aktueller_abschnitt:
                        abschnitts_liste.append(aktueller_abschnitt)
                        print(f"[DEBUG] Abschnitt abgeschlossen. Bisherige Anzahl: {len(abschnitts_liste)}")
                        aktueller_abschnitt = []

                    # Der Trenner-Text selbst soll im neuen Abschnitt erhalten bleiben
                    format_status = get_formatierung(para)
                    start_tags = format_tags_vor_text(format_status, offene_formatierungen)
                    end_tags = format_tags_nach_text(format_status, offene_formatierungen)

                    text_mit_tags = f"{start_tags}{text}{end_tags}" if text else f"{start_tags}{end_tags}"
                    aktueller_abschnitt.append(text_mit_tags)
                    continue

                format_status = get_formatierung(para)
                start_tags = format_tags_vor_text(format_status, offene_formatierungen)
                end_tags = format_tags_nach_text(format_status, offene_formatierungen)

                text_mit_tags = f"{start_tags}{text}{end_tags}" if text else f"{start_tags}{end_tags}"
                aktueller_abschnitt.append(text_mit_tags)

            if aktueller_abschnitt:
                abschnitts_liste.append(aktueller_abschnitt)

            print(f"[DEBUG] Anzahl erzeugter Abschnitte für {kapitel_name!r}: {len(abschnitts_liste)}")

            if not abschnitts_liste:
                print(f"[WARN] Keine Abschnitte für Kapitel {kapitel_name!r} erzeugt.")
                continue

            for idx, teil_abschnitt in enumerate(abschnitts_liste, start=1):
                if idx == 1:
                    kopfzeilen = teil_abschnitt[:ANZAHL_ÜBERSCHRIFTENZEILEN]
                    rest = teil_abschnitt[ANZAHL_ÜBERSCHRIFTENZEILEN:]

                    if kopfzeilen:
                        kopftext = "\n".join(kopfzeilen)

                        kopftext = re.sub(r"\|Einrueckung(Start|Ende)\|\s*", "", kopftext)
                        kopftext = re.sub(r"\|Zentriert(Start|Ende)\|\s*", "", kopftext)
                        kopftext = re.sub(r"\|Rechtsbuendig(Start|Ende)\|\s*", "", kopftext)

                        kopftext = f"|UeberschriftStart|\n{kopftext}\n|UeberschriftEnde|"
                    else:
                        kopftext = ""

                    text = kopftext + ("\n" + "\n".join(rest) if rest else "")
                    print(f"[DEBUG] Kapitelüberschrift für {kapitel_name!r} gesetzt.")
                else:
                    text = "\n".join(teil_abschnitt)

                # Noch offene Tags für diese Datei schließen
                end_tags = "".join(f"\n{END_TAGS[fmt].strip()}" for fmt in offene_formatierungen)
                text = text + end_tags

                dateipfad = ausgabe_ordner / f"{kapitel_name}_{idx:03}.txt"
                with open(dateipfad, "w", encoding="utf-8") as f:
                    f.write(text)

                print(f"[INFO] Gespeichert Teil {idx} von Kapitel {kapitel_name!r} als {dateipfad}")

            if offene_formatierungen:
                print(f"[WARN] Nicht geschlossene Tags am Ende von Kapitel {kapitel_name!r}: {offene_formatierungen}")
                letzte_datei = ausgabe_ordner / f"{kapitel_name}_{len(abschnitts_liste):03}.txt"
                with open(letzte_datei, "a", encoding="utf-8") as f:
                    for fmt in list(offene_formatierungen):
                        f.write(f"\n{END_TAGS[fmt].strip()}")
                offene_formatierungen.clear()

            melde_fortschritt(3)

    else:
        text_gesamt = "\n".join((p.text or "") for p in alle_paragraphen)
        dateiname_gesamt = os.path.splitext(os.path.basename(docx_datei))[0] + "_Gesamt.txt"
        dateipfad_gesamt = ausgabe_ordner / dateiname_gesamt

        with open(dateipfad_gesamt, "w", encoding="utf-8") as f:
            f.write(text_gesamt)

        print(f"[INFO] Gesamttext gespeichert: {dateipfad_gesamt}")

        if progress_callback:
            progress_callback("Gesamttext", 1.0)

    if progress_callback:
        progress_callback("Fertig", 100)