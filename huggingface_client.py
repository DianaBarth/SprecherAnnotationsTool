import subprocess
import sys
import os
import threading
import itertools
import time
from pathlib import Path
from transformers import T5Tokenizer, T5ForConditionalGeneration
from huggingface_hub import list_models, HfApi,hf_hub_download
import torch
from torch.utils.data import Dataset, DataLoader
     
import Eingabe.config as config # Importiere das komplette config-Modul

class HuggingFaceClient:
    def __init__(self):
        self.model_name = None
        self.model = None
        self.tokenizer = None
        self.hf_api = HfApi()  # API-Client initialisiert

        # Überprüfen und ggf. Installation von Transformers und Torch
        if not self.is_huggingface_installed():
            print("[INFO] Hugging Face ist nicht installiert. KI wird erstmal deaktiviert....")
            
            # self.install_huggingface()

    def is_huggingface_installed(self) -> bool:
        """Prüft, ob Hugging Face Transformers installiert ist."""
        try:
            import transformers  # noqa: F401
            return True
        except ImportError:
            return False

    def install_huggingface(self):
        """Installiert Hugging Face Transformers und Torch."""
        subprocess.check_call([sys.executable, "-m", "pip", "install", "transformers", "torch"])


    def CheckandSet_model(self,model_name:str):
        if  self.model_name == model_name:
            pass
        else:
            self.set_model(model_name)

    def set_model(self, model_name: str):
        """Lädt das angegebene Modell und den Tokenizer mit Ladeanzeige."""
        def spinner_func(done_flag):
            spinner = itertools.cycle(['|', '/', '-', '\\'])
            print(f"[HuggingFaceClient] Lade Modell '{model_name}', bitte warten… ", end="", flush=True)
            while not done_flag["done"]:
                sys.stdout.write(next(spinner))
                sys.stdout.flush()
                time.sleep(0.1)
                sys.stdout.write('\b')

        done_flag = {"done": False}
        spinner_thread = threading.Thread(target=spinner_func, args=(done_flag,))
        spinner_thread.start()

        try:
            self.tokenizer = T5Tokenizer.from_pretrained(model_name)
            self.model = T5ForConditionalGeneration.from_pretrained(model_name)
            self.model_name = model_name
        finally:
            done_flag["done"] = True
            spinner_thread.join()

        print("\n[HuggingFaceClient] Modell erfolgreich geladen.")

    def generate(self, prompt: str, max_length: int = 200) -> str:
        """Generiert eine Antwort für einen Prompt."""
        if not self.model_name:
            raise ValueError("Kein Modell gesetzt. Bitte set_model() aufrufen.")
        print(f"[INFO] Generiere mit '{self.model_name}': {prompt}")
        inputs = self.tokenizer(prompt, return_tensors="pt", padding=True, truncation=True)
        outputs = self.model.generate(
            inputs["input_ids"], max_length=max_length, num_return_sequences=1
        )
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def get_available_models(
        self,
        model_filter: str = None,
        language_keywords: list[str] = None,
        limit: int = 1000
    ) -> list[str]:
        """
        Liefert eine Liste verfügbarer Modelle vom Hugging Face Hub.
        :param model_filter: Filter-String (z.B. 't5', 'bert').
        :param language_keywords: Liste von Sprach-Keywords (z.B. ['deutsch','german']).
        :param limit: Maximale Anzahl zu ladender Modelle.
        """
        try:
            print(f"[DEBUG] get_available_models: filter={model_filter}, langs={language_keywords}")
            models = list_models(filter=model_filter, limit=limit, full=True)
            names: list[str] = []
            for m in models:
                model_id = m.modelId.lower()
                if language_keywords and not any(kw in model_id for kw in language_keywords):
                    continue
                names.append(m.modelId)
            names = sorted(set(names))
            print(f"[DEBUG] Gefundene Modelle: {len(names)}")
            return names
        except Exception as e:
            print(f"[ERROR] Modelle konnten nicht geladen werden: {e}")
            return ["t5-small", "t5-base"]

    def get_model_info(self, model_name: str) -> dict:
        """
        Liefert Metadaten für ein Modell (Größe, Parameter, Architektur, Tokenizer).
        """
        try:
            model_info = self.hf_api.model_info(model_name)
            config = model_info.config or {}
            num_parameters = config.get("num_parameters", "Unbekannt")
            arch = config.get("architectures", ["Unbekannt"])
            tokenizer = config.get("tokenizer_class", "Unbekannt")

            total_size = 0
            if hasattr(model_info, "siblings") and model_info.siblings:
                total_size = sum(getattr(s, 'size', 0) or 0 for s in model_info.siblings)
            size_mb = total_size / (1024 * 1024)

            return {
                "Model Size (MB)": f"{size_mb:.2f}",
                "Number of Parameters": num_parameters,
                "Architecture": arch[0] if isinstance(arch, list) else arch,
                "Tokenizer Class": tokenizer,
            }
        except Exception as e:
            print(f"[ERROR] Fehler beim Abrufen der Modellinformationen: {e}")
            return {"Error": str(e)}


    def get_installed_models(self) -> list[str]:
        """
        Gibt eine Liste lokal gecachter HuggingFace-Modelle zurück.
        Sucht in den beiden üblichen Cache-Pfaden.
        """
        try:
            model_names = set()

            # Pfad 1: neuer Hub-Cache
            hub_cache = Path.home() / ".cache" / "huggingface" / "hub"
            if hub_cache.exists():
                for model_dir in hub_cache.glob("models--*"):
                    if model_dir.is_dir():
                        # "models--user--modelname" wird zu "user/modelname"
                        model_name = model_dir.name.replace("models--", "").replace("--", "/")
                        model_names.add(model_name)

            # Pfad 2: älterer transformers-Cache (falls noch vorhanden)
            transformers_cache = Path.home() / ".cache" / "huggingface" / "transformers"
            if transformers_cache.exists():
                for model_dir in transformers_cache.glob("models--*"):
                    if model_dir.is_dir():
                        model_name = model_dir.name.replace("models--", "").replace("--", "/")
                        model_names.add(model_name)

            print(f"[INFO] Installierte Modelle gefunden: {len(model_names)}")
            return sorted(model_names)

        except Exception as e:
            print(f"[ERROR] Fehler beim Ermitteln der installierten Modelle: {e}")
            return []


    def check_and_load_model(self) -> bool:
        """Lädt das Modell, falls noch nicht geschehen.
        
        :return: True, wenn Modell geladen oder bereits vorhanden, False bei Fehler.
        """
        if self.model is not None and self.tokenizer is not None:
            # Modell ist bereits geladen
            return True

        if not self.model_name or not self.model_name.strip():
            raise ValueError("Kein Modell gesetzt oder Modellname ist leer.")

        try:
            self.set_model(self.model_name)
            return True
        except Exception as e:
            print(f"[ERROR] Fehler beim Laden des Modells '{self.model_name}': {e}")
            return False

    def run_model(self, prompt: str) -> str:
        """Generiert Text basierend auf einem Prompt."""
        self.check_and_load_model()
        return self.generate(prompt)

    def stop_model(self):
        """Optional: Stop-Logik für das Modell."""
        print(f"[INFO] Modell '{self.model_name}' benötigt keine Stop-Logik.")

    def __del__(self):
        print(f"[INFO] Lösche Modell '{self.model_name}'…")
        try:
            del self.model
            del self.tokenizer
        except Exception:
            pass

    def train_model_from_file(self, train_file_path: str, epochs: int = 1, batch_size: int = 4, learning_rate: float = 5e-5, progress_callback=None):
            """
            Trainiert das aktuell geladene Modell mit einer lokalen Textdatei.
            :param train_file_path: Pfad zur Trainingsdatei (Textdatei).
            :param epochs: Anzahl der Trainingsdurchläufe.
            :param batch_size: Batchgröße.
            :param learning_rate: Lernrate.
            :param progress_callback: Optionaler Callback(progress_fraction: float) zur Fortschrittsanzeige (0.0 - 1.0).
            """
            from torch.utils.data import Dataset, DataLoader
            import torch
            import os

            if self.model is None or self.tokenizer is None:
                raise ValueError("Kein Modell geladen. Bitte zuerst set_model() aufrufen.")

            if not os.path.isfile(train_file_path):
                raise FileNotFoundError(f"Trainingsdatei nicht gefunden: {train_file_path}")

            class TextDataset(Dataset):
                def __init__(self, texts, tokenizer, max_length=512):
                    self.tokenizer = tokenizer
                    self.texts = texts
                    self.max_length = max_length

                def __len__(self):
                    return len(self.texts)

                def __getitem__(self, idx):
                    encoding = self.tokenizer(
                        self.texts[idx],
                        max_length=self.max_length,
                        padding='max_length',
                        truncation=True,
                        return_tensors="pt"
                    )
                    input_ids = encoding['input_ids'].squeeze()
                    attention_mask = encoding['attention_mask'].squeeze()
                    return input_ids, attention_mask, input_ids  # labels = input_ids

            with open(train_file_path, "r", encoding="utf-8") as f:
                texts = [line.strip() for line in f if line.strip()]
            if not texts:
                raise ValueError("Trainingsdatei ist leer oder enthält keine validen Zeilen.")

            dataset = TextDataset(texts, self.tokenizer)
            dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model.to(device)
            self.model.train()

            optimizer = torch.optim.AdamW(self.model.parameters(), lr=learning_rate)

            total_batches = epochs * len(dataloader)
            batch_count = 0

            print(f"[TRAIN] Training auf {device} startet mit {len(dataset)} Beispielen...")

            for epoch in range(epochs):
                total_loss = 0
                for batch_idx, (input_ids, attention_mask, labels) in enumerate(dataloader):
                    input_ids = input_ids.to(device)
                    attention_mask = attention_mask.to(device)
                    labels = labels.to(device)

                    outputs = self.model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                    loss = outputs.loss

                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                    total_loss += loss.item()

                    batch_count += 1
                    if progress_callback:
                        progress_callback(batch_count / total_batches)

                    if batch_idx % 10 == 0:
                        print(f"[TRAIN] Epoch {epoch+1}/{epochs}, Batch {batch_idx+1}/{len(dataloader)}, Loss: {loss.item():.4f}")

                avg_loss = total_loss / len(dataloader)
                print(f"[TRAIN] Epoch {epoch+1} beendet, Durchschnitts-Loss: {avg_loss:.4f}")

            print("[TRAIN] Training abgeschlossen.")
            self.model.eval()
