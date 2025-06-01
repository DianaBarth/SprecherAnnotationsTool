from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

def load_german_model():
    model_name = "dbmdz/german-gpt2"
    try:
        print(f"Lade Tokenizer und Modell für {model_name}...")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(model_name)
        print("Modell erfolgreich geladen.")
        return tokenizer, model
    except Exception as e:
        print(f"Fehler beim Laden des Modells: {e}")
        return None, None

if __name__ == "__main__":
    tokenizer, model = load_german_model()
    if tokenizer and model:
        prompt = """Analysiere literarisch den folgenden Text:

        „Es war einmal ein kleines Dorf, versteckt zwischen den Bergen, wo die Zeit stillzustehen schien.“"""

        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=150,
                temperature=0.7,
                do_sample=True,
                top_p=0.9
            )

        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        print("\nAntwort:\n", generated_text)
    else:
        print("Modell konnte nicht geladen werden.")
