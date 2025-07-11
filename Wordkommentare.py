import json
import os
import re
import time
import itertools
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree
import unicodedata
import csv
from Eingabe import config

w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

def normalisiere(text):
    """
    Entfernt Sonderzeichen, ersetzt Bindestriche, normalisiert Unicode, reduziert Whitespace.
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("\u00A0", " ")     # geschütztes Leerzeichen
    text = text.replace("–", "-")          # Gedankenstrich
    text = text.replace("—", "-")          # Geviertstrich
    text = text.replace("‐", "-")          # weicher Bindestrich
    text = re.sub(r'\s+', ' ', text)       # Mehrfach-Whitespace
    return text.strip().lower()


def get_comments_part(part):
    for rel in part.rels.values():
        if rel.reltype == RT.COMMENTS:
            print("🔍 comments.xml gefunden.")
            return rel._target

    print("⚠️ Kein comments.xml gefunden, wird neu angelegt.")
    package = part.package
    partname = PackURI("/word/comments.xml")
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
    empty_comments_xml = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
    )
    comments_part = package.create_part(partname, content_type, empty_comments_xml)
    part.relate_to(comments_part, RT.COMMENTS)
    print("✅ comments.xml neu erstellt und verbunden.")
    return comments_part

def add_comment(paragraph, text, author="Auto", initials="AU"):
    if paragraph is None:
        print("⚠️ Kein Absatz zum Kommentieren vorhanden.")
        return

    part = paragraph.part
    comments_part = get_comments_part(part)
    if comments_part is None:
        print("⚠️ Keine comments.xml vorhanden.")
        return

    root = etree.fromstring(comments_part.blob)

    existing_ids = [int(c.get(qn("w:id"))) for c in root.findall(f'{{{w_ns}}}comment') if c.get(qn("w:id"))]
    new_id = max(existing_ids, default=0) + 1

    comment = OxmlElement('w:comment')
    comment.set(qn('w:id'), str(new_id))
    comment.set(qn('w:author'), author)
    comment.set(qn('w:initials'), initials)
    p = OxmlElement('w:p')
    r = OxmlElement('w:r')
    t = OxmlElement('w:t')
    t.text = text
    r.append(t)
    p.append(r)
    comment.append(p)
    root.append(comment)

    comment_range_start = OxmlElement('w:commentRangeStart')
    comment_range_start.set(qn('w:id'), str(new_id))
    comment_range_end = OxmlElement('w:commentRangeEnd')
    comment_range_end.set(qn('w:id'), str(new_id))
    comment_reference = OxmlElement('w:r')
    comment_reference_run = OxmlElement('w:commentReference')
    comment_reference_run.set(qn('w:id'), str(new_id))
    comment_reference.append(comment_reference_run)

    p = paragraph._p
    p.insert(0, comment_range_start)
    p.append(comment_range_end)
    p.append(comment_reference)

    comments_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    print(f"✅ Kommentar mit ID={new_id} erfolgreich hinzugefügt.")

def entferne_spezifische_kommentare(doc):
    comments_part = get_comments_part(doc.part)
    root = etree.fromstring(comments_part.blob)

    to_remove = []
    for c in root.findall(f'{{{w_ns}}}comment'):
        text = ''.join([t.text for t in c.findall(f'.//{{{w_ns}}}t') if t.text])
        if re.match(r'\[[^\]]+\.\d+\]', text):
            print(f"🗑 Entferne Kommentar mit Text: '{text}'")
            to_remove.append(c)
    for c in to_remove:
        root.remove(c)

    comments_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    print(f"✅ {len(to_remove)} Kommentare entfernt.")

def verarbeite_kapitel(doc, kapitel_config):
    kapitel_liste = kapitel_config["kapitel_liste"]
    kapitel_trenner = kapitel_config["Kapitel_trenner"]

    aktuelles_kapitel_text = None
    unterkapitel_nr = 1
    wort_zaehler = 0
    start_absatz = None

    absatz_iter = iter(doc.paragraphs)

    for absatz in absatz_iter:
        text = absatz.text.strip()

        # Kapitelanfang erkannt
        if text in kapitel_liste:
            # Vorherigen Kommentar setzen, falls offen
            if aktuelles_kapitel_text is not None and start_absatz is not None:
                kommentar_text = f"[{aktuelles_kapitel_text}.{unterkapitel_nr}] mit {wort_zaehler} Wörtern"
                add_comment(start_absatz, kommentar_text)
                print(f"💬 Kommentar gesetzt für Kapitel '{aktuelles_kapitel_text}': {kommentar_text}")

            aktuelles_kapitel_text = text
            unterkapitel_nr = 1
            wort_zaehler = 0
            start_absatz = absatz
            continue

        # Kapiteltrenner erkannt
        if text == kapitel_trenner and aktuelles_kapitel_text is not None:
            kommentar_text = f"[{aktuelles_kapitel_text}.{unterkapitel_nr}] mit {wort_zaehler} Wörtern"
            add_comment(start_absatz, kommentar_text)
            print(f"💬 Kommentar gesetzt für Unterkapitel '{aktuelles_kapitel_text}.{unterkapitel_nr}': {kommentar_text}")

            unterkapitel_nr += 1
            wort_zaehler = 0
            start_absatz = absatz  # jetzt trenner als Startabsatz fürs nächste Unterkapitel
            continue

        # Innerhalb Kapitel Wörter zählen
        if aktuelles_kapitel_text is not None:
            wort_zaehler += len(text.split())

    # Am Ende letzten Kommentar setzen, falls offen
    if aktuelles_kapitel_text is not None and start_absatz is not None:
        kommentar_text = f"[{aktuelles_kapitel_text}.{unterkapitel_nr}] mit {wort_zaehler} Wörtern (final)"
        add_comment(start_absatz, kommentar_text)
        print(f"💬 Letzter Kommentar für Kapitel '{aktuelles_kapitel_text}': {kommentar_text}")


def ist_datei_gesperrt(pfad):
    try:
        with open(pfad, 'a'):
            return False
    except PermissionError:
        return True

# --- Hauptausführung ---
GLOBALORDNER = config.GLOBALORDNER
eingabe_ordner = GLOBALORDNER['Eingabe']
parent_ordner = os.path.dirname(eingabe_ordner)
kapitel_config_path = os.path.join(parent_ordner, "kapitel_config.json")

projekt_root = os.path.abspath(os.path.join(eingabe_ordner, "..", ".."))
projektname = os.path.basename(parent_ordner)
docx_path = os.path.join(os.path.dirname(projekt_root), f"{projektname}.docx")

with open(kapitel_config_path, "r", encoding="utf-8") as f:
    kapitel_config = json.load(f)

print(f"📄 Öffne Dokument: {docx_path}")
doc = Document(docx_path)
entferne_spezifische_kommentare(doc)
verarbeite_kapitel(doc, kapitel_config)

zielpfad = docx_path.replace(".docx", "_kommentiert.docx")

max_versuche = 3
for versuch in range(max_versuche):
    if ist_datei_gesperrt(zielpfad):
        print(f"⛔ Datei '{zielpfad}' ist geöffnet. Bitte schließen und mit [Enter] bestätigen.")
        input()
        time.sleep(1)
    else:
        try:
            doc.save(zielpfad)
            print(f"✅ Fertig: Datei mit Kommentaren gespeichert:\n{zielpfad}")
        except Exception as e:
            print(f"❌ Fehler beim Speichern: {e}")
        break
else:
    print("❌ Datei konnte nach mehreren Versuchen nicht gespeichert werden. Bitte manuell schließen.")
