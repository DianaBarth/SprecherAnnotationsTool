import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import tkinter.font as tkFont
import hashlib
from collections import defaultdict
import Eingabe.config as config  # Importiere das komplette config-Modul

def zu_Hex_farbe(rgb):
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

def zu_PDF_farbe(rgb):
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
     
    def _pdf_y_position(self, pdf_canvas, y_gui_pos, text_hoehe):
        """Konvertiert GUI-y-Koordinate in PDF-y-Koordinate (invertiert)"""
        seiten_hoehe = pdf_canvas._pagesize[1]
        return seiten_hoehe - y_gui_pos - text_hoehe

    def positionen_zuruecksetzen(self):
        self.x_pos = 10
        self.y_pos = 10

    def rendern(self, index=0, dict_element=None, naechstes_dict_element=None, gui_canvas=None, pdf_canvas=None):
        if gui_canvas is not None:
            self.ist_PDF = False
            return self.auf_canvas_rendern(gui_canvas, index, dict_element,naechstes_dict_element)
        else:
            self.ist_PDF = True
            return self.auf_canvas_rendern(pdf_canvas, index, dict_element,naechstes_dict_element)

    def auf_canvas_rendern(self, canvas, index, element,naechstes_element=None):
        print(f"auf_canvas_rendern aufgerufen: index={index}, token={element.get('token', '')}, ist_PDF={self.ist_PDF}")

        token = element.get('token', '')
        annotation = element.get("annotation", [])

        # harter Zeilenumbruch
        if token == '' or 'zeilenumbruch' in annotation:
            print("Neuer Zeilenumbruch erkannt, Position zurücksetzen")
            self.x_pos = 10
            self.y_pos += 2 * self.zeilen_hoehe
            self.letzte_zeile_y_pos = self.y_pos  # neue Zeile merken
            return

        schrift = self.schrift_holen(element)

        # Berechne Breite des Tokens
        if not self.ist_PDF:
            schriftobjekt, schriftfarbe = schrift
            text_breite = schriftobjekt.measure(token)
            text_hoehe = schriftobjekt.metrics("linespace")
            print(f"Textbreite (GUI): {text_breite}, Texthöhe: {text_hoehe}, Schriftfarbe: {schriftfarbe}")
        else:
            schriftname, schriftgroesse, schriftfarbe = schrift          
            text_breite = canvas.stringWidth(token, schriftname, schriftgroesse)
            text_hoehe = schriftgroesse
            print(f"Textbreite (PDF): {text_breite}, Texthöhe: {text_hoehe}, Schriftfarbe: {schriftfarbe}")

        # Prüfen, ob das nächste Token ein Satzzeichen ohne Space ist
        extra_space = 2  # z.B. 2 Pixel Abstand nach Token
        try:            
            naechste_annotation = naechstes_element.get("annotation", [])
            if "satzzeichenOhneSpace" in naechste_annotation:
                extra_space = 0
        except IndexError:
            pass

        # Erzwungener Zeilenumbruch bei Überschreitung max. Breite
        if self.x_pos + text_breite + extra_space > self.max_breite:
            print(f"Zeilenumbruch erzwungen, da x_pos+text_breite+extra_space ({self.x_pos}+{text_breite}+{extra_space}) > max_breite ({self.max_breite})")
            self.x_pos = 10
            self.y_pos += 2 * self.zeilen_hoehe
            self.letzte_zeile_y_pos = self.y_pos  # neue Zeile merken

        print(f"Token zeichnen bei Position ({self.x_pos}, {self.y_pos})")
        self._zeichne_token(canvas, index, element, self.x_pos, self.y_pos, schrift)

        self.x_pos += text_breite + extra_space  # x-Position für das nächste Token aktualisieren
        print(f"Neue x_pos nach Zeichnen: {self.x_pos}")


    def get_person_color(self, person):
        print(f"get_person_color aufgerufen mit person={person}")
        if not person:
            print("Keine Person angegeben, Standardfarbe verwenden")
            rgb = config.FARBE_STANDARD
        else:
            h = hashlib.md5(person.encode('utf-8')).hexdigest()
            r = max(int(h[0:2], 16), 51)  # mind. ~0.2*255
            g = max(int(h[2:4], 16), 51)
            b = max(int(h[4:6], 16), 51)
            rgb = (r, g, b)
            print(f"Farbe für Person {person}: {rgb}")

        if self.ist_PDF:
            return zu_PDF_farbe(rgb)  
        else:
            return zu_Hex_farbe(rgb)  

    def verwende_hartkodiert_fuer_annotation(self, feldname, annotationswert):
        print(f"Prüfe verwende_hartkodiert_fuer_annotation: feldname={feldname}, annotationswert={annotationswert}")
        if not feldname or not annotationswert:
            print("Kein feldname oder annotationswert angegeben, Rückgabe False")
            return False

        annotationswert = annotationswert.lower()
        for aufgaben_id, annot_liste in config.AUFGABEN_ANNOTATIONEN.items():
            aufgabenname = config.KI_AUFGABEN.get(aufgaben_id)
            if aufgabenname.lower() != feldname.lower():
                continue
            for annot in annot_liste:
                name = annot.get("name").lower()
                verwende = annot.get("VerwendeHartKodiert", False)
                if name is None:
                    if verwende:
                        print(f"VerwendeHartKodiert=True für Feld {feldname} ohne Namen (allgemein) erkannt")
                        return True
                elif name.lower() == annotationswert.lower() and verwende:
                    print(f"VerwendeHartKodiert=True für Feld {feldname} mit Wert {annotationswert} erkannt")
                    return True
        print("Keine Hartkodierung aktiviert gefunden")
        return False

    def schrift_holen(self, element=None):

        betonung = element.get("betonung", None) if element else None    
        person = element.get("person", None) if element else None
        annotation = element.get("annotation", "") if element else ""

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
        

        if verwende_person_farbe and person:
            farbe = self.get_person_color(person)
        else:
            if self.ist_PDF:
                farbe = zu_PDF_farbe(config.FARBE_STANDARD)
            else:
                farbe = zu_Hex_farbe(config.FARBE_STANDARD)
                
        if self.ist_PDF:
            return familie, groesse, farbe  # PDF bekommt auch Farbe zurück
        else:
            schrift = tkFont.Font(family=familie, size=groesse)
            return schrift, farbe  # GUI bekommt Schrift + Farbe für z. B. Label.config(fg=farbe)
        
    def _zeichne_bild(self, canvas, pfad, x, y, w, h):
        if self.ist_PDF:
            try:
                canvas.drawImage(pfad, x, y, width=w, height=h*0.8, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print(f"Fehler beim Einfügen von Bild {pfad}: {e}")
        else:
            try:
                if not os.path.exists(pfad):
                    raise FileNotFoundError(f"Bild nicht gefunden: {pfad}")

                # Bild mit PIL öffnen und skalieren
                img = Image.open(pfad)
                faktor = (h * 0.5) / img.height  # Zielhöhe: 0.5 * h
                neue_breite = int(img.width * faktor)
                neue_hoehe = int(img.height * faktor)
                img = img.resize((neue_breite, neue_hoehe), Image.ANTIALIAS)

                tk_img = ImageTk.PhotoImage(img)
                canvas.image = getattr(canvas, "image", [])  # Verhindert Garbage Collection
                canvas.image.append(tk_img)

                canvas.create_image(x, y, anchor='nw', image=tk_img)
            except Exception as e:
                print(f"Fehler beim Zeichnen von Bild {pfad}: {e}")
                # Platzhalter-Rechteck, wenn Bild fehlt
                farbe = "#999999"
                canvas.create_rectangle(x, y, x + w, y + h * 0.5, outline="red", fill=farbe)

    def _zeichne_fehlendesBild(self, canvas, x, y, width, height, annotationsname):
        farbe = self.get_person_color(annotationsname)

        if not self.ist_PDF:
            # Tkinter: farbe ist Hex-String
            canvas.create_rectangle(
                x, y,
                x + width, y + height,
                fill='lightgrey',
                outline=farbe,
                width=2
            )

            canvas.create_text(
                x + width / 2,
                y + height / 2,
                text='?',
                fill=farbe,
                anchor='center',
                font=('Arial', int(height * 0.6))
            )

        else:
            # PDF: farbe ist Tupel (r,g,b) mit Werten 0..1
            r, g, b = farbe

            canvas.setFillColorRGB(0.8, 0.8, 0.8)
            canvas.rect(x, y, width, height, fill=1, stroke=0)

            canvas.setStrokeColorRGB(r, g, b)
            canvas.setLineWidth(2)
            canvas.rect(x, y, width, height, fill=0, stroke=1)

            canvas.setFillColorRGB(r, g, b)
            schriftgroesse = int(height * 0.6)
            canvas.setFont("Helvetica-Bold", schriftgroesse)
            canvas.drawCentredString(x + width / 2, y + height / 2 - schriftgroesse / 3, "?")

    def _get_aufgaben_id_by_name(self, name):
        for aufgaben_id, n in config.KI_AUFGABEN.items():
            if n == name:
                return aufgaben_id
        return None

    def _zeichne_pause_atempause(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_ATEMPAUSE
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.line(x, y_pos + oy + h, x + w, y_pos + oy + h)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_line(x, y_pos + oy + h, x + w, y_pos + oy + h, fill=farbe_hex, width=linien_breite)

    def _zeichne_pause_stau(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_STAU
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.line(x, y_pos + oy + h, x + w, y_pos + oy + h)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_line(x, y_pos + oy + h, x + w, y_pos + oy + h, fill=farbe_hex, width=linien_breite)

    def _zeichne_gedanken_weiter(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_GEDANKEN_ANFANG
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_gedanken_ende(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_GEDANKEN_ENDE
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_gedanken_pause(self, canvas, x, y_pos, w, h, oy, linien_breite):
        # ggf. eigene Farbe oder Stil
        farbe = config.FARBE_GEDANKEN_PAUSE if hasattr(config, "FARBE_GEDANKEN_PAUSE") else config.FARBE_GEDANKEN_ANFANG
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_spannung_start(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_SPANNUNG_START
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_spannung_halten(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_SPANNUNG_HALTEN
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_spannung_stop(self, canvas, x, y_pos, w, h, oy, linien_breite):
        farbe = config.FARBE_SPANNUNG_STOPP
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_person(self, canvas, x, y_pos, w, h, sprecher, oy, linien_breite):
        if not sprecher:
            return
        farbe = config.FARBE_SPRECHER.get(sprecher.lower())
        if not farbe:
            return
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)

    def _zeichne_ig(self, canvas, x, y_pos, w, h, wert, oy, linien_breite):  
        # Einfacher Rahmen in Standardfarbe
        farbe = config.FARBE_IG if hasattr(config, "FARBE_IG") else (0, 0, 0)
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.rect(x, y_pos + oy, w, h, fill=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h, outline=farbe_hex, width=linien_breite)
  
    def _zeichne_hartkodiert(self, canvas, aufgabenname, wert, x, y_pos, w, h, oy, linien_breite):
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
      
    def _zeichne_token(self, canvas, index, element, x, y_pos, schrift):
        token = element.get('token', '')
        tag = f'token_{index}'

        if not self.ist_PDF:
            # schrift ist ein Tuple: (tkFont.Font, (r, g, b))
            schriftobjekt, schriftfarbe = schrift

            canvas.create_text(
                x, y_pos,
                anchor='nw',
                text=token,
                font=schriftobjekt,
                fill=schriftfarbe,
                tags=(tag,)
            )
            w = schriftobjekt.measure(token)
            h = schriftobjekt.metrics("linespace")
            marker_y = y_pos
        else:
            # schrift ist Tuple: (fontname, fontsize, (r, g, b))
            pdf_schriftname, pdf_schriftgroesse, schriftfarbe = schrift
            y_pdf = self._pdf_y_position(canvas, y_pos, pdf_schriftgroesse)
            canvas.setFont(pdf_schriftname, pdf_schriftgroesse)
            if schriftfarbe:
                r, g, b = schriftfarbe
                canvas.setFillColorRGB(r, g, b)
            canvas.drawString(x, y_pdf, token)
            w = canvas.stringWidth(token, pdf_schriftname, pdf_schriftgroesse)
            h = pdf_schriftgroesse
            marker_y = y_pdf

        linien_breite = config.LINIENBREITE_STANDARD

        if not isinstance(element, dict):
            return

        for aufgabenname in config.KI_AUFGABEN.values():
            marker_wert = element.get(aufgabenname)

            aufgaben_id = self._get_aufgaben_id_by_name(aufgabenname)
            annot_liste = config.AUFGABEN_ANNOTATIONEN.get(aufgaben_id, [])

            for annot in annot_liste:
                name = annot.get("name")
                if name is not None and name != marker_wert:
                    continue

                oy = (h * 0.2) if aufgabenname == "ig" else (-h * 0.8)

                if self.verwende_hartkodiert_fuer_annotation(aufgabenname, marker_wert):
                    self._zeichne_hartkodiert(canvas, aufgabenname, marker_wert, x, marker_y, w, h, oy, linien_breite)
                elif annot.get("bild"):
                    self._zeichne_bild(canvas, annot["bild"], x, marker_y + oy, w, h)
                elif marker_wert:
                    self._zeichne_fehlendesBild(canvas, x, marker_y + oy, w, h, marker_wert)
                else:
                    pass
