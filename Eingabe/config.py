# ---------------------------------------------
# Konfigurationsdatei (config.py), Automatisch generiert am 2025-06-02T21:13:42.313866
# ---------------------------------------------

GLOBALORDNER = {'Eingabe': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/Eingabe', 'txt': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/txt', 'json': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/json', 'saetze': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/saetze', 'ki': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/ki', 'merge': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/merge', 'pdf': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/pdf', 'manuell': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/manuell', 'pdf2': 'G:/Dokumente/DianaBuch_FinisPostPortam/Buch/VersionBuch2025/testdaten annotationstool/Annotationstoolergebnisse/die Organisation_FinisPostPortam_mod/pdf2'}	# Ordnerstruktur für Ein- und Ausgabe

NUTZE_KI = True	# Schaltet alle KI-Funktionen zentral ein/aus
KI_AUFGABEN = {3: 'person', 4: 'betonung', 5: 'pause', 6: 'gedanken', 7: 'spannung', 8: 'ig', 9: 'position'}	# Aufgabenübersicht mit Aktivierungsstatus und Parametern
AUFGABEN_ANNOTATIONEN = {3: [{'name': None, 'bild': None, 'HartKodiert': 'farbeJePerson', 'VerwendeHartKodiert': True}], 4: [{'name': 'Hauptbetonung', 'bild': None, 'HartKodiert': 'fett', 'VerwendeHartKodiert': True}, {'name': 'Nebenbetonung', 'bild': None, 'HartKodiert': 'kursiv', 'VerwendeHartKodiert': True}], 5: [{'name': 'Atempause', 'bild': 'atempause.png', 'HartKodiert': 'Linie', 'VerwendeHartKodiert': False}, {'name': 'Staupause', 'bild': 'Staupause.png', 'HartKodiert': 'Rechteck', 'VerwendeHartKodiert': False}], 6: [{'name': 'gedanken_weiter', 'bild': 'Gedanken_weiter2.png', 'HartKodiert': 'Kreis', 'VerwendeHartKodiert': False}, {'name': 'gedanken_ende', 'bild': 'Gedanken_Ende2.png', 'HartKodiert': 'Linie', 'VerwendeHartKodiert': False}, {'name': 'pause_gedanken', 'bild': 'Gedanken_pause2.png', 'HartKodiert': 'Punkte', 'VerwendeHartKodiert': False}], 7: [{'name': 'Starten', 'bild': None, 'HartKodiert': 'ansteigende Linie', 'VerwendeHartKodiert': True}, {'name': 'Halten', 'bild': None, 'HartKodiert': 'waagrechte Linie', 'VerwendeHartKodiert': True}, {'name': 'Stoppen', 'bild': None, 'HartKodiert': 'abfallende Linie', 'VerwendeHartKodiert': True}], 8: [{'name': 'ik', 'HartKodiert': 'unterpunktet', 'bild': None, 'VerwendeHartKodiert': True}, {'name': 'ich', 'HartKodiert': 'unterstrichen', 'bild': None, 'VerwendeHartKodiert': True}], 9: [{'name': 'EinrueckungsStart', 'bild': None, 'HartKodiert': 'Eingerueckt', 'VerwendeHartKodiert': True}, {'name': 'EinrueckungsEnde', 'bild': None, 'HartKodiert': 'nichteingerueckt', 'VerwendeHartKodiert': True}, {'name': 'ZentriertStart', 'HartKodiert': 'Zentriert', 'bild': None, 'VerwendeHartKodiert': True}, {'name': 'ZentriertEnde', 'HartKodiert': 'Zentriert', 'bild': None, 'VerwendeHartKodiert': True}, {'name': 'RechtsbuendigStart', 'HartKodiert': 'Rechtsbuendig', 'bild': None, 'VerwendeHartKodiert': True}, {'name': 'RechtsbuendigEnde', 'HartKodiert': 'Rechtsbuendig', 'bild': None, 'VerwendeHartKodiert': True}]}	# Mögliche Annotationen für jede Aufgabe

# Annotationen für jede Aufgabe
FehlerAnzeigen = True

# Token-Begrenzungen für KI
MAX_NEW_TOKENS = 500
MAX_PROMPT_TOKENS = 250
MAX_TOTAL_TOKENS = 1500

# Allgemeine Formatierung
ANZAHL_ÜBERSCHRIFTENZEILEN = 2
BILDHOEHE_PX = 19
PDF_SEITENFORMAT = 'letter'
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
SCHRIFTART_STANDARD = 'Calibri'
SCHRIFTART_UEBERSCHRIFT ='Arial' 
SCHRIFTART_LEGENDE = 'Calibri'	

# Marker-Einstellungen
MARKER_BREITE_KURZ = 4
MARKER_BREITE_LANG = 5
MARKER_OFFSET_Y = 7
MARKER_OFFSET_Y_SPANNUNG = 5
GEDANKEN_STRICHMUSTER = (8, 4)
LINIENBREITE_STANDARD = 3

# Berechnungen basierend auf Layout
FARBE_STANDARD = (25, 25, 25)
FARBE_STAUPAUSE = (204, 102, 0)
FARBE_KOMB_PAUSE = (153, 0, 153)
FARBE_GEDANKEN = (0, 0, 204)
FARBE_ATEMPAUSE = (230, 153, 51)
FARBE_UNTERSTREICHUNG = (25, 25, 25)
FARBE_SPANNUNG = (168, 213, 186)


START_Y_POS = MAX_SEITENHOEHE - OBERER_SEITENRAND  # Berechnet automatisch die Y-Position (maximale Höhe minus oberer Rand)
MAX_ZEILENANZAHL = (MAX_SEITENHOEHE - OBERER_SEITENRAND - UNTERER_SEITENRAND) // ZEILENHOEHE  # Berechnung der maximalen Zeilenanzahl
