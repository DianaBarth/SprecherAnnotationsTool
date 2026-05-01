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

def log_antwort(dateiname, wortnr_bereich, content):
    try:
        print(
            f"[KI-ANTWORT] Datei={dateiname} | Bereich={wortnr_bereich}\n{content}\n"
        )
    except Exception as e:
        print(f"[WARNUNG] Konnte KI-Antwort nicht loggen: {e}")

def speichere_ki_json_antwort(ki_ordner, aufgaben_name, laufende_nr, json_datei, antwort):
    ki_ordner = Path(ki_ordner)
    ki_ordner.mkdir(parents=True, exist_ok=True)

    aufgaben_name_lower = str(aufgaben_name).lower()
    aufgabe_upper = str(aufgaben_name).upper()

    kapitel_id, abschnitt_id = ermittle_kapitel_abschnitt_id(json_datei)

    fallback_typ = "object" if aufgaben_name_lower == "kombination" else "array"
    daten = parse_ki_json_robust(antwort, fallback_typ=fallback_typ)

    if daten is None:
        ausgabe_datei = ki_ordner / (
            f"KI_{aufgabe_upper}_FEHLER_"
            f"{kapitel_id}_{abschnitt_id}_{laufende_nr:03}.json"
        )
        daten = {
            "fehler": "KI-Antwort konnte nicht als JSON repariert werden.",
            "raw": antwort,
            "quelle": Path(json_datei).name,
            "KapitelID": kapitel_id,
            "AbschnittID": abschnitt_id,
            "TeilNr": laufende_nr,
        }
    else:
        ausgabe_datei = ki_ordner / (
            f"KI_{aufgabe_upper}_"
            f"{kapitel_id}_{abschnitt_id}_{laufende_nr:03}.json"
        )

    with open(ausgabe_datei, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)

    print(f"[INFO] KI-Datei gespeichert: {ausgabe_datei}")

def KI_Analyse_Chat(client, messages, dateiname="", wortnr_bereich="", max_new_tokens=128):
    try:
        system_text = ""
        user_text = "Wichtig für diese Tokenliste: Wähle nur einzelne Anker-WortNr.Keine Zahlenreihen. Keine benachbarten WortNr. Wenn mehrere Wörter nebeneinander passen, nimm nur eins."

        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"].strip() + "\n"
            elif msg["role"] == "user":
                user_text += msg["content"].strip() + "\n"

        prompt = client.build_prompt(system_text, user_text)

        print("[INFO] Anfrage an lokales Modell über HuggingFaceClient steam SYSTEM:" + system_text + "USER:" + user_text)

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
    ki_ordner.mkdir(parents=True, exist_ok=True)

    try:
        if not isinstance(dateipfad, str):
            raise ValueError(f"Unerwarteter Dateipfad: {dateipfad}")

        aufgaben_name = config.KI_AUFGABEN.get(aufgabe, f"unbekannt{aufgabe}")
        aufgaben_name_lower = str(aufgaben_name).lower()

        ist_ig_aufgabe = aufgaben_name_lower == "ig"
        ist_person_aufgabe = aufgaben_name_lower == "person"
        ist_kombi_aufgabe = aufgaben_name_lower == "kombination"

        max_tokens_by_task = {
            "kombination": 512,
            "person": 384,
            "ig": 512,
        }
        antwort_max_new_tokens = max_tokens_by_task.get(aufgaben_name_lower, 128)

        # ----------------------------------------------------
        # PERSON: Sprecherliste injizieren
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

                print("[INFO] Sprecherliste injiziert.")

            except Exception as e:
                print(f"[WARNUNG] Sprecherliste konnte nicht injiziert werden: {e}")
                prompt = prompt.replace(
                    "{SPRECHER_LISTE_HIER_EINFÜGEN}",
                    "Keine bekannten Sprecher"
                )

        # ====================================================
        # IG-SPEZIALFALL
        # ====================================================
        if ist_ig_aufgabe:
            tmp_ig_result_file = ki_ordner / "_tmp_ki_ig_rohantwort.txt"
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

            with open(ig_woerter_datei, "r", encoding="utf-8") as f:
                eingabetext = f.read()

            if not eingabetext.strip():
                print("[WARNUNG] IG-Wortliste ist leer. IG-Analyse wird übersprungen.")
                return

            zeilen = [z for z in eingabetext.splitlines() if z.strip()]
            chunk_groesse = 100
            chunks = [zeilen[i:i + chunk_groesse] for i in range(0, len(zeilen), chunk_groesse)]

            print(f"[INFO] IG-Wortliste enthält {len(zeilen)} Zeilen.")
            print(f"[INFO] Verarbeite IG in {len(chunks)} Chunk(s).")

            alle_antworten = []

            for chunk_nr, chunk in enumerate(chunks, start=1):
                chunk_text = "\n".join(chunk)

                messages_Chat = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": chunk_text}
                ]

                messages_Flat = f"Anweisung:\n{prompt}\n\n{chunk_text}"

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
                    print(f"[WARNUNG] Keine IG-Antwort für Chunk {chunk_nr}")

            ki_ergebnis = "\n".join(alle_antworten).strip()

            if not ki_ergebnis:
                print("[WARNUNG] Kein IG-Ergebnis erhalten.")
                return

            with open(tmp_ig_result_file, "w", encoding="utf-8") as f:
                f.write(ki_ergebnis)

            splitte_ig_klassen_json(tmp_ig_result_file, ki_ordner)

            try:
                tmp_ig_result_file.unlink(missing_ok=True)
            except Exception:
                pass

            print("[INFO] IG-Analyse abgeschlossen.")
            return

        # ====================================================
        # NORMALFALL: PERSON / KOMBINATION
        # ====================================================
        json_datei = lade_json_zu_txt_datei(dateipfad)

        if not json_datei or not json_datei.exists():
            print(f"[WARNUNG] Keine passende JSON-Datei gefunden: {dateipfad}")
            return

        print(f"[INFO] Verwende JSON + Plaintext-Kontext: {json_datei}")

        with open(json_datei, "r", encoding="utf-8") as f:
            json_daten = json.load(f)

        if not isinstance(json_daten, list):
            print(f"[WARNUNG] JSON ist keine Liste: {json_datei}")
            return

        abschnitte = splitte_in_abschnitte_intelligent(json_daten)

        if abschnitte is None:
            print("[WARNUNG] splitte_in_abschnitte_intelligent() gab None zurück.")
            abschnitte = []

        if not isinstance(abschnitte, list):
            raise TypeError(
                f"splitte_in_abschnitte_intelligent() muss list zurückgeben, "
                f"gab aber {type(abschnitte).__name__}"
            )

        if not abschnitte:
            print(f"[WARNUNG] Keine Abschnitte erzeugt für {dateipfad}.")
            return

        print(f"[INFO] Verarbeite {len(abschnitte)} Abschnitt(e).")

        einzelantwort_nr = 1

        for abschnitt_nr, abschnitt in enumerate(abschnitte, start=1):
            tokens = abschnitt.get("tokens", [])
            prompt_fuer_abschnitt = str(prompt)
            reden = []

            start_wortnr = int(abschnitt.get("start_wortnr", 0))
            end_wortnr = int(abschnitt.get("end_wortnr", 0))
            wortnr_bereich = f"{start_wortnr}-{end_wortnr}"

            # ------------------------------------------------
            # PERSON: Rededaten injizieren
            # ------------------------------------------------
            if ist_person_aufgabe:
                prompt_fuer_abschnitt, reden = ersetze_rede_marker_fuer_person_prompt(
                    prompt_fuer_abschnitt,
                    tokens
                )

                if "{REDE_DATEN}" in prompt_fuer_abschnitt:
                    print("[WARNUNG] Prompt enthält nach Ersetzung noch {REDE_DATEN}!")

                if not reden:
                    print(f"[INFO] Abschnitt {abschnitt_nr}: keine Rede → übersprungen.")
                    continue

                print(f"[INFO] Abschnitt {abschnitt_nr}: {len(reden)} Rede(n) extrahiert.")

            # ------------------------------------------------
            # Prompt für Abschnitt bauen
            # ------------------------------------------------
            if ist_kombi_aufgabe:
                abschnitt_prompt = (
                    "ABSCHNITT ALS FLIESSTEXT:\n"
                    f"{abschnitt.get('text', '')}\n\n"
                    "TOKENLISTE MIT WORTNR:\n"
                    + "\n".join(
                        f"{t.get('WortNr')}: {t.get('tokenInklZahlwoerter') or t.get('token') or ''}"
                        for t in tokens
                        if t.get("tokenInklZahlwoerter") or t.get("token")
                    )
                )
            else:
                abschnitt_prompt = baue_ki_prompt(
                    abschnitt_text=abschnitt["text"],
                    tokens=tokens,
                    aufgabe_prompt=None,
                    kompakt=False
                )

            print("[DEBUG][KOMBINATION] Abschnitt-Prompt:")
            print(abschnitt_prompt[:3000])

            print(
                f"[INFO] Abschnitt {abschnitt_nr}/{len(abschnitte)} "
                f"Aufgabe={aufgaben_name} WortNr={wortnr_bereich}"
            )

            messages_Chat = [
                {"role": "system", "content": prompt_fuer_abschnitt},
                {"role": "user", "content": abschnitt_prompt}
            ]

            messages_Flat = (
                f"Anweisung:\n{prompt_fuer_abschnitt}\n\n"
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

            if not antwort:
                print(f"[WARNUNG] Keine Antwort für Abschnitt {abschnitt_nr}")
                continue

            # ------------------------------------------------
            # PERSON validieren
            # ------------------------------------------------
            if ist_person_aufgabe:
                bereinigte_person, fehler = validiere_person_antwort(
                    antwort,
                    reden
                )

                if fehler:
                    print(f"[WARNUNG][PERSON] Ungültige Antwort Abschnitt {abschnitt_nr}: {fehler}")
                    continue

                antwort = json.dumps(bereinigte_person, ensure_ascii=False, indent=2)

            # ------------------------------------------------
            # KOMBINATION validieren
            # ------------------------------------------------
            if ist_kombi_aufgabe:
                antwort, warnung = validiere_kombination_antwort(
                    antwort,
                    start_wortnr=start_wortnr,
                    end_wortnr=end_wortnr,
                    tokens=tokens
                )

                if warnung:
                    print(f"[WARNUNG][KOMBINATION] Abschnitt {abschnitt_nr}: {warnung}")

            # ------------------------------------------------
            # Einzeldatei speichern
            # ------------------------------------------------
            if ist_person_aufgabe or ist_kombi_aufgabe:
                speichere_ki_json_antwort(
                    ki_ordner=ki_ordner,
                    aufgaben_name=aufgaben_name,
                    laufende_nr=einzelantwort_nr,
                    json_datei=json_datei,
                    antwort=antwort
                )
                einzelantwort_nr += 1

        print(f"[INFO] {aufgaben_name}-Analyse abgeschlossen für {json_datei.name}")

    except Exception as e:
        print(f"[FEHLER] Fehler bei der Verarbeitung von {dateipfad}: {e}")
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

def validiere_kombination_antwort(
    antwort,
    start_wortnr,
    end_wortnr,
    tokens=None
):
    daten = parse_ki_json_robust(antwort, fallback_typ="object")

    ziel = leeres_kombi_json()

    if not isinstance(daten, dict):
        return json.dumps(ziel, ensure_ascii=False, indent=2), "Antwort ist kein JSON-Objekt"


    gesamt = 0
    warnungen = []

    satzanzahl = schaetze_satzanzahl(tokens or [])

    if satzanzahl <= 2:
        max_gesamt = 8
    elif satzanzahl <= 5:
        max_gesamt = 16
    elif satzanzahl <= 10:
        max_gesamt = 28
    else:
        max_gesamt = 40

    limits = {
        ("pause", "atempause"): max(2, satzanzahl),
        ("pause", "staupause"): max(1, min(satzanzahl, satzanzahl // 2 + 1)),

        ("gedanken", "gedanken_weiter"): max(1, satzanzahl // 2),
        ("gedanken", "gedanken_ende"): max(1, satzanzahl // 2),
        ("gedanken", "pause_gedanken"): max(1, satzanzahl // 3),

        ("betonung", "hauptbetonung"): max(2, satzanzahl),
        ("betonung", "nebenbetonung"): max(2, satzanzahl),

        ("spannung", "Starten"): 1,
        ("spannung", "Halten"): min(2, max(1, satzanzahl // 3)),
        ("spannung", "Stoppen"): 1,
    }
        
    for hauptkey, subdict in ziel.items():
        teil = daten.get(hauptkey, {})

        if not isinstance(teil, dict):
            warnungen.append(f"{hauptkey} ist kein Dict")
            continue

        for subkey in subdict:
            werte = teil.get(subkey, [])

            if not isinstance(werte, list):
                warnungen.append(f"{hauptkey}.{subkey} ist keine Liste")
                continue

            sauber = []
            limit = limits.get((hauptkey, subkey), 3)

            for nr in werte:
                try:
                    nr_int = int(nr)
                except Exception:
                    continue

                # ❌ außerhalb Bereich → raus
                if not (start_wortnr <= nr_int <= end_wortnr):
                    warnungen.append(f"{nr_int} außerhalb Bereich entfernt")
                    continue

                # ❌ Duplikate vermeiden
                if nr_int in sauber:
                    continue

                sauber.append(nr_int)

                # 🔥 Limit pro Liste
                if len(sauber) >= limit:
                    break

            # 🔥 globales Limit
            for nr in sauber:
                if gesamt >= max_gesamt:
                    break
                ziel[hauptkey][subkey].append(nr)
                gesamt += 1

    # 🔥 Sortierung für Stabilität
    for hauptkey in ziel:
        for subkey in ziel[hauptkey]:
            ziel[hauptkey][subkey] = sorted(ziel[hauptkey][subkey])

    print("[DEBUG][KOMBINATION] Roh geparst:")
    print(json.dumps(daten, ensure_ascii=False, indent=2))
    print(f"[DEBUG][KOMBINATION] Bereich: {start_wortnr}-{end_wortnr}")


    return json.dumps(ziel, ensure_ascii=False, indent=2), "; ".join(warnungen)


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

def normalisiere_ig_token(token, lowercase=True):
    token = (token or "").strip()
    token = unicodedata.normalize("NFC", token)

    if lowercase:
        token = token.lower()

    return token


def extrahiere_ig_woerter_aus_json(
    json_ordner,
    ausgabe_datei,
    lowercase=True,
    sort_case_insensitive=True,
    min_len=2,
    verwende_tokenInklZahlwoerter=True,
    ignoriere_spezialtokens=True,
    nur_tokens_mit_ig=True,
):
    json_ordner = Path(json_ordner)
    ausgabe_datei = Path(ausgabe_datei)

    if not json_ordner.exists():
        print(f"[FEHLER] JSON-Ordner existiert nicht: {json_ordner}")
        return

    json_dateien = sorted(json_ordner.glob("*_annotierungen.json"))

    if not json_dateien:
        print(f"[WARNUNG] Keine *_annotierungen.json-Dateien gefunden in: {json_ordner}")
        return

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

def splitte_ig_klassen_json(eingabe_datei, ki_ordner):
    ki_ordner = Path(ki_ordner)
    ki_ordner.mkdir(parents=True, exist_ok=True)

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
                .replace("ich-ig", "ig-ich")
            )

            if ist_mehrfach_klasse(klasse):
               sonder_set.add((wort, klasse))
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
       "KI_IG_Gesamt_SONDERFAELLE.json": [
        {"wort": wort, "klasse": klasse}
        for wort, klasse in sorted(sonder_set, key=lambda x: x[0])
    ],
    }

    for dateiname, daten in ausgaben.items():
        pfad = ki_ordner / dateiname

        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)

        print(f"[INFO] IG-Datei gespeichert: {pfad}")

def ermittle_kapitel_abschnitt_id(json_datei):
    json_datei = Path(json_datei)

    with open(json_datei, "r", encoding="utf-8") as f:
        daten = json.load(f)

    kapitelnummer = None

    if isinstance(daten, list):
        for eintrag in daten:
            if isinstance(eintrag, dict) and eintrag.get("KapitelNummer") not in (None, ""):
                kapitelnummer = eintrag.get("KapitelNummer")
                break

    if kapitelnummer is None:
        raise ValueError(f"Keine KapitelNummer in Datei gefunden: {json_datei.name}")

    kapitel_id = f"{int(kapitelnummer):03d}"

    # Abschnitt aus altem Quelldateinamen lesen:
    # z.B. "2. Aufbau der Welt (Kapitel IV–VI)_001_annotierungen.json"
    match = re.search(r"_(\d+)_annotierungen\.json$", json_datei.name)

    if match:
        abschnitt_id = f"{int(match.group(1)):03d}"
    else:
        # Fallback für evtl. andere Namen
        abschnitt_id = "001"

    return kapitel_id, abschnitt_id

def schaetze_satzanzahl(tokens):
    count = 0

    for t in tokens:
        annotation = str(t.get("annotation", "") or "")

        if "satzzeichenOhneSpaceDavor" in annotation:
            count += 1

    return max(1, count)