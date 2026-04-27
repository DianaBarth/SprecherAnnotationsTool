import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import tkinter.font as tkFont
import hashlib
from collections import defaultdict
import importlib
import colorsys

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
    
    def _verschiebe_token_gruppe(self, canvas, token_liste, y_pos, gesamtbreite):
        print(f"Verschiebe {len(token_liste)} Token(s) {self.ausrichtung} bei y={y_pos}")

        zwischenraum = 5
        seitenbreite = getattr(config, "MAX_ZEILENBREITE", 800) if self.ist_PDF else self.max_breite
        rechter_rand = getattr(config, "RECHTER_SEITENRAND", 50)
        linker_rand = getattr(config, "LINKER_SEITENRAND", 50)

        if self.ausrichtung == "zentriert":
            x_start = (seitenbreite - gesamtbreite) / 2
        elif self.ausrichtung == "rechtsbuendig":
            x_start = seitenbreite - rechter_rand - gesamtbreite
        else:
            x_start = linker_rand

        print(f"{self.ausrichtung} mit x_start = {x_start}")
        x_pos = x_start

        for token_dict in token_liste:
            wortNr = token_dict.get("WortNr")
            if wortNr is None:
                print("⚠️ Keine WortNr vorhanden – übersprungen")
                continue

            eintrag = self.canvas_elemente_pro_token.get(wortNr)
            if not eintrag:
                print(f"⚠️ Kein Canvas-Eintrag für WortNr {wortNr}")
                continue

            alte_x = eintrag["x"]
            alte_y = eintrag["y"]
            canvas_id = eintrag["canvas_id"]
            if canvas_id is None:
                print(f"⚠️ Keine CanvasID für WortNr {wortNr}")
                continue

            delta_x = x_pos - alte_x
            delta_y = y_pos - alte_y

            try:
                print(f"CanvasID: {canvas_id} → move by Δx={delta_x}, Δy={delta_y}")
                canvas.move(canvas_id, delta_x, delta_y)
            except Exception as e:
                print(f"Fehler beim Verschieben von CanvasID {canvas_id}: {e}")

            self.canvas_elemente_pro_token[wortNr] = {
                "x": x_pos,
                "y": y_pos,
                "canvas_id": canvas_id
            }

            schrift = self.schrift_holen(token_dict)
            token_breite = self.berechne_breite_des_tokens(token_dict, canvas, schrift)
            x_pos += token_breite + zwischenraum


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

        if self._handle_textausrichtung(canvas, element_kopie, positions_annot, annotation, index):
            return  # Gruppe aktiv → Token wird später gezeichnet


        self._handle_einrueckung(positions_annot, token, index)

        aktuelle_x = self.einrueckung_start_x if self.einrueckung_aktiv else config.LINKER_SEITENRAND

        if self._hat_annotation(element_kopie, "zeilenumbruch"):
            print("Neuer Zeilenumbruch erkannt, Position zurücksetzen")
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
        self.canvas_elemente_pro_token[index] = {"x": self.x_pos, "y": self.y_pos, "canvas_id": text_id}
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



    def _handle_textausrichtung(self, canvas, element, position, annotationen, index):
        position = (position or "").lower()
        token = element.get("token", "")

        # Start einer Ausrichtungsgruppe
        if self._position_ist_ausrichtung_start(position):
            self.ausrichtung = self._ausrichtung_aus_position(position)
            self.grouptyp_aktiv = self.ausrichtung
            self.group_start_index = index
            self.group_tokens = [(index, element)]
            self.group_start_y = self.y_pos
            return True

        # Innerhalb einer aktiven Gruppe
        if self.grouptyp_aktiv is not None:
            self.group_tokens.append((index, element))

            if self._position_ist_ausrichtung_ende(position):
                self._zeichne_ausrichtungsgruppe(canvas, self.group_tokens, self.group_start_y or self.y_pos)
                self._reset_gruppe()
                return True

            return True

        return False

    def _position_ist_ausrichtung_start(self, position):
        return position in ("zentriertstart", "rechtsbuendigstart", "linksbündigstart", "linksbuendigstart")


    def _position_ist_ausrichtung_ende(self, position):
        return position in ("zentriertende", "rechtsbuendigende", "linksbündigende", "linksbuendigende")


    def _ausrichtung_aus_position(self, position):
        position = (position or "").lower()

        if "zentriert" in position:
            return "zentriert"
        if "rechtsbuendig" in position or "rechtsbündig" in position:
            return "rechtsbuendig"
        if "linksbuendig" in position or "linksbündig" in position:
            return "linksbuendig"

        return None

    def _hat_annotation(self, element, name):
        annotation = element.get("annotation", "")
        name = str(name).lower()

        if isinstance(annotation, dict):
            return name in {str(k).lower() for k in annotation.keys()}

        if isinstance(annotation, list):
            return any(str(a).lower() == name for a in annotation)

        return name in str(annotation).lower()

 
    def _zeichne_ausrichtungsgruppe(self, canvas, gruppe, y_start):
        gruppe = list(gruppe)
        zwischenraum = 5 if not self.ist_PDF else 2

        subgruppen = []
        aktuelle_subgruppe = []

        for index, elem in gruppe:
            if self._hat_annotation(elem, "zeilenumbruch"):
                if aktuelle_subgruppe:
                    subgruppen.append(aktuelle_subgruppe)
                    aktuelle_subgruppe = []
                continue

            if elem.get("token", ""):
                aktuelle_subgruppe.append((index, elem))

        if aktuelle_subgruppe:
            subgruppen.append(aktuelle_subgruppe)

        aktuelle_y = y_start

        for subgruppe in subgruppen:
            gesamtbreite = 0

            for pos_in_zeile, (index, elem) in enumerate(subgruppe):
                token = elem.get("token", "")
                if not token:
                    continue

                if pos_in_zeile > 0 and not self._hat_annotation(elem, "satzzeichenOhneSpaceDavor"):
                    gesamtbreite += zwischenraum

                schrift = self.schrift_holen(elem)
                gesamtbreite += self.berechne_breite_des_tokens(elem, canvas, schrift)

            linker_rand = getattr(config, "LINKER_SEITENRAND", 50)
            rechter_rand = getattr(config, "RECHTER_SEITENRAND", 50)

            if self.ist_PDF:
                zeilenbreite = getattr(config, "MAX_ZEILENBREITE", 800)
            else:
                zeilenbreite = self.max_breite

            nutzbare_breite = zeilenbreite - linker_rand - rechter_rand

            if self.ausrichtung == "zentriert":
                x = linker_rand + max(0, (nutzbare_breite - gesamtbreite) / 2)
            elif self.ausrichtung == "rechtsbuendig":
                x = linker_rand + max(0, nutzbare_breite - gesamtbreite)
            else:
                x = linker_rand

            for pos_in_zeile, (index, elem) in enumerate(subgruppe):
                token = elem.get("token", "")
                if not token:
                    continue

                if pos_in_zeile > 0 and not self._hat_annotation(elem, "satzzeichenOhneSpaceDavor"):
                    x += zwischenraum

                schrift = self.schrift_holen(elem)
                text_breite, text_hoehe, schriftfarbe = self._berechne_textgroesse(
                    canvas,
                    schrift,
                    token
                )

                text_id = self._zeichne_token(canvas, index, elem, x, aktuelle_y, schrift)

                self.canvas_elemente_pro_token[index] = {
                    "x": x,
                    "y": aktuelle_y,
                    "canvas_id": text_id
                }

                x += text_breite

            aktuelle_y += self.zeilen_hoehe

        self.y_pos = aktuelle_y
        self.letzte_zeile_y_pos = aktuelle_y
        self.x_pos = getattr(config, "LINKER_SEITENRAND", 50)

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
                self.grouptyp_aktiv = "zentriert" if "zentriert" in starttyp else "rechtsbuendig"
                break
            elif token.get("token"):
                self.group_tokens.insert(0, token)
                self.group_width += self.berechne_breite_des_tokens(token, self.canvas, schrift)
                
    def _handle_einrueckung(self, position, token, index):
        if position == "einrueckungsstart":
            print(f"Einrückung gestartet bei Token '{token}' (Index {index})")
            self.einrueckung_aktiv = True
            self.y_pos += self.zeilen_hoehe
            self.x_pos = self.einrueckung_start_x
        elif position == "einrueckungsende":
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
        if not feldname or not annotationswert:
            return False

        feldname = str(feldname).lower()
        annotationswert = str(annotationswert).lower()

        annot_liste = config.ANNOTATIONEN.get(feldname, [])

        for annot in annot_liste:
            raw_name = annot.get("name")
            verwende = annot.get("VerwendeHartKodiert", False)

            if raw_name is None:
                return bool(verwende)

            if str(raw_name).lower() == annotationswert and verwende:
                return True

        return False


    def schrift_holen(self, element=None):
        importlib.reload(config)

        element = element or {}

        betonung = element.get("betonung", None)
        annotation = element.get("annotation", "") or ""

        # Personenfeld dynamisch aus Aufgabe 3 holen
        person = element.get("person", None)

        # Hartkodierung nur noch für Betonung relevant
        verwende_betonung = bool(betonung)

        # Schriftgröße / Familie bestimmen
        annotation_lower = str(annotation).lower()

        if "überschrift" in annotation_lower:
            groesse = config.UEBERSCHRIFT_GROESSE
            familie = config.SCHRIFTART_UEBERSCHRIFT
        elif "legende" in annotation_lower:
            groesse = config.LEGENDE_GROESSE
            familie = config.SCHRIFTART_LEGENDE
        else:
            groesse = config.TEXT_GROESSE
            familie = config.SCHRIFTART_STANDARD

        # Gewicht / Stil bestimmen
        if verwende_betonung:
            betonung_lower = str(betonung).lower()
            if "hauptbetonung" in betonung_lower:
                weight = "bold"
                slant = "roman"
            elif "nebenbetonung" in betonung_lower:
                weight = "normal"
                slant = "italic"
            else:
                weight = "normal"
                slant = "roman"
        else:
            weight = "normal"
            slant = "roman"

        # Farbe bestimmen:
        # Wenn eine Person gesetzt ist -> deterministische Hash-Farbe
        # sonst Standardfarbe
        if person:
            farbe = self.get_person_color(person)
        else:
            if self.ist_PDF:
                farbe = zu_PDF_farbe(config.FARBE_STANDARD)
            else:
                farbe = zu_Hex_farbe(config.FARBE_STANDARD)

        if self.ist_PDF:
            success = register_custom_font("", familie)

            if not success:
                print(f"[schrift_holen] ⚠️ Schrift '{familie}' konnte nicht registriert werden – PDF-Fallback wahrscheinlich.")

            print(f"[schrift_holen] → Schriftart: {familie}, Größe: {groesse}, Farbe: {farbe}, Person: {person}")
            return familie, groesse, farbe

        else:
            if familie not in tkFont.families():
                print(f"[WARNUNG] Font-Familie '{familie}' nicht verfügbar – Fallback wahrscheinlich!")

            schrift = tkFont.Font(
                family=familie,
                size=groesse,
                weight=weight,
                slant=slant
            )

            print(
                f"[schrift_holen] → Schriftart: {familie}, Größe: {groesse}, "
                f"Gewicht: {weight}, Stil: {slant}, Farbe: {farbe}, Person: {person}"
            )
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

        for aufgabenname in config.RECORDING_RENDER_MARKER:
            marker_wert = element.get(aufgabenname)

            if not marker_wert:
                continue

            annot_liste = config.ANNOTATIONEN.get(aufgabenname, [])
            annot_tag = f'{base_tag}_{aufgabenname}'

            for annot in annot_liste:
                name = annot.get("name")

                if name is not None and name != marker_wert:
                    continue

                if self.ist_PDF:
                    oy = -1.5 * h if aufgabenname == "ig" else h * 0.8
                else:
                    oy = h * 0.2 if aufgabenname == "ig" else -h * 0.8

                if aufgabenname == "ig" and "ig" not in token and not token.isdigit():
                    print(f"WARNUNG: 'ig'-Annotation für Token ohne 'ig': '{token}' (Index {index}) → übersprungen")
                    continue

                if self.verwende_hartkodiert_fuer_annotation(aufgabenname, marker_wert):
                    self._zeichne_hartkodiert(
                        canvas,
                        aufgabenname,
                        token,
                        marker_wert,
                        x,
                        marker_y,
                        w,
                        h,
                        oy,
                        linien_breite,
                        tag=(annot_tag,),
                        schrift=schrift
                    )
                elif annot.get("bild"):
                    self._zeichne_bild(
                        canvas,
                        annot["bild"],
                        x,
                        marker_y + oy,
                        w,
                        h,
                        marker_wert,
                        tag=(annot_tag,)
                    )
                elif marker_wert:
                    self._zeichne_fehlendesBild(
                        canvas,
                        x,
                        marker_y + oy,
                        w,
                        h,
                        marker_wert,
                        tag=(annot_tag,)
                    )
                            
        return text_id

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

    def name_zu_rgb_farbe(self, name: str):
        """
        Deterministische, gut sichtbare Farbe aus einem Namen.
        """
        if not name:
            return (180, 180, 180)

        text = str(name).strip().casefold()
        digest = hashlib.md5(text.encode("utf-8")).hexdigest()

        hue = int(digest[:8], 16) % 360
        sat_raw = int(digest[8:12], 16)
        light_raw = int(digest[12:16], 16)

        saturation = 0.55 + (sat_raw / 0xFFFF) * 0.20   # 0.55 .. 0.75
        lightness  = 0.45 + (light_raw / 0xFFFF) * 0.12 # 0.45 .. 0.57

        r, g, b = colorsys.hls_to_rgb(hue / 360.0, lightness, saturation)
        return (int(r * 255), int(g * 255), int(b * 255))

    def get_person_color(self, person_name):
        rgb = self.name_zu_rgb_farbe(person_name)
        if self.ist_PDF:
            return zu_PDF_farbe(rgb)
        return zu_Hex_farbe(rgb)