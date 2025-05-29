import os
import json
import re
import Eingabe.config as config # Importiere das komplette config-Modul

# Konfiguration
MODEL_NAME = ""  # Wird später durch GUI gesetzt/überschrieben

def KI_Analyse_Chat(client, messages, dateiname="", wortnr_bereich=""):
    try:
        # Kombiniere Messages zu Prompt-String
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"<SYSTEM>\n{msg['content']}\n</SYSTEM>\n"
            elif msg["role"] == "user":
                prompt += f"<USER>\n{msg['content']}\n</USER>\n"

        print("[INFO] Anfrage an lokales Modell über HuggingFaceClient …")
        # Modell explizit übergeben (falls gesetzt), sonst None
        content = client.generate(prompt,max_new_tokens = None)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        if dateiname and wortnr_bereich:
            log_antwort(dateiname, wortnr_bereich, content)

        return content
    except Exception as e:
        print(f"[FEHLER] KI-Anfrage fehlgeschlagen: {e}")
        return None

def KI_Analyse_Flat(client, prompt_text, dateiname="", wortnr_bereich=""):
    try:
        print("[INFO] Anfrage an lokales Modell über HuggingFaceClient …")
        content = client.generate(prompt_text, max_new_tokens=None)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        if dateiname and wortnr_bereich:
            log_antwort(dateiname, wortnr_bereich, content)

        return content
    except Exception as e:
        print(f"[FEHLER] KI-Anfrage fehlgeschlagen: {e}")
        return None


def daten_verarbeiten(client, prompt, dateipfad, ki_ordner, aufgabe, force = False ):
    try:
        if not isinstance(dateipfad, str):
            raise ValueError(f"Unerwarteter Dateipfad: {dateipfad}")

        aufgaben_name = config.KI_AUFGABEN.get(aufgabe, f"unbekannt{aufgabe}")
        result_file_name = f"{aufgaben_name}_{os.path.basename(dateipfad)}"
        result_file_path = os.path.join(ki_ordner, result_file_name)

        if os.path.exists(result_file_path) and not force:
            dekodiere_und_überschreibe(result_file_path)
            print(f"[INFO] Ergebnisdatei {result_file_path} existiert bereits. KI-Analyse wird übersprungen.")
        else:
            with open(dateipfad, 'r', encoding='utf-8') as f:
                satz_daten = json.load(f)

            messages_Chat = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(satz_daten)}
            ]
            messages_Flat = f"Anweisung: \n {prompt} \n Input: \n {json.dumps(satz_daten, ensure_ascii=False)}"

           # Daten an Modell übergeben
            if client.check_chat_model():
                ki_ergebnis = KI_Analyse_Chat(
                client, messages_Chat,
                dateiname=os.path.basename(dateipfad),
                wortnr_bereich="",             
                )
            else:
                ki_ergebnis = KI_Analyse_Flat(
                client, messages_Flat,
                dateiname=os.path.basename(dateipfad),
                wortnr_bereich="",             
                )

            if ki_ergebnis:                
             
                # → KI-Antwort in Textdatei speichern
                antwort_log_datei = os.path.join(ki_ordner, f"{aufgaben_name}_KIAntwort.txt")
                with open(antwort_log_datei, 'a', encoding='utf-8') as f:
                    f.write(ki_ergebnis + "\n\n")  # jeweils mit Abstand anhängen
                    
                try:
                    dekodiert = json.loads(ki_ergebnis)
                    ki_ergebnis = dekodiert
                except (json.JSONDecodeError, TypeError):
                    print("[HINWEIS] KI-Ergebnis war kein JSON-String oder bereits dekodiert.")

                with open(result_file_path, 'w', encoding='utf-8') as result_file:
                    json.dump(ki_ergebnis, result_file, indent=4, ensure_ascii=False)

                print(f"[INFO] Ergebnis gespeichert unter: {result_file_path}")
                dekodiere_und_überschreibe(result_file_path)
                
    except Exception as e:
        print(f"[FEHLER] Fehler bei der Verarbeitung von {dateipfad}: {e}")
        
def dekodiere_und_überschreibe(pfad):
    with open(pfad, 'r', encoding='utf-8') as f:
        inhalt = f.read()

    try:
        erster_decode = json.loads(inhalt)
        daten = json.loads(erster_decode)
    except json.JSONDecodeError as e:
        print(f"Fehler beim Dekodieren von {pfad}: {e}")
        return

    with open(pfad, 'w', encoding='utf-8') as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)

    print(f"Datei erfolgreich umgewandelt: {pfad}")

def log_antwort(dateiname, wortnr_bereich, content):
    log_datei = f"log_{dateiname}.txt"
    with open(log_datei, 'a', encoding='utf-8') as log_file:
        log_file.write(f"Bereich: {wortnr_bereich}, Antwort: {content}\n")
