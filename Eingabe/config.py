# ---------------------------------------------

# Konfigurationsdatei (config.py), Automatisch generiert am 2026-04-19T15:40:24.808736

# ---------------------------------------------



GLOBALORDNER = {'Eingabe': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/Eingabe', 'txt': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/txt', 'json': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/json', 'saetze': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/saetze', 'ki': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/ki', 'merge': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/merge', 'pdf': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/pdf', 'manuell': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/manuell', 'pdf2': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/pdf2'}	# Ordnerstruktur für Ein- und Ausgabe



GLOBALORDNER = {'Eingabe': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/Eingabe', 'txt': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/txt', 'json': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/json', 'saetze': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/saetze', 'ki': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/ki', 'merge': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/merge', 'pdf': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/pdf', 'manuell': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/manuell', 'pdf2': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/pdf2'}	# Ordnerstruktur für Ein- und Ausgabe

NUTZE_KI = True	# Schaltet alle KI-Funktionen zentral ein/aus
AKTIVE_KI_AUFGABEN = [3, 4, 9]
KI_MAX_NEW_TOKENS = 768

# KI_AUFGABEN = {3: 'person', 4: 'betonung', 5: 'pause', 6: 'gedanken', 7: 'spannung', 8: 'ig', 9: 'position'}	# Aufgabenübersicht mit Aktivierungsstatus und Parametern
KI_AUFGABEN = {
    3: "person",
    4: "kombination",
    5: "pause",        # bleibt (wird aber nicht mehr benutzt)
    6: "gedanken",     # bleibt (wird aber nicht mehr benutzt)
    7: "spannung",     # bleibt (wird aber nicht mehr benutzt)
    8: "betonung",     # bleibt (wird aber nicht mehr benutzt)
    9: "ig",
}

MERGE_AUFGABE_ID = 99

KOMBI_AUFGABEN_MAPPING = {
    "kombination": {
        "betonung": "betonung",
        "pause": "pause",
        "gedanken": "gedanken",
        "spannung": "spannung",
    }
}

AUFGABEN_ANNOTATIONEN = {3: [{'name': None, 'bild': None, 'HartKodiert': 'farbeJePerson', 'VerwendeHartKodiert': True, 'StartZeichen': '„', 'EndeZeichen': '“'}], 4: [{'name': 'Hauptbetonung', 'bild': None, 'HartKodiert': 'fett', 'VerwendeHartKodiert': True}, {'name': 'Nebenbetonung', 'bild': None, 'HartKodiert': 'kursiv', 'VerwendeHartKodiert': True}], 5: [{'name': 'Atempause', 'bild': 'atempause.png', 'HartKodiert': 'Linie', 'VerwendeHartKodiert': False}, {'name': 'Staupause', 'bild': 'Staupause.png', 'HartKodiert': 'Rechteck', 'VerwendeHartKodiert': False}], 6: [{'name': 'gedanken_weiter', 'bild': 'Gedanken_weiter.png', 'HartKodiert': 'Kreis', 'VerwendeHartKodiert': False}, {'name': 'gedanken_ende', 'bild': 'Gedanken_Ende.png', 'HartKodiert': 'Linie', 'VerwendeHartKodiert': False}, {'name': 'pause_gedanken', 'bild': 'Gedanken_pause.png', 'HartKodiert': 'Punkte', 'VerwendeHartKodiert': False}], 7: [{'name': 'Starten', 'bild': None, 'HartKodiert': 'ansteigende Linie', 'VerwendeHartKodiert': True}, {'name': 'Halten', 'bild': None, 'HartKodiert': 'waagrechte Linie', 'VerwendeHartKodiert': True}, {'name': 'Stoppen', 'bild': None, 'HartKodiert': 'abfallende Linie', 'VerwendeHartKodiert': True}], 8: [{'name': 'ik', 'HartKodiert': 'unterpunktet', 'bild': None, 'VerwendeHartKodiert': True}, {'name': 'ich', 'HartKodiert': 'unterstrichen', 'bild': None, 'VerwendeHartKodiert': True}], 9: [{'name': 'EinrückungsStart', 'bild': None, 'HartKodiert': 'Eingerückt', 'VerwendeHartKodiert': True}, {'name': 'EinrückungsEnde', 'bild': None, 'HartKodiert': 'nichteingerückt', 'VerwendeHartKodiert': True}, {'name': 'ZentriertStart', 'HartKodiert': 'Zentriert', 'bild': None, 'VerwendeHartKodiert': True}, {'name': 'ZentriertEnde', 'HartKodiert': 'Zentriert', 'bild': None, 'VerwendeHartKodiert': True}, {'name': 'RechtsbuendigStart', 'HartKodiert': 'Rechtsbuendig', 'bild': None, 'VerwendeHartKodiert': True}, {'name': 'RechtsbuendigEnde', 'HartKodiert': 'Rechtsbuendig', 'bild': None, 'VerwendeHartKodiert': True}]}	# Mögliche Annotationen für jede Aufgabe

# -------------------------------------------------
# Recording-UI: manuelle Annotationen
# KEINE Pipeline-/KI-Aufgaben
# -------------------------------------------------

ANNOTATIONEN = {
    "person": [
        {
            "name": None,
            "bild": None,
            "HartKodiert": "farbeJePerson",
            "VerwendeHartKodiert": True,
            "StartZeichen": "„",
            "EndeZeichen": "“",
        }
    ],
    "betonung": [
        {
            "name": "Hauptbetonung",
            "bild": None,
            "HartKodiert": "fett",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "Nebenbetonung",
            "bild": None,
            "HartKodiert": "kursiv",
            "VerwendeHartKodiert": True,
        },
    ],
    "pause": [
        {
            "name": "Atempause",
            "bild": "atempause.png",
            "HartKodiert": "Linie",
            "VerwendeHartKodiert": False,
        },
        {
            "name": "Staupause",
            "bild": "Staupause.png",
            "HartKodiert": "Rechteck",
            "VerwendeHartKodiert": False,
        },
    ],
    "gedanken": [
        {
            "name": "gedanken_weiter",
            "bild": "Gedanken_weiter.png",
            "HartKodiert": "Kreis",
            "VerwendeHartKodiert": False,
        },
        {
            "name": "gedanken_ende",
            "bild": "Gedanken_Ende.png",
            "HartKodiert": "Linie",
            "VerwendeHartKodiert": False,
        },
        {
            "name": "pause_gedanken",
            "bild": "Gedanken_pause.png",
            "HartKodiert": "Punkte",
            "VerwendeHartKodiert": False,
        },
    ],
    "spannung": [
        {
            "name": "Starten",
            "bild": None,
            "HartKodiert": "ansteigende Linie",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "Halten",
            "bild": None,
            "HartKodiert": "waagrechte Linie",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "Stoppen",
            "bild": None,
            "HartKodiert": "abfallende Linie",
            "VerwendeHartKodiert": True,
        },
    ],
    "ig": [
        {
            "name": "ik",
            "bild": None,
            "HartKodiert": "unterpunktet",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "ich",
            "bild": None,
            "HartKodiert": "unterstrichen",
            "VerwendeHartKodiert": True,
        },
    ],
    "position": [
        {
            "name": "EinrueckungsStart",
            "bild": None,
            "HartKodiert": "Eingerückt",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "EinrueckungsEnde",
            "bild": None,
            "HartKodiert": "nichteingerückt",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "ZentriertStart",
            "bild": None,
            "HartKodiert": "Zentriert",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "ZentriertEnde",
            "bild": None,
            "HartKodiert": "Zentriert",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "RechtsbuendigStart",
            "bild": None,
            "HartKodiert": "Rechtsbuendig",
            "VerwendeHartKodiert": True,
        },
        {
            "name": "RechtsbuendigEnde",
            "bild": None,
            "HartKodiert": "Rechtsbuendig",
            "VerwendeHartKodiert": True,
        },
    ],
}

ANNOTATION_SHORTCUTS = {
    "h": ("betonung", "Hauptbetonung"),
    "n": ("betonung", "Nebenbetonung"),

    "a": ("pause", "Atempause"),
    "s": ("pause", "Staupause"),

    "g": ("gedanken", "gedanken_weiter"),
    "e": ("gedanken", "gedanken_ende"),
    "p": ("gedanken", "pause_gedanken"),

    "1": ("spannung", "Starten"),
    "2": ("spannung", "Halten"),
    "3": ("spannung", "Stoppen"),

    "c": ("ig", "ich"),
    "k": ("ig", "ik"),
}

UI_SHORTCUTS = {
    "<Control-s>": {
        "label": "Strg+S",
        "description": "Speichern",
        "action": "save",
    },
    "<Control-z>": {
        "label": "Strg+Z",
        "description": "Rückgängig",
        "action": "undo",
    },
    "<Control-y>": {
        "label": "Strg+Y",
        "description": "Wiederholen",
        "action": "redo",
    },
    "<Control-Shift-Z>": {
        "label": "Strg+Shift+Z",
        "description": "Wiederholen",
        "action": "redo",
    },
    "<Left>": {
        "label": "←",
        "description": "Vorheriges Wort",
        "action": "token_prev",
    },
    "<Right>": {
        "label": "→",
        "description": "Nächstes Wort",
        "action": "token_next",
    },
    "<Up>": {
        "label": "↑",
        "description": "Zeile hoch",
        "action": "line_up",
    },
    "<Down>": {
        "label": "↓",
        "description": "Zeile runter",
        "action": "line_down",
    },

    "<Control-Left>": {
        "label": "Strg+←",
        "description": "5 Wörter zurück",
        "action": "token_prev_5",
    },
    "<Control-Right>": {
        "label": "Strg+→",
        "description": "5 Wörter vor",
        "action": "token_next_5",
    },
    "<Delete>": {
        "label": "Entf",
        "description": "Annotationen aktuelles Wort löschen",
        "action": "delete_current_annotations",
    },
    "<Alt-Left>": {
        "label": "Alt+←",
        "description": "Vorheriger Abschnitt",
        "action": "section_prev",
    },
    "<Alt-Right>": {
        "label": "Alt+→",
        "description": "Nächster Abschnitt",
        "action": "section_next",
    },
    "<Control-e>": {
        "label": "Strg+E",
        "description": "PDF exportieren",
        "action": "export_pdf",
    },
}


RECORDING_ANNOTATIONEN = {
    "person": {
        "label": "Sprecher",
        "values": "personen",
        "range_edit": True,
    },
    "betonung": {
        "label": "Betonung",
        "values": ANNOTATIONEN["betonung"],
    },
    "pause": {
        "label": "Pause",
        "values": ANNOTATIONEN["pause"],
    },
    "gedanken": {
        "label": "Gedanken",
        "values": ANNOTATIONEN["gedanken"],
    },
    "spannung": {
        "label": "Spannung",
        "values": ANNOTATIONEN["spannung"],
    },
    "ig": {
        "label": "Ich/Ik",
        "values": ANNOTATIONEN["ig"],
    },
    "position": {
        "label": "Position",
        "values": ANNOTATIONEN["position"],
    },
}



# -------------------------------------------------
# Recording-UI / Renderer: feldbasierte Annotationen
# KEINE KI-Aufgaben-IDs
# -------------------------------------------------


RECORDING_RENDER_MARKER = [
    "pause",
    "gedanken",
    "spannung",
    "ig",
]


SPRACHE = 'de'

# Annotationen für jede Aufgabe
FehlerAnzeigen = True

# Token-Begrenzungen für KI
MAX_NEW_TOKENS = 500
MAX_PROMPT_TOKENS = 2000
MAX_TOTAL_TOKENS = 4000

# Allgemeine Formatierung
EINRUECKUNGSFORMAT = ['zitat', 'schriftstücke', 'quote']
ANZAHL_ÜBERSCHRIFTENZEILEN = 2
BILDHOEHE_PX = 19
PDF_SEITENFORMAT = 'A4'
DATUMSFORMAT = '%Y-%m-%d_%H-%M-%S'



# Layout-Einstellungen
ZEICHENBREITE = 6
ZEILENHOEHE = 40
MAX_ZEILENBREITE = 540
MAX_SEITENHOEHE = 830

# Seitenränder
OBERER_SEITENRAND = 50
UNTERER_SEITENRAND = 50
LINKER_SEITENRAND = 30
RECHTER_SEITENRAND = 30
EINRUECKUNG = 40
START_X_POS = 50

# Schriftgrößen
UEBERSCHRIFT_GROESSE = 16
TEXT_GROESSE = 14
LEGENDE_GROESSE = 8

# Abstände
UEBERSCHRIFT_ABSTAND_FAKTOR = 0.5
ABSTAND_NACH_ABS = 15
ABSTANDNACHÜBERSCHRIFT = 60
TEXTZEILENABSTAND = 30
LINIENABSTAND = 2
ZEILENABSTAND = 5
SPANNUNG_NEIGUNG = 3

# Schriftarten
SCHRIFTART_STANDARD = 'Cascadia Mono'
SCHRIFTART_UEBERSCHRIFT = 'Courier New CE'
SCHRIFTART_LEGENDE = 'Source Code Pro'

# Marker-Einstellungen
MARKER_BREITE_KURZ = 4
MARKER_BREITE_LANG = 5
MARKER_OFFSET_Y = 7
MARKER_OFFSET_Y_SPANNUNG = 5
GEDANKEN_STRICHMUSTER = (8, 4)
LINIENBREITE_STANDARD = 3

# Berechnungen basierend auf Layout

# PERSONEN-ERKENNUNGSEINSTELLUNGEN
PERSONEN_QUELLE = 'yaml'	# oder kapitel_connfig.json
PERSONEN_CHAPTERS_DATEI = 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/Eingabe/chapters.yaml'
PERSONEN_CHARAKTERE_DATEI = 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/Die Organisation [EXTENDED EDITION] - vorbereitet/Eingabe/charakters.yaml'
PERSONEN_YAML_MAPPING = {'relevante_perioden': ['group_periods', 'external_periods'], 'ignorierte_perioden': ['orga_periods'], 'id_feld': 'id', 'name_feld': 'name', 'chapter_liste': 'chapters', 'subchapter_liste': 'subchapters', 'subchapter_id_feld': 'sub_id', 'subchapter_datum_feld': 'anchor_date', 'charakter_gruppen': ['children', 'internal_children', 'external_children', 'external_adults', 'internal_adults']}
FARBE_STANDARD = (25, 25, 25)
FARBE_STAUPAUSE = (204, 102, 0)
FARBE_KOMB_PAUSE = (153, 0, 153)
FARBE_GEDANKEN = (0, 0, 204)
FARBE_ATEMPAUSE = (230, 153, 51)
FARBE_UNTERSTREICHUNG = (25, 25, 25)
FARBE_SPANNUNG = (168, 213, 186)


START_Y_POS = MAX_SEITENHOEHE - OBERER_SEITENRAND  # Berechnet automatisch die Y-Position (maximale Höhe minus oberer Rand)
MAX_ZEILENANZAHL = (MAX_SEITENHOEHE - OBERER_SEITENRAND - UNTERER_SEITENRAND) // ZEILENHOEHE  # Berechnung der maximalen Zeilenanzahl
