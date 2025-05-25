import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, red, blue, green
import tkinter.font as tkFont

import Eingabe.config as config  # Importiere das komplette config-Modul

_rgb = lambda rgb: "#%02x%02x%02x" % rgb
    

class AnnotationRenderer:
    def __init__(self, ignorierte_annotationen=None, ignorier_ig=False, max_breite=680):
        self.ignorierte_annotationen = set(a.lower() for a in (ignorierte_annotationen or []))
        self.ignorier_ig = ignorier_ig
        self.max_breite = max_breite

        self.x_pos = 10
        self.y_pos = 10
        self.letzte_zeile_y_pos = 10
        self.zeilen_hoehe = 30  # Höhe pro Textzeile (kann dynamisch bestimmt werden)
        self._zu_hex = lambda rgb: "#%02x%02x%02x" % rgb


    def _pdf_y_position(self, pdf_canvas, y_gui_pos, text_hoehe):
        """Konvertiert GUI-y-Koordinate in PDF-y-Koordinate (invertiert)"""
        seiten_hoehe = pdf_canvas._pagesize[1]
        return seiten_hoehe - y_gui_pos - text_hoehe

    def positionen_zuruecksetzen(self):
        self.x_pos = 10
        self.y_pos = 10

    def rendern(self, index=0, dict_element=None, gui_canvas=None, pdf_canvas=None):
        if gui_canvas is not None:
            return self.auf_canvas_rendern(gui_canvas, index, dict_element, False)
        else:
            return self.auf_canvas_rendern(pdf_canvas, index, dict_element, True)
        
    def auf_canvas_rendern(self, canvas, index, element, ist_pdf=False):
        token = element.get('token', '')
        annotation = element.get("annotation", "")
        
        if token == '' or 'zeilenumbruch' in annotation:
            self.x_pos = 10
            self.y_pos += 2 * self.zeilen_hoehe
            self.letzte_zeile_y_pos = self.y_pos  # neue Zeile, also merken
            return

        schrift = self.schrift_holen(element, ist_pdf)
        text_breite = schrift.measure(token) if not ist_pdf else canvas.stringWidth(token, schrift[0], schrift[1])
        text_hoehe = schrift.metrics("linespace") if not ist_pdf else schrift[1]

        if self.x_pos + text_breite > self.max_breite:
            self.x_pos = 10
            self.y_pos += 2 * self.zeilen_hoehe
            self.letzte_zeile_y_pos = self.y_pos  # neue Zeile, merken

        if not ist_pdf:
            tag = f'token_{index}'
            canvas.create_text(self.x_pos, self.y_pos,
                            anchor='nw', text=token,
                            font=schrift, fill='black',
                            tags=(tag,))
            self._zeichne_marker(canvas, element, self.x_pos, self.y_pos, schrift, ist_pdf=False, vorherige_zeile=self.letzte_zeile_y_pos)

        else:
            y_pdf = self._pdf_y_position(canvas, self.y_pos, text_hoehe)
            pdf_schriftname, pdf_schriftgroesse = self.schrift_holen(element, ist_pdf)
            canvas.setFont(pdf_schriftname, pdf_schriftgroesse)
            canvas.drawString(self.x_pos, y_pdf, token)
            self._zeichne_marker(canvas, element, self.x_pos, y_pdf, schrift, ist_pdf=True, vorherige_zeile=self.letzte_zeile_y_pos)

        self.x_pos += text_breite + 10
        self.letzte_zeile_y_pos = self.y_pos  # aktuelle Zeile merken für nächstes Element
        

    def schrift_holen(self, element=None, ist_pdf=False):
        """
        Liefert entweder:
        - für Tkinter (ist_pdf=False) ein tkFont.Font-Objekt,
        - für PDF (ist_pdf=True) ein Tupel (schriftname, schriftgroesse) basierend auf config.

        Args:
            element: dict mit 'betonung' und 'annotation' (optional)
            ist_pdf: bool, ob PDF-Schrift zurückgegeben werden soll
        """

        betonung = element.get("betonung", "") if element else ""
        annotation = element.get("annotation", "") if element else ""

        betonung = betonung.lower()
        annotation = annotation.lower()

        if "überschrift" in annotation:
            groesse = config.UEBERSCHRIFT_GROESSE
            if "hauptbetonung" in betonung:
                familie = config.SCHRIFTART_UEBERSCHRIFT_HAUPT
            elif "nebenbetonung" in betonung:
                familie = config.SCHRIFTART_UEBERSCHRIFT_NEBEN
            else:
                familie = config.SCHRIFTART_UEBERSCHRIFT

        elif "legende" in annotation:
            groesse = config.LEGENDE_GROESSE
            if "hauptbetonung" in betonung:
                familie = config.SCHRIFTART_LEGENDE_HAUPT
            elif "nebenbetonung" in betonung:
                familie = config.SCHRIFTART_LEGENDE_NEBEN
            else:
                familie = config.SCHRIFTART_LEGENDE

        else:
            groesse = config.TEXT_GROESSE
            if "hauptbetonung" in betonung:
                familie = config.SCHRIFTART_BETONUNG_HAUPT
            elif "nebenbetonung" in betonung:
                familie = config.SCHRIFTART_BETONUNG_NEBEN
            else:
                familie = config.SCHRIFTART_STANDARD

        if ist_pdf:
            # PDF: gib Schriftname und Größe zurück (str, int)
            return familie, groesse
        else:
            # GUI: erstelle und gib Tkinter-Font-Objekt zurück
            return tkFont.Font(family=familie, size=groesse)

    def _zeichne_marker(self, canvas, element, x_pos, y_pos, schrift, ist_pdf=False, vorherige_zeile=None):
        """
        Zeichnet Marker (Pause, Spannung, Gedanken) auf Canvas.
        Unterscheidet Tkinter-Canvas (ist_pdf=False) und ReportLab PDF-Canvas (ist_pdf=True).

        Args:
            canvas: Tkinter Canvas oder ReportLab Canvas
            element: dict mit Annotationen (z.B. element["pause"], element["spannung"], element["gedanken"], element["token"])
            x_pos, y_pos: Position, an der der Token gezeichnet wurde (links oben)
            schrift: Tkinter Font-Objekt (für GUI) oder Tuple (schriftname, schriftgroesse) für PDF
            ist_pdf: bool, ob PDF-Canvas verwendet wird
            vorherige_zeile: int oder None, zuletzt gezeichnete Zeile (für Linienunterbrechung bei Zeilenwechsel)
        """

        print(f"Zeichne Marker für Token: '{element.get('token', '?')}' an Position ({x_pos}, {y_pos})")

        pause = element.get("pause", element.get("Pause", "")).lower()
        spannung = element.get("spannung", element.get("Spannung", "")).lower()
        gedanken = element.get("gedanken", element.get("Gedanken", "")).lower()
        token = element.get("token", "?")

        if not ist_pdf:
            text_breite = schrift.measure(token)
            text_hoehe = schrift.metrics("linespace")
        else:
            schrift_groesse = schrift[1]
            text_hoehe = schrift_groesse
            font_name = getattr(config, "PDF_FONT_NAME", "Helvetica")
            text_breite = canvas.stringWidth(token, font_name, schrift_groesse)

        print(f"text_breite={text_breite}, text_hoehe={text_hoehe}")

        oy = getattr(config, "MARKER_OFFSET_Y", 5)
        w = getattr(config, "MARKER_BREITE_KURZ", 6)
        h = w

        x = x_pos + text_breite / 2 - w / 2  # zentriert über Token
        unterstrich_y_pos = y_pos - 2  # Position Unterstrich

        # Farbwerte (für PDF als Color, für Tkinter als Hex)
        def zu_pdf_farbe(rgb):
            r, g, b = rgb
            return Color(r / 255, g / 255, b / 255)

        if ist_pdf:
            from reportlab.lib.colors import Color
            linien_breite = getattr(config, "LINIENBREITE_STANDARD", 1)
            canvas.setLineWidth(linien_breite)

            farbe_spannung = zu_pdf_farbe(getattr(config, "FARBE_SPANNUNG", (255, 0, 0)))
            farbe_pause = zu_pdf_farbe(getattr(config, "FARBE_PAUSE", (0, 0, 255)))
            farbe_gedanken = zu_pdf_farbe(getattr(config, "FARBE_GEDANKEN", (0, 128, 0)))
            farbe_atempause = zu_pdf_farbe(getattr(config, "FARBE_ATEMPAUSE", (128, 128, 128)))
            farbe_staupause = zu_pdf_farbe(getattr(config, "FARBE_STAUPAUSE", (64, 64, 64)))
            farbe_pause_gedanken = zu_pdf_farbe(getattr(config, "FARBE_GEDANKENPAUSE", (0, 128, 0)))
            farbe_komb_pause = zu_pdf_farbe(getattr(config, "FARBE_KOMB_PAUSE", (128, 0, 128)))
            farbe_gedankenweiter = zu_pdf_farbe(getattr(config, "FARBE_GEDANKENWEITER", (0, 128, 128)))
            farbe_gedankenende = zu_pdf_farbe(getattr(config, "FARBE_GEDANKENENDE", (128, 0, 0)))
            farbe_unterstrich = zu_pdf_farbe(getattr(config, "FARBE_UNTERSTREICHUNG", (0, 0, 0)))
        else:
            linien_breite = getattr(config, "LINIENBREITE_STANDARD", 1)

            def rgb2hex(rgb):
                return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

            farbe_spannung = rgb2hex(getattr(config, "FARBE_SPANNUNG", (255, 0, 0)))
            farbe_pause = rgb2hex(getattr(config, "FARBE_PAUSE", (0, 0, 255)))
            farbe_gedanken = rgb2hex(getattr(config, "FARBE_GEDANKEN", (0, 128, 0)))
            farbe_atempause = rgb2hex(getattr(config, "FARBE_ATEMPAUSE", (128, 128, 128)))
            farbe_staupause = rgb2hex(getattr(config, "FARBE_STAUPAUSE", (64, 64, 64)))
            farbe_pause_gedanken = rgb2hex(getattr(config, "FARBE_GEDANKENPAUSE", (0, 128, 0)))
            farbe_komb_pause = rgb2hex(getattr(config, "FARBE_KOMB_PAUSE", (128, 0, 128)))
            farbe_gedankenweiter = rgb2hex(getattr(config, "FARBE_GEDANKENWEITER", (0, 128, 128)))
            farbe_gedankenende = rgb2hex(getattr(config, "FARBE_GEDANKENENDE", (128, 0, 0)))
            farbe_unterstrich = rgb2hex(getattr(config, "FARBE_UNTERSTREICHUNG", (0, 0, 0)))

        # --- Spannung zeichnen ---

        if spannung == "starten":
            print("Spannung: starten")
            if ist_pdf:
                canvas.setStrokeColor(farbe_spannung)
                canvas.setLineWidth(linien_breite)
                steps = 10
                path_bogen = canvas.beginPath()
                for i in range(steps):
                    t = i / float(steps)
                    x1 = x_pos + t * text_breite
                    y1 = y_pos + oy + h / 2 + t * getattr(config, "SPANNUNG_NEIGUNG", 5)
                    if i == 0:
                        path_bogen.moveTo(x1, y1)
                    else:
                        path_bogen.lineTo(x1, y1)
                canvas.drawPath(path_bogen)
            else:
                canvas.create_line(x_pos, y_pos + oy + h / 2,
                                x_pos + text_breite, y_pos + oy + h / 2 + getattr(config, "SPANNUNG_NEIGUNG", 5),
                                fill=farbe_spannung, width=linien_breite, smooth=True)

        elif spannung == "halten":
            print("Spannung: halten")
            if ist_pdf:
                canvas.setStrokeColor(farbe_spannung)
                canvas.setLineWidth(linien_breite)
                y = y_pos + oy + h / 2
                path_halten = canvas.beginPath()
                path_halten.moveTo(x_pos, y)
                path_halten.lineTo(x_pos + text_breite, y)
                canvas.drawPath(path_halten)
            else:
                canvas.create_line(x_pos, y_pos + oy + h / 2,
                                x_pos + text_breite, y_pos + oy + h / 2,
                                fill=farbe_spannung, width=linien_breite)

        elif spannung == "stoppen":
            print("Spannung: stoppen")
            if ist_pdf:
                canvas.setStrokeColor(farbe_spannung)
                canvas.setLineWidth(linien_breite)
                # Punktlinie
                path_stoppen = canvas.beginPath()
                path_stoppen.moveTo(x_pos + text_breite, y_pos + oy + h / 2)
                path_stoppen.lineTo(x_pos + text_breite, y_pos + oy + h / 2)
                canvas.drawPath(path_stoppen)
                # Abfallender Bogen
                steps = 10
                path_bogen = canvas.beginPath()
                for i in range(steps):
                    t = i / float(steps)
                    x1 = x_pos + t * text_breite
                    y1 = y_pos + oy + h / 2 - t * getattr(config, "SPANNUNG_NEIGUNG", 5)
                    if i == 0:
                        path_bogen.moveTo(x1, y1)
                    else:
                        path_bogen.lineTo(x1, y1)
                canvas.drawPath(path_bogen)
            else:
                canvas.create_line(x_pos, y_pos + oy + h / 2 + getattr(config, "SPANNUNG_NEIGUNG", 5),
                                x_pos + text_breite, y_pos + oy + h / 2,
                                fill=farbe_spannung, width=linien_breite, smooth=True)

        # --- Pause zeichnen ---
        # Atempause: einfache Linie
        if "atempause" in pause:
            print("Pause: Atempause")
            if ist_pdf:
                canvas.setStrokeColor(farbe_atempause)
                canvas.setLineWidth(linien_breite)
                length = text_breite / 2
                x_start = x_pos + (text_breite - length) / 2
                y = unterstrich_y_pos
                canvas.line(x_start, y, x_start + length, y)
            else:
                length = text_breite / 2
                x_start = x_pos + (text_breite - length) / 2
                y = unterstrich_y_pos
                canvas.create_line(x_start, y, x_start + length, y, fill=farbe_atempause, width=linien_breite)

        # Staupause: gestrichelte Linie
        if "staupause" in pause:
            print("Pause: Staupause")
            if ist_pdf:
                canvas.setStrokeColor(farbe_staupause)
                canvas.setLineWidth(linien_breite)
                length = text_breite / 2
                x_start = x_pos + (text_breite - length) / 2
                y = unterstrich_y_pos
                canvas.setDash(3, 3)
                canvas.line(x_start, y, x_start + length, y)
                canvas.setDash()  # Reset Dash
            else:
                length = text_breite / 2
                x_start = x_pos + (text_breite - length) / 2
                y = unterstrich_y_pos
                canvas.create_line(x_start, y, x_start + length, y, fill=farbe_staupause, width=linien_breite, dash=(3, 3))

        # Kombination von Pause und Gedanken?
        if "pause_gedanken" in pause:
            print("Pause: Pause+Gedanken")
            # Hier Beispiel: rote gestrichelte Linie
            if ist_pdf:
                canvas.setStrokeColor(farbe_pause_gedanken)
                canvas.setLineWidth(linien_breite)
                length = text_breite
                y = unterstrich_y_pos
                canvas.setDash(5, 2)
                canvas.line(x_pos, y, x_pos + length, y)
                canvas.setDash()
            else:
                length = text_breite
                y = unterstrich_y_pos
                canvas.create_line(x_pos, y, x_pos + length, y, fill=farbe_pause_gedanken, width=linien_breite, dash=(5, 2))

        # --- Gedanken zeichnen ---
        if gedanken == "weiter":
            print("Gedanken: weiter")
            if ist_pdf:
                canvas.setStrokeColor(farbe_gedankenweiter)
                canvas.setLineWidth(linien_breite)
                x1 = x_pos + text_breite / 2
                y1 = y_pos + oy
                y2 = y1 - h
                canvas.line(x1, y1, x1, y2)
            else:
                x1 = x_pos + text_breite / 2
                y1 = y_pos + oy
                y2 = y1 - h
                canvas.create_line(x1, y1, x1, y2, fill=farbe_gedankenweiter, width=linien_breite)

        elif gedanken == "ende":
            print("Gedanken: ende")
            if ist_pdf:
                canvas.setStrokeColor(farbe_gedankenende)
                canvas.setLineWidth(linien_breite)
                x1 = x_pos + text_breite / 2
                y1 = y_pos + oy
                y2 = y1 - h
                canvas.line(x1, y1, x1, y2)
                canvas.line(x1 - w / 2, y2, x1 + w / 2, y2)
            else:
                x1 = x_pos + text_breite / 2
                y1 = y_pos + oy
                y2 = y1 - h
                canvas.create_line(x1, y1, x1, y2, fill=farbe_gedankenende, width=linien_breite)
                canvas.create_line(x1 - w / 2, y2, x1 + w / 2, y2, fill=farbe_gedankenende, width=linien_breite)

        # Unterstrich als Abschluss
        if ist_pdf:
            canvas.setStrokeColor(farbe_unterstrich)
            canvas.setLineWidth(linien_breite)
            canvas.line(x_pos, unterstrich_y_pos, x_pos + text_breite, unterstrich_y_pos)
        else:
            canvas.create_line(x_pos, unterstrich_y_pos, x_pos + text_breite, unterstrich_y_pos, fill=farbe_unterstrich, width=linien_breite)
