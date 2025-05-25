import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, red, blue, green
import tkinter.font as tkFont

import Eingabe.config as config # Importiere das komplette config-Modul

_rgb = lambda rgb: "#%02x%02x%02x" % rgb

class AnnotationRenderer:
    def __init__(self, ignore_annotations=None, ignore_ig=False):
        """
        ignore_annotations: Liste von Annotation-Namen (case-insensitiv), die ignoriert werden sollen
        """
        self.ignore_annotations = set(a.lower() for a in (ignore_annotations or []))
        self.ignore_ig = ignore_ig

    def render(self, idx =0, dict_element ={}, gui_parent=None, pdf_canvas=None, x=0, y=0, text_width=0):
        """
        Hauptmethode: Entscheidet, ob GUI-Buttons oder PDF gezeichnet werden.

        Args:
          dict_element: Dict mit mindestens 'token' und 'annotation' (String, Komma-separiert)
          gui_parent: Tkinter Frame oder ähnliches (für GUI-Modus)
          pdf_canvas: ReportLab Canvas (für PDF-Modus)
          x,y: Position für PDF-Zeichnen
          text_width: Breite des Tokens in PDF-Koordinaten (für Marker)

        Returns:
          - GUI-Modus: Dict {'token_button': Button, 'marker_buttons': [Buttons]}
          - PDF-Modus: None (direkt auf pdf_canvas gezeichnet)
        """
        annotation_str = dict_element.get("annotation", "")
        annotations = [a.strip().lower() for a in annotation_str.split(",") if a.strip() and a.strip().lower() not in self.ignore_annotations]

        if gui_parent is not None:
            return self._render_gui(idx,dict_element, annotations, gui_parent, x, y)

        elif pdf_canvas is not None:
            self._render_pdf(pdf_canvas, dict_element, x, y, text_width, annotations)
            return None

        else:
            raise ValueError("Bitte gui_parent oder pdf_canvas angeben.")

    # --- GUI RENDERING ---

    def _get_gui_font(self, betonung: str, ist_ueberschrift: bool, ist_legende: bool) -> tkFont.Font:
        """
        Liefert ein tkinter-Font-Objekt basierend auf den config-Schriftarten
        und -größen für Überschrift, Legende oder Standardtext.
        """
        betonung = betonung or ""
        # PDF-Helper gibt uns Fontname / Size, hier erstellen wir das tkFont
        if ist_ueberschrift:
            if "hauptbetonung" in betonung:
                fam = config.SCHRIFTART_UEBERSCHRIFT_HAUPT
            elif "nebenbetonung" in betonung:
                fam = config.SCHRIFTART_UEBERSCHRIFT_NEBEN
            else:
                fam = config.SCHRIFTART_UEBERSCHRIFT
            size = config.UEBERSCHRIFT_GROESSE

        elif ist_legende:
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

    def _render_gui(self, idx, dict_element, annotations, parent, x_pos, y_pos):
        token = dict_element.get("token", "")
        ist_ueberschrift = dict_element.get("KapitelName") is None and dict_element.get("WortNr",0)==0
        ist_legende = False  # je nach Anwendungsfall

        # bestimme Font und Farbe
        betonung = dict_element.get("annotation", "")
        font = self._get_gui_font(betonung, ist_ueberschrift, ist_legende)
        fg = "black"
        if "person" in annotations and hasattr(config, "FARBE_PERSON"):
            fg = self._rgb(config.FARBE_PERSON)

        # Messe Breite und Höhe
        text_width = font.measure(token)
        pixel_breite = max(20, text_width + 20)
        height = font.metrics("linespace") + 10

        # Erzeuge Canvas
        canvas = tk.Canvas(parent, width=pixel_breite, height=height,
                           highlightthickness=1, bd=0)
        canvas.place(x=x_pos, y=y_pos)

        # Text zeichnen
        canvas.create_text(10, height//2, anchor="w", text=token,
                           font=font, fill=fg)

        # … dein on_click + Marker-Aufruf …

        return {"canvas": canvas, "pixel_breite": pixel_breite}
    

    def _draw_markers_on_canvas(self, c, e, x_pos, y_pos, text_width, prev_line, height, font):
            # Werte aus dict
            pause    = e.get("Pause", "").lower()
            spannung = e.get("Spannung", "").lower()
            gedanken = e.get("Gedanken", "").lower()
            token    = e.get("token", "")
            zeile    = e.get("zeile", 0)

            oy = getattr(config, "MARKER_OFFSET_Y", 5)
            w  = getattr(config, "MARKER_BREITE_KURZ", 6)
            h  = getattr(config, "MARKER_BREITE_KURZ", 6)

            # Zeilenwechsel?
            if zeile != prev_line:
                return

            mid_x = x_pos + text_width/2 - w/2

            # --- Spannung: Starten ---
            if spannung == "starten":
                pts = []
                steps = 10
                for i in range(steps+1):
                    t = i/steps
                    xi = x_pos + t*text_width
                    yi = y_pos + oy + h/2 + t*getattr(config, "SPANNUNG_NEIGUNG", 3)
                    pts.append((xi, yi))
                for a,b in zip(pts, pts[1:]):
                    c.create_line(a[0],a[1], b[0],b[1],
                                fill=self._rgb(config.FARBE_SPANNUNG),
                                width=getattr(config, "LINIENBREITE_STANDARD", 1))
            # --- Spannung: Halten ---
            elif spannung == "halten":
                yline = y_pos + oy + h/2
                c.create_line(x_pos, yline, x_pos+text_width, yline,
                            fill=self._rgb(config.FARBE_SPANNUNG),
                            width=getattr(config, "LINIENBREITE_STANDARD", 1))
            # --- Spannung: Stoppen ---
            elif spannung == "stoppen":
                xend = x_pos+text_width
                ymid = y_pos+oy+h/2
                c.create_oval(xend,ymid, xend+1,ymid+1,
                            outline=self._rgb(config.FARBE_SPANNUNG))
                pts = []
                steps = 10
                for i in range(steps+1):
                    t = i/steps
                    xi = x_pos + t*text_width
                    yi = ymid - t*getattr(config, "SPANNUNG_NEIGUNG", 3)
                    pts.append((xi, yi))
                for a,b in zip(pts, pts[1:]):
                    c.create_line(a[0],a[1], b[0],b[1],
                                fill=self._rgb(config.FARBE_SPANNUNG),
                                width=getattr(config, "LINIENBREITE_STANDARD", 1))

            # --- ig-Unterstreichung/Punktierung ---
            if not self.ignore_ig:
                # Ende-ig
                if token.lower().endswith("ig"):
                    ig_start = text_width - font.measure("ig")
                    yline = height//2 + font.metrics("linespace")//2 - 2
                    c.create_line(x_pos+10+ig_start, yline,
                                x_pos+10+ig_start+font.measure("ig"), yline,
                                fill=self._rgb(getattr(config, "FARBE_UNTERSTREICHUNG", (0,0,0))),
                                width=getattr(config, "LINIENBREITE_STANDARD", 1))
                # Binnen-ig
                for i in range(len(token)-2):
                    if token[i:i+2].lower()=="ig" and i != len(token)-2:
                        xpos = x_pos + 10 + font.measure(token[:i+1])
                        ypos = height//2 + font.metrics("linespace")//2
                        r = 2
                        c.create_oval(xpos-r, ypos, xpos+r, ypos+2*r,
                                    fill=self._rgb(getattr(config, "FARBE_UNTERSTREICHUNG", (0,0,0))),
                                    outline="")

            # --- Pausenmarker ---
            if "atempause" in pause:
                yline = y_pos + oy + h + 2
                length = getattr(config, "MARKER_BREITE_LANG", 12)*2
                c.create_line(mid_x, yline, mid_x+length, yline,
                            fill=self._rgb(getattr(config, "FARBE_ATEMPAUSE", (1,0,0))),
                            width=getattr(config, "LINIENBREITE_STANDARD", 1))
            if "staupause" in pause:
                c.create_rectangle(mid_x, y_pos+oy, mid_x+w, y_pos+oy+h,
                                fill=self._rgb(getattr(config, "FARBE_STAUPAUSE", (0,1,0))),
                                width=0)
            if "pause_gedanken" in gedanken:
                cx = mid_x + w/2; cy = y_pos+oy+h/2; r = w/2
                c.create_oval(cx-r, cy-r, cx+r, cy+r,
                            fill=self._rgb(getattr(config, "FARBE_GEDANKENPAUSE", (0,0,1))),
                            width=0)

            if "gedanken_ende" in gedanken and "pause_gedanken" not in gedanken:
                off = w/2
                c.create_line(x_pos+off, y_pos+oy, x_pos+off+w, y_pos+oy, fill=_rgb(config.FARBE_GEDANKENENDE), width=config.LINIENBREITE_STANDARD)
                c.create_line(x_pos+off, y_pos+oy+h, x_pos+off+w, y_pos+oy+h, fill=_rgb(config.FARBE_GEDANKENENDE), width=config.LINIENBREITE_STANDARD)




    