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


def speichere_ki_json_antwort(ki_ordner, aufgaben_name, laufende_nr, json_datei, antwort):
    ki_ordner = Path(ki_ordner)
    ki_ordner.mkdir(parents=True, exist_ok=True)

    aufgabe_upper = str(aufgaben_name).upper()
    orig_json_name = Path(json_datei).stem

    daten = parse_ki_json_robust(antwort, fallback_typ="array")

    if daten is None:
        ausgabe_datei = ki_ordner / f"KI_{aufgabe_upper}_FEHLER_{laufende_nr:03}_{orig_json_name}.json"
        daten = {
            "fehler": "KI-Antwort konnte nicht als JSON repariert werden.",
            "raw": antwort
        }
    else:
        ausgabe_datei = ki_ordner / f"KI_{aufgabe_upper}_{laufende_nr:03}_{orig_json_name}.json"

    with open(ausgabe_datei, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)

    print(f"[INFO] KI-Datei gespeichert: {ausgabe_datei}")
    
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



def rekonstruiere_text_aus_tokens(tokens):
    text = ""
    letztes_ohne_space_danach = False

    for eintrag in tokens:
        token = eintrag.get("tokenInklZahlwoerter") or eintrag.get("token") or ""
        annotation = eintrag.get("annotation", "")

        if not token:
            continue

        ohne_space_davor = "satzzeichenOhneSpaceDavor" in annotation
        ohne_space_danach = "satzzeichenOhneSpaceDanach" in annotation

        if not text:
            text += token
        elif ohne_space_davor or letztes_ohne_space_danach:
            text += token
        else:
            text += " " + token

        letztes_ohne_space_danach = ohne_space_danach

    return text.strip()


def extrahiere_reden_aus_tokens(tokens):
    reden = []
    in_rede = False
    aktuelle_tokens = []
    rede_start = None

    oeffner = {"„", "‚", "\""}
    schliesser = {"“", "‘", "\""}

    for eintrag in tokens:
        token = eintrag.get("tokenInklZahlwoerter") or eintrag.get("token") or ""
        wortnr = eintrag.get("WortNr")

        if token in oeffner and not in_rede:
            in_rede = True
            aktuelle_tokens = []
            rede_start = None
            continue

        if token in schliesser and in_rede:
            if aktuelle_tokens and rede_start is not None:
                reden.append({
                    "RedeStart": int(rede_start),
                    "RedeEnde": int(aktuelle_tokens[-1]["WortNr"]),
                    "Rede": rekonstruiere_text_aus_tokens(aktuelle_tokens)
                })

            in_rede = False
            aktuelle_tokens = []
            rede_start = None
            continue

        if in_rede:
            if not token:
                continue

            if rede_start is None:
                rede_start = wortnr

            aktuelle_tokens.append(eintrag)

    return reden


def ersetze_rede_marker_fuer_person_prompt(prompt, tokens):
    if "{REDE_DATEN}" not in prompt:
        return prompt, []

    reden = extrahiere_reden_aus_tokens(tokens)
    print(f"[DEBUG][PERSON] Abschnitt : extrahierte Reden:")
    print(json.dumps(reden, ensure_ascii=False, indent=2))

    rede_daten_text = json.dumps(
        reden,
        ensure_ascii=False,
        indent=2
    )

    prompt = prompt.replace("{REDE_DATEN}", rede_daten_text)

    return prompt, reden


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
        # Sprecherliste injizieren
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

                print(f"[INFO] Sprecherliste injiziert.")

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
            basis_name = Path(dateipfad).stem
            basis_name = basis_name.replace("_annotierungen", "")
            basis_name = re.sub(r"_abschnitt_?\d+$", "", basis_name)

            result_file_name = f"{aufgaben_name}_{basis_name}.txt"

        result_file_path = ki_ordner / result_file_name

        # ----------------------------------------------------
        # Ergebnis überspringen
        # ----------------------------------------------------
        if result_file_path.exists() and not force:
            print(f"[INFO] Ergebnis existiert bereits → übersprungen.")
            return

        ki_ergebnis = ""

        # ====================================================
        # NORMALFALL (inkl. PERSON)
        # ====================================================
        json_datei = lade_json_zu_txt_datei(dateipfad)

        if not json_datei or not json_datei.exists():
            print(f"[WARNUNG] Kein JSON → Fallback TXT")

            with open(dateipfad, "r", encoding="utf-8") as f:
                eingabetext = f.read()

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": eingabetext}
            ]

            ki_ergebnis = KI_Analyse_Chat(client, messages)

        else:
            with open(json_datei, "r", encoding="utf-8") as f:
                json_daten = json.load(f)

            abschnitte = splitte_in_abschnitte_intelligent(json_daten)

            alle_antworten = []
            einzelantwort_nr = 1  
            
            for abschnitt_nr, abschnitt in enumerate(abschnitte, start=1):

                tokens = abschnitt.get("tokens", [])

                # --------------------------------------------
                # PERSON: Reden extrahieren
                # --------------------------------------------
                # WICHTIG: immer vom bereits vorbereiteten prompt ausgehen
                prompt_fuer_abschnitt = str(prompt)

                if ist_person_aufgabe:
                    prompt_fuer_abschnitt, reden = ersetze_rede_marker_fuer_person_prompt(
                        prompt_fuer_abschnitt,
                        tokens
                    )

                    if "{REDE_DATEN}" in prompt_fuer_abschnitt:
                        print("[WARNUNG] Prompt enthält nach Ersetzung noch {REDE_DATEN}!")

                    if not reden:
                        print(f"[INFO] Abschnitt {abschnitt_nr}: keine Rede → skip")
                        continue

                    print(f"[INFO] Abschnitt {abschnitt_nr}: {len(reden)} Reden extrahiert")
                                # --------------------------------------------
                    # Prompt bauen
                    # --------------------------------------------
                abschnitt_prompt = baue_ki_prompt(
                    abschnitt_text=abschnitt["text"],
                    tokens=tokens,
                    aufgabe_prompt=None,
                    kompakt=False
                )

                messages = [
                    {"role": "system", "content": prompt_fuer_abschnitt},
                    {"role": "user", "content": abschnitt_prompt}
                ]

                antwort = KI_Analyse_Chat(
                    client,
                    messages,
                    dateiname=os.path.basename(dateipfad),
                    wortnr_bereich=f"{abschnitt.get('start_wortnr')}-{abschnitt.get('end_wortnr')}",
                    max_new_tokens=antwort_max_new_tokens
                )

                start_wortnr = int(abschnitt.get("start_wortnr", 0))
                end_wortnr = int(abschnitt.get("end_wortnr", 0))

                if antwort and aufgaben_name_lower == "person":
                    bereinigte_person, fehler = validiere_person_antwort(antwort, reden)

                    if fehler:
                        print(f"[WARNUNG][PERSON] Ungültige Antwort: {fehler}")
                    else:
                        antwort = json.dumps(bereinigte_person, ensure_ascii=False, indent=2)

                if antwort and aufgaben_name_lower == "kombination":
                    antwort, warnung = validiere_kombination_antwort(
                        antwort,
                        start_wortnr=start_wortnr,
                        end_wortnr=end_wortnr
                    )

                    if warnung:
                        print(f"[WARNUNG][KOMBINATION] {warnung}")

                if antwort:
                    # Filter (bleibt unverändert)
                    if aufgaben_name_lower == "betonung":
                        antwort = filtere_wortnr_json(...)

                    elif aufgaben_name_lower == "pause":
                        antwort = filtere_wortnr_json(...)

                    elif aufgaben_name_lower == "gedanken":
                        antwort = filtere_wortnr_json(...)

                    elif aufgaben_name_lower == "spannung":
                        antwort = filtere_wortnr_json(...)

                    # 🔥 NEU: Einzeldatei speichern
                    if antwort and aufgaben_name_lower in {"person", "kombination"}:
                        speichere_ki_json_antwort(
                            ki_ordner=ki_ordner,
                            aufgaben_name=aufgaben_name,
                            laufende_nr=einzelantwort_nr,
                            json_datei=json_datei,
                            antwort=antwort
                        )
                        einzelantwort_nr += 1

                    # 🔥 WICHTIG: NICHT mehr sammeln!
                    if aufgaben_name_lower not in {"person", "kombination"}:
                        if antwort:
                            alle_antworten.append(antwort.strip())

                ki_ergebnis = "\n".join(alle_antworten)

        # ----------------------------------------------------
        # Ergebnis speichern
        # ----------------------------------------------------
        if ki_ergebnis:
            with open(result_file_path, "w", encoding="utf-8") as f:
                f.write(ki_ergebnis)

            print(f"[INFO] Ergebnis gespeichert: {result_file_path}")
        else:
            print("[WARNUNG] Kein Ergebnis.")

    except Exception as e:
        print(f"[FEHLER] {e}")
        traceback.print_exc()

    finally:
        gc.collect()

def validiere_person_antwort(antwort, erwartete_reden):
    daten = parse_ki_json_robust(antwort, fallback_typ="array")

    if not isinstance(daten, list):
        return None, "Antwort ist kein JSON-Array"

    if len(daten) != len(erwartete_reden):
        return None, f"Anzahl falsch: erwartet {len(erwartete_reden)}, erhalten {len(daten)}"

    bereinigt = []

    for idx, rede in enumerate(erwartete_reden):
        eintrag = daten[idx]

        # Neues Format: ["Jott", "Uh", "Uh"]
        if isinstance(eintrag, str):
            sprecher = eintrag

        else:
            sprecher = "Unbekannt"

        bereinigt.append({
            "Sprecher": str(sprecher),
            "RedeStart": int(rede["RedeStart"]),
            "RedeEnde": int(rede["RedeEnde"]),
            "Rede": rede.get("Rede", "")
        })

    return bereinigt, None


def parse_ki_json_robust(text, fallback_typ="array"):
    if not text:
        return [] if fallback_typ == "array" else {}

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()

    # JSON-Teil finden
    if fallback_typ == "array":
        start = text.find("[")
        ende = text.rfind("]")
    else:
        start = text.find("{")
        ende = text.rfind("}")

    if start != -1 and ende != -1 and ende > start:
        text = text[start:ende + 1]

    kandidaten = [text]

    repariert = text

    # Typische LLM-Fehler
    repariert = repariert.replace("“", '"').replace("”", '"')
    repariert = repariert.replace("„", '"')
    repariert = repariert.replace("'", '"')

    # trailing commas entfernen
    repariert = re.sub(r",\s*([\]}])", r"\1", repariert)

    # Python-None/True/False zu JSON
    repariert = re.sub(r"\bNone\b", "null", repariert)
    repariert = re.sub(r"\bTrue\b", "true", repariert)
    repariert = re.sub(r"\bFalse\b", "false", repariert)

    kandidaten.append(repariert)

    for kandidat in kandidaten:
        try:
            return json.loads(kandidat)
        except Exception:
            pass

    return None

def validiere_kombination_antwort(antwort, start_wortnr, end_wortnr):
    daten = parse_ki_json_robust(antwort, fallback_typ="object")

    ziel = leeres_kombi_json()

    if not isinstance(daten, dict):
        return json.dumps(ziel, ensure_ascii=False, indent=2), "Antwort ist kein JSON-Objekt"

    max_pro_liste = 3
    max_gesamt = 12
    gesamt = 0
    warnungen = []

    for hauptkey, subkeys in ziel.items():
        teil = daten.get(hauptkey, {})

        if not isinstance(teil, dict):
            warnungen.append(f"{hauptkey} ist kein Dict")
            continue

        for subkey in subkeys:
            werte = teil.get(subkey, [])

            if not isinstance(werte, list):
                warnungen.append(f"{hauptkey}.{subkey} ist keine Liste")
                continue

            sauber = []

            for nr in werte:
                try:
                    nr_int = int(nr)
                except Exception:
                    continue

                if not (start_wortnr <= nr_int <= end_wortnr):
                    warnungen.append(f"WortNr außerhalb Bereich entfernt: {nr_int}")
                    continue

                if nr_int not in sauber:
                    sauber.append(nr_int)

                if len(sauber) >= max_pro_liste:
                    break

            for nr in sauber:
                if gesamt >= max_gesamt:
                    break
                ziel[hauptkey][subkey].append(nr)
                gesamt += 1

    return json.dumps(ziel, ensure_ascii=False, indent=2), "; ".join(warnungen)

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

def splitte_ig_klassen_json(eingabe_datei, ki_ordner):
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

            klasse = (
                klasse
                .replace("ig_ich", "ig-ich")
                .replace("ig/ich", "ig-ich")
                .replace("ig ich", "ig-ich")
            )

            if ist_mehrfach_klasse(klasse):
                sonder_set.add(f"{wort}\t{klasse}")
            elif klasse == "ik":
                ik_set.add(wort)
            elif klasse == "ich":
                ich_set.add(wort)
            elif klasse == "kein":
                kein_set.add(wort)
            else:
                kein_set.add(wort)

    ausgaben = {
        "KI_IG_Gesamt_ICH.json": sorted(ich_set),
        "KI_IG_Gesamt_IK.json": sorted(ik_set),
        "KI_IG_Gesamt_KEIN.json": sorted(kein_set),
        "KI_IG_Gesamt_SONDERFAELLE.json": sorted(sonder_set),
    }

    for dateiname, daten in ausgaben.items():
        pfad = Path(ki_ordner) / dateiname
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)

        print(f"[INFO] IG-Datei gespeichert: {pfad}")

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