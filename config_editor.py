import os
import platform
import ast
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox, colorchooser, BooleanVar
import tkinter.font as tkfont
from PIL import Image, ImageTk
import colorsys
from datetime import datetime
import importlib
import shutil
import random
import re
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import Eingabe.config as config # Importiere das komplette config-Modul

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("Segoe UI", 9))
        label.pack(ipadx=1)

    def hide(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

# Scrollbarer Frame Wrapper
class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self, borderwidth=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Mausrad scrollen
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

class KIAufgabenEditor(tk.Frame):
    def __init__(self, parent, nutzeKI_var, eingabe_ordner="Eingabe", ki_aufgaben=None, aufgaben_annotationen=None):
        super().__init__(parent)

        self.nutzeKI_var = nutzeKI_var
        self.eingabe_ordner = eingabe_ordner
        self.aufgaben = ki_aufgaben.copy() if ki_aufgaben else config.KI_AUFGABEN.copy()
        self.entries = {}
        self.aufgabenbezeichnung = {}
        self.annotation_buttons = {}
        self.annotation_frames = {}
        self.aufgaben_annotationen = aufgaben_annotationen or {}
        self.bilder_cache = {}
        self.btn_delete = {}
        self.btn_prompt = {}
        self.create_widgets()

    def aufgabe_loeschen(self, nummer):
        if nummer in self.entries:
            self.entries[nummer].destroy()
            self.annotation_frames[nummer].destroy()
            if nummer in self.btn_delete:
                self.btn_delete[nummer].destroy()
            if nummer in self.btn_prompt:
                self.btn_prompt[nummer].destroy()

            #Promot-Datei löschen
            aufgabenname = self.aufgaben[nummer]
            if aufgabenname:
                print(f"Löschen eingeleitet für Prompt-Datei für {aufgabenname}")
                prompt_datei = os.path.join("Eingabe", "prompts", f"{aufgabenname}.txt")
                if os.path.exists(prompt_datei):
                    try:
                        os.remove(prompt_datei)
                        print(f"Prompt-Datei {prompt_datei} gelöscht")
                    except Exception as e:
                        print(f"Fehler beim Löschen der Prompt-Datei {prompt_datei}: {e}")

            self.entries.pop(nummer, None)
            self.aufgaben.pop(nummer, None)
            self.aufgabenbezeichnung.pop(nummer, None)
            self.aufgaben_annotationen.pop(nummer, None)
            self.annotation_buttons.pop(nummer, None)
            self.annotation_frames.pop(nummer, None)
            self.btn_delete.pop(nummer, None)
            self.btn_prompt.pop(nummer, None)

            # Neu aufbauen (damit Reihenfolge & Nummerierung passt)
            for widget in self.winfo_children():
                widget.destroy()
            self.create_widgets()

            if not self.nutzeKI_var.get():
                self.hide_prompt_buttons()


    def neue_aufgabe_hinzufuegen(self):
        name = simpledialog.askstring("Neue Aufgabe", "Wie soll die neue Aufgabe heißen?", parent=self)
        if name and name.strip():
            neue_nummer = self._naechste_freie_nummer()
            self.aufgaben[neue_nummer] = name
            self.aufgaben_annotationen[neue_nummer] = []

            for widget in self.winfo_children():
                widget.destroy()
            self.create_widgets()

            if not self.nutzeKI_var.get():
                self.hide_prompt_buttons()

    def create_widgets(self):
        nummern_sortiert = sorted(self.aufgaben.keys(), key=int)
        for idx, nummer in enumerate(nummern_sortiert, start=1):
            aufgabe = self.aufgaben[nummer]
            
            aufgabenbezeichnung = ttk.Label(self, text=f"Annotations-Aufgabe {idx}:")
            aufgabenbezeichnung.grid(row=(idx-1)*3, column=0, padx=5, pady=2, sticky="e")
            self.aufgabenbezeichnung[nummer] = aufgabenbezeichnung
            
            entry = ttk.Entry(self)
            entry.insert(0, aufgabe)
            entry.grid(row=(idx-1)*3, column=1, padx=5, pady=2, sticky="we")
            self.entries[nummer] = entry
            
            btn_prompt = ttk.Button(self, text="Prompt", command=lambda n=nummer: self.open_prompt_editor(n))
            btn_prompt.grid(row=(idx-1)*3, column=2, padx=5, pady=2, sticky="w")
            self.btn_prompt[nummer] = btn_prompt
           
            annot_frame = ttk.Frame(self)
            annot_frame.grid(row=(idx-1)*3+1, column=0, columnspan=3, sticky="we", padx=5, pady=5)
            self.annotation_frames[nummer] = annot_frame

            self.annotation_buttons[nummer] = []
            self._build_annotation_buttons(nummer, annot_frame)

            btn_add = ttk.Button(annot_frame, text="+ Neue Annotation",
                                command=lambda n=nummer, f=annot_frame: self.add_annotation(n, f))
            btn_add.grid(row=0, column=0, sticky="w", padx=2)

            if not any(a.get("HartKodiert") for a in self.aufgaben_annotationen.get(nummer, [])):
                img_trash = self._lade_icon("papierkorb.jpg")
                btn_delete = ttk.Button(self, image=img_trash, command=lambda n=nummer: self.aufgabe_loeschen(n))
                btn_delete.image = img_trash
                btn_delete.grid(row=(idx-1)*3, column=3, padx=5, pady=2, sticky="w")
                self.btn_delete[nummer] = btn_delete

        self.columnconfigure(1, weight=1)

        if not self.nutzeKI_var.get():
            self.hide_prompt_buttons()

        row_offset = len(nummern_sortiert) * 3
        self.btn_neue_aufgabe = ttk.Button(self, text="+ Neue Annotations-Aufgabe", command=self.neue_aufgabe_hinzufuegen)
        self.btn_neue_aufgabe.grid(row=row_offset, column=2, padx=5, pady=10, sticky="w")

    
    def _naechste_freie_nummer(self):
        nummern = set(self.aufgaben.keys())
        i = 3
        while i in nummern:
            i += 1
        return i


    def _build_annotation_buttons(self, aufgaben_nummer, frame):
        """
        Baut die Buttons für vorhandene Annotationen in einem gegebenen Frame neu auf.

        :param aufgaben_nummer: Nummer der KI-Aufgabe
        :param frame: Frame-Widget, in dem die Buttons erstellt werden
        """
        # Alte Annotationen außer dem "+ Neue Annotation"-Button entfernen
        for widget in frame.winfo_children():
            if isinstance(widget, (tk.Button, ttk.Button)) and widget.cget("text") != "+ Neue Annotation":
                widget.destroy()

        annots = self.aufgaben_annotationen.get(aufgaben_nummer, [])
        self.annotation_buttons[aufgaben_nummer] = []

        # Für jede Annotation einen Button mit Bild (falls vorhanden) erstellen
        for idx, annot in enumerate(annots, start=1):  # +1, damit "+ Neue Annotation" immer links bleibt

            name = annot.get("name", "Unbenannte Annotation")

            if name:
                bild_datei = annot.get("bild")

                img_obj = None
                if bild_datei:
                    bild_pfad = os.path.join("Eingabe", "bilder", bild_datei)
                    if os.path.exists(bild_pfad):
                        img_obj = self._lade_icon(bild_datei)

                if img_obj:
                    btn = tk.Button(frame, text=name, image=img_obj, compound="left")
                    btn.image = img_obj  # Referenz speichern, sonst wird Bild gelöscht
                else:
                    btn = tk.Button(frame, text=name)

                # Binde Klick auf Button an Editier-Funktion, Button selbst wird mitgegeben
                btn.config(command=lambda a=annot, n=aufgaben_nummer, b=btn: self.edit_annotation(n, a, b))

                btn.grid(row=0, column=idx, padx=5, pady=5, sticky="w")
                self.annotation_buttons[aufgaben_nummer].append(btn)

    def _lade_icon(self, bildname):
        """
        Lädt ein Bild, skaliert es auf config.BILDHOEHE_PX Höhe und cached es.

        :param bildname: Name zum Bild
        :return: Tkinter PhotoImage-Objekt
        """


        if bildname in self.bilder_cache:
            return self.bilder_cache[bildname]
        else:
            zielpfad = os.path.join("Eingabe", "bilder",bildname)
            
        pil_img = Image.open(zielpfad)
        ratio = config.BILDHOEHE_PX / pil_img.height
        neue_breite = int(pil_img.width * ratio)
        pil_img = pil_img.resize((neue_breite, config.BILDHOEHE_PX), Image.LANCZOS)
        tkimg = ImageTk.PhotoImage(pil_img)
        self.bilder_cache[bildname] = tkimg
        return tkimg
    
    def hide_prompt_buttons(self):
        """Blendet alle Prompt-Buttons aus."""
        for btn in self.btn_prompt.values():
            btn.grid_remove()

    def show_prompt_buttons(self):
        """Zeigt alle Prompt-Buttons an."""
        for btn in self.btn_prompt.values():
            btn.grid()

    def edit_annotation(self, aufgaben_nummer, annotation, main_button=None):
        """
        Öffnet ein Popup zum Bearbeiten einer Annotation.

        :param aufgaben_nummer: Nummer der Aufgabe
        :param annotation: Dictionary mit Annotation-Daten
        :param main_button: Button, der die Annotation repräsentiert (für Bild-Update)
        """
        popup = tk.Toplevel(self)
        popup.title(f"Annotation bearbeiten: {annotation['name']}")
        popup.geometry("+%d+%d" % (popup.winfo_screenwidth() // 2 - 200, popup.winfo_screenheight() // 2 - 100))

        frame = ttk.Frame(popup, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")

        # Name der Annotation (Label)
        name_label = ttk.Label(frame, text=annotation["name"])
        name_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        def toggle_hartkodiert():
            annotation["VerwendeHartKodiert"] = checkbox_var.get()

        # Hartkodiert-Text anzeigen, falls vorhanden
        hartkodiert_text = annotation.get("HartKodiert")
        if hartkodiert_text:
            ttk.Label(frame, text=f"HartKodiert: {hartkodiert_text}", foreground="gray")\
                .grid(row=1, column=0, padx=5, pady=5, sticky="w")

            # Checkbox zum Umschalten der Hartkodierung
            checkbox_var = BooleanVar(value=annotation.get("VerwendeHartKodiert", False))
            # Checkbox
            cb = ttk.Checkbutton(frame, text="Verwende HartKodiert", variable=checkbox_var, command=toggle_hartkodiert)
            cb.grid(row=2, column=0, padx=5, pady=5, sticky="w")

        else:
            checkbox_var = tk.BooleanVar(value=False)

        def select_image():
            datei = filedialog.askopenfilename(filetypes=[("Bilddateien", "*.png;*.jpg;*.jpeg;*.gif")])
            if datei:
                if config.GLOBALORDNER.get("Eingabe",None):
                    zielordner1 = os.path.join("Eingabe", "bilder")
                    zielordner2 = os.path.join(config.GLOBALORDNER["Eingabe"], "bilder")
                    os.makedirs(zielordner2, exist_ok=True)                    
                    zielpfad2 = os.path.join(zielordner2, os.path.basename(datei))
                    self._speichere_skalierte_version(datei, zielpfad2)
                else:
                    zielordner1 = os.path.join("Eingabe", "bilder")
                    zielpfad1 = os.path.join(zielordner1, os.path.basename(datei))
            
                os.makedirs(zielordner1, exist_ok=True)                    
                zielpfad1 = os.path.join(zielordner1, os.path.basename(datei))
                self._speichere_skalierte_version(datei, zielpfad1)
                annotation["bild"] = os.path.basename(zielpfad1)
                bild_label.config(text=annotation["bild"])

                # Bild im Hauptbutton aktualisieren
                if main_button:
                    img_obj = self._lade_icon(os.path.basename(datei))
                    if img_obj:
                        main_button.config(image=img_obj, compound="left")
                        main_button.image = img_obj
                    else:
                        main_button.config(image="", compound="none")
                        main_button.image = None

   
        # Label für Bilddatei
        bild_label = ttk.Label(frame, text=annotation.get("bild", "kein Bild"))
        bild_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")

        # Button zum Bild auswählen
        btn_bild = ttk.Button(frame, text="Bild wählen", command=select_image)
        btn_bild.grid(row=4, column=0, padx=5, pady=5, sticky="w")

        # Close-Button
        btn_close = ttk.Button(frame, text="Schließen", command=popup.destroy)
        btn_close.grid(row=5, column=0, padx=5, pady=10, sticky="e")

    def _speichere_skalierte_version(self, quelle, ziel):
        """Speichert eine skalierte Version eines Bildes."""
        pil_img = Image.open(quelle)
        ratio = config.BILDHOEHE_PX / pil_img.height
        neue_breite = int(pil_img.width * ratio)
        pil_img = pil_img.resize((neue_breite, config.BILDHOEHE_PX), Image.LANCZOS)
        pil_img.save(ziel)

    def add_annotation(self, aufgaben_nummer, frame):
        """
        Fügt eine neue Annotation für eine Aufgabe hinzu, mit Abrage des neuen Namens.

        :param aufgaben_nummer: Nummer der Aufgabe
        :param frame: Frame, in dem Annotation-Buttons angezeigt werden
        """
        name = simpledialog.askstring("Neue Annotation", "Wie soll die neue Annotation heißen?", parent=self)
        if name and name.strip():
            neue_annot = {"name": name.strip(), "bild": None, "VerwendeHartKodiert": False}
            if aufgaben_nummer not in self.aufgaben_annotationen:
                self.aufgaben_annotationen[aufgaben_nummer] = []
            self.aufgaben_annotationen[aufgaben_nummer].append(neue_annot)
            self._build_annotation_buttons(aufgaben_nummer, frame)

    def open_prompt_editor(self, aufgaben_nummer):
        """Öffnet den Prompt-Editor für die gegebene Aufgabe."""
        try:
            aufgabenName = self.aufgaben[aufgaben_nummer]
            prompts_folder = os.path.join("Eingabe", "prompts")
            PromptEditor(self, aufgabennr=aufgaben_nummer, aufgabenname=aufgabenName, prompt_folder=prompts_folder,aufgaben_annotationen =self.aufgaben_annotationen)
        except IndexError:
            messagebox.showerror("Fehler", f"Ungültige Aufgabennummer: {aufgaben_nummer}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Prompt-Editor konnte nicht geöffnet werden:\n{str(e)}")
            
    def get_ki_aufgaben(self):
        """Gibt die aktuellen KI-Aufgaben als Dictionary zurück."""
        return {num: entry.get() for num, entry in self.entries.items()}

    def get_aufgaben_annotationen(self):
        """Gibt das Dictionary der Annotationen zurück."""
        return self.aufgaben_annotationen

    def get_aufgaben(self):
         return self.aufgaben
         
    def get_annotationen(self):
        # Rückgabe der Annotationen
        return self.aufgaben_annotationen

    def _refresh_text(self):
        for nummer, entry in self.entries.items():
            if nummer in self.aufgaben:
                entry.delete(0, tk.END)
                entry.insert(0, self.aufgaben[nummer])
            else:
                entry.delete(0, tk.END)

    def set_aufgaben(self, neue_aufgaben):
        self.aufgaben = neue_aufgaben
        self._refresh_text()

    
    def set_annotationen(self, neue_annotationen):        
        self.aufgaben_annotationen = neue_annotationen
        for nummer, frame in self.annotation_frames.items():
            self._build_annotation_buttons(nummer, frame)

            import shutil

    def werkszustand_wiederherstellen(self):
        prompts_ordner = os.path.join("Eingabe", "prompts")
        prompts_orig_ordner = os.path.join("Eingabe", "prompts_orig")

        # 1. Alle Dateien aus 'prompts' löschen, die nicht in 'prompts_orig' existieren
        if os.path.exists(prompts_ordner):
            for datei in os.listdir(prompts_ordner):
                pfad = os.path.join(prompts_ordner, datei)
                orig_pfad = os.path.join(prompts_orig_ordner, datei)
                if os.path.isfile(pfad) and not os.path.exists(orig_pfad):
                    try:
                        os.remove(pfad)
                        print(f"Gelöscht: {pfad}")
                    except Exception as e:
                        print(f"Fehler beim Löschen von {pfad}: {e}")

        # 2. Alle Originaldateien wiederherstellen
        if os.path.exists(prompts_orig_ordner):
            for datei in os.listdir(prompts_orig_ordner):
                quellpfad = os.path.join(prompts_orig_ordner, datei)
                zielpfad = os.path.join(prompts_ordner, datei)
                if os.path.isfile(quellpfad):
                    try:
                        shutil.copyfile(quellpfad, zielpfad)
                        print(f"Wiederhergestellt: {zielpfad}")
                    except Exception as e:
                        print(f"Fehler beim Wiederherstellen von {zielpfad}: {e}")

        # 3. Alle Widgets aus dem Editor löschen
            for widget in self.winfo_children():
                widget.destroy()

            # 4. GUI neu aufbauen
            self.create_widgets()
  

def tkfont_to_reportlab_font(tkfont_tuple):
    """Wandelt Tkinter-Font-Tupel in ReportLab-Fontnamen + Größe um."""
    if not tkfont_tuple or len(tkfont_tuple) < 2:
        raise ValueError("tkfont_tuple braucht mindestens (Fontname, Größe)")
    fontname = tkfont_tuple[0]
    fontsize = tkfont_tuple[1]
    style = tkfont_tuple[2].lower() if len(tkfont_tuple) > 2 else ""

    if style == "bold":
        font_rl = f"{fontname}-Bold"
    elif style in ("italic", "oblique"):
        font_rl = f"{fontname}-Oblique"
    else:
        font_rl = fontname
    return font_rl, fontsize

def register_custom_font(font_path: str, font_name: str) -> bool:
    """
    Registriert eine TrueType-Fontdatei in ReportLab.
    True → schon vorhanden oder erfolgreich registriert
    False → Datei fehlt oder Fehler bei der Registrierung
    """
    if font_name in pdfmetrics.getRegisteredFontNames():
        return True
    if not os.path.isfile(font_path):
        return False
    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        return True
    except Exception as e:
        print(f"[FontDropdown] Fehler beim Registrieren von {font_name}: {e}")
        return False

def parse_font_style(fontname):
    # Beispiel input: "Cascadia Code Light"
    # Output: ("Cascadia Code", "Light")

    parts = fontname.split()
    # Angenommen, die letzten 1-2 Wörter können Gewicht/Stil sein, rest Familie

    # Häufige Gewicht/Stil-Bezeichnungen
    style_keywords = { 'bold', 'italic'}

    # Suche von hinten nach Stilwörtern
    style_parts = []
    for part in reversed(parts):
        if part.lower() in style_keywords:
            style_parts.insert(0, part)
        else:
            break

    family_len = len(parts) - len(style_parts)
    family = ' '.join(parts[:family_len])
    style = ' '.join(style_parts)
    return family, style

class FontDropdown(tk.Frame):
    FONT_SIZE = 12

    def __init__(self, parent, initial_font=None, path=None, callback=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.path = path
        self.callback = callback

        self.all_fonts = self.get_mono_fonts(self.path)
        self.filtered_fonts = self.all_fonts[:]
       
        if initial_font:
            self.default_font = self.find_replacement_font(initial_font, self.all_fonts)
        else:
            self.default_font = self.all_fonts[0] if self.all_fonts else "TkFixedFont"

        lname = self.default_font.lower()
        # Filter-Flags basierend auf initialem Font setzen
        self.bold = "bold" in lname
        self.italic = ("italic" in lname) or ("oblique" in lname)

        self.var = tk.StringVar(value=self.default_font)

        self.update_filter()

        base, style = parse_font_style(self.default_font)
        style_parts = style.split() if style else []
        self.display = ttk.Label(self, textvariable=self.var,
                                 font=(base, self.FONT_SIZE, *style_parts),
                                 relief="sunken", anchor="w", padding=4,
                                 width=30)
        self.display.grid(row=0, column=0, sticky="ew")
        self.display.bind("<Button-1>", self._toggle_canvas)

        self.columnconfigure(0, weight=1)

        self.canvas_window = None
     
    def get(self):
        return self.var.get() or None

    def set(self, value):
        font_to_use = self.find_replacement_font(value, self.all_fonts)
        if font_to_use != value:
            print(f"[FontDropdown] '{value}' nicht gefunden, ersetze durch '{font_to_use}'.")
        self.var.set(font_to_use)
        base, style = parse_font_style(font_to_use)
        style_parts = style.split() if style else []
        self.display.config(font=(base, self.FONT_SIZE, *style_parts))
        self._check_path_and_font()

    # def get_mono_fonts(self, search_path = None):
    #       # Relevante Stichworte für Monospace-Schriften
    #     keywords = ["mono", "console", "code", "fixed", "courier",
    #                 "menlo", "consolas", "dejavu", "inconsolata"]

    #     mono_fonts = {}


    #     # Liste aller TTF-Dateien im Suchpfad (rekursiv)
    #     if search_path:
    #         alle_ttf_pfade = self.find_ttf_path(None, search_path, True)
      
    #         for pfad in alle_ttf_pfade:
    #             name = os.path.splitext(os.path.basename(pfad))[0]
    #             name_clean = name.lower()
    #             if any(k in name_clean for k in keywords):
    #                 mono_fonts[name] = pfad

    #         return mono_fonts or {"TkFixedFont": None}

    #     else:

    #         all_fonts = sorted(tkfont.families(), key=str.lower)
    #         relevante_fonts = [f for f in all_fonts if any(k in f.lower() for k in keywords)]

    #           # Versuche TTF-Dateipfade zu finden
    #         font_paths = {}
    #         for font in relevante_fonts:
    #             pfad = self.find_ttf_path(font, search_path,False)
    #             if pfad:
    #                 font_paths[font] = pfad
            
    #         return font_paths or {"TkFixedFont": None}

    def get_mono_fonts(self, search_path=None):
        keywords = ["mono", "console", "code", "fixed", "courier",
                    "menlo", "consolas", "dejavu", "inconsolata"]

        if search_path:
            # Alle TTF-Dateien im Pfad finden
            alle_ttf_pfade = self.find_ttf_path(None, search_path, True)
            fonts = []

            for pfad in alle_ttf_pfade:
                name = os.path.splitext(os.path.basename(pfad))[0]
                name_clean = name.lower()
                if any(k in name_clean for k in keywords):
                    fonts.append(name)

            return sorted(fonts) if fonts else self._fallback_font()
        else:
            # Systemfonts prüfen
            try:
                all_fonts = tkfont.families()
            except tk.TclError:
                all_fonts = []

            relevante_fonts = [f for f in all_fonts if any(k in f.lower() for k in keywords)]
            return sorted(relevante_fonts) if relevante_fonts else self._fallback_font()

    def _fallback_font(self):
        """Gibt fallback-Font zurück, falls vorhanden – sonst leere Liste."""
        try:
            fonts = tkfont.families()
            if "TkFixedFont" in fonts:
                return ["TkFixedFont"]
        except tk.TclError:
            pass
        return []

    def update_filter(self):
        # Filter Fonts basierend auf initialem Stil (bold, italic)
        self.filtered_fonts = [
            f for f in self.all_fonts
            if (not self.bold or "bold" in f.lower())
            and (not self.italic or ("italic" in f.lower() or "oblique" in f.lower()))
        ] or self.all_fonts[:]

        if self.var.get() not in self.filtered_fonts:
            self.set(self.filtered_fonts[0])

    def _toggle_canvas(self, _=None):
        if self.canvas_window and self.canvas_window.winfo_exists():
            self.canvas_window.destroy()
            self.canvas_window = None
        else:
            self._open_canvas()

    def _open_canvas(self):
        self.update_filter()
        self.canvas_window = tk.Toplevel(self)
        self.canvas_window.wm_overrideredirect(True)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self.canvas_window.geometry(f"+{x}+{y}")

        canvas = tk.Canvas(self.canvas_window, width=self.winfo_width(),
                           height=200, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        sbar = ttk.Scrollbar(self.canvas_window, orient="vertical",
                             command=canvas.yview)
        sbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sbar.set)

        frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=frame, anchor="nw")

        for fname in self.filtered_fonts:
            base, style = parse_font_style(fname)
            style_parts = style.split() if style else []
            lbl = tk.Label(frame, text=fname,
                           font=(base, self.FONT_SIZE, *style_parts),
                           anchor="w")
            lbl.pack(fill="x", padx=2, pady=1)
            lbl.bind("<Button-1>",
                     lambda e, fn=fname: (self.set(fn),
                                          self.canvas_window.destroy()))

        frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

        def _on_mousewheel(event):
            try:
                if not canvas.winfo_exists():
                    return "break"
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
            except Exception as e:
                print(f"Scroll-Fehler: {e}")
            return "break"  # verhindert Weiterleitung ans Hauptfenster

        # Mousewheel binden
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

        # Fokus schließen bei Klick außerhalb
        self.canvas_window.bind("<FocusOut>", lambda e: self.canvas_window.destroy())
        self.canvas_window.focus_set()
      
        self.canvas_window.focus_set()

    def find_replacement_font(self, fontname, all_fonts):
        if fontname in all_fonts:
            return fontname
        m = re.match(r"([A-Za-z\s]+)([-\s]?(Bold|Italic|Oblique))?", fontname, re.I)
        if not m:
            return self._random_font_by_style("", all_fonts) or "TkFixedFont"
        base = m.group(1).strip()
        style = (m.group(3) or "").lower()
        base_candidates = [f for f in all_fonts if f.lower().startswith(base.lower())]
        if style:
            styled = [f for f in base_candidates if style in f.lower()] or \
                     [f for f in all_fonts if style in f.lower()]
            if styled:
                return random.choice(styled)
        normal = [f for f in all_fonts if all(s not in f.lower() for s in ["bold", "italic", "oblique"])]
        return random.choice(normal) if normal else "TkFixedFont"

    def _random_font_by_style(self, style, all_fonts):
        style = style.lower()
        pool = ([f for f in all_fonts if style in f.lower()] if style else
                [f for f in all_fonts if all(s not in f.lower() for s in ["bold", "italic", "oblique"])])
        return random.choice(pool) if pool else None

    def _check_path_and_font(self):
        fontname = self.var.get()
        if not self.path:
            if self.callback:
                self.callback("Kein Font-Pfad gesetzt.")
            return

        path = self.find_ttf_path(fontname, self.path)
        if not path:
            if self.callback:
                self.callback(f"Font '{fontname}' nicht im Pfad gefunden.")
            return

        ok = register_custom_font(path, fontname)
        if not ok and self.callback:
            self.callback(f"Registrierung von '{fontname}' fehlgeschlagen.")

    def clean_name(self,name):
        return re.sub(r'[^a-z0-9]', '', name.lower())

    def find_ttf_path(self, fontname, search_path, ShowAll=False):
        matches = []
        for root, _, files in os.walk(search_path):
            for f in files:
                if f.lower().endswith(".ttf"):
                    f_clean = self.clean_name(os.path.splitext(f)[0])
                    if ShowAll:
                        matches.append(os.path.join(root, f))
                    elif fontname and self.clean_name(fontname) == f_clean:
                        return os.path.join(root, f)
        return matches if ShowAll else None


class ConfigEditor(ttk.Frame):
    """Seite zum Bearbeiten der config.py mit speziellem Editor für KI_AUFGABEN"""

    def __init__(self, parent, notebook, dashboard,eingabe_ordner ="Eingabe"):
        super().__init__(parent)
        self.notebook = notebook
        self.dashboard = dashboard
        self.eingabe_ordner = eingabe_ordner
        self.notebook.add(self, text="⚙️ Einstellungen")

        self.entries = {}
        self._build_widgets()
        self.notebook.hide(self)

    def get_standard_font_path(self):
        system = platform.system()
        if system == "Windows":
            return os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        elif system == "Darwin":  # macOS
            return "/Library/Fonts"
        elif system == "Linux":
            # Bevorzugter neuer Standard
            user_font_path = os.path.expanduser("~/.local/share/fonts")
            if os.path.exists(user_font_path):
                return user_font_path
            # Fallbacks
            if os.path.exists("/usr/share/fonts"):
                return "/usr/share/fonts"
        return ""  # Falls nicht erkannt

  
    def on_nutzeKI_changed(self, *args):
        if self.ki_aufgaben_editor:
            if self.nutzeKI_var.get():
                self.ki_aufgaben_editor.show_prompt_buttons()
            else:
                self.ki_aufgaben_editor.hide_prompt_buttons()

    def _build_widgets(self):
        import tkinter.font as tkfont
        import tkinter as tk

        # Clear previous widgets (z.B. nach Reset)
        for child in self.winfo_children():
            child.destroy()

        # Kopfbereich mit Buttons
        btn_close = ttk.Button(self, text="✖", width=3, command=self._close_tab)
        btn_close.grid(row=0, column=8, sticky="ne", padx=10, pady=5)

        top_btns = ttk.Frame(self)
        top_btns.grid(row=0, column=1, columnspan=7, sticky="ne", padx=10, pady=5)
        style = ttk.Style()
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=10)

        btn_save = ttk.Button(top_btns, text="Speichern", style="Big.TButton", command=self._save)
        btn_load = ttk.Button(top_btns, text="Laden", style="Big.TButton", command=self._load)
        btn_discard = ttk.Button(top_btns, text="Verwerfen", style="Big.TButton", command=self._reset)

        btn_save.grid(row=0, column=0, padx=5)
        btn_load.grid(row=0, column=1, padx=5)
        btn_discard.grid(row=0, column=2, padx=5)

        # --- KI_AUFGABEN Editor direkt unter den Buttons ---
        Aufgabenframe = ttk.Frame(self)
        Aufgabenframe.grid(row=1, column=0, sticky="w", padx=10, pady=2)

        self.nutzeKI_var = tk.BooleanVar(value=getattr(config, "NUTZE_KI", True))
        self.nutzeKI_var.trace_add("write", self.on_nutzeKI_changed)

        ttk.Label(Aufgabenframe, text="ANNOTATIONS-AUFGABEN").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(Aufgabenframe, text="nutze KI für diese Aufgaben?", variable=self.nutzeKI_var).grid(row=1, column=0, sticky="w")

        print("Checkbox mit nutzeKI_var erstellt:", self.nutzeKI_var.get())
        self.aufgaben_frame = ttk.Frame(self, borderwidth=1, relief="sunken")
        self.aufgaben_frame.grid(row=1, column=1, columnspan=8, sticky="nsew", padx=5, pady=2)
        self.aufgaben_frame.columnconfigure(0, weight=1)
        self.aufgaben_frame.rowconfigure(0, weight=1)
        self._build_aufgaben_editor()

        # Scrollbarer Bereich für Konfiguration
        scrollframe = ScrollableFrame(self)
        scrollframe.grid(row=2, column=0, columnspan=9, sticky="nsew", padx=5, pady=5)
        for c in range(9):
            self.columnconfigure(c, weight=1)

        self.rowconfigure(2, weight=1)

        self.config_frame = scrollframe.scrollable_frame
        for i in range(100):
            self.config_frame.rowconfigure(i, weight=0)

        # --- WICHTIG: Konfiguration der 9 Spalten ---
        for c in (0, 3, 6):
            self.config_frame.columnconfigure(c, weight=0)  # Labels fester
        for c in (1, 4, 7):
            self.config_frame.columnconfigure(c, weight=1)
        for c in (2, 5, 8):
            self.config_frame.columnconfigure(c, minsize=15, weight=0)

        # Einträge aus config-Datei lesen
        self.eintraege = []
        kommentare = {}

        config_path = os.path.join("Eingabe", "config.py")
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                zeilen = f.readlines()

            start = 0
            for i, line in enumerate(zeilen):
                if not line.strip().startswith("#") and line.strip() != "":
                    start = i
                    break

            for line in zeilen[start:]:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                if line.strip().startswith("#") and "=" not in line:
                    self.eintraege.append(("__GROUP__", line.strip("# ").strip()))
                else:
                    parts = line.split("#", 1)
                    code = parts[0].strip()
                    comment = parts[1].strip() if len(parts) > 1 else ""
                    if "=" in code:
                        key, val = map(str.strip, code.split("=", 1))
                        if key not in ("GLOBALORDNER", "NUTZE_KI", "KI_AUFGABEN", "AUFGABEN_ANNOTATIONEN", "START_Y_POS", "MAX_ZEILENANZAHL"):
                            self.eintraege.append((key, val, comment))
        else:
            import inspect
            for n, v in inspect.getmembers(config):
                if not n.startswith("__") and not inspect.ismodule(v) and not inspect.isfunction(v) and n not in ("KI_AUFGABEN", "GLOBALORDNER", "AUFGABEN_ANNOTATIONEN"):
                    self.eintraege.append((n, repr(v), ""))

        row = 0
        paar_index = 0
        self.entries.clear()
        self.color_buttons = {}

        for eintrag in self.eintraege:
            if eintrag[0] == "__GROUP__":
                label = ttk.Label(self.config_frame, text=eintrag[1], font=("Segoe UI", 14, "bold"), anchor="center", justify="center")
                label.grid(row=row, column=0, columnspan=9, sticky="ew", pady=(10, 2), padx=10)
                row += 1
                paar_index = 0
                continue

            name, val, comment = eintrag
            base_col = paar_index * 3
            col_label = base_col
            col_entry = base_col + 1

            if name.startswith("FARBE_"):
                hex_color = "#ffffff"
                rgb_val = (255, 255, 255)
                try:
                    v = val.strip()
                    if v.startswith("#"):
                        hex_color = v
                        rgb_val = tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))
                    else:
                        t = ast.literal_eval(v)
                        if isinstance(t, tuple) and len(t) == 3:
                            rgb_val = tuple(int(c) for c in t)
                            hex_color = '#%02x%02x%02x' % rgb_val
                except Exception:
                    pass

                def make_color_cmd(n=name):
                    def cmd():
                        current_hex = self.color_buttons[n]["bg"]
                        rgb_tuple, new_hex = tk.colorchooser.askcolor(color=current_hex, parent=self)
                        if new_hex:
                            rgb_int = tuple(int(c) for c in rgb_tuple)
                            self.color_buttons[n].config(bg=new_hex)
                            self.color_buttons[n].color_value = rgb_int
                    return cmd

                lbl = ttk.Label(self.config_frame, text=name)
                lbl.grid(row=row, column=col_label, sticky="w", padx=10, pady=2)

                btn = tk.Button(self.config_frame, bg=hex_color, width=3, relief="sunken", command=make_color_cmd())
                btn.color_value = rgb_val
                btn.grid(row=row, column=col_entry, sticky="w", padx=5, pady=2)
                self.color_buttons[name] = btn
                self.entries[name] = None

                if comment:
                    ToolTip(lbl, comment)
                    ToolTip(btn, comment)

            elif name.startswith("SCHRIFTART_"):
                available_fonts = tkfont.families()
                fontname = val.strip('"\'')
                lbl = ttk.Label(self.config_frame, text=name, font=(fontname, 10))
                lbl.grid(row=row, column=col_label, sticky="w", padx=10, pady=2)

                fd = FontDropdown(self.config_frame, fonts=None, initial_font=fontname)
                fd.set(fontname)
                fd.grid(row=row, column=col_entry, sticky="ew", padx=5)
                if comment:
                    fd.tooltip = ToolTip(fd, comment)
                self.entries[name] = fd

            else:
                lbl = ttk.Label(self.config_frame, text=name)
                lbl.grid(row=row, column=col_label, sticky="w", padx=10, pady=2)

                e = ttk.Entry(self.config_frame, width=30)
                e.insert(0, val)
                e.grid(row=row, column=col_entry, sticky="ew", padx=5)

                if comment:
                    ToolTip(lbl, comment)
                    ToolTip(e, comment)

                self.entries[name] = e

            paar_index += 1
            if paar_index > 2:
                paar_index = 0
                row += 1

    def _build_aufgaben_editor(self):
        for widget in self.aufgaben_frame.winfo_children():
            widget.destroy()
        
        
        ordner =  getattr(config, "GLOBALORDNER", )   
        if ordner:
            eingabe_ordner = ordner.get("Eingabe")
        else:
            eingabe_ordner = "Eingabe"

        ki_aufgaben_dict = getattr(config, "KI_AUFGABEN", {})
        aufgaben_annotationen_dict = getattr(config, "AUFGABEN_ANNOTATIONEN", {})

        self.ki_aufgaben_editor = KIAufgabenEditor(
            self.aufgaben_frame,
            self.nutzeKI_var,
            eingabe_ordner,      
            ki_aufgaben_dict.copy(),
            aufgaben_annotationen_dict.copy()
        )
        self.ki_aufgaben_editor.grid(row=0, column=0, sticky="nsew")

    def _close_tab(self):
        if hasattr(self, "notebook"):
            self.notebook.hide(self)

    def _load(self):
        import re
        import shutil
        import importlib.util
        from tkinter import messagebox, filedialog

        lokal_ordner = "Eingabe"
        global_ordner = config.GLOBALORDNER.get("Eingabe", "Eingabe")

        default_path = os.path.join(lokal_ordner, "config_default.py")
        try:
            spec = importlib.util.spec_from_file_location("default_config", default_path)
            default_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(default_mod)
        except Exception as e:
            messagebox.showerror("Fehler", f"Standard-Konfig ({default_path}) konnte nicht geladen werden:\n{e}")
            return

        datei = filedialog.askopenfilename(
            title="Config-Datei zum Laden auswählen",
            filetypes=[("Python Dateien", "*.py"), ("Alle Dateien", "*.*")]
        )
        if not datei:
            return

        try:
            spec = importlib.util.spec_from_file_location("user_config", datei)
            user_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(user_mod)
        except Exception as e:
            messagebox.showerror("Fehler", f"Ausgewählte Datei konnte nicht geladen werden:\n{e}")
            return

        # Pflichtfelder aus der Default-Konfiguration
        default_attrs = {k for k in dir(default_mod) if not k.startswith("_")}
        user_attrs = {k for k in dir(user_mod) if not k.startswith("_")}
        fehlend = default_attrs - user_attrs
        if fehlend:
            messagebox.showerror("Fehler", f"In der ausgewählten Datei fehlen Pflichtfelder:\n{fehlend}")
            return

        # Dateien lokal und global kopieren
        lokal_config_path = os.path.join(lokal_ordner, "config.py")
        global_config_path = os.path.join(global_ordner, "config.py")

        try:
            shutil.copy(datei, lokal_config_path)
            shutil.copy(datei, global_config_path)
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte config.py nicht kopieren:\n{e}")
            return

        # Kommentare aus der Datei auslesen (für ToolTips)
        kommentare = {}
        try:
            with open(datei, "r", encoding="utf-8") as f:
                zeilen = f.readlines()
                start = 0
                for i, line in enumerate(zeilen):
                    if not line.strip().startswith("#") and line.strip() != "":
                        start = i
                        break
                for line in zeilen[start:]:
                    line = line.rstrip("\n")
                    match = re.match(r"^(\w+)\s*=\s*(.+?)\t#\s*(.+)$", line)
                    if match:
                        name = match.group(1)
                        kommentar = match.group(3)
                        kommentare[name] = kommentar
        except Exception:
            kommentare = {}

        # Werte in self.entries übernehmen und ggf. ToolTip setzen
        for n, e in self.entries.items():
            if e is None:
                continue  # Widget nicht vorhanden
            val = getattr(user_mod, n, None)
            if val is not None:
                e.delete(0, "end")
                e.insert(0, str(val))
                if n in kommentare:
                    ToolTip(e, kommentare[n])

        # KI-Aufgaben und Annotationen setzen
        self.ki_aufgaben_editor.set_aufgaben(getattr(user_mod, "KI_AUFGABEN"))
        self.ki_aufgaben_editor.set_annotationen(getattr(user_mod, "AUFGABEN_ANNOTATIONEN"))

        # WICHTIG: GUI aktualisieren
        if hasattr(self, "build_widget") and callable(self.build_widget):
            self.build_widget()

        messagebox.showinfo("Erfolg", "Config wurde geladen und GUI aktualisiert.")


    def _save(self):
    
        header_block = [
            "# ---------------------------------------------",
            f"# Konfigurationsdatei (config.py), Automatisch generiert am {datetime.now().isoformat()}",
            "# ---------------------------------------------",
            "",
        ]
        ki_aufgaben_dict = self.ki_aufgaben_editor.get_aufgaben()
        aufgaben_annotationen_dict = self.ki_aufgaben_editor.get_annotationen()
        globalordner_str = {k: str(v) for k, v in getattr(config, 'GLOBALORDNER', {}).items()}

        # Headerblock als Start
        lines = header_block[:]

        # Variablen-Definitionen anfügen
        lines += [
            f"GLOBALORDNER = {repr(globalordner_str)}\t# Ordnerstruktur für Ein- und Ausgabe",
            "",
            f"NUTZE_KI = {repr(self.nutzeKI_var.get())}\t# Schaltet alle KI-Funktionen zentral ein/aus",
            f"KI_AUFGABEN = {repr(ki_aufgaben_dict)}\t# Aufgabenübersicht mit Aktivierungsstatus und Parametern",
            f"AUFGABEN_ANNOTATIONEN = {repr(aufgaben_annotationen_dict)}\t# Mögliche Annotationen für jede Aufgabe",
            "",
        ]

        # Einträge aus self.eintraege verarbeiten (Kommentare, Variablen)
        for eintrag in self.eintraege:
            if eintrag[0] == "__GROUP__":
                # Leerzeile vor Gruppenüberschrift (außer am Anfang)
                if len(lines) > 0 and lines[-1] != "":
                    lines.append("")
                gruppe = eintrag[1]
                lines.append(f"# {gruppe}")
            else:
                name, val, comment = eintrag
                e = self.entries.get(name, None)  # zuerst e definieren

                 # NEU: Behandlung für Schriftart-Comboboxen
                if name.startswith("SCHRIFTART_") and e is not None and isinstance(e, FontDropdown):
                    selected_font  = e.get()  # FontDropdown.get() liefert String
                    val_repr = repr(selected_font )
                elif e is not None:
                    val_str = e.get()
                    try:
                        val_eval = ast.literal_eval(val_str)
                        val_repr = repr(val_eval)
                    except Exception:
                        val_repr = repr(val_str)

                # Farben ans Ende verschieben, daher überspringen
                if name.startswith("FARBE_"):
                    continue
                else:
                    if name in self.entries and self.entries[name] is not None:                        
                        val_str = e.get()
                        try:
                            val_eval = ast.literal_eval(val_str)
                            val_repr = repr(val_eval)
                        except Exception:
                            val_repr = repr(val_str)
                        kommentar = getattr(e, "tooltip", None)
                        kommentar_text = kommentar.text if kommentar else ""
                        if kommentar_text:
                            lines.append(f"{name} = {val_repr}\t# {kommentar_text}")
                        else:
                            lines.append(f"{name} = {val_repr}")
                    else:
                        # Fallback auf Wert aus eintraege
                        if comment:
                            lines.append(f"{name} = {repr(val)}\t# {comment}")
                        else:
                            lines.append(f"{name} = {repr(val)}")
        # Farben ans Ende, damit sie nicht doppelt vorkommen
        for n, btn in self.color_buttons.items():
            rgb = getattr(btn, "color_value", (255, 255, 255))
            lines.append(f"{n} = {repr(rgb)}")

         # Nun manuell die beiden speziellen Zeilen hinzufügen
        lines.append("") 
        lines.append("") # optional Leerzeile
        lines.append("START_Y_POS = MAX_SEITENHOEHE - OBERER_SEITENRAND  # Berechnet automatisch die Y-Position (maximale Höhe minus oberer Rand)")
        lines.append("MAX_ZEILENANZAHL = (MAX_SEITENHOEHE - OBERER_SEITENRAND - UNTERER_SEITENRAND) // ZEILENHOEHE  # Berechnung der maximalen Zeilenanzahl")

        # Lokalen Ordner sicherstellen
        lokal_ordner = "Eingabe"
        os.makedirs(lokal_ordner, exist_ok=True)

        lokal_datei = os.path.join(lokal_ordner, "config.py")
        tmp_datei = os.path.join(lokal_ordner, "_tmp_config.py")

        # Falls Datei existiert und Header enthält, nur den Inhaltsteil ersetzen (ab Zeile 6)
        if os.path.exists(lokal_datei):
            try:
                with open(lokal_datei, "r", encoding="utf-8") as f:
                    alte_zeilen = f.readlines()
                if any("Automatisch generiert am" in z for z in alte_zeilen[:5]):
                    # Ersetze nur den Bereich nach dem Header
                    lines = alte_zeilen[:6] + lines[len(header_block):]
            except Exception:
                pass  # Falls Datei gesperrt o.ä., einfach komplett neu schreiben

        # Schreibe temporäre Datei
        with open(tmp_datei, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        # Ersetze config.py mit temporärer Datei
        try:
            os.replace(tmp_datei, lokal_datei)
        except PermissionError:
            messagebox.showwarning("Warnung", "config.py war gesperrt – versuche erzwungenes Überschreiben.")
            try:
                os.remove(lokal_datei)
                os.replace(tmp_datei, lokal_datei)
            except Exception as e:
                messagebox.showerror("Fehler", f"config.py konnte nicht überschrieben werden:\n{e}")
                return

        # Optional global speichern, falls GLOBALORDNER anders als "Eingabe"
        global_ordner = config.GLOBALORDNER.get("Eingabe", "Eingabe")
        if global_ordner != "Eingabe":
            os.makedirs(global_ordner, exist_ok=True)
            global_datei = os.path.join(global_ordner, "config.py")
            with open(global_datei, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

        messagebox.showinfo("Erfolg", "config.py gespeichert.")

        # Versuche config-Modul neu zu laden
        try:
            importlib.reload(config)
        except Exception as e:
            messagebox.showwarning("Warnung", f"config-Modul konnte nicht neu geladen werden:\n{e}")

        # Aktualisiere Dashboard, falls vorhanden
        if hasattr(self.dashboard, "lade_aufgaben_checkboxes"):
            self.dashboard.lade_aufgaben_checkboxes()

    def _reset(self):
        lokal_ordner = self.eingabe_ordner  # z.B. "./Eingabe"
        global_ordner = config.GLOBALORDNER.get("Eingabe", "Eingabe")

        default_path = os.path.join(lokal_ordner, "config_default.py")
        lokal_config_path = os.path.join(lokal_ordner, "config.py")
        global_config_path = os.path.join(global_ordner, "config.py")

        # Auf Werkszustand zurücksetzen (z. B. KI-Prompts)
        self.ki_aufgaben_editor.werkszustand_wiederherstellen()

        if not os.path.exists(default_path):
            messagebox.showerror("Fehler", f"Standard-Konfig-Datei '{default_path}' nicht gefunden.")
            return

        try:
            os.makedirs(global_ordner, exist_ok=True)
            shutil.copy(default_path, global_config_path)
            shutil.copy(default_path, lokal_config_path)
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Kopieren:\n{e}")
            return

        # Konfig neu laden
        importlib.reload(config)

        # Widgets neu aufbauen
        self._build_widgets()

        # Checkboxes neu laden
        self.dashboard.lade_aufgaben_checkboxes()

        messagebox.showinfo("Zurückgesetzt", "Standard-Konfiguration wurde aktualisiert.")
    
class PromptEditor(tk.Toplevel):
    def __init__(self, parent, aufgabennr, aufgabenname, prompt_folder,aufgaben_annotationen):
        super().__init__(parent)
        self.title(f"Prompt Editor: {aufgabenname}")
        self.geometry("700x550")

        self.prompt_folder = prompt_folder
        self.aufgabenname = aufgabenname
        self.aufgabennr = aufgabennr

        self.aufgaben_annotationen = aufgaben_annotationen
        self.is_generated_from_default = False

        self.text = tk.Text(self, wrap="word")
        self.text.pack(expand=True, fill="both", padx=10, pady=10)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=5)

        save_btn = ttk.Button(button_frame, text="Speichern", command=self.save)
        save_btn.pack(side="left", padx=5)

        reset_btn = ttk.Button(button_frame, text="Zurücksetzen", command=self.reset_prompt)
        reset_btn.pack(side="left", padx=5)

        self.load_prompt()
        self.original_text = self.text.get("1.0", tk.END)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_prompt(self):
        datei = os.path.join(self.prompt_folder, f"{self.aufgabenname}.txt")
        default_datei = os.path.join("Eingabe", "prompts_orig", "defaultprompt.txt")

        if os.path.exists(datei):
            with open(datei, "r", encoding="utf-8") as f:
                content = f.read()
            self.is_generated_from_default = False
        elif os.path.exists(default_datei):
            with open(default_datei, "r", encoding="utf-8") as f:
                content = f.read()
            content = self.replace_placeholders(content)
            self.is_generated_from_default = True
        else:
            content = ""
            self.is_generated_from_default = False

        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)

    def reset_prompt(self):
        if not messagebox.askyesno("Zurücksetzen", "Soll der ursprüngliche Prompt wirklich wiederhergestellt werden?"):
            return

        orig_datei = os.path.join("Eingabe", "prompts_orig", f"{self.aufgabenname}.txt")
        default_datei = os.path.join("Eingabe", "prompts_orig", "defaultprompt.txt")

        if os.path.exists(orig_datei):
            with open(orig_datei, "r", encoding="utf-8") as f:
                content = f.read()
            self.is_generated_from_default = False
        elif os.path.exists(default_datei):
            with open(default_datei, "r", encoding="utf-8") as f:
                content = f.read()
            content = self.replace_placeholders(content)
            self.is_generated_from_default = True
        else:
            content = ""
            self.is_generated_from_default = False

        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)

    def replace_placeholders(self, content):
        annots = self.aufgaben_annotationen.get(self.aufgabennr, [])
        if annots:
            annot_namen = [a.get("name", "") for a in annots]
            content = content.replace("{Annotationen}", str(annot_namen))
            content = content.replace("{Annotation1}", annot_namen[0] if annot_namen else "")
        content = content.replace("{AufgabenNr}", str(self.aufgabennr))
        content = content.replace("{AufgabenName}", self.aufgabenname)
        return content

    def save(self):
        text = self.text.get("1.0", tk.END)
        lines = text.splitlines()
        lines = [line for line in lines if not line.strip().startswith("#")]
        clean_text = "\n".join(lines)

        datei = os.path.join(self.prompt_folder, f"{self.aufgabenname}.txt")
        with open(datei, "w", encoding="utf-8") as f:
            f.write(clean_text)
        messagebox.showinfo("Gespeichert", f"Prompt für '{self.aufgabenname}' gespeichert.")
        self.original_text = self.text.get("1.0", tk.END)
        self.is_generated_from_default = False

    def on_close(self):
        current_text = self.text.get("1.0", tk.END)
        if current_text.strip() != self.original_text.strip() or self.is_generated_from_default:
            if messagebox.askyesno("Änderungen speichern?", "Der Prompt wurde geändert oder aus einer Vorlage generiert.\nMöchten Sie die Änderungen speichern?"):
                self.save()
        self.destroy()
