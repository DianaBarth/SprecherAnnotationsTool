import os
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, red, blue, green
import tkinter.font as tkFont

import Eingabe.config as config # Importiere das komplette config-Modul

class AnnotationRenderer:
    def __init__(self, ignore_annotations=None):
        """
        ignore_annotations: Liste von Annotation-Namen (case-insensitiv), die ignoriert werden sollen
        """
        self.ignore_annotations = set(a.lower() for a in (ignore_annotations or []))

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

    def _render_gui(self, idx , dict_element, annotations, parent, x_pos, y_pos):

        token = dict_element.get("token","")
        
        font = tkFont.nametofont("TkDefaultFont")
        button_width = max(40, font.measure(token) + 20)
        

        # Debug-Prints
        print(f"[DEBUG] Token: '{token}'")
        print(f"[DEBUG] Position: x={x_pos}, y={y_pos}")
        print(f"[DEBUG] Breite (px): {button_width}")
        print(f"[DEBUG] Annotationen: {annotations}")



        btn_style = self._bestimme_token_button_style(annotations)
        token_btn = tk.Button(parent, text=token,       
            fg=btn_style.get('fg', 'black'),
            font=btn_style.get('font', ('Arial', 10)))
            
        token_btn.config(relief="solid", borderwidth=1)    
            
        token_btn.place(x=x_pos, y=y_pos, width=button_width, height=30)

        print(f"[DEBUG] #{idx}: Token-Button für '{token}' erstellt an ({x_pos}, {y_pos}) mit Breite {button_width}")

        return {'token_button': token_btn, 'marker_buttons': []}


        # # 2) Marker-Buttons für Bilder oder hartkodierte Marker:
        # marker_buttons = []

        # # Durch alle Annotationen aus config durchgehen, für Match marker erzeugen
        # for aufgabe_id, annotationen_liste in config.AUFGABEN_ANNOTATIONEN.items():
        #     for annot in annotationen_liste:
        #         name = annot.get('name')
        #         if not name:
        #             continue
        #         name_lower = name.lower()
        #         if name_lower in annotations:
        #             verwende_hartkodiert = annot.get('VerwendeHartKodiert', True)
        #             bild = annot.get('bild')

        #             if not verwende_hartkodiert and bild:
        #                 # Bild-Button
        #                 btn = self._create_image_button(parent, bild)
        #             else:
        #                 # Hartkodierter Marker-Button als farbiger Text
        #                 btn = self._create_hartkodierter_marker_button(parent, annot.get('HartKodiert', 'Marker'))
        #             marker_buttons.append(btn)

        # # 3) Unterstreiche 'ig' am Wortende und setze Punktierung auf Binnen-'ig'
        # self._style_ig_in_token_button(token, token_btn)

        # return {"token_button": token_btn, "marker_buttons": marker_buttons}

    def _bestimme_token_button_style(self, annotations):
        """
        Gibt ein Style-Dict mit 'fg' (Farbe) und 'font' zurück, basierend auf Annotationen
        Beispiel: Hauptbetonung = fett, Nebenbetonung = kursiv
        """

        # Default
        fg = "black"
        font = ("Arial", 10, "normal")

        # Beispiele für Schriftstile:
        if "hauptbetonung" in annotations:
            font = tkFont.Font(family="Arial", size=10, weight="bold")
        elif "nebenbetonung" in annotations:
            font = tkFont.Font(family="Arial", size=10, weight="italic")

        # Farbe für Person (Beispiel)
        if "person" in annotations:
            fg = config.FARBE_PERSON if hasattr(config, "FARBE_PERSON") else "blue"

        return {"fg": fg, "font": font}

    # def _create_image_button(self, parent, bildname):
    #     """
    #     Erzeugt einen Tkinter Button mit Bild aus ./Eingabe/bilder/{bildname}
    #     Bild wird auf max 24x24 px skaliert.
    #     """
    #     bildpfad = os.path.join("Eingabe", "bilder", bildname)
    #     if not os.path.exists(bildpfad):
    #         # Falls Bild fehlt, Button mit Text
    #         return tk.Button(parent, text="[Bild fehlt]")
    #     try:
    #         img = Image.open(bildpfad)
    #         img.thumbnail((24, 24))
    #         img_tk = ImageTk.PhotoImage(img)
    #         btn = tk.Button(parent, image=img_tk)
    #         btn.image = img_tk  # Referenz erhalten
    #         return btn
    #     except Exception as e:
    #         return tk.Button(parent, text="[Bild Fehler]")

    # def _create_hartkodierter_marker_button(self, parent, text):
    #     """
    #     Erzeugt einfachen Button mit Text als Marker
    #     """
    #     return tk.Button(parent, text=text)

    # def _style_ig_in_token_button(self, token, token_button):
    #     """
    #     Setzt Unterstreichung am Wortende 'ig' und Punktierung (Unterpunkt) auf Binnen-'ig'
    #     Für Tkinter-Button funktioniert nur begrenzt:
    #     --> Lösung: Schriftart mit Underline für Endung, ansonsten kann man Unterpunkt schlecht darstellen,
    #     deshalb keine reine Button-Variante möglich.
    #     -> Alternative: Tooltip o. Label
    #     """

    #     # Hier können wir nur 'ig' am Ende unterstreichen via Font-Konfiguration nicht direkt
    #     # Tkinter Button unterstützt kein partielle Unterstreichung, also schwierig.
    #     # Alternative: Gesamten Text unterstreichen, oder Tooltip mit Hinweis
    #     if token.endswith("ig"):
    #         # Gesamten Text unterstreichen als Workaround
    #         f = token_button.cget("font")
    #         # Font-Objekt bauen
    #         font = tk.font.Font(font=f)
    #         font.configure(underline=True)
    #         token_button.configure(font=font)

        # Binnen-ig Unterpunktung wäre mit Button schwer darstellbar
        # Alternative: z.B. Tooltip oder Zusatzlabel anzeigen (hier nicht implementiert)
        # Für GUI bessere Lösung wäre RichText, aber Tkinter unterstützt das nicht direkt.

    # --- PDF RENDERING ---

    # def _render_pdf(self, c, dict_element, x_pos, y_pos, text_width, annotations):
    #     """
    #     Zeichnet Token + Marker auf ReportLab Canvas
    #     """
    #     token = dict_element.get("token", "?")

    #     # 1) Schriftart & Farbe setzen
    #     self._set_pdf_font_and_color(c, annotations)

    #     # 2) Token zeichnen
    #     c.drawString(x_pos, y_pos, token)

    #     # 3) Marker zeichnen (Bilder oder hartkodiert)
    #     for aufgabe_id, annotationen_liste in config.AUFGABEN_ANNOTATIONEN.items():
    #         for annot in annotationen_liste:
    #             name = annot.get('name')
    #             if not name:
    #                 continue
    #             name_lower = name.lower()
    #             if name_lower in annotations:
    #                 verwende_hartkodiert = annot.get('VerwendeHartKodiert', True)
    #                 bild = annot.get('bild')

    #                 if not verwende_hartkodiert and bild:
    #                     bildpfad = os.path.join("Eingabe", "bilder", bild)
    #                     if os.path.exists(bildpfad):
    #                         try:
    #                             # Bildposition leicht oberhalb Text
    #                             c.drawImage(bildpfad, x_pos, y_pos + 12, width=12, height=12, mask='auto')
    #                         except:
    #                             pass
    #                 else:
    #                     # Hartkodierte Marker je nach Name
    #                     self._zeichne_hartkodierten_marker_pdf(c, name_lower, x_pos, y_pos, text_width)

    #     # 4) "ig" Markierungen (Unterstreichen am Wortende, Unterpunkt bei Binnen-ig)
    #     self._zeichne_ig_marker_pdf(c, token, x_pos, y_pos, text_width)

    # def _set_pdf_font_and_color(self, c, annotations):
    #     """
    #     Setzt Font und Farbe auf Canvas c je nach Annotationen
    #     """

    #     # Default
    #     fontname = "Helvetica"
    #     fontsize = 12
    #     color = black

    #     if "hauptbetonung" in annotations:
    #         fontname = "Helvetica-Bold"
    #     elif "nebenbetonung" in annotations:
    #         fontname = "Helvetica-Oblique"

    #     if "person" in annotations:
    #         color = config.FARBE_PERSON if hasattr(config, "FARBE_PERSON") else blue

    #     c.setFont(fontname, fontsize)
    #     c.setFillColor(color)

    # def _zeichne_hartkodierten_marker_pdf(self, c, name, x_pos, y_pos, text_width):
    #     """
    #     Zeichnet Marker (Linien, Kreise, Rechtecke) auf PDF
    #     Nutzt Farben & Linienbreiten aus config (Beispielwerte anpassen)
    #     """
    #     c.saveState()
    #     linienbreite = getattr(config, "LINIENBREITE_STANDARD", 1)
    #     c.setLineWidth(linienbreite)

    #     # Beispiel-Marker nach Name (aus deinem Beispiel übernommen)
    #     if name == "starten":
    #         c.setStrokeColor(config.FARBE_SPANNUNG if hasattr(config, "FARBE_SPANNUNG") else green)
    #         c.line(x_pos, y_pos + 15, x_pos + text_width, y_pos + 20)
    #     elif name == "halten":
    #         c.setStrokeColor(config.FARBE_SPANNUNG if hasattr(config, "FARBE_SPANNUNG") else green)
    #         c.line(x_pos, y_pos + 15, x_pos + text_width, y_pos + 15)
    #     elif name == "stoppen":
    #         c.setStrokeColor(config.FARBE_SPANNUNG if hasattr(config, "FARBE_SPANNUNG") else green)
    #         c.line(x_pos, y_pos + 20, x_pos + text_width, y_pos + 15)
    #     elif name == "linie":
    #         c.setStrokeColor(black)
    #         c.line(x_pos, y_pos + 10, x_pos + text_width, y_pos + 10)
    #     elif name == "rechteck":
    #         c.setStrokeColor(black)
    #         c.rect(x_pos, y_pos + 8, text_width / 2, 8)
    #     elif name == "kreis":
    #         c.setStrokeColor(black)
    #         c.circle(x_pos + text_width / 4, y_pos + 12, 4)
    #     elif name == "fett":
    #         # Beispiel: nichts, da Schrift schon fett
    #         pass
    #     # Weitere hartkodierte Marker nach Bedarf hier ergänzen
    #     c.restoreState()

    # def _zeichne_ig_marker_pdf(self, c, token, x_pos, y_pos, text_width):
    #     """
    #     Zeichnet Unterstreichung für 'ig' am Wortende
    #     Zeichnet Unterpunkte (kleine Punkte) für Binnen-'ig'
    #     """

    #     c.saveState()
    #     c.setStrokeColor(black)
    #     c.setLineWidth(1)

    #     # Unterstreiche 'ig' am Wortende
    #     if token.endswith("ig"):
    #         text_len = c.stringWidth(token, "Helvetica", 12)
    #         # Position des 'ig' etwa: am Ende minus Breite von "ig"
    #         ig_width = c.stringWidth("ig", "Helvetica", 12)
    #         start_x = x_pos + text_len - ig_width
    #         c.line(start_x, y_pos - 2, start_x + ig_width, y_pos - 2)

    #     # Binnen 'ig' -> Unterpunkt zeichnen
    #     # Suche alle 'ig' im Wort, außer am Ende
    #     indices = []
    #     for i in range(len(token)-2):
    #         if token[i:i+2] == "ig":
    #             indices.append(i)

    #     for idx in indices:
    #         if idx == len(token)-2:
    #             continue  # Endung, bereits gezeichnet

    #         # Unterpunkt zeichnen: kleiner Kreis unter Buchstaben
    #         pos_x = x_pos + c.stringWidth(token[:idx+1], "Helvetica", 12)
    #         pos_y = y_pos - 5
    #         c.circle(pos_x, pos_y, 1, stroke=1, fill=1)

    #     c.restoreState()



if __name__ == "__main__":  
    import tkinter as tk

    root = tk.Tk()
    renderer = AnnotationRenderer(ignore_annotations=["test"])

    token_data = {
        "token": "Wichtig",
        "annotation": "Hauptbetonung, Person, Starten"
    }

    frame = tk.Frame(root)
    frame.pack()

    result = renderer.render(token_data, gui_parent=frame)
    result['token_button'].pack(side="left")
    for mb in result['marker_buttons']:
        mb.pack(side="left")

    root.mainloop()