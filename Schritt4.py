import os
import re
import gc
import json
import traceback
import regex
from collections import Counter
from pathlib import Path
import unicodedata
import Eingabe.config as config
from KI_Analyse_Flat import baue_ki_prompt, lade_json_zu_txt_datei, splitte_in_abschnitte_intelligent  
import personen_resolver

MODEL_NAME = ""  # Wird später durch GUI gesetzt/überschrieben
IG_ANALYSE_IN_DIESEM_LAUF_ERLEDIGT = False

def KI_Analyse_Chat(client, messages, dateiname="", wortnr_bereich="", max_new_tokens=128):
    try:
        system_text = ""
        user_text = ""

        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"].strip() + "\n"
            elif msg["role"] == "user":
                user_text += msg["content"].strip() + "\n"

        prompt = client.build_prompt(system_text, user_text)

        print("[INFO] Anfrage an lokales Modell über HuggingFaceClient STREAM …")

        def on_token(piece):
            print(piece, end="", flush=True)

        content = client.generate_stream(
            prompt,
            on_token=on_token,
            max_new_tokens=max_new_tokens,
            hard_cap=max_new_tokens,
            temperature=0.0,
        )

        print("\n[INFO] Stream abgeschlossen.")

        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        if dateiname and wortnr_bereich:
            log_antwort(dateiname, wortnr_bereich, content)

        return content

    except Exception as e:
        print(f"[FEHLER] KI-Anfrage fehlgeschlagen: {e}")
        traceback.print_exc()        
        return None 
    
def KI_Analyse_Flat(client, prompt_text, dateiname="", wortnr_bereich="", max_new_tokens=128):
    try:
        print("[INFO] Anfrage an lokales Modell über HuggingFaceClient STREAM …")

        def on_token(piece):
            print(piece, end="", flush=True)

        content = client.generate_stream(
            prompt_text,
            on_token=on_token,
            max_new_tokens=max_new_tokens,
            hard_cap=max_new_tokens,
            temperature=0.0,
        )

        print("\n[INFO] Stream abgeschlossen.")

        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        if dateiname and wortnr_bereich:
            log_antwort(dateiname, wortnr_bereich, content)

        return content

    except Exception as e:
        print(f"[FEHLER] KI-Anfrage fehlgeschlagen: {e}")
        traceback.print_exc()
        return None


def daten_verarbeiten(client, prompt, dateipfad, ki_ordner, aufgabe, force=False):
    print(f"[DEBUG] schritt4.daten_verarbeiten gestartet für {dateipfad} und {aufgabe}")
    ki_ordner = Path(ki_ordner)

    try:
        if not isinstance(dateipfad, str):
            raise ValueError(f"Unerwarteter Dateipfad: {dateipfad}")

        aufgaben_name = config.KI_AUFGABEN.get(aufgabe, f"unbekannt{aufgabe}")
        aufgaben_name_lower = str(aufgaben_name).lower()

        ist_ig_aufgabe = aufgaben_name_lower == "ig"
        ist_person_aufgabe = aufgaben_name_lower == "person"

        max_tokens_by_task = {
            "kombination": 512,
            "person": 384,
            "ig": 512,
        }
        antwort_max_new_tokens = max_tokens_by_task.get(aufgaben_name_lower, 128)

        # ----------------------------------------------------
        # Person: Sprecherliste injizieren
        # ----------------------------------------------------
        if ist_person_aufgabe and "{SPRECHER_LISTE_HIER_EINFÜGEN}" in prompt:
            try:
                json_datei_fuer_personen = lade_json_zu_txt_datei(dateipfad)

                personen = personen_resolver.lade_personen_fuer_datei_ohne_kapitel_config(
                    dateipfad=str(json_datei_fuer_personen or dateipfad)
                )
                sprecher_liste_text = personen_resolver.formatiere_personen_fuer_prompt(personen)

                prompt = prompt.replace(
                    "{SPRECHER_LISTE_HIER_EINFÜGEN}",
                    sprecher_liste_text
                )

                print(f"[INFO] Sprecherliste injiziert: {sprecher_liste_text}")

            except Exception as e:
                print(f"[WARNUNG] Sprecherliste konnte nicht injiziert werden: {e}")
                prompt = prompt.replace(
                    "{SPRECHER_LISTE_HIER_EINFÜGEN}",
                    "Keine bekannten Sprecher"
                )

        # ----------------------------------------------------
        # Ergebnisdatei bestimmen
        # ----------------------------------------------------
        if ist_ig_aufgabe:
            result_file_name = "ig_wortliste.txt"
        else:
            result_file_name = f"{aufgaben_name}_{os.path.basename(dateipfad)}"

        result_file_path = ki_ordner / result_file_name

        # ----------------------------------------------------
        # IG: Wortliste erzeugen
        # ----------------------------------------------------
        if ist_ig_aufgabe:
            ig_woerter_datei = ki_ordner / "ig_woerter.txt"

            print("[INFO] Erzeuge IG-Wortliste aus JSON-Dateien ...")

            extrahiere_ig_woerter_aus_json(
                json_ordner=config.GLOBALORDNER["json"],
                ausgabe_datei=ig_woerter_datei,
                lowercase=True,
                min_len=2,
                verwende_tokenInklZahlwoerter=True,
            )

            if not ig_woerter_datei.exists():
                print(f"[FEHLER] IG-Wortliste wurde nicht erzeugt: {ig_woerter_datei}")
                return

        # ----------------------------------------------------
        # Vorhandenes Ergebnis überspringen
        # ----------------------------------------------------
        if result_file_path.exists() and not force:
            print(f"[INFO] Ergebnisdatei {result_file_path} existiert bereits. KI-Analyse wird übersprungen.")

            if ist_ig_aufgabe:
                splitte_ig_klassen(result_file_path, ki_ordner)

            return

        ki_ergebnis = ""

        # ====================================================
        # IG-SPEZIALFALL
        # ====================================================
        if ist_ig_aufgabe:
            with open(ig_woerter_datei, "r", encoding="utf-8") as f:
                eingabetext = f.read()

            if not eingabetext.strip():
                print("[WARNUNG] IG-Wortliste ist leer. IG-Analyse wird übersprungen.")
                return

            print(f"[INFO] Verwende IG-Wortliste statt Kapiteltext: {ig_woerter_datei}")

            zeilen = [z for z in eingabetext.splitlines() if z.strip()]
            chunk_groesse = 100
            chunks = [zeilen[i:i + chunk_groesse] for i in range(0, len(zeilen), chunk_groesse)]

            print(f"[INFO] IG-Wortliste enthält {len(zeilen)} Zeilen.")
            print(f"[INFO] Verarbeite IG in {len(chunks)} Chunk(s) à maximal {chunk_groesse} Wörter.")

            alle_antworten = []

            for chunk_nr, chunk in enumerate(chunks, start=1):
                chunk_text = "\n".join(chunk)

                print(f"[INFO] IG-Chunk {chunk_nr}/{len(chunks)} mit {len(chunk)} Zeilen")

                messages_Chat = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": chunk_text}
                ]

                messages_Flat = f"Anweisung:\n{prompt}\n{chunk_text}"

                if client.check_chat_model():
                    antwort = KI_Analyse_Chat(
                        client,
                        messages_Chat,
                        dateiname=os.path.basename(dateipfad),
                        wortnr_bereich=f"ig_chunk_{chunk_nr:03}",
                        max_new_tokens=antwort_max_new_tokens,
                    )
                else:
                    antwort = KI_Analyse_Flat(
                        client,
                        messages_Flat,
                        dateiname=os.path.basename(dateipfad),
                        wortnr_bereich=f"ig_chunk_{chunk_nr:03}",
                        max_new_tokens=antwort_max_new_tokens,
                    )

                if antwort:
                    alle_antworten.append(antwort.strip())
                else:
                    print(f"[WARNUNG] Keine Antwort für IG-Chunk {chunk_nr}")

            ki_ergebnis = "\n".join(alle_antworten).strip()

        # ====================================================
        # NORMALE AUFGABEN: person / kombination / ältere Tasks
        # ====================================================
        else:
            json_datei = lade_json_zu_txt_datei(dateipfad)

            # ------------------------------------------------
            # Fallback: keine JSON-Datei gefunden
            # ------------------------------------------------
            if not json_datei or not json_datei.exists():
                print(f"[WARNUNG] Keine passende JSON-Datei gefunden. Fallback auf TXT: {dateipfad}")

                with open(dateipfad, "r", encoding="utf-8") as f:
                    eingabetext = f.read()

                messages_Chat = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": eingabetext}
                ]

                messages_Flat = f"Anweisung:\n{prompt}\n\n{eingabetext}"

                if client.check_chat_model():
                    ki_ergebnis = KI_Analyse_Chat(
                        client,
                        messages_Chat,
                        dateiname=os.path.basename(dateipfad),
                        wortnr_bereich="",
                        max_new_tokens=antwort_max_new_tokens,
                    )
                else:
                    ki_ergebnis = KI_Analyse_Flat(
                        client,
                        messages_Flat,
                        dateiname=os.path.basename(dateipfad),
                        wortnr_bereich="",
                        max_new_tokens=antwort_max_new_tokens,
                    )

            # ------------------------------------------------
            # JSON-Datei vorhanden
            # ------------------------------------------------
            else:
                print(f"[INFO] Verwende JSON + Plaintext-Kontext: {json_datei}")

                with open(json_datei, "r", encoding="utf-8") as f:
                    json_daten = json.load(f)

                # --------------------------------------------
                # Fallback: JSON ist keine Liste
                # --------------------------------------------
                if not isinstance(json_daten, list):
                    print(f"[WARNUNG] JSON ist keine Liste. Fallback auf TXT: {json_datei}")

                    with open(dateipfad, "r", encoding="utf-8") as f:
                        eingabetext = f.read()

                    messages_Chat = [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": eingabetext}
                    ]

                    messages_Flat = f"Anweisung:\n{prompt}\n\n{eingabetext}"

                    if client.check_chat_model():
                        ki_ergebnis = KI_Analyse_Chat(
                            client,
                            messages_Chat,
                            dateiname=os.path.basename(dateipfad),
                            wortnr_bereich="",
                            max_new_tokens=antwort_max_new_tokens,
                        )
                    else:
                        ki_ergebnis = KI_Analyse_Flat(
                            client,
                            messages_Flat,
                            dateiname=os.path.basename(dateipfad),
                            wortnr_bereich="",
                            max_new_tokens=antwort_max_new_tokens,
                        )

                # --------------------------------------------
                # Normalfall: JSON-Liste in Abschnitte splitten
                # --------------------------------------------
                else:
                    abschnitte = splitte_in_abschnitte_intelligent(json_daten)

                    # PERSON-GUARD: Kapitel ohne Dialog überspringen
                    if ist_person_aufgabe:
                        hat_dialog = False

                        for eintrag in json_daten:
                            token = (
                                eintrag.get("tokenInklZahlwoerter")
                                or eintrag.get("token")
                                or ""
                            )

                            if any(q in token for q in ['"', '„', '“', '‚', '‘']):
                                hat_dialog = True
                                break

                        if not hat_dialog:
                            print(f"[INFO] Keine Anführungszeichen in {dateipfad} → überspringe Person-Analyse.")
                            return

                    if abschnitte is None:
                        print("[WARNUNG] splitte_in_abschnitte_intelligent() gab None zurück. Fallback: leer.")
                        abschnitte = []

                    if not isinstance(abschnitte, list):
                        raise TypeError(
                            f"splitte_in_abschnitte_intelligent() muss list zurückgeben, "
                            f"gab aber {type(abschnitte).__name__}"
                        )

                    if not abschnitte:
                        print(f"[WARNUNG] Keine Abschnitte erzeugt für {dateipfad}. KI-Analyse wird übersprungen.")
                        return

                    print(f"[INFO] Verarbeite {len(abschnitte)} Abschnitt(e) mit Plaintext + WortNr-Mapping.")

                    alle_antworten = []

                    for abschnitt_nr, abschnitt in enumerate(abschnitte, start=1):

                        # PERSON-GUARD: Abschnitt ohne Dialog überspringen
                        if ist_person_aufgabe:
                            tokens = abschnitt.get("tokens", [])

                            hat_dialog = any(
                                any(
                                    q in str(
                                        t.get("tokenInklZahlwoerter")
                                        or t.get("token")
                                        or ""
                                    )
                                    for q in ['"', '„', '“', '‚', '‘']
                                )
                                for t in tokens
                            )

                            if not hat_dialog:
                                print(f"[INFO] Abschnitt {abschnitt_nr} ohne Dialog → übersprungen.")
                                continue

                        kompakt = aufgaben_name_lower in {
                            "pause",
                            "gedanken",
                            "betonung",
                            "spannung",
                            "kombination",
                        }

                        abschnitt_prompt = baue_ki_prompt(
                            abschnitt_text=abschnitt["text"],
                            tokens=abschnitt["tokens"],
                            aufgabe_prompt=None,
                            kompakt=kompakt
                        )

                        print(f"[DEBUG][Prompt] kompakt={kompakt} | Aufgabe={aufgaben_name}")

                        start_wortnr = int(abschnitt.get("start_wortnr", 0))
                        end_wortnr = int(abschnitt.get("end_wortnr", 0))
                        wortnr_bereich = f"{start_wortnr}-{end_wortnr}"

                        print(
                            f"[INFO] Abschnitt {abschnitt_nr}/{len(abschnitte)} "
                            f"WortNr {wortnr_bereich}"
                        )

                        messages_Chat = [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": abschnitt_prompt}
                        ]

                        messages_Flat = (
                            f"Anweisung:\n{prompt}\n\n"
                            f"{abschnitt_prompt}"
                        )

                        if client.check_chat_model():
                            antwort = KI_Analyse_Chat(
                                client,
                                messages_Chat,
                                dateiname=os.path.basename(dateipfad),
                                wortnr_bereich=wortnr_bereich,
                                max_new_tokens=antwort_max_new_tokens,
                            )
                        else:
                            antwort = KI_Analyse_Flat(
                                client,
                                messages_Flat,
                                dateiname=os.path.basename(dateipfad),
                                wortnr_bereich=wortnr_bereich,
                                max_new_tokens=antwort_max_new_tokens,
                            )

                        if antwort:
                            # Alte Einzelaufgaben optional filtern
                            if aufgaben_name_lower == "betonung":
                                antwort = filtere_wortnr_json(
                                    antwort,
                                    erlaubte_keys=["hauptbetonung", "nebenbetonung"],
                                    start_wortnr=start_wortnr,
                                    end_wortnr=end_wortnr,
                                    max_pro_key=5,
                                )

                            elif aufgaben_name_lower == "pause":
                                antwort = filtere_wortnr_json(
                                    antwort,
                                    erlaubte_keys=["atempause", "staupause"],
                                    start_wortnr=start_wortnr,
                                    end_wortnr=end_wortnr,
                                    max_pro_key=8,
                                )

                            elif aufgaben_name_lower == "gedanken":
                                antwort = filtere_wortnr_json(
                                    antwort,
                                    erlaubte_keys=["gedanken_weiter", "gedanken_ende", "pause_gedanken"],
                                    start_wortnr=start_wortnr,
                                    end_wortnr=end_wortnr,
                                    max_pro_key=8,
                                )

                            elif aufgaben_name_lower == "spannung":
                                antwort = filtere_wortnr_json(
                                    antwort,
                                    erlaubte_keys=["Starten", "Halten", "Stoppen"],
                                    start_wortnr=start_wortnr,
                                    end_wortnr=end_wortnr,
                                    max_pro_key=5,
                                )

                            if antwort:
                                alle_antworten.append(antwort.strip())
                            else:
                                print(f"[WARNUNG] Antwort für Abschnitt {abschnitt_nr} wurde weggefiltert.")
                        else:
                            print(f"[WARNUNG] Keine Antwort für Abschnitt {abschnitt_nr}")

                    if aufgaben_name_lower == "kombination":
                        ki_ergebnis = merge_kombi_antworten(alle_antworten)
                    else:
                        ki_ergebnis = "\n".join(alle_antworten).strip()

        # ----------------------------------------------------
        # Ergebnis speichern
        # ----------------------------------------------------
        if ki_ergebnis:
            print("KI Roh-Ausgabe:\n", ki_ergebnis)

            antwort_log_datei = ki_ordner / f"{aufgaben_name}_KIAntwort.txt"
            with open(antwort_log_datei, "a", encoding="utf-8") as f:
                f.write(ki_ergebnis + "\n\n")

            with open(result_file_path, "w", encoding="utf-8") as result_file:
                result_file.write(ki_ergebnis)

            print(f"[INFO] Ergebnis gespeichert unter: {result_file_path}")

            if ist_ig_aufgabe:
                splitte_ig_klassen(result_file_path, ki_ordner)
        else:
            print("[WARNUNG] Kein KI-Ergebnis erhalten.")

    except Exception as e:
        print(f"[FEHLER] Fehler bei der Verarbeitung von {dateipfad}: {e}")
        traceback.print_exc()

    finally:
        gc.collect()

def log_antwort(dateiname, wortnr_bereich, content):
    try:
        print(
            f"[KI-ANTWORT] Datei={dateiname} | Bereich={wortnr_bereich}\n{content}\n"
        )
    except Exception as e:
        print(f"[WARNUNG] Konnte KI-Antwort nicht loggen: {e}")

def extrahiere_json_objekt(text):
    if not text:
        return None

    start = text.find("{")
    ende = text.rfind("}")

    if start == -1 or ende == -1 or ende <= start:
        return None

    try:
        return json.loads(text[start:ende + 1])
    except Exception:
        return None


def filtere_wortnr_json(antwort_text, erlaubte_keys, start_wortnr, end_wortnr, max_pro_key=None):
    daten = extrahiere_json_objekt(antwort_text)

    if not isinstance(daten, dict):
        print("[WARNUNG][KI-JSON] Antwort ist kein gültiges JSON-Objekt.")
        return None

    bereinigt = {}

    for key in erlaubte_keys:
        werte = daten.get(key, [])

        if not isinstance(werte, list):
            werte = []

        gefiltert = []

        for nr in werte:
            try:
                nr_int = int(nr)
            except Exception:
                continue

            if start_wortnr <= nr_int <= end_wortnr:
                if nr_int not in gefiltert:
                    gefiltert.append(nr_int)
            else:
                print(
                    f"[WARNUNG][KI-JSON] Entferne WortNr außerhalb Abschnitt: "
                    f"{nr_int} nicht in {start_wortnr}-{end_wortnr}"
                )

        if max_pro_key is not None:
            gefiltert = gefiltert[:max_pro_key]

        bereinigt[key] = gefiltert

    return json.dumps(bereinigt, ensure_ascii=False, indent=2)   

def normalisiere_ig_token(token, lowercase=True):
    """
    Vereinheitlicht Token für IG-Listen:
    - trimmt Leerzeichen
    - optional alles klein
    - Unicode normalisieren
    """
    token = (token or "").strip()
    token = unicodedata.normalize("NFC", token)

    if lowercase:
        token = token.lower()

    return token

import re
from pathlib import Path

def splitte_ig_klassen(eingabe_datei, ki_ordner):
    ik_set = set()
    ich_set = set()
    kein_set = set()
    sonder_set = set()

    def ist_mehrfach_klasse(klasse):
        return re.fullmatch(r"(ik|ich)(-(ik|ich))+", klasse) is not None

    with open(eingabe_datei, "r", encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile:
                continue

            teile = zeile.split("\t")
            if len(teile) < 2:
                continue

            wort = teile[0].strip().lower()
            klasse = teile[1].strip().lower()

            # Normalisieren
            klasse = (
                klasse
                .replace("ig_ich", "ig-ich")
                .replace("ig/ich", "ig-ich")
                .replace("ig ich", "ig-ich")
            )

            # 🔥 NEUE LOGIK
            if ist_mehrfach_klasse(klasse):
                sonder_set.add(f"{wort}\t{klasse}")
                continue

            if klasse == "ik":
                ik_set.add(wort)
            elif klasse == "ich":
                ich_set.add(wort)
            elif klasse == "kein":
                kein_set.add(wort)
            else:
                kein_set.add(wort)

    # Dateien schreiben
    with open(Path(ki_ordner) / "ik_aussprache.txt", "w", encoding="utf-8") as f:
        for w in sorted(ik_set):
            f.write(w + "\n")

    with open(Path(ki_ordner) / "ich_aussprache.txt", "w", encoding="utf-8") as f:
        for w in sorted(ich_set):
            f.write(w + "\n")

    with open(Path(ki_ordner) / "kein_ig.txt", "w", encoding="utf-8") as f:
        for w in sorted(kein_set):
            f.write(w + "\n")

    with open(Path(ki_ordner) / "ig_sonderfälle.txt", "w", encoding="utf-8") as f:
        for eintrag in sorted(sonder_set):
            f.write(eintrag + "\n")

    print(f"[INFO] ik-Wörter: {len(ik_set)}")
    print(f"[INFO] ich-Wörter: {len(ich_set)}")
    print(f"[INFO] kein-ig-Wörter: {len(kein_set)}")
    print(f"[INFO] Sonderfälle (mehrere ig): {len(sonder_set)}")

def ist_echtes_wort(token):
    """
    True nur für echte Wörter.
    Erlaubt Buchstaben inkl. Umlaute, Bindestrich und Apostroph.
    Keine Zahlen, keine Satzzeichen-only, keine Tags.
    """
    token = (token or "").strip()

    if not token:
        return False

    if token.startswith("|") and token.endswith("|"):
        return False

    # Mindestens ein Buchstabe
    if not regex.search(r"\p{L}", token):
        return False

    # Nur Buchstaben, kombinierende Zeichen, Bindestrich, Apostroph
    return regex.fullmatch(r"[\p{L}\p{M}'’\-]+", token) is not None

def extrahiere_ig_woerter_aus_json(
    json_ordner,
    ausgabe_datei,
    lowercase=True,
    sort_case_insensitive=True,
    min_len=1,
    verwende_tokenInklZahlwoerter=True,
    ignoriere_spezialtokens=True,
    nur_tokens_mit_ig=True,
):
    """
    Extrahiert IG-Wörter aus *_annotierungen.json-Dateien.

    Ausgabeformat:
        ein Wort pro Zeile

    Keine Häufigkeit.
    Keine Flexionsbündelung.
    Keine Basisformen.
    """
    json_ordner = Path(json_ordner)
    ausgabe_datei = Path(ausgabe_datei)

    if not json_ordner.exists():
        print(f"[FEHLER] JSON-Ordner existiert nicht: {json_ordner}")
        return

    json_dateien = sorted(json_ordner.glob("*_annotierungen.json"))
    if not json_dateien:
        print(f"[WARNUNG] Keine *_annotierungen.json-Dateien gefunden in: {json_ordner}")
        return

    print(f"[INFO] Starte IG-Extraktion aus {len(json_dateien)} JSON-Dateien ...")

    woerter_set = set()

    for datei in json_dateien:
        try:
            with open(datei, "r", encoding="utf-8") as f:
                daten = json.load(f)

            if not isinstance(daten, list):
                print(f"[WARNUNG] Datei hat kein Listenformat, überspringe: {datei.name}")
                continue

            for eintrag in daten:
                if not isinstance(eintrag, dict):
                    continue

                if verwende_tokenInklZahlwoerter:
                    token = eintrag.get("tokenInklZahlwoerter") or eintrag.get("token") or ""
                else:
                    token = eintrag.get("token") or ""

                token = normalisiere_ig_token(token, lowercase=lowercase)

                if not token:
                    continue

                if ignoriere_spezialtokens:
                    if token.startswith("|") and token.endswith("|"):
                        continue
                    if token in {"", "_", "__"}:
                        continue

                clean_token = re.sub(r"[^\wäöüÄÖÜß]", "", token).strip()

                if not clean_token:
                    continue

                if len(clean_token) < min_len:
                    continue

                if nur_tokens_mit_ig and "ig" not in clean_token.lower():
                    continue

                woerter_set.add(clean_token)

        except Exception as e:
            print(f"[FEHLER] Fehler beim Lesen von {datei.name}: {e}")

    sortierte_woerter = sorted(
        woerter_set,
        key=lambda x: x.lower() if sort_case_insensitive else x
    )

    ausgabe_datei.parent.mkdir(parents=True, exist_ok=True)

    with open(ausgabe_datei, "w", encoding="utf-8") as f:
        for wort in sortierte_woerter:
            f.write(wort + "\n")

    print(f"[INFO] IG-Wörter extrahiert: {len(sortierte_woerter)}")
    print(f"[✓] IG-Wortliste gespeichert: {ausgabe_datei}")


def extrahiere_json_objekt_robust(text):
    if not text:
        return None

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"```$", "", text.strip()).strip()

    start = text.find("{")
    if start == -1:
        return None

    tiefe = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            tiefe += 1
        elif ch == "}":
            tiefe -= 1
            if tiefe == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None

    return None


def leeres_kombi_json():
    return {
        "pause": {
            "atempause": [],
            "staupause": []
        },
        "gedanken": {
            "gedanken_weiter": [],
            "gedanken_ende": [],
            "pause_gedanken": []
        },
        "betonung": {
            "hauptbetonung": [],
            "nebenbetonung": []
        },
        "spannung": {
            "Starten": [],
            "Halten": [],
            "Stoppen": []
        }
    }


def merge_kombi_antworten(antworten):
    merged = leeres_kombi_json()

    for antwort in antworten:
        daten = extrahiere_json_objekt_robust(antwort)

        if not isinstance(daten, dict):
            print("[WARNUNG] Kombi-Antwort konnte nicht als JSON gelesen werden.")
            continue

        for hauptkey, kategorien in merged.items():
            teil = daten.get(hauptkey, {})

            if not isinstance(teil, dict):
                continue

            for subkey in kategorien.keys():
                werte = teil.get(subkey, [])

                if not isinstance(werte, list):
                    continue

                for nr in werte:
                    try:
                        nr_int = int(nr)
                    except Exception:
                        continue

                    if nr_int not in merged[hauptkey][subkey]:
                        merged[hauptkey][subkey].append(nr_int)

    for hauptkey in merged:
        for subkey in merged[hauptkey]:
            merged[hauptkey][subkey] = sorted(merged[hauptkey][subkey])

    return json.dumps(merged, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    extrahiere_ig_woerter_aus_json(
        json_ordner=config.GLOBALORDNER["json"],
        ausgabe_datei=Path(config.GLOBALORDNER["ki"]) / "ig_woerter.txt",
        lowercase=True,    
        min_len=2,
        verwende_tokenInklZahlwoerter=True,
    )