import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, red, blue, green
import tkinter.font as tkFont

import Eingabe.config as config # Importiere das komplette config-Modul

_rgb = lambda rgb: "#%02x%02x%02x" % rgb
    

class AnnotationRenderer:
    def __init__(self, ignore_annotations=None, ignore_ig=False, max_width=680):
        self.ignore_annotations = set(a.lower() for a in (ignore_annotations or []))
        self.ignore_ig = ignore_ig
        self.max_width = max_width

        self.x_pos = 10
        self.y_pos = 10
        self.line_text_height = 30  # Höhe pro Textzeile (kann dynamisch bestimmt werden)
        self._to_hex = lambda rgb: "#%02x%02x%02x" % rgb
        
    def reset_positions(self):
        self.x_pos = 10
        self.y_pos = 10

    def render(self, idx=0, dict_element=None, gui_parent=None, pdf_canvas=None):
        if gui_parent is not None:
            return self.render_on_canvas(gui_parent, idx, dict_element)
        # PDF-Modus o.ä. ggf. später

    def render_on_canvas(self, canvas, idx, element):
        token = element.get('token', '')

    # Zeilenumbruch, wenn Annotation "zeilenumbruch" enthält oder Token leer ist
        
        annotation = element.get("annotation", "")

        if token == '' or 'zeilenumbruch' in annotation:
            self.x_pos = 10
            self.y_pos += self.line_text_height 
            return

        # Bestimme Font und Textbreite (Tkinter Font benötigt Canvas oder config)
      
        font = self._get_gui_font( element)
        text_width = font.measure(token)
        text_height = font.metrics("linespace")

        # Zeilenumbruch, wenn kein Platz mehr
        if self.x_pos + text_width > self.max_width:
            self.x_pos = 10
            self.y_pos += self.line_text_height

        # Text zeichnen
        tag = f'token_{idx}'
        canvas.create_text(self.x_pos, self.y_pos,
                           anchor='nw', text=token,
                           font=font, fill='black',
                           tags=(tag,))

        self._draw_markers_on_canvas(canvas, element, self.x_pos, self.y_pos, font)

        # Position für nächsten Token verschieben
        self.x_pos += text_width + 10

    def _get_gui_font(self, element = None) -> tkFont.Font:
        """
        Liefert ein tkinter-Font-Objekt basierend auf den config-Schriftarten
        und -größen für Überschrift, Legende oder Standardtext.
        """


        betonung = element.get("betonung","")
        annotation = element.get("Annotation","")

        # PDF-Helper gibt uns Fontname / Size, hier erstellen wir das tkFont
        if "überschrift" in annotation.lower():

            if "hauptbetonung" in betonung:
                fam = config.SCHRIFTART_UEBERSCHRIFT_HAUPT
            elif "nebenbetonung" in betonung:
                fam = config.SCHRIFTART_UEBERSCHRIFT_NEBEN
            else:
                fam = config.SCHRIFTART_UEBERSCHRIFT
            size = config.UEBERSCHRIFT_GROESSE

        elif  "legende" in annotation.lower():
            if "hauptbetonung" in betonung:
                fam = config.SCHRIFTART_LEGENDE_HAUPT
            elif "nebenbetonung" in betonung:
                fam = config.SCHRIFTART_LEGENDE_NEBEN
            else:
                fam = config.SCHRIFTART_LEGENDE
            size = config.LEGENDE_GROESSE

        else:
            if "hauptbetonung" in betonung:
                fam = config.SCHRIFTART_BETONUNG_HAUPT
            elif "nebenbetonung" in betonung:
                fam = config.SCHRIFTART_BETONUNG_NEBEN
            else:
                fam = config.SCHRIFTART_STANDARD
            size = config.TEXT_GROESSE

        # Erstelle und gib den Font zurück
        return tkFont.Font(family=fam, size=size)

    def _draw_markers_on_canvas(self, c, e, x_pos, y_pos, font):
        # Werte aus dict
        pause = e.get("Pause", "").lower()
        spannung = e.get("Spannung", "").lower()
        gedanken = e.get("Gedanken", "").lower()
        token = e.get("token", "")

        text_width = font.measure(token)
        text_height = font.metrics("linespace")

        oy = getattr(config, "MARKER_OFFSET_Y", 5)
        w = getattr(config, "MARKER_BREITE_KURZ", 6)
        h = getattr(config, "MARKER_BREITE_KURZ", 6)

        mid_x = x_pos + text_width / 2 - w / 2

        # Spannung zeichnen
        color_sp = self._to_hex(getattr(config, "FARBE_SPANNUNG", (255, 0, 0)))
        line_w = getattr(config, "LINIENBREITE_STANDARD", 1)
        height = font.metrics("linespace")

        if spannung == "starten":
            pts = []
            for i in range(11):
                t = i / 10
                xi = x_pos + t * text_width
                yi = y_pos + height // 2 + oy + t * getattr(config, "SPANNUNG_NEIGUNG", 3)
                pts.append((xi, yi))
            for p1, p2 in zip(pts, pts[1:]):
                c.create_line(*p1, *p2, fill=color_sp, width=line_w)

        elif spannung == "halten":
            y = y_pos + height // 2 + oy
            c.create_line(x_pos, y, x_pos + text_width, y, fill=color_sp, width=line_w)

        elif spannung == "stoppen":
            xend = x_pos + text_width
            ymid = y_pos + height // 2 + oy
            c.create_oval(xend, ymid, xend + 1, ymid + 1, outline=color_sp)
            pts = []
            for i in range(11):
                t = i / 10
                xi = x_pos + t * text_width
                yi = ymid - t * getattr(config, "SPANNUNG_NEIGUNG", 3)
                pts.append((xi, yi))
            for p1, p2 in zip(pts, pts[1:]):
                c.create_line(*p1, *p2, fill=color_sp, width=line_w)

        # ig-Unterstreichung/Punktierung
        if not self.ignore_ig:
            color_ug = self._to_hex(getattr(config, "FARBE_UNTERSTREICHUNG", (0, 0, 0)))
            # Wortende
            if token.lower().endswith("ig"):
                ig_start = font.measure(token) - font.measure("ig")
                yline = y_pos + height // 2 + font.metrics("linespace") // 2 - 2
                c.create_line(x_pos + ig_start, yline, x_pos + ig_start + font.measure("ig"), yline,
                                fill=color_ug, width=line_w)
            # Binnen
            for i in range(len(token) - 2):
                if token[i:i + 2].lower() == "ig" and i != len(token) - 2:
                    xpos = x_pos + font.measure(token[:i + 1])
                    ypos = y_pos + height // 2 + font.metrics("linespace") // 2
                    c.create_oval(xpos - 2, ypos, xpos + 2, ypos + 4, fill=color_ug, outline="")

        # Pausen
        if "atempause" in pause:
            yline = y_pos + height // 2 + oy + h + 2
            color_ap = self._to_hex(getattr(config, "FARBE_ATEMPAUSE", (255, 0, 0)))
            length = getattr(config, "MARKER_BREITE_LANG", 12) * 2
            c.create_line(mid_x, yline, mid_x + length, yline, fill=color_ap, width=line_w)

        if "staupause" in pause:
            color_spu = self._to_hex(getattr(config, "FARBE_STAUPAUSE", (0, 255, 0)))
            c.create_rectangle(mid_x, y_pos + height // 2 + oy, mid_x + w, y_pos + height // 2 + oy + h,
                                fill=color_spu, width=0)

        if "pause_gedanken" in gedanken:
            color_gp = self._to_hex(getattr(config, "FARBE_GEDANKENPAUSE", (0, 0, 255)))
            cx = mid_x + w / 2
            cy = y_pos + height // 2 + oy + h / 2
            r = w / 2
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color_gp, width=0)

        # Gedankenschluss
        if "gedanken_ende" in gedanken and "pause_gedanken" not in gedanken:
            color_ge = self._to_hex(getattr(config, "FARBE_GEDANKENENDE", (0, 0, 0)))
            off = w / 2
            c.create_line(mid_x, y_pos + height // 2 + oy, mid_x + w, y_pos + height // 2 + oy, fill=color_ge, width=line_w)
            c.create_line(mid_x, y_pos + height // 2 + oy + h, mid_x + w, y_pos + height // 2 + oy + h, fill=color_ge, width=line_w)