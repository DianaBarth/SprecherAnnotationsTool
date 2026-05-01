import os
import json
from collections import defaultdict
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
import hashlib
from pathlib import Path
import Eingabe.config as config # Importiere das komplette config-Modul

# ---------------------------------------------
# Hilfsfunktionen zur PDF-Erstellung und Formatierung
# ---------------------------------------------

# Globale Farbzuordnung: jede Person bekommt eine eigene Farbe

farben_dict = defaultdict(lambda: colors.black)
def get_person_color(person):
    """Gibt Farb-Tupel für eine Person zurück."""
    if not person:
        return config.FARBE_STANDARD
    h = hashlib.md5(person.encode('utf-8')).hexdigest()
    r = max(int(h[0:2], 16) / 255.0, 0.2)
    g = max(int(h[2:4], 16) / 255.0, 0.2)
    b = max(int(h[4:6], 16) / 255.0, 0.2)
    return r, g, b

def gruppiere_zeilen(tokens):
    """
    Gruppiert Tokens nach Seite und Zeile zur strukturierten Verarbeitung.
    """
    zeilen = defaultdict(list)
    for t in tokens:
        zeilen[(t["seite"], t["zeile"])].append(t)
    return zeilen


def setze_schriftart_und_format(c, betonung, ist_ueberschrift, ist_legende):
    """
    Setzt Schriftart und -größe je nach Betonung und Texttyp.
    """   
    if betonung is None:
        betonung = ""  # Leerer String statt None

    if ist_ueberschrift:
        if "hauptbetonung" in betonung:
            c.setFont(config.SCHRIFTART_UEBERSCHRIFT_HAUPT, config.UEBERSCHRIFT_GROESSE)
        elif "nebenbetonung" in betonung:
            c.setFont(config.SCHRIFTART_UEBERSCHRIFT_NEBEN, config.UEBERSCHRIFT_GROESSE)
        else:
            c.setFont(config.SCHRIFTART_UEBERSCHRIFT, config.UEBERSCHRIFT_GROESSE)
    elif ist_legende:
        if "hauptbetonung" in betonung:
            c.setFont(config.SCHRIFTART_LEGENDE_HAUPT, config.LEGENDE_GROESSE)
        elif "nebenbetonung" in betonung:
            c.setFont(config.SCHRIFTART_LEGENDE_NEBEN, config.LEGENDE_GROESSE)
        else:
            c.setFont(config.SCHRIFTART_LEGENDE, config.LEGENDE_GROESSE)
    else:
        if "hauptbetonung" in betonung:
            c.setFont(config.SCHRIFTART_BETONUNG_HAUPT, config.TEXT_GROESSE)
        elif "nebenbetonung" in betonung:
            c.setFont(config.SCHRIFTART_BETONUNG_NEBEN, config.TEXT_GROESSE)
        else:
            c.setFont(config.SCHRIFTART_STANDARD, config.TEXT_GROESSE)


def berechne_ueberschrift_position(c, text, seitenbreite):
    """
    Berechnet die x-Position für eine zentrierte Überschrift basierend auf ihrer Breite.
    """
    tw = c.stringWidth(text, config.SCHRIFTART_UEBERSCHRIFT_HAUPT, config.UEBERSCHRIFT_GROESSE)
    return (seitenbreite - tw) / 2


def zeichne_mehrzeilige_ueberschrift(c, zeilen_tokens, seitenbreite, y_pos, betonung):
    """
    Zeichnet eine mehrzeilige Überschrift mittig mit Unterstreichung und Abständen.
    """
    setze_schriftart_und_format(c, betonung, True, False)
    for zeile_tokens in zeilen_tokens:
        zeile = " ".join(zeile_tokens).strip()
        if not zeile:
            continue
        x = berechne_ueberschrift_position(c, zeile, seitenbreite)
        c.drawString(x, y_pos, zeile)

        # Unterstreichen
        tw = c.stringWidth(zeile, config.SCHRIFTART_UEBERSCHRIFT_HAUPT, config.UEBERSCHRIFT_GROESSE)
        c.setLineWidth(1)
        c.line(x, y_pos - config.LINIENABSTAND, x + tw, y_pos - config.LINIENABSTAND)

        y_pos -= config.ZEILENHOEHE  # Zeilenabstand

    y_pos -= config.ABSTANDNACHÜBERSCHRIFT  # Zusätzlicher Abstand

    # Verhindert negative y-Position
    if y_pos < config.UNTERER_SEITENRAND:
        y_pos = config.UNTERER_SEITENRAND

    return y_pos


def zeichne_überschrift(canvas, text, x_pos, y_pos):
    """
    Zeichnet eine Überschrift auf das PDF.
    """
    canvas.setFont(config.FONT_ÜBERSCHRIFT, config.FONT_SIZE_ÜBERSCHRIFT)
    canvas.setFillColor(colors.black)
    canvas.drawString(x_pos, y_pos, text)
    y_pos -= config.ZEILENHOEHE
    return y_pos


def zeichne_text(canvas, text, x_pos, y_pos):
    """
    Zeichnet normalen Text auf das PDF.
    """
    canvas.setFont(config.FONT_STANDARD, config.FONT_SIZE_STANDARD)
    canvas.setFillColor(colors.black)
    canvas.drawString(x_pos, y_pos, text)
    y_pos -= config.ZEILENHOEHE
    return y_pos

# ---------------------------------------------
# PDF-Erstellung
# ---------------------------------------------

def erstelle_pdf(dateiname, json_data):
    """
    Erstellt das PDF-Dokument aus JSON-Daten und speichert es.
    """
    c = canvas.Canvas(dateiname, pagesize=letter)
    seitenhoehe = letter[1]
    seite_nummer = 1

    # Zeichne die Seite mit json_data (die Funktion zeichne_seite ist extern definiert)
    c = zeichne_seite(c, json_data, seite_nummer, seitenhoehe)

    c.save()

def verarbeite_tokens(tokens):
    """
    Berechnet Seiten-, Zeilen-, x- und y-Position sowie Darstellungsform für Tokens.
    Unterstützt "zeilenumbruch", "satzzeichenOhneSpace" und "satzzeichenMitSpace".
    """
    laufende_breite = 0
    zeilen_nummer = 0
    x_start = 50  # linker Rand
    y_pos = 0     # wird ggf. beim Zeichnen pro Zeile berechnet

    for i, eintrag in enumerate(tokens):
        annotation = [a.strip() for a in eintrag.get("annotation", [])]
        token = eintrag.get("token", "")

        # harter Zeilenumbruch
        if ("zeilenumbruch" in annotation or "Zeilenumbruch" in annotation) and not token:
            laufende_breite = 0
            zeilen_nummer += 1
            eintrag.update({
                "text_anzeige": "",
                "word_width": 0,
                "extra_space": 0,
                "seite": zeilen_nummer // config.MAX_ZEILENANZAHL + 1,
                "zeile": zeilen_nummer,
                "x": x_start,
                "y": y_pos  # wird später dynamisch gesetzt
            })
            continue

        # Leerzeichenlogik
        if i + 1 < len(tokens):
            next_annotation = tokens[i + 1].get("annotation", [])
            next_is_satzzeichen_ohne_space = "satzzeichenOhneSpace" in next_annotation
        else:
            next_is_satzzeichen_ohne_space = False

        if next_is_satzzeichen_ohne_space:
            extra_space = 0
            text_anzeige = token
        else:
            extra_space = 1
            text_anzeige = f"{token} "

        # Wortbreite berechnen
        word_width = len(token) + extra_space
        neue_laufende_breite = laufende_breite + word_width

        # automatischer Umbruch
        if neue_laufende_breite > config.MAX_ZEILENBREITE:
            zeilen_nummer += 1
            laufende_breite = 0
            neue_laufende_breite = word_width  # dieses Wort beginnt neue Zeile

        laufende_breite = neue_laufende_breite

        eintrag.update({
            "is_satzzeichen": "satzzeichenOhneSpace" in annotation or "satzzeichenMitSpace" in annotation,
            "extra_space": extra_space,
            "word_width": word_width,
            "text_anzeige": text_anzeige,
            "laufende_breite": laufende_breite,
            "zeile": zeilen_nummer,
            "seite": zeilen_nummer // config.MAX_ZEILENANZAHL + 1,
            "x": x_start + laufende_breite * config.ZEICHENBREITE,
            "y": y_pos  # wird ggf. beim Zeichnen durch Zeilennummer ersetzt
        })

    return tokens

def berechne_positionen(tokens):
    """
    Berechnet X- und Y-Position jedes Tokens.
    """
    seiten_zeilen = defaultdict(list)
    for e in tokens:
        seiten_zeilen[(e["seite"], e["zeile"])].append(e)
    for (seite, zeile), grp in seiten_zeilen.items():
        x = config.START_X_POS
        for e in grp:
            e["x"] = x
            e["y_offset"] = zeile * config.ZEILENHOEHE
            x += e["word_width"] * config.ZEICHENBREITE


def zeichne_seite(c, tokens, seite_nummer, seitenhoehe):
    farben_dict.clear()  # Reset der Farbindividuen
    for t in tokens:
        p = t.get("Person", "")
        if p:
            farben_dict[p] = colors.Color(*get_person_color(p))  # Weise jeder Person eine Farbe zu

    c.setFont(config.SCHRIFTART_STANDARD, config.TEXT_GROESSE)  # Standard-Schriftart setzen
    c.drawString(config.START_X_POS, seitenhoehe - 30, f"Seite {seite_nummer}")  # Seitenzahl einfügen
    zeilen = gruppiere_zeilen(tokens)  # Gruppiere die Tokens nach Seiten und Zeilen
    y_pos = seitenhoehe - config.OBERER_SEITENRAND  # Initiale y-Position
    ueb = [[]]  # Liste für mehrzeilige Überschriften
    x_off = config.START_X_POS  # Initiale x-Position für den Text
    zeilenumbruch_pos = y_pos  # Position für den nächsten Zeilenumbruch
    vorherige_zeile = 0  # Initiale Zeilennummer setzen
    ist_überschrift = False
    ist_legende = False

    for (s, z), grp in sorted(zeilen.items()):
        if s != seite_nummer:
            continue

        for e in grp:
            ann = [a.strip() for a in e.get("annotation", "").split(',')]

            if "Überschrift" in ann:
                ist_überschrift = True
                ist_legende = False
                tok = e.get("token", "")
                if "zeilenumbruch" in ann:
                    ueb.append([])  # Neue Zeile für Überschrift
                else:
                    ueb[-1].append(tok)
                continue
            elif "Legende" in ann:
                ist_legende = True
                ist_überschrift = False
            else:
                 ist_überschrift = False
                 ist_legende = False
                 
            if ueb and any(ueb):
                # Zeichne die Überschrift, wenn mehrzeilige Überschrift vorhanden ist
                zeichne_mehrzeilige_ueberschrift(c, ueb, letter[0], zeilenumbruch_pos, grp[0].get("Betonung", ""))

                # Setze y_pos nach der Überschrift explizit, damit der Text nicht darüber gezeichnet wird
                zeilenumbruch_pos -= config.ZEILENHOEHE  # Verwende den Abstand für die Zeilenhöhe

                ueb = [[]]  # Liste für mehrzeilige Überschrift zurücksetzen
                continue

            if "zeilenumbruch" in ann and not e.get("token") and not any(ueb):
                zeilenumbruch_pos -= config.ZEILENHOEHE  # Verwende Zeilenhöhe für den Abstand
                x_off = config.START_X_POS
                continue

            c.setFillColor(farben_dict[e.get("Person", "")])  # Setzt die Farbe für die Person
            setze_schriftart_und_format(c, e.get("Betonung"), ist_überschrift, ist_legende)  # Schriftart setzen je nach Betonung
            txt = e.get("token", "")
            txt_width = stringWidth(txt, c._fontname, c._fontsize)  # Berechne Breite des Textes

            # Überprüfe, ob der Text in die Zeile passt
            if x_off + txt_width > config.MAX_ZEILENBREITE:
                # Wenn Text nicht mehr passt, setze Umbruch
                zeilenumbruch_pos -= config.ZEILENHOEHE  # Zeilenhöhe reduzieren (nächste Zeile)
                x_off = config.START_X_POS  # Setze x-Offset für neue Zeile zurück

            # Wenn ein Zeilenumbruch in der Annotation vorhanden ist, füge extra Abstand ein
            if "zeilenumbruch" in ann:
                zeilenumbruch_pos -= config.ZEILENHOEHE  # Zeilenhöhe für Abstand nach einem „Zeilenumbruch“

            # Zeichne den Text
            c.drawString(x_off, zeilenumbruch_pos, txt)
            vorherige_zeile = zeichne_marker(c, e, x_off, zeilenumbruch_pos, txt_width, vorherige_zeile)  # Marker für Pausen oder Gedanken zeichnen
            x_off += txt_width + (stringWidth(" ", c._fontname, c._fontsize) if e.get("extra_space", 0) else 0)

            # Wenn der Text über das Ende der Seite hinausgeht, füge einen Seitenumbruch ein
            if zeilenumbruch_pos < config.UNTERER_SEITENRAND:
                c.showPage()  # Neue Seite, wenn Schwelle überschritten
                zeilenumbruch_pos = seitenhoehe - config.OBERER_SEITENRAND  # Setze Position zurück

    return c

def zeichne_marker(c, e, x_pos, y_pos, text_width, vorherige_zeile):
    pause = e.get("Pause", "")
    spannung = e.get("Spannung", "")  # Direkt aus dem Event 'e' die Spannung holen
    token = e.get("token", "?")
    gedanken = e.get("Gedanken", "")
 
    oy = config.MARKER_OFFSET_Y
    w = config.MARKER_BREITE_KURZ
    h = config.MARKER_BREITE_KURZ

    x = x_pos + text_width / 2 - w / 2  # exakt zentriert über dem Token
    zeile = e.get("zeile", 0)
    unterstrich_y_pos = y_pos - 2  # Y-Position des Unterstrichs unterhalb des Textes

    # Wenn der Zeilenumbruch erkannt wird, unterbrich die Linie
    if zeile != vorherige_zeile:
        return zeile  # Zeilenwechsel erkannt, also Linie unterbrechen
      
    # Spannungsbögen zeichnen (Starten)
    if spannung == "Starten":
        c.setStrokeColorRGB(*config.FARBE_SPANNUNG)
        c.setLineWidth(config.LINIENBREITE_STANDARD)

        steps = 10  # Anzahl der Schritte für die Bogenbildung
        path_bogen = c.beginPath()
        for i in range(steps):
            t = i / float(steps)
            x1 = x_pos + t * text_width
            y1 = y_pos + oy + h / 2 + t * config.SPANNUNG_NEIGUNG  # Steigend!
            if i == 0:
                path_bogen.moveTo(x1, y1)
            else:
                path_bogen.lineTo(x1, y1)
        c.drawPath(path_bogen)

    # Spannungsbögen zeichnen (Halten)
    elif spannung == "Halten":
        c.setStrokeColorRGB(*config.FARBE_SPANNUNG)
        c.setLineWidth(config.LINIENBREITE_STANDARD)
        path_halten = c.beginPath()

        start_x = x_pos
        end_x = x_pos + text_width

        y = y_pos + oy + h / 2
        path_halten.moveTo(start_x, y)
        path_halten.lineTo(end_x, y)
        c.drawPath(path_halten)

    elif spannung == "Stoppen":
        c.setStrokeColorRGB(*config.FARBE_SPANNUNG)
        c.setLineWidth(config.LINIENBREITE_STANDARD)

        # Gerade Linie (nur als Markierungspunkt)
        path_stoppen = c.beginPath()
        path_stoppen.moveTo(x_pos + text_width, y_pos + oy + h / 2)
        path_stoppen.lineTo(x_pos + text_width, y_pos + oy + h / 2)
        c.drawPath(path_stoppen)

        # Abfallender Bogen von Start bis Ende des Tokens
        steps = 10
        path_bogen = c.beginPath()
        for i in range(steps):
            t = i / float(steps)
            x1 = x_pos + t * text_width
            y1 = y_pos + oy + h / 2 - t * config.SPANNUNG_NEIGUNG  # Abfallend!
            if i == 0:
                path_bogen.moveTo(x1, y1)
            else:
                path_bogen.lineTo(x1, y1)
        c.drawPath(path_bogen)

    # Unterstrich für "ig" am Ende des Tokens
    if token.endswith("ig"):
        c.setStrokeColorRGB(*config.FARBE_UNTERSTREICHUNG)  # Unterstrichfarbe aus config
        c.setLineWidth(config.LINIENBREITE_STANDARD)  # Stärkere Linie
        unterstrich_x_pos = x_pos + text_width - config.ZEICHENBREITE * 2  # Position des 'ig' am Ende des Tokens
        c.line(unterstrich_x_pos, unterstrich_y_pos, unterstrich_x_pos + config.ZEICHENBREITE * 2, unterstrich_y_pos)

    # Punkte für Binnen-"ig"
    else:
        binnen_ig_index = token.find("ig")
        if binnen_ig_index != -1 and binnen_ig_index + 2 != len(token):
            # Berechne x-Position des Binnen-"ig"
            binnen_ig_x_pos = x_pos + binnen_ig_index * config.ZEICHENBREITE

            c.setFillColorRGB(*config.FARBE_UNTERSTREICHUNG)  # Punktfarbe = Unterstreichungsfarbe
            punkt_radius = 0.8  # Größe der Punkte

            # Zwei kleine Punkte unter "i" und "g"
            for i in range(2):
                punkt_x = binnen_ig_x_pos + i * config.ZEICHENBREITE + config.ZEICHENBREITE / 2
                punkt_y = unterstrich_y_pos - config.ZEILENABSTAND * 0.2  # leicht unter der Textlinie
                c.circle(punkt_x, punkt_y, punkt_radius, stroke=0, fill=1)
                
        # Pausen und Gedankenmarkierungen
    if "atempause" in pause:
        c.setStrokeColorRGB(*config.FARBE_ATEMPAUSE)
        c.setLineWidth(config.LINIENBREITE_STANDARD)
        length = config.MARKER_BREITE_LANG * 2
        c.line(x, y_pos + oy + h + 2, x + length, y_pos + oy + h + 2)

    if "staupause" in pause:
        c.setFillColorRGB(*config.FARBE_STAUPAUSE)
        c.rect(x, y_pos + oy, w, h, fill=1, stroke=0)

    if "pause_gedanken" in gedanken:
        c.setFillColorRGB(*config.FARBE_GEDANKENPAUSE)
        c.circle(x + w / 2, y_pos + oy + h / 2, w / 2, fill=1, stroke=0)

    # Kombination von Pausen (z. B. Staupause + Gedankenende)
    if "staupause" in pause and "gedanken_ende" in gedanken:
        c.setStrokeColorRGB(*config.FARBE_KOMB_PAUSE)
        c.setLineWidth(config.LINIENBREITE_STANDARD)
        c.rect(x, y_pos + oy, w, h, fill=0)
        c.line(x, y_pos + oy, x + w, y_pos + oy + h)
        c.line(x, y_pos + oy + h, x + w, y_pos + oy)

    # Gedankenmarkierungen
    if "gedanken_weiter" in gedanken:
        c.setStrokeColorRGB(*config.FARBE_GEDANKENWEITER)
        c.setLineWidth(config.LINIENBREITE_STANDARD)
        c.setDash(*config.GEDANKEN_STRICHMUSTER)
        c.line(x, y_pos + oy + h / 2, x + config.MARKER_BREITE_LANG, y_pos + oy + h / 2)
        c.setDash()

    # Gedankenschluss
    if "gedanken_ende" in gedanken and "pause_gedanken" not in gedanken:
        c.setStrokeColorRGB(*config.FARBE_GEDANKENENDE)
        c.setLineWidth(config.LINIENBREITE_STANDARD)
        off = w / 2
        c.line(x + off, y_pos + oy, x + off + w, y_pos + oy)
        c.line(x + off, y_pos + oy + h, x + off + w, y_pos + oy + h)

    return vorherige_zeile  # Gibt die Zeile zurück, um die Marker korrekt weiterzugeben


# ---------------------------------------------
# Hauptfunktion für die Visualisierung
# ---------------------------------------------

def visualisiere_annotationen(eingabe_ordner, ausgabe_ordner, ausgewaehlte_kapitel=None, progress_callback=None):
    """
    Lädt JSON-Annotationen, filtert Kapitel optional und erstellt PDFs.
    """

    eingabe_ordner = Path(eingabe_ordner)
    ausgabe_ordner = Path(ausgabe_ordner)

    os.makedirs(ausgabe_ordner, exist_ok=True)

    dateien = [fn for fn in os.listdir(eingabe_ordner) if fn.endswith('.json')]
    gefilterte_dateien = [
        fn for fn in dateien
        if ausgewaehlte_kapitel is None or os.path.splitext(fn)[0].replace("_gesamt", "") in ausgewaehlte_kapitel
    ]

    for fn in gefilterte_dateien:
        kapitel_name = os.path.splitext(fn)[0].replace("_gesamt", "")
        json_datei = os.path.join(eingabe_ordner, fn)
        with open(json_datei, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        # Unterschritt 1: Tokens verarbeiten
        verarbeite_tokens(json_data)
        if progress_callback:
            progress_callback( 1/3*100)

        # Unterschritt 2: Positionen berechnen
        berechne_positionen(json_data)
        if progress_callback:
            progress_callback( 2/3*100)

        # Unterschritt 3: PDF erstellen
        ts = datetime.now().strftime(config.DATUMSFORMAT)
        pdf_datei = os.path.join(ausgabe_ordner, f"{os.path.splitext(fn)[0]}_{ts}.pdf")
        erstelle_pdf(pdf_datei, json_data)
        if progress_callback:
            progress_callback( 100)