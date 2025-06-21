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
    def __init__(self,ignorierte_annotationen=None, ignorier_ig=False, max_breite=300):
        self.ignorierte_annotationen = set(a.lower() for a in (ignorierte_annotationen or []))
        self.ignorier_ig = ignorier_ig
        self.max_breite = max_breite
        self.x_pos = config.LINKER_SEITENRAND
        self.y_pos = config.LINKER_SEITENRAND
        self.letzte_zeile_y_pos =config.LINKER_SEITENRAND
        self.canvas_elemente_pro_token = {}    
        self.zeilen_hoehe = config.ZEILENHOEHE
        self.einrueckung_aktiv = False
        self.einrueckung_start_x = config.LINKER_SEITENRAND + 50  # z.B. 50 Punkte eingerückt

        self.grouptyp_aktiv = None  # "zentriert", "rechts" oder None
        self.group_start_index = None
        self.group_tokens = []
        self.group_start_y = None
        self.group_width = 0

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
        self.x_pos =config.LINKER_SEITENRAND 
        self.y_pos = config.LINKER_SEITENRAND

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


    
    def berechne_breite_des_tokens(self, element_kopie, canvas, schrift):
        token = element_kopie.get('token', '')
        if not self.ist_PDF:
            schriftobjekt, _ = schrift
            return schriftobjekt.measure(token)
        else:
            schriftname, schriftgroesse, _ = schrift
            return canvas.stringWidth(token, schriftname, schriftgroesse)


    def zeichne_token_gruppe_neu(self, canvas, token_gruppe):
        schrift = self.schrift_holen(token_gruppe[0]) if token_gruppe else None
        abstand = 5

        # Gesamte Breite der Tokens + Abstände in der Zeile berechnen
        gesamtbreite = sum(self.berechne_breite_des_tokens(t, canvas, schrift) for t in token_gruppe) + abstand * (len(token_gruppe) - 1)

        canvas_breite = int(canvas.cget("width"))
        rechter_rand_abstand = config.RECHTER_SEITENRAND

        # x-Start so setzen, dass gesamte Zeile rechtsbündig ist
        x_start = canvas_breite - gesamtbreite - rechter_rand_abstand

        y = self.group_start_y
        x = x_start

        for idx, token in enumerate(token_gruppe):
            schrift = self.schrift_holen(token)
            self._zeichne_token(canvas, idx, token, x, y, schrift)
            breite = self.berechne_breite_des_tokens(token, canvas, schrift)
            token['x'] = x
            token['y'] = y
            x += breite + abstand

    def auf_canvas_rendern(self, canvas, index, element, naechstes_element=None):
        element_kopie = dict(element)

        # Zahlwörter ersetzen, falls aktiviert
        if getattr(self, 'use_number_words', False) and 'tokenInklZahlwoerter' in element:
            element_kopie["original_token"] = element.get("token", "")
            element_kopie['token'] = element['tokenInklZahlwoerter']

        token = element_kopie.get('token', '')
        annotation = element_kopie.get("annotation", {})
        positions_annot = element_kopie.get("position", "").lower()

        print(f"auf_canvas_rendern aufgerufen: index={index}, token='{token}', ist_PDF={self.ist_PDF}")

        self._ignoriere_annotationen(element_kopie)

        # Wenn Gruppe aktiv, und Token gehört dazu, wird es in _handle_textausrichtung gesammelt
        if self._handle_textausrichtung(canvas, element_kopie, positions_annot, annotation, index):
            return  # Gruppe aktiv → Token wird später gezeichnet

        self._handle_einrueckung(positions_annot, token, index)

        aktuelle_x = self.einrueckung_start_x if self.einrueckung_aktiv else config.LINKER_SEITENRAND

        if 'zeilenumbruch' in annotation:
            print("Neuer Zeilenumbruch erkannt, Position zurücksetzen")
            # Gruppe offen lassen — nicht schließen!
            self.y_pos += self.zeilen_hoehe
            self.letzte_zeile_y_pos = self.y_pos
            self.x_pos = aktuelle_x
            return

        schrift = self.schrift_holen(element_kopie)
        text_breite, text_hoehe, schriftfarbe = self._berechne_textgroesse(canvas, schrift, token)

        extra_space = 10 if not self.ist_PDF else 2
        if isinstance(naechstes_element, dict):
            naechste_annotation = naechstes_element.get("annotation", {})
            if "satzzeichenOhneSpace" in naechste_annotation:
                extra_space = 0

        self._handle_umbruch(canvas, text_breite, extra_space)

        if self.x_pos < aktuelle_x:
            self.x_pos = aktuelle_x

        print(f"Token zeichnen bei Position ({self.x_pos}, {self.y_pos})")
        text_id = self._zeichne_token(canvas, index, element_kopie, self.x_pos, self.y_pos, schrift)
        self.canvas_elemente_pro_token[index] = {
            "x": self.x_pos,
            "y": self.y_pos,
            "canvas_id": text_id,
            "token": element_kopie.get("token")
        }
        self.x_pos += text_breite + extra_space
        print(f"Neue x_pos nach Zeichnen: {self.x_pos}")

    

    def _ignoriere_annotationen(self, element):
        for key in self.ignorierte_annotationen:
            if key in element and element[key]:
                print(f"Token '{element.get('token')}' Annotation '{key}' wird ignoriert - Zeichne normal")
                element[key] = None

    def _reset_gruppe(self):
        self.grouptyp_aktiv = None
        self.group_start_index = None
        self.group_tokens = []
        self.group_start_y = None
        self.group_width = 0
        self.ausrichtung = None

    def _handle_textausrichtung(self, canvas, element, positions_annot, annotation, index):
        # Initialisierung, falls nicht vorhanden
        if not hasattr(self, 'grouptyp_aktiv'):
            self.grouptyp_aktiv = None
        if not hasattr(self, 'aktuelle_token_gruppe'):
            self.aktuelle_token_gruppe = []

        print(f"_handle_textausrichtung: position='{positions_annot}', index={index}, grouptyp_aktiv={self.grouptyp_aktiv}")

        if positions_annot == 'rechtsbuendigstart':
            print("rechtsbuendigstart erkannt - starte neue Gruppe")
            self.grouptyp_aktiv = 'rechts'
            self.aktuelle_token_gruppe = [element]
            return True

        if self.grouptyp_aktiv == 'rechts':
            if 'zeilenumbruch' in annotation:
                print("Zeilenumbruch innerhalb offener Gruppe - speichern und Gruppe bleibt offen")
                element['_hat_zeilenumbruch'] = True
                self.aktuelle_token_gruppe.append(element)
                return True

            if positions_annot == 'rechtsbuendigende':
                print("rechtsbuendigende erkannt - schließe Gruppe und zeichne")
                self.aktuelle_token_gruppe.append(element)
                self.zeichne_token_gruppe_init(canvas, self.aktuelle_token_gruppe)
                self.grouptyp_aktiv = None
                self.aktuelle_token_gruppe = []
                return True

            print(f"Token innerhalb offener Gruppe hinzufügen: index={index}")
            self.aktuelle_token_gruppe.append(element)
            return True

        # Keine Gruppe aktiv, normaler Token
        return False

 
    def _rekonstruiere_gruppe_bis_start(self, end_index, aktuelles_element, endetyp):
        # Ermittelt die Gruppe rückwärts vom Ende bis zum Start-Token
        starttyp = "zentriertstart" if "zentriert" in endetyp else "rechtsbuendigstart"
        self.group_tokens = []
        self.group_width = 0
        self.group_start_y = None
        self.group_start_index = None

        # Für y-Position evtl. von gespeicherter Position
        if end_index in self.canvas_elemente_pro_token:
            self.group_start_y = self.canvas_elemente_pro_token[end_index]["y"]
        else:
            self.group_start_y = self.y_pos

        # Alle Tokens rückwärts durchsuchen, self.alle_tokens muss alle Elemente enthalten
        for i in range(end_index - 1, -1, -1):
            token = self.alle_tokens[i]
            pos = token.get("position", "").lower()
            schrift = self.schrift_holen(token)

            if pos == starttyp:
                self.group_start_index = i
                self.group_tokens.insert(0, token)
                self.group_width += self.berechne_breite_des_tokens(token, self.canvas, schrift)
                self.grouptyp_aktiv = "zentriert" if "zentriert" in starttyp else "rechts"
                break
            elif token.get("token"):
                self.group_tokens.insert(0, token)
                self.group_width += self.berechne_breite_des_tokens(token, self.canvas, schrift)
                
    def _handle_einrueckung(self, position, token, index):
        if position == "einrückungsstart":
            print(f"Einrückung gestartet bei Token '{token}' (Index {index})")
            self.einrueckung_aktiv = True
            self.y_pos += self.zeilen_hoehe
            self.x_pos = self.einrueckung_start_x
        elif position == "einrückungsende":
            print(f"Einrückung beendet bei Token '{token}' (Index {index})")
            self.einrueckung_aktiv = False
            self.y_pos += self.zeilen_hoehe
            self.x_pos = config.LINKER_SEITENRAND

    def _berechne_textgroesse(self, canvas, schrift, token):
        if not self.ist_PDF:
            schriftobjekt, schriftfarbe = schrift
            breite = schriftobjekt.measure(token)
            hoehe = schriftobjekt.metrics("linespace")
        else:
            schriftname, schriftgroesse, schriftfarbe = schrift
            breite = canvas.stringWidth(token, schriftname, schriftgroesse)
            hoehe = schriftgroesse
        return breite, hoehe, schriftfarbe

    def _handle_umbruch(self, canvas, breite, extra_space):
        if self.ist_PDF:
            if self.x_pos + breite + extra_space > config.MAX_ZEILENBREITE:
                print(f"Zeilenumbruch PDF: {self.x_pos} + {breite} + {extra_space} > {config.MAX_ZEILENBREITE}")
                self.y_pos += self.zeilen_hoehe
                self.letzte_zeile_y_pos = self.y_pos
                self.x_pos = self.einrueckung_start_x if self.einrueckung_aktiv else config.LINKER_SEITENRAND

            if self.y_pos + self.zeilen_hoehe > 792 - 40:
                print(f"Seitenumbruch bei y_pos={self.y_pos}")
                canvas.showPage()
                self.x_pos = config.LINKER_SEITENRAND
                self.y_pos = 40
                self.letzte_zeile_y_pos = self.y_pos
        else:
            if self.x_pos + breite + extra_space > self.max_breite:
                print(f"Zeilenumbruch GUI: {self.x_pos} + {breite} + {extra_space} > {self.max_breite}")
                self.y_pos += self.zeilen_hoehe
                self.letzte_zeile_y_pos = self.y_pos
                self.x_pos = self.einrueckung_start_x if self.einrueckung_aktiv else config.LINKER_SEITENRAND



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

    def _zeichne_bild(self, canvas, bildname, x, y, w, h,annotationsname, tag=None):
        pfad = os.path.join(config.GLOBALORDNER["Eingabe"], "bilder",bildname)   
        if self.ist_PDF:
            try:
                canvas.drawImage(pfad, x + w/2, y, height=config.BILDHOEHE_PX, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print(f"Fehler beim Einfügen von Bild {pfad}: {e}")
        else:
            try:
                if not os.path.exists(pfad):
                    raise FileNotFoundError(f"Bild nicht gefunden: {pfad}")

                # Bild mit PIL öffnen und skalieren
                img = Image.open(pfad)
           
                tk_img = ImageTk.PhotoImage(img)
                canvas.image = getattr(canvas, "image", [])  # Verhindert Garbage Collection
                canvas.image.append(tk_img)

                if tag is not None:
                    canvas.create_image(x + w/2, y, anchor='nw', image=tk_img, tag=tag)
                else:
                    canvas.create_image(x + w/2, y, anchor='nw', image=tk_img)

            except Exception as e:
                print(f"Fehler beim Zeichnen von Bild {pfad}: {e}")
                # Platzhalter-Rechteck, wenn Bild fehlt
                self._zeichne_fehlendesBild(canvas,x,y,w,h,annotationsname, tag)

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
            text_id =canvas.create_text(
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
                    self._zeichne_bild(canvas,annot["bild"], x, marker_y + oy, w, h, marker_wert, tag=(annot_tag,))
                elif marker_wert:
                    self._zeichne_fehlendesBild(canvas, x, marker_y + oy, w, h, marker_wert, tag=(annot_tag,))
                    
        return text_id

    def annotation_aendern(self, canvas, idx, aufgabenname, element):
        self.ist_PDF = False

        tag = f'token_{idx}'
        canvas.delete(tag)
        tag_aufgabe = f'token_{idx}_{aufgabenname}'
        canvas.delete(tag_aufgabe)

        x = self.canvas_elemente_pro_token[idx]["x"]
        y = self.canvas_elemente_pro_token[idx]["y"]

        # Element kopieren, damit Original unverändert bleibt
        element_kopie = dict(element)

        # Wenn use_number_words aktiv und tokenInklZahlwoerter vorhanden, dann token überschreiben
        if getattr(self, "use_number_words", False) and 'tokenInklZahlwoerter' in element_kopie:
            element_kopie['original_token'] = element_kopie.get('token', '')
            element_kopie['token'] = element_kopie['tokenInklZahlwoerter']

        schrift = self.schrift_holen(element_kopie)
        self._zeichne_token(canvas, idx, element_kopie, x, y, schrift)

    def zeichne_token_gruppe_init(self, canvas, token_liste):
        # Sicherstellen, dass der Canvas die aktuelle Breite kennt
        canvas.update_idletasks()
        rechte_grenze = canvas.winfo_width() - config.RECHTER_SEITENRAND  # z. B. 10–20 px Puffer

        zeilen = []
        aktuelle_zeile = []

        # Tokens in Zeilen splitten anhand von _hat_zeilenumbruch
        for token in token_liste:
            aktuelle_zeile.append(token)
            if token.get('_hat_zeilenumbruch'):
                zeilen.append(aktuelle_zeile)
                aktuelle_zeile = []
        if aktuelle_zeile:
            zeilen.append(aktuelle_zeile)

        y_pos = self.y_pos
        extra_space = 10 if not self.ist_PDF else 2
        schrift_cache = {}

        for zeile in zeilen:
            # Gesamtbreite der Zeile berechnen
            gesamtbreite = 0
            for token in zeile:
                tid = id(token)
                schrift = schrift_cache[tid] = self.schrift_holen(token)
                text = token.get("token", "")
                text_breite, _, _ = self._berechne_textgroesse(canvas, schrift, text)
                gesamtbreite += text_breite + extra_space
            gesamtbreite -= extra_space  # letztes extra_space abziehen

            # Start-x so berechnen, dass Zeile rechtsbündig an rechte_grenze anschließt
            x_pos = rechte_grenze - gesamtbreite
            if x_pos < 0:
                print(f"⚠️  Zeile ist zu lang zum rechtsbündigen Zeichnen – sie wird abgeschnitten (breite={gesamtbreite}, canvas={rechte_grenze})")
                x_pos = 0  # Notfall: nicht negativ werden

            # Tokens der Zeile zeichnen
            for token in zeile:
                schrift = schrift_cache[id(token)]
                text = token.get("token", "")
                text_breite, _, _ = self._berechne_textgroesse(canvas, schrift, text)

                self._zeichne_token(canvas, None, token, x_pos, y_pos, schrift)
                x_pos += text_breite + extra_space

            y_pos += self.zeilen_hoehe

        self.y_pos = y_pos
