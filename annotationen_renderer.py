import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, red, blue, green
import tkinter.font as tkFont

import Eingabe.config as config # Importiere das komplette config-Modul


class AnnotationRenderer:
    def __init__(self, ignore_annotations=None, ignore_ig=False):
        self.ignore_annotations = set(a.lower() for a in (ignore_annotations or []))
        self.ignore_ig = ignore_ig
        self._to_hex = lambda rgb: "#%02x%02x%02x" % rgb

    def render_on_canvas(self, canvas, idx, element, x_pos, y_pos, prev_line):
        """
        Zeichnet ein Token + Marker auf den gegebenen Canvas bei (x_pos, y_pos).
        """
        token = element.get('token', '')
        annotation_str = element.get('annotation', '')
        annotations = [a.strip().lower() for a in annotation_str.split(',') if a.strip().lower() not in self.ignore_annotations]

        # Font und Stil
        ist_ue = element.get('KapitelName') is None and element.get('WortNr',0)==0
        ist_leg = False
        betonung = annotation_str
        font = self._get_gui_font(betonung, ist_ue, ist_leg)
        fg = 'black'
        if 'person' in annotations and hasattr(config, 'FARBE_PERSON'):
            fg = self._to_hex(config.FARBE_PERSON)

        # Text zeichnen mit Tag
        tag = f'token_{idx}'
        canvas.create_text(x_pos, y_pos,
                           anchor='nw', text=token,
                           font=font, fill=fg,
                           tags=(tag,))

        # Marker drüber
        text_w = font.measure(token)
        self._draw_markers(canvas, element, x_pos, y_pos, text_w, font, prev_line)

    def _get_gui_font(self, betonung, ist_ue, ist_leg):
        betonung = betonung or ''
        if ist_ue:
            if 'hauptbetonung' in betonung:
                fam = config.SCHRIFTART_UEBERSCHRIFT_HAUPT
            elif 'nebenbetonung' in betonung:
                fam = config.SCHRIFTART_UEBERSCHRIFT_NEBEN
            else:
                fam = config.SCHRIFTART_UEBERSCHRIFT
            size = config.UEBERSCHRIFT_GROESSE
        elif ist_leg:
            if 'hauptbetonung' in betonung:
                fam = config.SCHRIFTART_LEGENDE_HAUPT
            elif 'nebenbetonung' in betonung:
                fam = config.SCHRIFTART_LEGENDE_NEBEN
            else:
                fam = config.SCHRIFTART_LEGENDE
            size = config.LEGENDE_GROESSE
        else:
            if 'hauptbetonung' in betonung:
                fam = config.SCHRIFTART_BETONUNG_HAUPT
            elif 'nebenbetonung' in betonung:
                fam = config.SCHRIFTART_BETONUNG_NEBEN
            else:
                fam = config.SCHRIFTART_STANDARD
            size = config.TEXT_GROESSE
        return tkFont.Font(family=fam, size=size)

    def _draw_markers(self, canvas, e, x_pos, y_pos, text_w, font, prev_line):
        # Beispiel: Zeilenwechsel
        zeile = e.get('zeile', 0)
        if zeile != prev_line:
            return
        # Beispiel Spannungsbogen Starten
        spann = e.get('Spannung','').lower()
        if spann == 'starten':
            color = self._to_hex(config.FARBE_SPANNUNG)
            lw = getattr(config, 'LINIENBREITE_STANDARD', 1)
            # einfacher Bogen über Token und nächsten
            canvas.create_arc(x_pos, y_pos-10, x_pos+text_w*2, y_pos+10,
                              style='arc', outline=color, width=lw)
        # Weitere Marker analog implementieren...

    