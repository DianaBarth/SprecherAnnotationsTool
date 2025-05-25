# ---------------------------------------------

# Konfigurationsdatei (config.py), Automatisch generiert am 2025-05-24T10:53:36.947118

# ---------------------------------------------



GLOBALORDNER = {}	# Ordnerstruktur für Ein- und Ausgabe



GLOBALORDNER = {}	# Ordnerstruktur für Ein- und Ausgabe

NUTZE_KI = False	# Schaltet alle KI-Funktionen zentral ein/aus
KI_AUFGABEN = {3: 'person', 4: 'betonung', 5: 'pause', 6: 'gedanken', 7: 'spannung'}	# Aufgabenübersicht mit Aktivierungsstatus und Parametern
AUFGABEN_ANNOTATIONEN =4: [{'name': 'Hauptbetonung', 'bild': None, 'HartKodiert': 'fett', 'VerwendeHartKodiert': True}, {4: [{'name': 'Hauptbetonung', 'bild': None, 'HartKodiert': 'fett', 'VerwendeHartKodiert': True}, {'name': 'Nebenbetonung', 'bild': None, 'HartKodiert': 'kursiv', 'VerwendeHartKodiert': True}], 5: [{'name': 'Atempause', 'bild': None, 'HartKodiert': 'Linie', 'VerwendeHartKodiert': True}, {'name': 'Staupause', 'bild': None, 'HartKodiert': 'Rechteck', 'VerwendeHartKodiert': True}], 6: [{'name': 'gedanken_weiter', 'bild': None, 'HartKodiert': 'Kreis', 'VerwendeHartKodiert': True}, {'name': 'gedanken_ende', 'bild': None, 'HartKodiert': 'Linie', 'VerwendeHartKodiert': True}, {'name': 'pause_gedanken', 'bild': None, 'HartKodiert': 'Punkte', 'VerwendeHartKodiert': True}], 7: [{'name': 'Starten', 'bild': None, 'HartKodiert': 'ansteigende Linie', 'VerwendeHartKodiert': True}, {'name': 'Halten', 'bild': None, 'HartKodiert': 'waagrechte Linie', 'VerwendeHartKodiert': True}, {'name': 'Stoppen', 'bild': None, 'HartKodiert': 'abfallende Linie', 'VerwendeHartKodiert': True}]}	# Mögliche Annotationen für jede Aufgabe

# Allgemein
ANZAHL_ÜBERSCHRIFTENZEILEN = 2
BILDHOEHE_PX = 19
PDF_SEITENFORMAT = 'letter'
DATUMSFORMAT = '%Y-%m-%d_%H-%M-%S'

# Seitenlayout
ZEICHENBREITE = 6
ZEILENHOEHE = 30
MAX_ZEILENBREITE = 500
MAX_SEITENHOEHE = 830

# Seitenränder und Abstände
OBERER_SEITENRAND = 50
UNTERER_SEITENRAND = 50
LINKER_SEITENRAND = 10
START_X_POS = 50

# Schriftgrößen
UEBERSCHRIFT_GROESSE = 16
TEXT_GROESSE = 10
LEGENDE_GROESSE = 8

# Abstände
UEBERSCHRIFT_ABSTAND_FAKTOR = 0.5
ABSTAND_NACH_ABS = 15
ABSTANDNACHÜBERSCHRIFT = 60
TEXTZEILENABSTAND = 30
LINIENABSTAND = 2
ZEILENABSTAND = 5
SPANNUNG_NEIGUNG = 3

# Farben

# Schriftarten
SCHRIFTART_STANDARD = 'Consolas'	# Schriftart für normalen Text 
SCHRIFTART_BETONUNG_HAUPT = 'Cascadia Mono SemiBold'	# Schriftart für Hauptbetonung 
SCHRIFTART_BETONUNG_NEBEN = 'Source Code Pro Black'	# Schriftart für Nebenbetonung 
SCHRIFTART_UEBERSCHRIFT = 'Courier New'	# Schriftart für Überschrift 
SCHRIFTART_UEBERSCHRIFT_HAUPT = 'Cascadia Code ExtraLight'	# Schriftart für Hauptüberschrift
SCHRIFTART_UEBERSCHRIFT_NEBEN = 'Courier New TUR'	# Schriftart für Nebenüberschrift
SCHRIFTART_LEGENDE = 'Source Code Pro Black'	# Schriftart für Überschrift 
SCHRIFTART_LEGENDE_HAUPT = 'Cascadia Mono SemiBold'	# Schriftart für Hauptüberschrift 
SCHRIFTART_LEGENDE_NEBEN = 'Cascadia Mono'	# Schriftart für Nebenüberschrift 

# Zeichenabstände für Marker
MARKER_BREITE_KURZ = 4
MARKER_BREITE_LANG = 5
MARKER_OFFSET_Y = 7
MARKER_OFFSET_Y_SPANNUNG = 5
GEDANKEN_STRICHMUSTER = (1, 2)
LINIENBREITE_STANDARD = 1

START_Y_POS = MAX_SEITENHOEHE - OBERER_SEITENRAND  # Berechnet automatisch die Y-Position (maximale Höhe minus oberer Rand)
MAX_ZEILENANZAHL = (MAX_SEITENHOEHE - OBERER_SEITENRAND - UNTERER_SEITENRAND) // ZEILENHOEHE  # Berechnung der maximalen Zeilenanzahl

#FARBEN
FARBE_STANDARD = (25, 25, 25)
FARBE_STAUPAUSE = (204, 102, 0)
FARBE_KOMB_PAUSE = (153, 0, 153)
FARBE_GEDANKENPAUSE = (0, 0, 204)
FARBE_ATEMPAUSE = (230, 153, 51)
FARBE_GEDANKENWEITER = (128, 128, 128)
FARBE_GEDANKENENDE = (128, 128, 128)
FARBE_UNTERSTREICHUNG = (25, 25, 25)
FARBE_SPANNUNG = (168, 213, 186)
