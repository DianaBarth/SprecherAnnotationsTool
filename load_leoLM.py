from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

def load_leolm_model():
    model_name = "leoLM/leo-mistral-hessianai-7b"
    try:
        print(f"Lade Tokenizer für {model_name}...")
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

        print(f"Lade Sprachmodell für {model_name}...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
            trust_remote_code=True
        )
        print("Modell und Tokenizer erfolgreich geladen.")
        return tokenizer, model
    except Exception as e:
        print(f"Fehler beim Laden des Modells: {e}")
        return None, None

if __name__ == "__main__":
    tokenizer, model = load_leolm_model()
    if model and tokenizer:
        # Beispielprompt (dein Format)
        prompt = """Aufgabe: Erkenne Betonungen.
Gegeben ist ein JSON mit Tokens.
[
  {"KapitelNummer": "1", "WortNr": 1, "token": "Das"},
  {"KapitelNummer": "1", "WortNr": 2, "token": "Haus"},
  {"KapitelNummer": "1", "WortNr": 3, "token": "ist"},
  {"KapitelNummer": "1", "WortNr": 4, "token": "hoch"},
  {"KapitelNummer": "1", "WortNr": 5, "token": "."}
]
Gib nur ein JSON-Array mit Betonungen zurück:"""

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=200,
                temperature=0.2,
                do_sample=False
            )

        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        print("\nAntwort:\n", generated_text)
    else:
        print("Modell konnte nicht geladen werden.")
