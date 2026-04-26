from pathlib import Path

from Eingabe import config

from pathlib import Path
import re
import Eingabe.config as config


def lade_json_zu_txt_datei(dateipfad):
    txt_pfad = Path(dateipfad)
    name = txt_pfad.stem

    # 🔥 Abschnitt entfernen → zurück zur Kapiteldatei
    name = re.sub(r"_abschnitt_\d+$", "", name)

    json_name = f"{name}_annotierungen.json"
    json_pfad = Path(config.GLOBALORDNER["json"]) / json_name

    if not json_pfad.exists():
        print(f"[WARNUNG] JSON-Datei nicht gefunden: {json_pfad}")
        return None

    return json_pfad

def hole_token(eintrag):
    return (
        eintrag.get("tokenInklZahlwoerter")
        or eintrag.get("token")
        or eintrag.get("Token")
        or ""
    )


def ist_zeilenumbruch(eintrag):
    annotation = str(eintrag.get("annotation", "")).lower()
    typ = str(eintrag.get("typ", "")).lower()
    token = str(hole_token(eintrag)).lower()

    return (
        annotation == "zeilenumbruch"
        or typ == "zeilenumbruch"
        or token in {"\\n", "\n", "<br>", "[zeilenumbruch]"}
    )


def baue_plaintext_aus_tokens(tokens):
    text = ""

    for eintrag in tokens:
        token = (
            eintrag.get("tokenInklZahlwoerter")
            or eintrag.get("token")
            or ""
        )

        annotation = (eintrag.get("annotation") or "").strip()

        if not token and annotation != "zeilenumbruch":
            continue

        if annotation == "zeilenumbruch":
            text = text.rstrip() + "\n"
            continue

        if annotation == "satzzeichenOhneSpaceDavor":
            text = text.rstrip() + token

        elif annotation == "satzzeichenOhneSpaceDanach":
            if text and not text.endswith((" ", "\n")):
                text += " "
            text += token

        elif annotation == "satzzeichenMitSpace":
            if text and not text.endswith((" ", "\n")):
                text += " "
            text += token
            text += " "

        else:
            if text and not text.endswith((" ", "\n")):
                text += " "
            text += token

    return text.strip()

def ist_satzende_token(token):
    token = str(token).strip()
    return token in {".", "!", "?", "…"} or token.endswith((".", "!", "?", "…"))


def baue_ki_prompt(abschnitt_text, tokens, aufgabe_prompt=None, kompakt=False):
    prompt_teile = []

    if aufgabe_prompt:
        prompt_teile.append("AUFGABE:")
        prompt_teile.append(str(aufgabe_prompt).strip())
        prompt_teile.append("")

    prompt_teile.append("TEXT:")
    prompt_teile.append(abschnitt_text.strip())
    prompt_teile.append("")

    if kompakt and tokens:
        start = tokens[0].get("WortNr", "")
        ende = tokens[-1].get("WortNr", "")

        prompt_teile.append("WORTNR:")
        prompt_teile.append(
            f"Start: {start}, Ende: {ende}. "
            f"Jedes Wort und jedes Satzzeichen zählt als genau 1 WortNr."
        )

    else:
        metadata_zeilen = []

        for eintrag in tokens:
            wortnr = eintrag.get("WortNr", "")
            token = hole_token(eintrag)

            if wortnr == "" or not str(token).strip():
                continue

            metadata_zeilen.append(f"{wortnr}:{token}")

        prompt_teile.append("TOKENS:")
        prompt_teile.append("\n".join(metadata_zeilen))

    return "\n".join(prompt_teile).strip()


def ist_satzende_token(eintrag):
    annotation = str(eintrag.get("annotation", "")).lower()
    token = str(hole_token(eintrag)).strip()

    return (
        token in {".", "!", "?", "…"}
        or token.endswith((".", "!", "?", "…"))
        or "satzende" in annotation
    )


def erstelle_abschnitt_dict(aktuelle_tokens):
    text = baue_plaintext_aus_tokens(aktuelle_tokens)

    return {
        "text": text,
        "tokens": aktuelle_tokens.copy(),
        "start_wortnr": aktuelle_tokens[0].get("WortNr"),
        "end_wortnr": aktuelle_tokens[-1].get("WortNr"),
    }


def splitte_in_abschnitte_intelligent(
    json_daten,
    max_tokens_pro_abschnitt=120,
    min_tokens_pro_abschnitt=80,
):
    abschnitte = []
    aktuelle_tokens = []
    letzter_war_zeilenumbruch = False

    def finde_letztes_satzende(tokens):
        for i in range(len(tokens) - 1, -1, -1):
            if ist_satzende_token(tokens[i]):
                return i
        return None

    def debug_token_info(token):
        return f"WortNr {token.get('WortNr')} ('{hole_token(token)}')"

    def abschliessen(cut_index=None, reason=""):
        nonlocal aktuelle_tokens, letzter_war_zeilenumbruch

        if not aktuelle_tokens:
            return

        if cut_index is None:
            cut_index = len(aktuelle_tokens)

        teil = aktuelle_tokens[:cut_index]
        rest = aktuelle_tokens[cut_index:]

        if teil:
            start = teil[0].get("WortNr")
            ende = teil[-1].get("WortNr")
            print(f"[DEBUG][Split][Abschluss] {reason} → WortNr {start}-{ende} | Tokens: {len(teil)}")
            abschnitte.append(erstelle_abschnitt_dict(teil))

        if rest:
            print(f"[DEBUG][Split][Rest] startet bei {debug_token_info(rest[0])} | Tokens: {len(rest)}")

        aktuelle_tokens = rest
        letzter_war_zeilenumbruch = False

    for eintrag in json_daten:
        annotation = str(eintrag.get("annotation") or "").strip().lower()
        token = hole_token(eintrag)

        # Zeilenumbruch nur als Split nutzen, wenn der Abschnitt schon sinnvoll groß ist
        if annotation == "zeilenumbruch":
            if aktuelle_tokens and not letzter_war_zeilenumbruch:
                if len(aktuelle_tokens) >= min_tokens_pro_abschnitt:
                    print(f"[DEBUG][Split][Zeilenumbruch] bei {debug_token_info(eintrag)}")
                    abschliessen(reason="Zeilenumbruch")
                else:
                    print(
                        f"[DEBUG][Split][ZeilenumbruchIgnoriert] "
                        f"nur {len(aktuelle_tokens)}/{min_tokens_pro_abschnitt} Tokens"
                    )

            letzter_war_zeilenumbruch = True
            continue

        letzter_war_zeilenumbruch = False

        if not token:
            continue

        aktuelle_tokens.append(eintrag)

        if ist_satzende_token(eintrag):
            print(f"[DEBUG][Split][Satzende] erkannt bei {debug_token_info(eintrag)}")

        # Max-Token dominiert: erst wenn zu groß, zum letzten Satzende zurück
        if len(aktuelle_tokens) >= max_tokens_pro_abschnitt:
            print(
                f"[DEBUG][Split][Tokenlimit] erreicht: "
                f"{len(aktuelle_tokens)}/{max_tokens_pro_abschnitt} Tokens"
            )

            idx = finde_letztes_satzende(aktuelle_tokens)

            if idx is not None and idx + 1 >= min_tokens_pro_abschnitt:
                token_cut = aktuelle_tokens[idx]
                print(
                    f"[DEBUG][Split][SoftCut] letztes Satzende bei "
                    f"{debug_token_info(token_cut)} (Index {idx})"
                )
                abschliessen(idx + 1, reason="Tokenlimit→Satzende")
            else:
                print("[WARNUNG][Split][HardCut] Kein brauchbares Satzende gefunden → harter Cut")
                abschliessen(reason="Tokenlimit hart")

    if aktuelle_tokens:
        start = aktuelle_tokens[0].get("WortNr")
        ende = aktuelle_tokens[-1].get("WortNr")
        print(f"[DEBUG][Split][Final] WortNr {start}-{ende} | Tokens: {len(aktuelle_tokens)}")
        abschnitte.append(erstelle_abschnitt_dict(aktuelle_tokens))

    print(f"[INFO][Split] Gesamt Abschnitte: {len(abschnitte)}")

    return abschnitte