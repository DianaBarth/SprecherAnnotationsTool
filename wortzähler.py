import os
import re
import tkinter as tk
from tkinter import ttk
from collections import defaultdict

# ✅ config.py einbinden
try:
    from Eingabe.config import GLOBALORDNER
except ImportError:
    raise ImportError("config.py mit GLOBALORDNER fehlt oder GLOBALORDNER ist nicht definiert.")

TEXT_DIR = GLOBALORDNER['txt']

# Tags zum Entfernen
START_TAGS = {
    "Einrueckung": "|EinrueckungStart| ",
    "Zentriert": "|ZentriertStart| ",
    "Rechtsbuendig": "|RechtsbuendigStart| ",
}
END_TAGS = {
    "Einrueckung": "|EinrueckungEnde| ",
    "Zentriert": "|ZentriertEnde| ",
    "Rechtsbuendig": "|RechtsbuendigEnde| ",
}
IGNORE_TAGS = set(START_TAGS.values()) | set(END_TAGS.values())

# Dateiname: Kapitel_123.txt
FILE_PATTERN = re.compile(r'^(.+?)_(\d{3})\.txt$')

def roman_to_int(s):
    roman_numerals = {
        'M': 1000, 'CM': 900, 'D': 500, 'CD': 400,
        'C': 100, 'XC': 90, 'L': 50, 'XL': 40,
        'X': 10, 'IX': 9, 'V': 5, 'IV': 4, 'I': 1
    }
    i = 0
    result = 0
    while i < len(s):
        if i+1 < len(s) and s[i:i+2] in roman_numerals:
            result += roman_numerals[s[i:i+2]]
            i += 2
        elif s[i] in roman_numerals:
            result += roman_numerals[s[i]]
            i += 1
        else:
            return None  # Ungültig
    return result

def chapter_sort_key(chapter_name):
    prefix = chapter_name.split("_")[0].strip()  # z. B. "IX. Kapitelname" oder "Prolog"

    # 1. Prolog ganz vorne, egal wie geschrieben
    if prefix.lower().startswith("prolog"):
        return (0, 0)

    # 2. Römische Zahl mit Punkt am Anfang (z. B. "IX. Die Zeit")
    match = re.match(r'^([IVXLCDM]+)\.', prefix.upper())
    if match:
        roman = match.group(1)
        value = roman_to_int(roman)
        if value is not None:
            return (1, value)

    # 3. Alles andere kommt danach
    return (2, prefix)

def clean_and_count_words(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    for tag in IGNORE_TAGS:
        text = text.replace(tag, "")
    return len(re.findall(r'\b\w+\b', text, flags=re.UNICODE))


def process_files(directory):
    # Kapitel → Liste von Wortzahlen in Reihenfolge des Auftretens
    chapter_files = defaultdict(list)
    max_len = 0

    for filename in sorted(os.listdir(directory)):
        match = FILE_PATTERN.match(filename)
        if match:
            chapter = match.group(1)
            path = os.path.join(directory, filename)
            count = clean_and_count_words(path)
            chapter_files[chapter].append(count)

    # Maximal notwendige Zeilenanzahl
    max_len = max(len(v) for v in chapter_files.values())

    # Kapitel sortiert nach den römischen Zahlen
    sorted_chapters = sorted(chapter_files.keys(),  key=chapter_sort_key)

    # Tabellenstruktur: Liste von Zeilen → Dict mit Kapitel: Wert
    table_rows = []
    for i in range(max_len):
        row = {}
        for chapter in sorted_chapters:
            if i < len(chapter_files[chapter]):
                row[chapter] = chapter_files[chapter][i]
            else:
                row[chapter] = ""
        table_rows.append(row)

    return table_rows, sorted_chapters, chapter_files

def export_to_txt(table_rows, chapters, chapter_files):
    import os
    export_dir = os.path.dirname(TEXT_DIR)  # eine Ebene höher als 'txt'
    filepath = os.path.join(export_dir, "wortzaehlung_export.txt")   
    
    with open(filepath, "w", encoding="utf-8") as f:
            # Kopfzeile
        f.write("Nr.\t" + "\t".join(chapters) + "\n")

        # Datenzeilen
        for idx, row in enumerate(table_rows, 1):
            zeile = [str(idx)] + [str(row[chap]) for chap in chapters]
            f.write("\t".join(zeile) + "\n")

        # Summenzeile
        summe = ["→ Summe"] + [str(sum(chapter_files[chap])) for chap in chapters]
        f.write("\t".join(summe) + "\n")

    print(f"Exportiert nach {filepath}")

def create_gui(table_rows, chapters, chapter_files):
    root = tk.Tk()
    root.title("Wortanzahl pro Datei (Kapitel = Spalten)")

    columns = ["Nr."] + chapters
    tree = ttk.Treeview(root, columns=columns, show="headings")

    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="center", width=120)

    # Datenzeilen
    for idx, row in enumerate(table_rows, 1):
        values = [idx] + [row[chapter] for chapter in chapters]
        tree.insert("", "end", values=values)

    # Summenzeile
    sum_row = ["→ Summe"]
    for chapter in chapters:
        summe = sum(chapter_files[chapter])
        sum_row.append(summe)
    tree.insert("", "end", values=sum_row, tags=("summe",))

    # Stil
    tree.tag_configure("summe", background="#ffe5cc", font=("Arial", 10, "bold"))
    tree.pack(fill=tk.BOTH, expand=True)

    # Export-Button
    export_button = tk.Button(
        root,
        text="Als TXT exportieren",
        command=lambda: export_to_txt(table_rows, chapters, chapter_files),
        bg="#d9ead3",
        font=("Arial", 10, "bold")
    )
    export_button.pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    rows, chapters, filedata = process_files(TEXT_DIR)
    create_gui(rows, chapters, filedata)
