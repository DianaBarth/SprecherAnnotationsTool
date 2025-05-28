import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import tkinter.font as tkFont
import hashlib
from collections import defaultdict
import Eingabe.config as config  # Importiere das komplette config-Modul

def _rgb_to_hex(rgb):
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

def zu_pdf_farbe(rgb):
    return tuple(x / 255.0 for x in rgb)


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
            self.letzte_zeile_y_pos = self.y_pos  # neue Zeile merken
            return

        schrift = self.schrift_holen(element, ist_pdf)
        text_breite = schrift.measure(token) if not ist_pdf else canvas.stringWidth(token, schrift[0], schrift[1])
        text_hoehe = schrift.metrics("linespace") if not ist_pdf else schrift[1]

        if self.x_pos + text_breite > self.max_breite:
            self.x_pos = 10
            self.y_pos += 2 * self.zeilen_hoehe
            self.letzte_zeile_y_pos = self.y_pos  # neue Zeile merken

        # Neu: Ein einziger Aufruf von _zeichne_token mit ist_pdf als Parameter
        self._zeichne_token(canvas, index, element, self.x_pos, self.y_pos, schrift, ist_pdf)

        self.x_pos += text_breite  # x-Position für das nächste Token aktualisieren

    def get_person_color(self,person):
        """Gibt Farb-Tupel für eine Person zurück."""
        if not person:
            return config.FARBE_STANDARD
        h = hashlib.md5(person.encode('utf-8')).hexdigest()
        r = max(int(h[0:2], 16) / 255.0, 0.2)
        g = max(int(h[2:4], 16) / 255.0, 0.2)
        b = max(int(h[4:6], 16) / 255.0, 0.2)
        return r, g, b

    def verwende_hartkodiert_fuer_annotation(self,feldname, annotationswert):
        """
        Prüft, ob für einen bestimmten Wert in einem gegebenen Feld (z. B. "Hauptbetonung" in "betonung"
        oder "Peter" in "person") laut config.AUFGABEN_ANNOTATIONEN 'VerwendeHartKodiert' aktiviert ist.
        """
        if not feldname or not annotationswert:
            return False

        annotationswert = annotationswert.lower()
        for aufgaben_id, annot_liste in config.AUFGABEN_ANNOTATIONEN.items():
            aufgabenname = config.KI_AUFGABEN.get(aufgaben_id)
            if aufgabenname != feldname:
                continue
            for annot in annot_liste:
                name = annot.get("name")
                verwende = annot.get("VerwendeHartKodiert", False)
                if name is None:
                    # Wenn name=None (z. B. bei person), dann prüfen wir nur auf das Feld + True
                    if verwende:
                        return True
                elif name.lower() == annotationswert and verwende:
                    return True
        return False

    def schrift_holen(self, element=None, ist_pdf=False):
        betonung = element.get("betonung", None) if element else None
        annotation = element.get("annotation", None) if element else None
        person = element.get("person", None) if element else None

        if betonung:
            verwende_betonung = self.verwende_hartkodiert_fuer_annotation("betonung", betonung)
        else:
            verwende_betonung = False
      
        if person:
            verwende_person_farbe = self.verwende_hartkodiert_fuer_annotation("person", person)
        else:
            verwende_person_farbe = False

        # Schriftgröße und Familie bestimmen
        if "überschrift" in annotation.lower():
            groesse = config.UEBERSCHRIFT_GROESSE
            if verwende_betonung:
                if "hauptbetonung" in betonung.lower():
                    familie = config.SCHRIFTART_UEBERSCHRIFT_HAUPT
                elif "nebenbetonung" in betonung.lower():
                    familie = config.SCHRIFTART_UEBERSCHRIFT_NEBEN
                else:
                    familie = config.SCHRIFTART_UEBERSCHRIFT
            else:
                familie = config.SCHRIFTART_UEBERSCHRIFT

        elif "legende" in annotation.lower():
            groesse = config.LEGENDE_GROESSE
            if verwende_betonung:
                if "hauptbetonung" in betonung.lower():
                    familie = config.SCHRIFTART_LEGENDE_HAUPT
                elif "nebenbetonung" in betonung.lower():
                    familie = config.SCHRIFTART_LEGENDE_NEBEN
                else:
                    familie = config.SCHRIFTART_LEGENDE
            else:
                familie = config.SCHRIFTART_LEGENDE

        else:
            groesse = config.TEXT_GROESSE
            if verwende_betonung:
                if "hauptbetonung" in betonung.lower():
                    familie = config.SCHRIFTART_BETONUNG_HAUPT
                elif "nebenbetonung" in betonung.lower():
                    familie = config.SCHRIFTART_BETONUNG_NEBEN
                else:
                    familie = config.SCHRIFTART_STANDARD
            else:
                familie = config.SCHRIFTART_STANDARD

        # Farbe bestimmen
        farbe = config.FARBE_STANDARD
        if verwende_person_farbe and person:
            farbe = self.get_person_color(person)

        if ist_pdf:
            return familie, groesse, farbe  # PDF bekommt auch Farbe zurück
        else:
            schrift = tkFont.Font(family=familie, size=groesse)
            return schrift, farbe  # GUI bekommt Schrift + Farbe für z. B. Label.config(fg=farbe)


    # def auf_canvas_rendern(self, canvas, index, element, ist_pdf=False):
    #     token = element.get('token', '')
    #     annotation = element.get("annotation", "")
        
    #     if token == '' or 'zeilenumbruch' in annotation:
    #         self.x_pos = 10
    #         self.y_pos += 2 * self.zeilen_hoehe
    #         self.letzte_zeile_y_pos = self.y_pos  # neue Zeile, also merken
    #         return

    #     schrift = self.schrift_holen(element, ist_pdf)
    #     text_breite = schrift.measure(token) if not ist_pdf else canvas.stringWidth(token, schrift[0], schrift[1])
    #     text_hoehe = schrift.metrics("linespace") if not ist_pdf else schrift[1]

    #     if self.x_pos + text_breite > self.max_breite:
    #         self.x_pos = 10
    #         self.y_pos += 2 * self.zeilen_hoehe
    #         self.letzte_zeile_y_pos = self.y_pos  # neue Zeile, merken

    #     if not ist_pdf:
    #         tag = f'token_{index}'
    #         canvas.create_text(self.x_pos, self.y_pos,
    #                         anchor='nw', text=token,
    #                         font=schrift, fill='black',
    #                         tags=(tag,))            
    #         self._zeichne_marker(canvas, element, self.x_pos, self.y_pos, schrift, ist_pdf)

    #     else:
    #         y_pdf = self._pdf_y_position(canvas, self.y_pos, text_hoehe)
    #         pdf_schriftname, pdf_schriftgroesse = self.schrift_holen(element, ist_pdf)
    #         canvas.setFont(pdf_schriftname, pdf_schriftgroesse)
    #         canvas.drawString(self.x_pos, y_pdf, token)
    #         self._zeichne_marker(canvas, element, self.x_pos, y_pdf, schrift, ist_pdf)

    #     self.x_pos += text_breite + 10
    #     self.letzte_zeile_y_pos = self.y_pos  # aktuelle Zeile merken für nächstes Element
        
    # def schrift_holen(self, element=None, ist_pdf=False):
    #     """
    #     Liefert entweder:
    #     - für Tkinter (ist_pdf=False) ein tkFont.Font-Objekt,
    #     - für PDF (ist_pdf=True) ein Tupel (schriftname, schriftgroesse) basierend auf config.

    #     Args:
    #         element: dict mit 'betonung' und 'annotation' (optional)
    #         ist_pdf: bool, ob PDF-Schrift zurückgegeben werden soll
    #     """

    #     betonung = element.get("betonung", "") if element else ""
    #     annotation = element.get("annotation", "") if element else ""

    #     betonung = betonung.lower()
    #     annotation = annotation.lower()

    #     if "überschrift" in annotation:
    #         groesse = config.UEBERSCHRIFT_GROESSE
    #         if "hauptbetonung" in betonung:
    #             familie = config.SCHRIFTART_UEBERSCHRIFT_HAUPT
    #         elif "nebenbetonung" in betonung:
    #             familie = config.SCHRIFTART_UEBERSCHRIFT_NEBEN
    #         else:
    #             familie = config.SCHRIFTART_UEBERSCHRIFT

    #     elif "legende" in annotation:
    #         groesse = config.LEGENDE_GROESSE
    #         if "hauptbetonung" in betonung:
    #             familie = config.SCHRIFTART_LEGENDE_HAUPT
    #         elif "nebenbetonung" in betonung:
    #             familie = config.SCHRIFTART_LEGENDE_NEBEN
    #         else:
    #             familie = config.SCHRIFTART_LEGENDE

    #     else:
    #         groesse = config.TEXT_GROESSE
    #         if "hauptbetonung" in betonung:
    #             familie = config.SCHRIFTART_BETONUNG_HAUPT
    #         elif "nebenbetonung" in betonung:
    #             familie = config.SCHRIFTART_BETONUNG_NEBEN
    #         else:
    #             familie = config.SCHRIFTART_STANDARD

    #     if ist_pdf:
    #         # PDF: gib Schriftname und Größe zurück (str, int)
    #         return familie, groesse
    #     else:
    #         # GUI: erstelle und gib Tkinter-Font-Objekt zurück
    #         return tkFont.Font(family=familie, size=groesse)
        
    def _zeichne_bild(self, canvas, pfad, x, y, w, h, ist_pdf):
        if ist_pdf:
            try:
                canvas.drawImage(pfad, x, y, width=w, height=h, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print(f"Fehler beim Einfügen von Bild {pfad}: {e}")

    def _get_aufgaben_id_by_name(self, name):
        for id, n in config.KI_AUFGABEN.items():
            if n == name:
                return id
        return None

    # def _zeichne_betonung_haupt(self, canvas, x, y_pos, w, h, oy, linien_breite):
    #     farbe = config.FARBE_BETONUNG_HAUPT
    #     if hasattr(canvas, "setFillColor"):  # PDF canvas (ReportLab)
    #         canvas.setFillColor(zu_pdf_farbe(farbe))
    #         canvas.rect(x, y_pos + oy, w, h, fill=1, stroke=0)
    #     else:  # Tkinter canvas
    #         farbe_hex = _rgb_to_hex(farbe)
    #         canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, fill=farbe_hex, outline="")

    # def _zeichne_betonung_neben(self, canvas, x, y_pos, w, h, oy, linien_breite):
    #     farbe = config.FARBE_BETONUNG_NEBEN
    #     if hasattr(canvas, "setFillColor"):
    #         canvas.setFillColor(zu_pdf_farbe(farbe))
    #         canvas.rect(x, y_pos + oy, w, h, fill=1, stroke=0)
    #     else:
    #         farbe_hex = _rgb_to_hex(farbe)
    #         canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, fill=farbe_hex, outline="")

    def _zeichne_pause_atempause(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_ATEMPAUSE
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.line(x, y_pos + oy + h, x + w, y_pos + oy + h)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_line(x, y_pos + oy + h, x + w, y_pos + oy + h, fill=farbe_hex, width=linien_breite)

    def _zeichne_pause_stau(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_STAU
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.line(x, y_pos + oy + h, x + w, y_pos + oy + h)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_line(x, y_pos + oy + h, x + w, y_pos + oy + h, fill=farbe_hex, width=linien_breite)

    def _zeichne_gedanken_weiter(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_GEDANKEN_ANFANG
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_gedanken_ende(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_GEDANKEN_ENDE
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_gedanken_pause(self, canvas, x, y_pos, w, h, oy, linien_breite):
        # ggf. eigene Farbe oder Stil
        farbe = config.FARBE_GEDANKEN_PAUSE if hasattr(config, "FARBE_GEDANKEN_PAUSE") else config.FARBE_GEDANKEN_ANFANG
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_spannung_start(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_SPANNUNG_START
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_spannung_halten(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_SPANNUNG_HALTEN
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_spannung_stop(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_SPANNUNG_STOPP
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_person(self, canvas, x, y_pos, w, h, sprecher, oy, linien_breite):
        if not sprecher:
            return
        farbe = config.FARBE_SPRECHER.get(sprecher.lower())
        if not farbe:
            return
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_ig(self, canvas, x, y_pos, w, h, wert, oy, linien_breite):  
        # Einfacher Rahmen in Standardfarbe
        farbe = config.FARBE_IG if hasattr(config, "FARBE_IG") else (0, 0, 0)
        if hasattr(canvas, "setStrokeColor"):
            canvas.setStrokeColor(zu_pdf_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = _rgb_to_hex(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)
  
    def _zeichne_hartkodiert(self, canvas, aufgabenname, wert, x, y_pos, w, h, oy, ist_pdf, linien_breite):
        if aufgabenname == "betonung":
            if wert == "Hauptbetonung":
                self._zeichne_betonung_haupt(canvas, x, y_pos, w, h, oy, linien_breite)
            elif wert == "Nebenbetonung":
                self._zeichne_betonung_neben(canvas, x, y_pos, w, h, oy, linien_breite)
        elif aufgabenname == "pause":
            if wert == "Atempause":
                self._zeichne_pause_atem(canvas, x, y_pos, w, h, oy, linien_breite)
            elif wert == "Staupause":
                self._zeichne_pause_stau(canvas, x, y_pos, w, h, oy, linien_breite)
        elif aufgabenname == "gedanken":
            if wert == "gedanken_weiter":
                self._zeichne_gedanken_weiter(canvas, x, y_pos, w, h, oy, linien_breite)
            elif wert == "gedanken_ende":
                self._zeichne_gedanken_ende(canvas, x, y_pos, w, h, oy, linien_breite)
            elif wert == "pause_gedanken":
                self._zeichne_gedanken_pause(canvas, x, y_pos, w, h, oy, linien_breite)
        elif aufgabenname == "spannung":
            if wert == "Starten":
                self._zeichne_spannung_start(canvas, x, y_pos, w, h, oy, linien_breite)
            elif wert == "Halten":
                self._zeichne_spannung_halten(canvas, x, y_pos, w, h, oy, linien_breite)
            elif wert == "Stoppen":
                self._zeichne_spannung_stop(canvas, x, y_pos, w, h, oy, linien_breite)
        elif aufgabenname == "person":
            self._zeichne_person(canvas, x, y_pos, w, h, wert, oy, linien_breite)
        elif aufgabenname == "ig":
            self._zeichne_ig(canvas, x, y_pos, w, h, wert, oy, linien_breite)

    def _zeichne_token(self, canvas, index, element, x, y_pos, schrift, ist_pdf=False):
        token = element.get('token', '')
        tag = f'token_{index}'

        if not ist_pdf:
            # Token auf Tkinter-Canvas zeichnen
            canvas.create_text(
                x, y_pos,
                anchor='nw',
                text=token,
                font=schrift,
                fill='black',
                tags=(tag,)
            )
            w = schrift.measure(token)
            h = schrift.metrics("linespace")
            marker_y = y_pos
        else:
            # Token auf PDF-Canvas zeichnen
            y_pdf = self._pdf_y_position(canvas, y_pos, schrift[1])
            pdf_schriftname, pdf_schriftgroesse = schrift
            canvas.setFont(pdf_schriftname, pdf_schriftgroesse)
            canvas.drawString(x, y_pdf, token)
            w = canvas.stringWidth(token, pdf_schriftname, pdf_schriftgroesse)
            h = pdf_schriftgroesse
            marker_y = y_pdf

        linien_breite = config.LINIENBREITE_STANDARD
        marker = element.get("annotation", {})

        if isinstance(marker, str):
            # Falls marker fälschlich ein String ist (nicht dict), überspringen
            return

        for aufgabenname in config.KI_AUFGABEN.values():
            marker_wert = marker.get(aufgabenname) if isinstance(marker, dict) else None
            if not marker_wert:
                continue

            aufgaben_id = self._get_aufgaben_id_by_name(aufgabenname)
            annot_liste = config.AUFGABEN_ANNOTATIONEN.get(aufgaben_id, [])

            for annot in annot_liste:
                name = annot.get("name")
                if name is not None and name != marker_wert:
                    continue  # nur wenn expliziter Match

                # Y-Verschiebung je nach Aufgabe
                oy = (h * 0.2) if aufgabenname == "ig" else (-h * 0.8)

                if self.verwende_hartkodiert_fuer_annotation(aufgabenname, marker_wert):
                    self._zeichne_hartkodiert(canvas, aufgabenname, marker_wert, x, marker_y, w, h, oy, ist_pdf, linien_breite)
                elif annot.get("bild"):
                    self._zeichne_bild(canvas, annot["bild"], x, marker_y + oy, w, h, ist_pdf)
                else:
                    # Weitere Darstellungen möglich
                    pass


    # def _zeichne_token(self, canvas, index, element, x, y_pos, schrift, ist_pdf=False):
    #     token = element.get('token', '')
    #     tag = f'token_{index}'

    #     if not ist_pdf:
    #         # Token auf Tkinter-Canvas zeichnen
    #         canvas.create_text(x, y_pos,
    #                         anchor='nw', text=token,
    #                         font=schrift, fill='black',
    #                         tags=(tag,))
    #         w = schrift.measure(token)
    #         h = schrift.metrics("linespace")
    #         marker_y = y_pos
    #     else:
    #         # Token auf PDF-Canvas zeichnen
    #         y_pdf = self._pdf_y_position(canvas, y_pos, schrift[1])
    #         pdf_schriftname, pdf_schriftgroesse = schrift
    #         canvas.setFont(pdf_schriftname, pdf_schriftgroesse)
    #         canvas.drawString(x, y_pdf, token)
    #         w = canvas.stringWidth(token, pdf_schriftname, pdf_schriftgroesse)
    #         h = pdf_schriftgroesse
    #         marker_y = y_pdf

    #     linien_breite = config.LINIENBREITE_STANDARD
    #     marker = element.get("annotation", {})

    #     if isinstance(marker, str):
    #         # ggf. Umwandlung falls nötig
    #         pass

    #     for aufgabenname in config.KI_AUFGABEN.values():
    #         marker_wert = marker.get(aufgabenname) if isinstance(marker, dict) else None
    #         if not marker_wert:
    #             continue

    #         annot_liste = config.AUFGABEN_ANNOTATIONEN.get(
    #             self._get_aufgaben_id_by_name(aufgabenname), [])

    #         for annot in annot_liste:
    #             if not annot.get("name") or annot["name"] != marker_wert:
    #                 continue

    #             # Verschiebung Y je nach Aufgabe (oben/unten)
    #             oy = (h * 0.2) if aufgabenname == "ig" else (-h * 0.8)

    #             if annot.get("VerwendeHartKodiert"):
    #                 self._zeichne_hartkodiert(canvas, aufgabenname, marker_wert, x, marker_y, w, h, oy, ist_pdf, linien_breite)
    #             elif annot.get("bild"):
    #                 self._zeichne_bild(canvas, annot["bild"], x, marker_y + oy, w, h, ist_pdf)
    #             else:
    #                 # weitere Markerarten, wenn nötig
    #                 pass

    
    # def _zeichne_marker(self, canvas, element, x, y_pos, schrift, ist_pdf):
    #     linien_breite = config.LINIENBREITE_STANDARD
    #     w = schrift.measure(element.get('token', ''))
    #     h = schrift.metrics("linespace")

    #     # Marker-Daten aus dem Element:
    #     marker = element.get("annotation", {})
    #     if isinstance(marker, str):
    #         # Falls annotation ein String ist, z.B. "betonung=haupt;ig", ggf. in dict parsen (je nach Datenformat)
    #         # Hier beispielhaft: marker = parse_annotation_string(marker)
    #         # Falls schon dict, dann ok.
    #         pass

    #     # Für jede Aufgabe (person, betonung, pause, gedanken, spannung, ig, ...)
    #     for aufgabenname in config.KI_AUFGABEN.values():
    #         marker_wert = marker.get(aufgabenname) if isinstance(marker, dict) else None
    #         if not marker_wert:
    #             continue

    #         # Liste aller Annotationsinfos für diese Aufgabe:
    #         annot_liste = config.AUFGABEN_ANNOTATIONEN.get(
    #             self._get_aufgaben_id_by_name(aufgabenname), [])

    #         for annot in annot_liste:
    #             if not annot.get("name"):
    #                 continue
    #             if annot["name"] != marker_wert:
    #                 continue

    #             # oy je nach Annotationstyp festlegen
    #             if aufgabenname == "ig":
    #                 # IG-Marker unter Token zeichnen
    #                 oy = h * 0.2
    #             else:
    #                 # Andere Marker über Token zeichnen
    #                 oy = -h * 0.8

    #             if annot.get("VerwendeHartKodiert"):
    #                 self._zeichne_hartkodiert(canvas, aufgabenname, marker_wert, x, y_pos, w, h, oy, ist_pdf, linien_breite)
    #             elif annot.get("bild"):
    #                 self._zeichne_bild(canvas, annot["bild"], x, y_pos + oy, w, h, ist_pdf)
    #             else:
    #                 # Falls keine Hartkodiert oder Bild, kannst du hier z.B. weitere Zeichnungsarten ergänzen
    #                 pass
 
    
    # def _zeichne_marker(self, canvas, element, x, y_pos, schrift, ist_pdf):

    #     linien_breite = config.LINIENBREITE_STANDARD

    #     for aufgabenname in config.KI_AUFGABEN.values():
    #         marker_wert = marker.get(aufgabenname)
    #         if not marker_wert:
    #             continue

    #         annot_liste = config.AUFGABEN_ANNOTATIONEN.get(
    #             self._get_aufgaben_id_by_name(aufgabenname), [])

    #         for annot in annot_liste:
    #             if not annot.get("name"):
    #                 continue
    #             if annot["name"] != marker_wert:
    #                 continue

    #             if annot.get("VerwendeHartKodiert"):
    #                 self._zeichne_hartkodiert(canvas, aufgabenname, marker_wert, x, y_pos, w, h, oy, ist_pdf, linien_breite)
    #             elif annot.get("bild"):
    #                 self._zeichne_bild(canvas, annot["bild"], x, y_pos + oy, w, h, ist_pdf)


      
    # def _zeichne_betonung(self,canvas, x, y_pos, w, h, betonung, oy, ist_pdf, linien_breite):
    #     if betonung == "haupt":
    #         farbe = config.FARBE_BETONUNG_HAUPT
    #     elif betonung == "neben":
    #         farbe = config.FARBE_BETONUNG_NEBEN
    #     else:
    #         return

    #     if ist_pdf:
    #         canvas.setFillColor(zu_pdf_farbe(farbe))
    #         canvas.rect(x, y_pos + oy, w, h, fill=1, stroke=0)
    #     else:
    #         farbe_hex = _rgb_to_hex(farbe)
    #         canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, fill=farbe_hex, outline="")

    # def _zeichne_pause(self,canvas, x, y_pos, w, h, pause, oy, ist_pdf, linien_breite):
    #     if pause == "atempause":
    #         farbe = config.FARBE_ATEMPAUSE
    #     elif pause == "staupause":
    #         farbe = config.FARBE_STAU
    #     else:
    #         return

    #     if ist_pdf:
    #         canvas.setStrokeColor(zu_pdf_farbe(farbe))
    #         canvas.setLineWidth(linien_breite)
    #         canvas.line(x, y_pos + oy + h, x + w, y_pos + oy + h)
    #     else:
    #         farbe_hex = _rgb_to_hex(farbe)
    #         canvas.create_line(x, y_pos + oy + h, x + w, y_pos + oy + h, fill=farbe_hex, width=linien_breite)

    # def _zeichne_gedanken(self,canvas, x, y_pos, w, h, gedanken, oy, ist_pdf, linien_breite):
    #     if gedanken == "anfang":
    #         farbe = config.FARBE_GEDANKEN_ANFANG
    #     elif gedanken == "ende":
    #         farbe = config.FARBE_GEDANKEN_ENDE
    #     else:
    #         return

    #     if ist_pdf:
    #         canvas.setStrokeColor(zu_pdf_farbe(farbe))
    #         canvas.setLineWidth(linien_breite)
    #         canvas.rect(x, y_pos + oy, w, h, fill=0)
    #     else:
    #         farbe_hex = _rgb_to_hex(farbe)
    #         canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    # def _zeichne_direkte_rede(self,canvas, x, y_pos, w, h, sprecher, oy, ist_pdf, linien_breite):
    #     if not sprecher:
    #         return
    #     farbe = config.FARBE_SPRECHER.get(sprecher.lower())
    #     if not farbe:
    #         return

    #     if ist_pdf:
    #         canvas.setStrokeColor(zu_pdf_farbe(farbe))
    #         canvas.setLineWidth(linien_breite)
    #         canvas.rect(x, y_pos + oy, w, h, fill=0)
    #     else:
    #         farbe_hex = _rgb_to_hex(farbe)
    #         canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    # def _zeichne_kombinationen(self, canvas, x, y_pos, w, h, pause, gedanken, oy, ist_pdf, linien_breite):
    #     if "staupause" in pause and "ende" in gedanken:
    #         farbe = config.FARBE_KOMB_PAUSE
    #         if ist_pdf:
    #             canvas.setStrokeColor(zu_pdf_farbe(farbe))
    #             canvas.setLineWidth(linien_breite)
    #             canvas.rect(x, y_pos + oy, w, h, fill=0)
    #             canvas.line(x, y_pos + oy, x + w, y_pos + oy + h)
    #             canvas.line(x, y_pos + oy + h, x + w, y_pos + oy)
    #         else:
    #             farbe_hex = _rgb_to_hex(farbe)
    #             canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)
    #             canvas.create_line(x, y_pos + oy, x + w, y_pos + oy + h, fill=farbe_hex, width=linien_breite)
    #             canvas.create_line(x, y_pos + oy + h, x + w, y_pos + oy, fill=farbe_hex, width=linien_breite)

    # def _zeichne_marker(self, canvas, x, y_pos, w, h, marker, oy, ist_pdf):
    #     linien_breite = config.LINIENBREITE_STANDARD

    #     self._zeichne_fuer_aufgabe(canvas, 4, x, y_pos, w, h, marker.get("betonung"), oy, ist_pdf, linien_breite)
    #     self._zeichne_fuer_aufgabe(canvas, 5, x, y_pos, w, h, marker.get("pause"), oy, ist_pdf, linien_breite)
    #     self._zeichne_fuer_aufgabe(canvas, 6, x, y_pos, w, h, marker.get("gedanken"), oy, ist_pdf, linien_breite)
    #     self._zeichne_fuer_aufgabe(canvas, 3, x, y_pos, w, h, marker.get("sprecher"), oy, ist_pdf, linien_breite)
    #     self._zeichne_kombinationen(canvas, x, y_pos, w, h, marker.get("pause"), marker.get("gedanken"), oy, ist_pdf, linien_breite)





    # def _zeichne_marker(self,canvas, x, y_pos, w, h, marker, oy, ist_pdf):
    #     betonung = marker.get("betonung")
    #     pause = marker.get("pause")
    #     gedanken = marker.get("gedanken")
    #     sprecher = marker.get("sprecher")

    #     linien_breite = config.LINIENBREITE_STANDARD

    #     self._zeichne_betonung(canvas, x, y_pos, w, h, betonung, oy, ist_pdf, linien_breite)
    #     self._zeichne_pause(canvas, x, y_pos, w, h, pause, oy, ist_pdf, linien_breite)
    #     self._zeichne_gedanken(canvas, x, y_pos, w, h, gedanken, oy, ist_pdf, linien_breite)
    #     self._zeichne_direkte_rede(canvas, x, y_pos, w, h, sprecher, oy, ist_pdf, linien_breite)
    #     self._zeichne_kombinationen(canvas, x, y_pos, w, h, pause, gedanken, oy, ist_pdf, linien_breite)

  

    # def _zeichne_marker(self, canvas, element, x_pos, y_pos, schrift, ist_pdf=False, vorherige_zeile=None):
    #     """
    #     Zeichnet Marker (Pause, Spannung, Gedanken) auf Canvas.
    #     Unterscheidet Tkinter-Canvas (ist_pdf=False) und ReportLab PDF-Canvas (ist_pdf=True).

    #     Args:
    #         canvas: Tkinter Canvas oder ReportLab Canvas
    #         element: dict mit Annotationen (z.B. element["pause"], element["spannung"], element["gedanken"], element["token"])
    #         x_pos, y_pos: Position, an der der Token gezeichnet wurde (links oben)
    #         schrift: Tkinter Font-Objekt (für GUI) oder Tuple (schriftname, schriftgroesse) für PDF
    #         ist_pdf: bool, ob PDF-Canvas verwendet wird
    #         vorherige_zeile: int oder None, zuletzt gezeichnete Zeile (für Linienunterbrechung bei Zeilenwechsel)
    #     """

    #     print(f"Zeichne Marker für Token: '{element.get('token', '?')}' an Position ({x_pos}, {y_pos})")

    #     pause = element.get("pause", element.get("Pause", "")).lower()
    #     spannung = element.get("spannung", element.get("Spannung", "")).lower()
    #     gedanken = element.get("gedanken", element.get("Gedanken", "")).lower()
    #     token = element.get("token", "?")

    #     if not ist_pdf:
    #         text_breite = schrift.measure(token)
    #         text_hoehe = schrift.metrics("linespace")
    #     else:
    #         schrift_groesse = schrift[1]
    #         text_hoehe = schrift_groesse
    #         font_name = getattr(config, "PDF_FONT_NAME", "Helvetica")
    #         text_breite = canvas.stringWidth(token, font_name, schrift_groesse)

    #     print(f"text_breite={text_breite}, text_hoehe={text_hoehe}")

    #     oy = getattr(config, "MARKER_OFFSET_Y", 5)
    #     w = getattr(config, "MARKER_BREITE_KURZ", 6)
    #     h = w

    #     x = x_pos + text_breite / 2 - w / 2  # zentriert über Token
    #     unterstrich_y_pos = y_pos - 2  # Position Unterstrich

    #     # Farbwerte (für PDF als Color, für Tkinter als Hex)
    #     def zu_pdf_farbe(rgb):
    #         r, g, b = rgb
    #         return Color(r / 255, g / 255, b / 255)

    #     if ist_pdf:
    #         from reportlab.lib.colors import Color
    #         linien_breite = getattr(config, "LINIENBREITE_STANDARD", 1)
    #         canvas.setLineWidth(linien_breite)

    #         farbe_spannung = zu_pdf_farbe(getattr(config, "FARBE_SPANNUNG", (255, 0, 0)))
    #         farbe_atempause = zu_pdf_farbe(getattr(config, "FARBE_ATEMPAUSE", (128, 128, 128)))
    #         farbe_staupause = zu_pdf_farbe(getattr(config, "FARBE_STAUPAUSE", (64, 64, 64)))
    #         farbe_pause_gedanken = zu_pdf_farbe(getattr(config, "FARBE_GEDANKENPAUSE", (0, 128, 0)))
    #         farbe_komb_pause = zu_pdf_farbe(getattr(config, "FARBE_KOMB_PAUSE", (128, 0, 128)))
    #         farbe_gedankenweiter = zu_pdf_farbe(getattr(config, "FARBE_GEDANKENWEITER", (0, 128, 128)))
    #         farbe_gedankenende = zu_pdf_farbe(getattr(config, "FARBE_GEDANKENENDE", (128, 0, 0)))
    #         farbe_unterstrich = zu_pdf_farbe(getattr(config, "FARBE_UNTERSTREICHUNG", (0, 0, 0)))
    #     else:
    #         linien_breite = getattr(config, "LINIENBREITE_STANDARD", 1)

    #         def rgb2hex(rgb):
    #             return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    #         farbe_spannung = rgb2hex(getattr(config, "FARBE_SPANNUNG", (255, 0, 0)))
    #         farbe_atempause = rgb2hex(getattr(config, "FARBE_ATEMPAUSE", (128, 128, 128)))
    #         farbe_staupause = rgb2hex(getattr(config, "FARBE_STAUPAUSE", (64, 64, 64)))
    #         farbe_pause_gedanken = rgb2hex(getattr(config, "FARBE_GEDANKENPAUSE", (0, 128, 0)))
    #         farbe_komb_pause = rgb2hex(getattr(config, "FARBE_KOMB_PAUSE", (128, 0, 128)))
    #         farbe_gedankenweiter = rgb2hex(getattr(config, "FARBE_GEDANKENWEITER", (0, 128, 128)))
    #         farbe_gedankenende = rgb2hex(getattr(config, "FARBE_GEDANKENENDE", (128, 0, 0)))
    #         farbe_unterstrich = rgb2hex(getattr(config, "FARBE_UNTERSTREICHUNG", (0, 0, 0)))

    #     # --- Spannung zeichnen ---

    #     if spannung == "starten":
    #         print("Spannung: starten")
    #         if ist_pdf:
    #             canvas.setStrokeColor(farbe_spannung)
    #             canvas.setLineWidth(linien_breite)
    #             steps = 10
    #             path_bogen = canvas.beginPath()
    #             for i in range(steps):
    #                 t = i / float(steps)
    #                 x1 = x_pos + t * text_breite
    #                 y1 = y_pos + oy + h / 2 + t * getattr(config, "SPANNUNG_NEIGUNG", 5)
    #                 if i == 0:
    #                     path_bogen.moveTo(x1, y1)
    #                 else:
    #                     path_bogen.lineTo(x1, y1)
    #             canvas.drawPath(path_bogen)
    #         else:
    #             canvas.create_line(x_pos, y_pos + oy + h / 2,
    #                             x_pos + text_breite, y_pos + oy + h / 2 + getattr(config, "SPANNUNG_NEIGUNG", 5),
    #                             fill=farbe_spannung, width=linien_breite, smooth=True)

    #     elif spannung == "halten":
    #         print("Spannung: halten")
    #         if ist_pdf:
    #             canvas.setStrokeColor(farbe_spannung)
    #             canvas.setLineWidth(linien_breite)
    #             y = y_pos + oy + h / 2
    #             path_halten = canvas.beginPath()
    #             path_halten.moveTo(x_pos, y)
    #             path_halten.lineTo(x_pos + text_breite, y)
    #             canvas.drawPath(path_halten)
    #         else:
    #             canvas.create_line(x_pos, y_pos + oy + h / 2,
    #                             x_pos + text_breite, y_pos + oy + h / 2,
    #                             fill=farbe_spannung, width=linien_breite)

    #     elif spannung == "stoppen":
    #         print("Spannung: stoppen")
    #         if ist_pdf:
    #             canvas.setStrokeColor(farbe_spannung)
    #             canvas.setLineWidth(linien_breite)
    #             # Punktlinie
    #             path_stoppen = canvas.beginPath()
    #             path_stoppen.moveTo(x_pos + text_breite, y_pos + oy + h / 2)
    #             path_stoppen.lineTo(x_pos + text_breite, y_pos + oy + h / 2)
    #             canvas.drawPath(path_stoppen)
    #             # Abfallender Bogen
    #             steps = 10
    #             path_bogen = canvas.beginPath()
    #             for i in range(steps):
    #                 t = i / float(steps)
    #                 x1 = x_pos + t * text_breite
    #                 y1 = y_pos + oy + h / 2 - t * getattr(config, "SPANNUNG_NEIGUNG", 5)
    #                 if i == 0:
    #                     path_bogen.moveTo(x1, y1)
    #                 else:
    #                     path_bogen.lineTo(x1, y1)
    #             canvas.drawPath(path_bogen)
    #         else:
    #             canvas.create_line(x_pos, y_pos + oy + h / 2 + getattr(config, "SPANNUNG_NEIGUNG", 5),
    #                             x_pos + text_breite, y_pos + oy + h / 2,
    #                             fill=farbe_spannung, width=linien_breite, smooth=True)

    #     # --- Pause zeichnen ---
    #     # Atempause: einfache Linie
    #     if "atempause" in pause:
    #         print("Pause: Atempause")
    #         if ist_pdf:
    #             canvas.setStrokeColor(farbe_atempause)
    #             canvas.setLineWidth(linien_breite)
    #             length = text_breite / 2
    #             x_start = x_pos + (text_breite - length) / 2
    #             y = unterstrich_y_pos
    #             canvas.line(x_start, y, x_start + length, y)
    #         else:
    #             length = text_breite / 2
    #             x_start = x_pos + (text_breite - length) / 2
    #             y = unterstrich_y_pos
    #             canvas.create_line(x_start, y, x_start + length, y, fill=farbe_atempause, width=linien_breite)

    #     # Staupause: gestrichelte Linie
    #     if "staupause" in pause:
    #         print("Pause: Staupause")
    #         if ist_pdf:
    #             canvas.setStrokeColor(farbe_staupause)
    #             canvas.setLineWidth(linien_breite)
    #             length = text_breite / 2
    #             x_start = x_pos + (text_breite - length) / 2
    #             y = unterstrich_y_pos
    #             canvas.setDash(3, 3)
    #             canvas.line(x_start, y, x_start + length, y)
    #             canvas.setDash()  # Reset Dash
    #         else:
    #             length = text_breite / 2
    #             x_start = x_pos + (text_breite - length) / 2
    #             y = unterstrich_y_pos
    #             canvas.create_line(x_start, y, x_start + length, y, fill=farbe_staupause, width=linien_breite, dash=(3, 3))

    #     # Kombination von Pause und Gedanken?
    #     if "pause_gedanken" in pause:
    #         print("Pause: Pause+Gedanken")
    #         # Hier Beispiel: rote gestrichelte Linie
    #         if ist_pdf:
    #             canvas.setStrokeColor(farbe_pause_gedanken)
    #             canvas.setLineWidth(linien_breite)
    #             length = text_breite
    #             y = unterstrich_y_pos
    #             canvas.setDash(5, 2)
    #             canvas.line(x_pos, y, x_pos + length, y)
    #             canvas.setDash()
    #         else:
    #             length = text_breite
    #             y = unterstrich_y_pos
    #             canvas.create_line(x_pos, y, x_pos + length, y, fill=farbe_pause_gedanken, width=linien_breite, dash=(5, 2))

    #     # --- Gedanken zeichnen ---
    #     if gedanken == "gedanken_weiter":
    #         print("Gedanken: weiter")
    #         if ist_pdf:
    #             canvas.setStrokeColor(farbe_gedankenweiter)
    #             canvas.setLineWidth(linien_breite)
    #             x1 = x_pos + text_breite / 2
    #             y1 = y_pos + oy
    #             y2 = y1 - h
    #             canvas.line(x1, y1, x1, y2)
    #         else:
    #             x1 = x_pos + text_breite / 2
    #             y1 = y_pos + oy
    #             y2 = y1 - h
    #             canvas.create_line(x1, y1, x1, y2, fill=farbe_gedankenweiter, width=linien_breite)

    #     elif gedanken == "gedanken_ende":
    #         print("Gedanken: ende")
    #         if ist_pdf:
    #             canvas.setStrokeColor(farbe_gedankenende)
    #             canvas.setLineWidth(linien_breite)
    #             x1 = x_pos + text_breite / 2
    #             y1 = y_pos + oy
    #             y2 = y1 - h
    #             canvas.line(x1, y1, x1, y2)
    #             canvas.line(x1 - w / 2, y2, x1 + w / 2, y2)
    #         else:
    #             x1 = x_pos + text_breite / 2
    #             y1 = y_pos + oy
    #             y2 = y1 - h
    #             canvas.create_line(x1, y1, x1, y2, fill=farbe_gedankenende, width=linien_breite)
    #             canvas.create_line(x1 - w / 2, y2, x1 + w / 2, y2, fill=farbe_gedankenende, width=linien_breite)

    #     # Unterstrich als Abschluss
    #     if ist_pdf:
    #         canvas.setStrokeColor(farbe_unterstrich)
    #         canvas.setLineWidth(linien_breite)
    #         canvas.line(x_pos, unterstrich_y_pos, x_pos + text_breite, unterstrich_y_pos)
    #     else:
    #         canvas.create_line(x_pos, unterstrich_y_pos, x_pos + text_breite, unterstrich_y_pos, fill=farbe_unterstrich, width=linien_breite)
