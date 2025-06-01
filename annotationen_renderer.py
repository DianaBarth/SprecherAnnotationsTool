import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import tkinter.font as tkFont
import hashlib
from collections import defaultdict
import importlib

import Eingabe.config as config  # Importiere das komplette config-Modul
from config_editor import ToolTip
from config_editor import register_custom_font

def zu_Hex_farbe(rgb):
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

def zu_PDF_farbe(rgb):
    return tuple(x / 255.0 for x in rgb)


class AnnotationRenderer:
    def __init__(self,ignorierte_annotationen=None, ignorier_ig=False, max_breite=500):
        self.ignorierte_annotationen = set(a.lower() for a in (ignorierte_annotationen or []))
        self.ignorier_ig = ignorier_ig
        self.max_breite = max_breite
        self.x_pos = 10
        self.y_pos = 10
        self.letzte_zeile_y_pos = 10
        self.canvas_elemente_pro_token = {}    
        self.zeilen_hoehe = config.ZEILENHOEHE

    def _pdf_y_position(self, canvas, y_gui_pos, text_hoehe):
        """
        Berechnet die korrekte Y-Position für PDF, da PDF-Seiten bei (0,0) unten beginnen.
        Für GUI ist diese Funktion nicht erforderlich – daher Rückgabe der Originalposition.
        """
        if not self.ist_PDF:
            # Absicherung: Im GUI-Kontext keine Umrechnung notwendig
            return y_gui_pos

        seiten_hoehe = canvas._pagesize[1]
        y_rel = y_gui_pos % seiten_hoehe  # Falls mehrere Seiten
        y_pdf = seiten_hoehe - y_rel - text_hoehe
        return y_pdf
        
    def _berechne_zeichenoffsets(self, canvas, token, schrift, ist_pdf):
        if ist_pdf:
            schriftname, schriftgroesse, _ = schrift
            breite_funktion = lambda c: canvas.stringWidth(c, schriftname, schriftgroesse)
        else:
            schriftobjekt, _  = schrift
            breite_funktion = lambda c: schriftobjekt.measure(c)

        zeichenbreiten = [breite_funktion(c) for c in token]
        offsets = [0]
        for b in zeichenbreiten[:-1]:
            offsets.append(offsets[-1] + b)
        return zeichenbreiten, offsets


    def positionen_zuruecksetzen(self):
        self.x_pos = 10
        self.y_pos = 10

    def markiere_token_mit_rahmen(self, canvas, wortNr):
        """
        Löscht alle bisherigen Rahmen und zeichnet einen roten Rahmen um das Token mit der angegebenen wortNr.
        """
        # Alte Rahmen entfernen
        canvas.delete("rahmen")

        # Tag des Tokens, wie beim Zeichnen vergeben
        tag = f"token_{wortNr}"
        bbox = canvas.bbox(tag)
        if bbox is None:
            print(f"Kein Token mit Nummer {wortNr} gefunden (Tag: {tag})")
            return

        x1, y1, x2, y2 = bbox
        padding = 2
        rahmen = canvas.create_rectangle(
            x1 - padding,
            y1 - padding,
            x2 + padding,
            y2 + padding,
            outline="red",
            width=2,
            tag=("rahmen", f"rahmen_{wortNr}")
        )
        print(f"Rahmen um Token {wortNr} bei ({x1}, {y1}, {x2}, {y2}) gezeichnet")
        return rahmen

    def rendern(self, index=0, dict_element=None, naechstes_dict_element=None, gui_canvas=None, pdf_canvas=None):
        if gui_canvas is not None:
            self.ist_PDF = False
            return self.auf_canvas_rendern(gui_canvas, index, dict_element,naechstes_dict_element)
        else:
            self.ist_PDF = True
            self.max_pdf_hoehe = pdf_canvas._pagesize[1] - 50
            return self.auf_canvas_rendern(pdf_canvas, index, dict_element,naechstes_dict_element)


    def auf_canvas_rendern(self, canvas, index, element, naechstes_element=None):
        # Entscheide, ob Zahlwörter genutzt werden sollen (hier als Flag der Klasse)
        if getattr(self, 'use_number_words', False) and 'tokenInklZahlwoerter' in element:
            element_kopie = dict(element)  # Kopie, damit Original nicht verändert wird
            element_kopie["original_token"] = element.get("token", "")
            element_kopie['token'] = element['tokenInklZahlwoerter']
        else:
            element_kopie = dict(element)

        print(f"auf_canvas_rendern aufgerufen: index={index}, token={element_kopie.get('token', '')}, ist_PDF={self.ist_PDF}")

        # Ignorierte Annotationen aus element_kopie entfernen,
        # damit sie nicht für die Schriftwahl berücksichtigt werden
        for key in self.ignorierte_annotationen:
            if key in element_kopie and element_kopie[key]:
                print(f"Token '{element_kopie.get('token', '')}' Annotation '{key}' wird ignoriert - Zeichne normal")
                element_kopie[key] = None

        token = element_kopie.get('token', '')
        annotation = element_kopie.get("annotation", [])

        # harter Zeilenumbruch
        if token == '' or 'zeilenumbruch' in annotation:
            print("Neuer Zeilenumbruch erkannt, Position zurücksetzen")
            self.x_pos = 10
            self.y_pos += self.zeilen_hoehe
            self.letzte_zeile_y_pos = self.y_pos
            return

        schrift = self.schrift_holen(element_kopie)

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
        if not self.ist_PDF:
            extra_space = 1  # GUI: kleiner Abstand, z.B. 1 Pixel
        else:
            extra_space = 1  # PDF: ebenfalls klein, z.B. 1 Punkt

        try:
            naechste_annotation = naechstes_element.get("annotation", [])
            if "satzzeichenOhneSpace" in naechste_annotation:
                extra_space = 0
        except (IndexError, AttributeError):
            pass

        # Erzwungener Zeilenumbruch bei Überschreitung max. Breite
        if self.x_pos + text_breite + extra_space > self.max_breite:
            print(f"Zeilenumbruch erzwungen, da x_pos+text_breite+extra_space ({self.x_pos}+{text_breite}+{extra_space}) > max_breite ({self.max_breite})")
            self.x_pos = 10
            self.y_pos += self.zeilen_hoehe
            self.letzte_zeile_y_pos = self.y_pos

        # Seitenumbruch (nur bei PDF)
        if self.ist_PDF:
            seitenhoehe = 792  # z.B. DIN A4 Hochformat in Punkten, ggf. anpassen
            rand_unten = 40
            if self.y_pos + self.zeilen_hoehe > seitenhoehe - rand_unten:
                print(f"Seitenumbruch erzwungen bei y_pos={self.y_pos}")
                canvas.showPage()
                self.x_pos = 10
                self.y_pos = 40  # Startposition unter Rand
                self.letzte_zeile_y_pos = self.y_pos

        print(f"Token zeichnen bei Position ({self.x_pos}, {self.y_pos})")
        self._zeichne_token(canvas, index, element_kopie, self.x_pos, self.y_pos, schrift)

        # Position speichern für späteres Annotation-Update
        self.canvas_elemente_pro_token[index] = {"x": self.x_pos, "y": self.y_pos}

        # Position für nächstes Token aktualisieren
        self.x_pos += text_breite + extra_space
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
        importlib.reload(config)

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

        # Schriftgröße bestimmen
        if "überschrift" in annotation.lower():
            groesse = config.UEBERSCHRIFT_GROESSE
            familie = config.SCHRIFTART_UEBERSCHRIFT
        elif "legende" in annotation.lower():
            groesse = config.LEGENDE_GROESSE
            familie = config.SCHRIFTART_LEGENDE
        else:
            groesse = config.TEXT_GROESSE
            familie = config.SCHRIFTART_STANDARD

        # Gewicht und Stil setzen
        if verwende_betonung:
            if "hauptbetonung" in (betonung or "").lower():
                weight = "bold"
                slant = "roman"
            elif "nebenbetonung" in (betonung or "").lower():
                weight = "normal"
                slant = "italic"  # kursiv für Nebenbetonung
            else:
                weight = "normal"
                slant = "roman"
        else:
            weight = "normal"
            slant = "roman"

        # Farbe bestimmen
        if verwende_person_farbe and person:
            farbe = self.get_person_color(person)
        else:
            if self.ist_PDF:
                farbe = zu_PDF_farbe(config.FARBE_STANDARD)
            else:
                farbe = zu_Hex_farbe(config.FARBE_STANDARD)

        if self.ist_PDF:
                 # 💡 Font-Dateipfad konstruieren – hier als Beispiel (ggf. dynamisch machen)
            success = register_custom_font("", familie)

            if not success:
                print(f"[schrift_holen] ⚠️ Schrift '{familie}' konnte nicht registriert werden – PDF-Fallback wahrscheinlich.")
           
            print(f"[schrift_holen] → Schriftart: {familie}, Größe: {groesse}, Farbe: {farbe}")
            return familie, groesse, farbe
        else:
            if familie not in tkFont.families():
                print(f"[WARNUNG] Font-Familie '{familie}' nicht verfügbar – Fallback wahrscheinlich!")

            schrift = tkFont.Font(family=familie, size=groesse, weight=weight, slant=slant)
            print(f"[schrift_holen] → Schriftart: {familie}, Größe: {groesse}, Gewicht: {weight}, Stil: {slant}, Farbe: {farbe}")
            return schrift, farbe

    def _zeichne_bild(self, canvas, pfad, x, y, w, h, tag=None):
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

                if tag is not None:
                    canvas.create_image(x, y, anchor='nw', image=tk_img, tag=tag)
                else:
                    canvas.create_image(x, y, anchor='nw', image=tk_img)

            except Exception as e:
                print(f"Fehler beim Zeichnen von Bild {pfad}: {e}")
                # Platzhalter-Rechteck, wenn Bild fehlt
                farbe = "#999999"
                canvas.create_rectangle(x, y, x + w, y + h * 0.5, outline="red", fill=farbe)

    def _zeichne_fehlendesBild(self, canvas, x, y, width, height, annotationsname, tag=None):
        farbe = self.get_person_color(annotationsname)

        if not self.ist_PDF:
            # Tkinter: Farbe ist Hex-String
            canvas.create_rectangle(
                x, y,
                x + width, y + height,
                fill='lightgrey',
                outline=farbe,
                width=2,
                tag=tag
            )

            canvas.create_text(
                x + width / 2,
                y + height / 2,
                text='?',
                fill=farbe,
                anchor='center',
                font=('Arial', int(height * 0.6)),
                tag=tag
            )

        else:
            # PDF: Farbe ist Tupel (r,g,b) mit Werten 0..1
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

    def _zeichne_pause_atem(self, canvas, x, y_pos, w, h, oy, linien_breite, tag=None):
        farbe = config.FARBE_ATEMPAUSE
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(config.LINIENBREITE_STANDARD)          
            canvas.line(x, y_pos + oy + h/2, x + w, y_pos + oy+ h/2)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_line(x, y_pos + oy +h/2, x + w, y_pos + oy + h/2, fill=farbe_hex, width=linien_breite, tags=tag)

    def _zeichne_pause_stau(self, canvas, x, y_pos, w, h, oy, linien_breite, tag=None):
        farbe = config.FARBE_STAUPAUSE
        if self.ist_PDF:
            canvas.setFillColor(zu_PDF_farbe(farbe))
            canvas.rect(x, y_pos + oy, w, h, fill=1, stroke=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_rectangle(x, y_pos + oy, x + w, y_pos + oy + h/2, fill=farbe_hex, outline="", tags=tag)

    def _zeichne_gedanken_weiter(self, canvas, x, y_pos, w, h, oy, linien_breite, tag=None):
        farbe = config.FARBE_GEDANKEN
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.setDash(*config.GEDANKEN_STRICHMUSTER)
            canvas.line(x, y_pos + oy + h / 2, x + w, y_pos + oy + h / 2)
            canvas.setDash()
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_line(
                x, y_pos + oy + h / 2, x + w, y_pos + oy + h / 2,
                fill=farbe_hex, width=linien_breite, dash=config.GEDANKEN_STRICHMUSTER, tags=tag
            )

    def _zeichne_gedanken_ende(self, canvas, x, y_pos, w, h, oy, linien_breite, tag=None):
        farbe = config.FARBE_GEDANKEN
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)         
            canvas.line(x, y_pos + oy + h, x + w, y_pos + oy + h)
        else:
            farbe_hex = zu_Hex_farbe(farbe)          
            canvas.create_line(x, y_pos + oy + h, x + w, y_pos + oy + h, fill=farbe_hex, width=linien_breite, tags=tag)

    def _zeichne_gedanken_pause(self, canvas, x, y_pos, w, h, oy, linien_breite, tag=None):
        farbe = config.FARBE_GEDANKEN
        max_radius_px = 11
        if self.ist_PDF:
            canvas.setFillColor(zu_PDF_farbe(farbe))
            radius = min(max_radius_px, w / 4)
            canvas.circle(x + w / 2, y_pos + oy + h / 2, radius, fill=1, stroke=0)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            radius = min(max_radius_px, w / 4)
            cx = x + w / 2
            cy = y_pos + oy + h / 2
            canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=farbe_hex, outline="", tags=tag)

    def _zeichne_spannung_start(self, canvas, x, y_pos, w, h, oy, linien_breite, tag=None):
        farbe = config.FARBE_SPANNUNG
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            steps = 10
            path = canvas.beginPath()
            for i in range(steps):
                t = i / float(steps)
                x1 = x + t * w
                y1 = y_pos + oy + h / 2 + t * config.SPANNUNG_NEIGUNG
                if i == 0:
                    path.moveTo(x1, y1)
                else:
                    path.lineTo(x1, y1)
            canvas.drawPath(path)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            points = []
            steps = 10
            for i in range(steps + 1):
                t = i / steps
                x1 = x + t * w
                y1 = y_pos + oy + h / 2 - t * config.SPANNUNG_NEIGUNG
                points.append((x1, y1))
            for i in range(len(points) - 1):
                canvas.create_line(points[i][0], points[i][1], points[i+1][0], points[i+1][1], fill=farbe_hex, width=linien_breite, tags=tag)

    def _zeichne_spannung_halten(self, canvas, x, y_pos, w, h, oy, linien_breite, tag=None):
        farbe = config.FARBE_SPANNUNG
        y = y_pos + oy + h / 2
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            path = canvas.beginPath()
            path.moveTo(x, y)
            path.lineTo(x + w, y)
            canvas.drawPath(path)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            canvas.create_line(x, y, x + w, y, fill=farbe_hex, width=linien_breite, tags=tag)

    def _zeichne_spannung_stop(self, canvas, x, y_pos, w, h, oy, linien_breite, tag=None):
        farbe = config.FARBE_SPANNUNG
        y = y_pos + oy + h / 2
        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            steps = 10
            path = canvas.beginPath()
            for i in range(steps):
                t = i / float(steps)
                x1 = x + t * w
                y1 = y - t * config.SPANNUNG_NEIGUNG
                if i == 0:
                    path.moveTo(x1, y1)
                else:
                    path.lineTo(x1, y1)
            canvas.drawPath(path)
        else:
            farbe_hex = zu_Hex_farbe(farbe)
            points = []
            steps = 10
            for i in range(steps + 1):
                t = i / steps
                x1 = x + t * w
                y1 = y + t * config.SPANNUNG_NEIGUNG
                points.append((x1, y1))
            for i in range(len(points) - 1):
                canvas.create_line(points[i][0], points[i][1], points[i+1][0], points[i+1][1], fill=farbe_hex, width=linien_breite, tags=tag)

  
    def _zeichne_ik(self, canvas, x, y_pos, w, h, oy, linien_breite, token, igNr, numerisch=False, tag=None, schrift=None):
        farbe = config.FARBE_UNTERSTREICHUNG
        punkt_radius = 0.8
        zeichenbreiten, offsets = self._berechne_zeichenoffsets(canvas, token, schrift, self.ist_PDF)

        if numerisch:
            for i in range(len(token)):
                punkt_x = x + offsets[i] + zeichenbreiten[i] / 2
                punkt_y = y_pos + oy + h + config.ZEILENABSTAND * 0.1
                if self.ist_PDF:
                    canvas.setFillColor(zu_PDF_farbe(farbe))
                    canvas.circle(punkt_x, punkt_y, punkt_radius, fill=1, stroke=0)
                else:
                    canvas.create_oval(
                        punkt_x - punkt_radius, punkt_y - punkt_radius,
                        punkt_x + punkt_radius, punkt_y + punkt_radius,
                        fill=zu_Hex_farbe(farbe), outline="", tags=tag
                    )
            return

        ig_indices = [i for i in range(len(token) - 1) if token[i:i+2] == "ig"]
        if igNr >= len(ig_indices):
            return

        i = ig_indices[igNr]
        for j in range(2):
            punkt_x = x + offsets[i + j] + zeichenbreiten[i + j] / 2
            punkt_y = y_pos + oy + h + config.ZEILENABSTAND * 0.1
            if self.ist_PDF:
                canvas.setFillColor(zu_PDF_farbe(farbe))
                canvas.circle(punkt_x, punkt_y, punkt_radius, fill=1, stroke=0)
            else:
                canvas.create_oval(
                    punkt_x - punkt_radius, punkt_y - punkt_radius,
                    punkt_x + punkt_radius, punkt_y + punkt_radius,
                    fill=zu_Hex_farbe(farbe), outline="", tags=tag
                )


    def _zeichne_ich(self, canvas, x, y_pos, w, h, oy, linien_breite, token, igNr, numerisch=False, tag=None, schrift=None):
        farbe = config.FARBE_UNTERSTREICHUNG
        unterstrich_y_pos = y_pos + oy + h + config.ZEILENABSTAND * 0.1
        zeichenbreiten, offsets = self._berechne_zeichenoffsets(canvas, token, schrift, self.ist_PDF)

        if numerisch:
            if self.ist_PDF:
                canvas.setStrokeColor(zu_PDF_farbe(farbe))
                canvas.setLineWidth(linien_breite)
                canvas.line(x, unterstrich_y_pos, x + w, unterstrich_y_pos)
            else:
                canvas.create_line(
                    x, unterstrich_y_pos,
                    x + w, unterstrich_y_pos,
                    fill=zu_Hex_farbe(farbe),
                    width=linien_breite,
                    tags=tag
                )
            return

        ig_indices = [i for i in range(len(token) - 1) if token[i:i+2] == "ig"]
        if igNr >= len(ig_indices):
            return

        i = ig_indices[igNr]
        start_x = x + offsets[i]
        end_x = x + offsets[i + 2] if (i + 2 < len(offsets)) else x + w

        if self.ist_PDF:
            canvas.setStrokeColor(zu_PDF_farbe(farbe))
            canvas.setLineWidth(linien_breite)
            canvas.line(start_x, unterstrich_y_pos, end_x, unterstrich_y_pos)
        else:
            canvas.create_line(
                start_x, unterstrich_y_pos,
                end_x, unterstrich_y_pos,
                fill=zu_Hex_farbe(farbe),
                width=linien_breite,
                tags=tag
            )


    def _zeichne_hartkodiert(self, canvas, aufgabenname, token, wert, x, y_pos, w, h, oy, linien_breite, tag="", schrift = None):
        if aufgabenname == "pause":
            if wert == "Atempause":
                self._zeichne_pause_atem(canvas, x, y_pos, w, h, oy, linien_breite, tag=tag)
            elif wert == "Staupause":
                self._zeichne_pause_stau(canvas, x, y_pos, w, h, oy, linien_breite, tag=tag)
        elif aufgabenname == "gedanken":
            if wert == "gedanken_weiter":
                self._zeichne_gedanken_weiter(canvas, x, y_pos, w, h, oy, linien_breite, tag=tag)
            elif wert == "gedanken_ende":
                self._zeichne_gedanken_ende(canvas, x, y_pos, w, h, oy, linien_breite, tag=tag)
            elif wert == "pause_gedanken":
                self._zeichne_gedanken_pause(canvas, x, y_pos, w, h, oy, linien_breite, tag=tag)
        elif aufgabenname == "spannung":
            if wert == "Starten":
                self._zeichne_spannung_start(canvas, x, y_pos, w, h, oy, linien_breite, tag=tag)
            elif wert == "Halten":
                self._zeichne_spannung_halten(canvas, x, y_pos, w, h, oy, linien_breite, tag=tag)
            elif wert == "Stoppen":
                self._zeichne_spannung_stop(canvas, x, y_pos, w, h, oy, linien_breite, tag=tag)
        elif aufgabenname == "ig":
            if token.isdigit():  # Vollständig numerisches Token (z.B. "30")
                letzter_wert = wert.split("-")[-1]
                if letzter_wert == "ik":
                    self._zeichne_ik(canvas, x, y_pos, w, h, oy, linien_breite, token, igNr=0, numerisch=True, tag=tag, schrift = schrift)
                elif letzter_wert == "ich":
                    self._zeichne_ich(canvas, x, y_pos, w, h, oy, linien_breite, token, igNr=0, numerisch=True, tag=tag, schrift = schrift)
                return  # Keine weitere Bearbeitung nötig

            # Alle "ig"-Vorkommen im Token finden
            ig_indices = [i for i in range(len(token) - 1) if token[i:i+2] == "ig"]
            if not ig_indices:
                return  # Kein "ig" im Token → nichts tun
            # Zerlege den Wert in eine Liste z.B. ["ik", "ik", "ich"]
            ig_werte = wert.split("-")
            # Für jedes vorkommende "ig" im Token:
            for igNr, art in enumerate(ig_werte):
                if igNr >= len(ig_indices):
                    break  # Mehr Anweisungen als "ig"-Vorkommen? Ignorieren.
                if art == "ik":
                    self._zeichne_ik(canvas, x, y_pos, w, h, oy, linien_breite, token, igNr, numerisch=False, tag=tag, schrift = schrift)
                elif art == "ich":
                    self._zeichne_ich(canvas, x, y_pos, w, h, oy, linien_breite, token, igNr, numerisch=False, tag=tag, schrift = schrift)

    def _zeichne_token(self, canvas, index, element, x, y_pos, schrift):
        token = element.get('token', '')
        base_tag = f'token_{index}'

        betonung = element.get('betonung', None)
        tags = [base_tag]
        if betonung:
            annot_tag = f'{base_tag}_betonung_{betonung.lower()}'
            tags.append(annot_tag)

        # Zeichne den Token
        if not self.ist_PDF:
            schriftobjekt, schriftfarbe = schrift
            canvas.create_text(
                x, y_pos,
                anchor='nw',
                text=token,
                font=schriftobjekt,
                fill=schriftfarbe,
                tags=tuple(tags)
            )
            self.Durchschnittsbreite = schriftobjekt.measure("M")
            w = schriftobjekt.measure(token)
            h = schriftobjekt.metrics("linespace")
            marker_y = y_pos
        else:
            pdf_schriftname, pdf_schriftgroesse, schriftfarbe = schrift
            y_pdf = self._pdf_y_position(canvas, y_pos, pdf_schriftgroesse)
            canvas.setFont(pdf_schriftname, pdf_schriftgroesse)
            if schriftfarbe:
                r, g, b = schriftfarbe
                canvas.setFillColorRGB(r, g, b)
            canvas.drawString(x, y_pdf, token)
            self.Durchschnittsbreite = canvas.stringWidth("M", pdf_schriftname, pdf_schriftgroesse)
            w = canvas.stringWidth(token, pdf_schriftname, pdf_schriftgroesse)
            h = pdf_schriftgroesse
            marker_y = y_pdf
            print(f"[PDF] Token #{index} '{token}' bei Position ({x:.1f}, {y_pdf:.1f}), Größe: ({w:.1f}x{h})")

        linien_breite = config.LINIENBREITE_STANDARD

        # Sicherheit: Ignoriere Annotationen, wenn kein Dictionary
        if not isinstance(element, dict):
            return

        for aufgabenname in config.KI_AUFGABEN.values():
            marker_wert = element.get(aufgabenname)
            if marker_wert is None:
                continue

            aufgaben_id = self._get_aufgaben_id_by_name(aufgabenname)
            annot_liste = config.AUFGABEN_ANNOTATIONEN.get(aufgaben_id, [])

            annot_tag = f'{base_tag}_{aufgabenname}'

            for annot in annot_liste:
                name = annot.get("name")
                if name is not None and name != marker_wert:
                    continue

                # Positions-Offsets
                if self.ist_PDF:
                    oy = - 1.5 * h if aufgabenname == "ig" else h * 0.8
                else:
                    oy = h * 0.2 if aufgabenname == "ig" else -h * 0.8

                # 🧠 Schutz: Zeichne 'ig' Marker nur, wenn Token 'ig' enthält
                if aufgabenname == "ig" and "ig" not in token:
                    print(f"WARNUNG: 'ig'-Annotation für Token ohne 'ig': '{token}' (Index {index}) → übersprungen")
                    continue

                if self.verwende_hartkodiert_fuer_annotation(aufgabenname, marker_wert):
                    self._zeichne_hartkodiert(canvas, aufgabenname, token, marker_wert, x, marker_y, w, h, oy, linien_breite, tag=(annot_tag,), schrift = schrift)
                elif annot.get("bild"):
                    self._zeichne_bild(canvas, annot["bild"], x, marker_y + oy, w, h, tag=(annot_tag,))
                elif marker_wert:
                    self._zeichne_fehlendesBild(canvas, x, marker_y + oy, w, h, marker_wert, tag=(annot_tag,))


    def annotation_aendern(self, canvas, wortnr, aufgabenname, element):
        self.ist_PDF = False

        tag = f'token_{wortnr}'
        canvas.delete(tag)
        tag_aufgabe = f'token_{wortnr}_{aufgabenname}'
        canvas.delete(tag_aufgabe)

        x = self.canvas_elemente_pro_token[wortnr]["x"]
        y = self.canvas_elemente_pro_token[wortnr]["y"]

        # Element kopieren, damit Original unverändert bleibt
        element_kopie = dict(element)

        # Wenn use_number_words aktiv und tokenInklZahlwoerter vorhanden, dann token überschreiben
        if getattr(self, "use_number_words", False) and 'tokenInklZahlwoerter' in element_kopie:
            element_kopie['original_token'] = element_kopie.get('token', '')
            element_kopie['token'] = element_kopie['tokenInklZahlwoerter']

        schrift = self.schrift_holen(element_kopie)
        self._zeichne_token(canvas, wortnr, element_kopie, x, y, schrift)