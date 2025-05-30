import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import time
import json


prompt_datei = "Eingabe/prompts/betonung.txt"
json_datei = r"G:\Dokumente\DianaBuch_FinisPostPortam\Buch\VersionBuch2025\testdaten annotationstool\Annotationstoolergebnisse\die Organisation_FinisPostPortam_mod\satz\Prolog – Finis post portam_annotierungen_001.json"
modell_name = "leoLM/leo-mistral-hessianai-7b"
max_new_tokens = 200


def main():
    print("[INFO] Lade Tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained(modell_name)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        print(f"[INFO] Pad-Token auf EOS gesetzt: {tokenizer.pad_token}")

    print("[INFO] Lade Modell ...")
    model = AutoModelForCausalLM.from_pretrained(
        modell_name,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",  # wichtig für größere Modelle
        offload_folder="./Offload",
    )

    # === PROMPT UND DATEN LADEN ===
    with open(prompt_datei, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    with open(json_datei, "r", encoding="utf-8") as f:
        beispiel_text = json.load(f)

    kompletter_prompt = f"{prompt_text.strip()}\nEingabe:\n{json.dumps(beispiel_text, indent=2, ensure_ascii=False)}"

    print("[INFO] Tokenisiere Prompt ...")
    inputs = tokenizer(kompletter_prompt, return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    print("[INFO] Starte Textgenerierung ...")
    with torch.no_grad():
        start = time.time()
        outputs = model.generate(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            max_new_tokens=20,
            pad_token_id=tokenizer.pad_token_id,
            do_sample=False  # deterministisch für Debug-Zwecke
        )
        duration = time.time() - start

    output_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"\n[ERFOLG] Antwort nach {duration:.2f} Sekunden:")
    print("--------------------------------------------------")
    print(output_text)
    print("--------------------------------------------------")

    if torch.cuda.is_available():
        print("\n[GPU] CUDA Speicherstatus:")
        print(torch.cuda.memory_summary())


# def main():


#     # === MODELL UND TOKENIZER LADEN ===
#     print("[INFO] Lade Tokenizer ...")
#     tokenizer = AutoTokenizer.from_pretrained(modell_name, trust_remote_code=True)
#     if tokenizer.pad_token is None:
#         tokenizer.pad_token = tokenizer.eos_token
#         print(f"[INFO] Pad-Token auf EOS gesetzt: {tokenizer.pad_token}")

#     print("[INFO] Lade Modell ...")
#     model = MistralForCausalLM.from_pretrained(
#         modell_name,
#         torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
#         device_map="auto",
#         offload_folder="./Offload",
#         trust_remote_code=True
#     )

#     # === PROMPT UND DATEN LADEN ===
#     with open(prompt_datei, "r", encoding="utf-8") as f:
#         prompt_text = f.read()

#     with open(json_datei, "r", encoding="utf-8") as f:
#         annotationen = json.load(f)

#     # Beispiel: Erste Annotation anhängen, wenn vorhanden
#     beispiel = json.dumps(annotationen[0], ensure_ascii=False, indent=2) if isinstance(annotationen, list) else str(annotationen)
#     kompletter_prompt = f"{prompt_text.strip()}\n\Eingabe:\n{beispiel}"

#     # === TOKENISIEREN UND GENERIEREN ===
#     print("[INFO] Tokenisiere Prompt ...")
#     inputs = tokenizer(
#         kompletter_prompt,
#         return_tensors="pt",
#         padding=True,
#         truncation=True,
#         return_attention_mask=True
#     ).to(model.device)

#     print("[INFO] Starte Textgenerierung ...")
#     start = time.time()
#     outputs = model.generate(
#         inputs["input_ids"],
#         attention_mask=inputs["attention_mask"],
#         max_new_tokens=max_new_tokens,
#         pad_token_id=tokenizer.pad_token_id
#     )
#     dauer = time.time() - start

#     # === ERGEBNIS AUSGEBEN ===
#     antwort = tokenizer.decode(outputs[0], skip_special_tokens=True)
#     print(f"\n[ERFOLG] Antwort nach {dauer:.2f} Sekunden:\n{'-'*50}\n{antwort}")


if __name__ == "__main__":
    main()
