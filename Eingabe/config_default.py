# ---------------------------------------------
# Konfigurationsdatei (config.py), automatisch generiert am 2025-05-31
# ---------------------------------------------

# Ordnerstruktur für Ein- und Ausgabe
GLOBALORDNER = {}
NUTZE_KI = True  # Schaltet alle KI-Funktionen zentral ein oder aus

# Aufgabenübersicht mit IDs und Kurzbezeichnungen
KI_AUFGABEN = {
    3: 'person',      # Personenkennung
    4: 'betonung',    # Betonung (Haupt/Neben)
    5: 'pause',       # Pausen (Atem/Stau)
    6: 'gedanken',    # Gedankenstruktur
    7: 'spannung',    # Spannungsverlauf
    8: 'ig'           # Ich/Gedanken-Erkennung
}

# Annotationen für jede Aufgabe
AUFGABEN_ANNOTATIONEN = {
    3: [{'name': None, 'bild': None, 'HartKodiert': 'farbeJePerson', 'VerwendeHartKodiert': True}],
    4: [
        {'name': 'Hauptbetonung', 'bild': None, 'HartKodiert': 'fett', 'VerwendeHartKodiert': True},
        {'name': 'Nebenbetonung', 'bild': None, 'HartKodiert': 'kursiv', 'VerwendeHartKodiert': True}
    ],
    5: [
        {'name': 'Atempause', 'bild': None, 'HartKodiert': 'Linie', 'VerwendeHartKodiert': True},
        {'name': 'Staupause', 'bild': None, 'HartKodiert': 'Rechteck', 'VerwendeHartKodiert': True}
    ],
    6: [
        {'name': 'gedanken_weiter', 'bild': None, 'HartKodiert': 'Kreis', 'VerwendeHartKodiert': True},
        {'name': 'gedanken_ende', 'bild': None, 'HartKodiert': 'Linie', 'VerwendeHartKodiert': True},
        {'name': 'pause_gedanken', 'bild': None, 'HartKodiert': 'Punkte', 'VerwendeHartKodiert': True}
    ],
    7: [
        {'name': 'Starten', 'bild': None, 'HartKodiert': 'ansteigende Linie', 'VerwendeHartKodiert': True},
        {'name': 'Halten', 'bild': None, 'HartKodiert': 'waagrechte Linie', 'VerwendeHartKodiert': True},
        {'name': 'Stoppen', 'bild': None, 'HartKodiert': 'abfallende Linie', 'VerwendeHartKodiert': True}
    ],
    8: [
        {'name': 'ik', 'HartKodiert': 'unterpunktet', 'bild': None, 'VerwendeHartKodiert': True},
        {'name': 'ich', 'HartKodiert': 'unterstrichen', 'bild': None, 'VerwendeHartKodiert': True}
    ]
}

FehlerAnzeigen = True  # Aktiviert die Anzeige von Fehlern während der Laufzeit

# Token-Begrenzungen für KI
MAX_NEW_TOKENS = 500         # Maximale neue Tokens, die generiert werden dürfen
MAX_PROMPT_TOKENS = 250     # Maximale Tokens im Prompt (Eingabe)
MAX_TOTAL_TOKENS = 1500      # Gesamtanzahl Tokens inkl. Prompt und Antwort

# Allgemeine Formatierung
ANZAHL_ÜBERSCHRIFTENZEILEN = 2   # Anzahl Zeilen für Kapitelüberschriften
BILDHOEHE_PX = 19                # Bildhöhe in Pixel
PDF_SEITENFORMAT = 'letter'      # Format der PDF-Seiten (z. B. letter, A4)
DATUMSFORMAT = '%Y-%m-%d_%H-%M-%S'  # Format für Zeitstempel

# Layout-Einstellungen
ZEICHENBREITE = 6            # Zeichenbreite für Layout-Berechnung
ZEILENHOEHE = 30             # Höhe einer Textzeile
MAX_ZEILENBREITE = 500       # Maximale Breite einer Zeile in Pixel
MAX_SEITENHOEHE = 830        # Maximale Seitenhöhe in Pixel

# Seitenränder
OBERER_SEITENRAND = 50       # Abstand oben
UNTERER_SEITENRAND = 50      # Abstand unten
LINKER_SEITENRAND = 10       # Abstand links
START_X_POS = 50             # Start-X-Position für Text

# Schriftgrößen
UEBERSCHRIFT_GROESSE = 16    # Schriftgröße für Überschriften
TEXT_GROESSE = 14            # Normale Textgröße
LEGENDE_GROESSE = 8          # Legendentextgröße

# Abstände
UEBERSCHRIFT_ABSTAND_FAKTOR = 0.5  # Faktor zur Berechnung von Überschriftenabstand
ABSTAND_NACH_ABS = 15              # Abstand nach einem Absatz
ABSTANDNACHÜBERSCHRIFT = 60        # Abstand nach einer Kapitelüberschrift
TEXTZEILENABSTAND = 30             # Abstand zwischen Textzeilen
LINIENABSTAND = 2                  # Abstand zwischen Linien
ZEILENABSTAND = 5                  # Abstand zwischen logischen Zeilen
SPANNUNG_NEIGUNG = 3               # Neigungswert für Spannungsverlauf

# Schriftarten
SCHRIFTART_STANDARD = 'Calibri'
SCHRIFTART_UEBERSCHRIFT ='Arial' 
SCHRIFTART_LEGENDE = 'Calibri'	


# Marker-Einstellungen
MARKER_BREITE_KURZ = 4       # Breite für kurze Marker
MARKER_BREITE_LANG = 5       # Breite für lange Marker
MARKER_OFFSET_Y = 7          # Vertikale Verschiebung für Marker
MARKER_OFFSET_Y_SPANNUNG = 5 # Y-Versatz bei Spannung
GEDANKEN_STRICHMUSTER = (8, 4)   # Muster für Gedankenlinien (Strich, Lücke)
LINIENBREITE_STANDARD = 1        # Standardbreite für Linien

# Farben für Annotationen
FARBE_STANDARD = (25, 25, 25)             # Standardfarbe (Text)
FARBE_STAUPAUSE = (204, 102, 0)           # Farbe für Staupausen
FARBE_KOMB_PAUSE = (153, 0, 153)          # Kombinierte Pause
FARBE_GEDANKEN = (0, 0, 204)              # Gedankenfarbe
FARBE_ATEMPAUSE = (230, 153, 51)          # Atempause
FARBE_UNTERSTREICHUNG = (25, 25, 25)      # Unterstreichungen
FARBE_SPANNUNG = (168, 213, 186)          # Spannungskurve

# Berechnungen basierend auf Layout
START_Y_POS = MAX_SEITENHOEHE - OBERER_SEITENRAND  # Start-Y-Position für Inhalte
MAX_ZEILENANZAHL = (MAX_SEITENHOEHE - OBERER_SEITENRAND - UNTERER_SEITENRAND) // ZEILENHOEHE  # Berechnet maximale Zeilenanzahl pro Seite
