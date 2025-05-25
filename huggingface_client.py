import subprocess
import sys
import os
import threading
import itertools
import time
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import T5Tokenizer, T5ForConditionalGeneration
from huggingface_hub import list_models, HfApi


class HuggingFaceClient:
    """
    Wrapper-Klasse für Hugging Face Modelle.
    Lädt Modelle und Tokenizer, listet verfügbare Modelle,
    führt Textgenerierung aus und ermöglicht Training auf lokalen Dateien.
    """

    def __init__(self, log_manager = None):
        self.model_name: Optional[str] = None
        self.model: Optional[T5ForConditionalGeneration] = None
        self.tokenizer: Optional[T5Tokenizer] = None
        self.hf_api = HfApi()
        self.log_manager = log_manager

        if not self.is_huggingface_installed():
            print("[INFO] Hugging Face Transformers ist nicht installiert. KI wird deaktiviert...")

    def is_huggingface_installed(self) -> bool:
        """Prüft, ob Hugging Face Transformers installiert ist."""
        try:
            import transformers  # noqa: F401
            return True
        except ImportError:
            return False

    def install_huggingface(self):
        """Installiert Transformers und Torch via pip."""
        subprocess.check_call([sys.executable, "-m", "pip", "install", "transformers", "torch"])

    def check_and_set_model(self, model_name: str):
        """
        Setzt ein Modell, falls es noch nicht gesetzt ist.
        """
        if self.model_name != model_name:
            self.set_model(model_name)

    def set_model(self, model_name: str):
        """
        Lädt das Modell und den Tokenizer mit einer Ladeanimation.
        """
        def spinner_func(done_flag):
            spinner = itertools.cycle(['|', '/', '-', '\\'])
            print(f"[HuggingFaceClient] Lade Modell '{model_name}', bitte warten... ", end="", flush=True)
            while not done_flag["done"]:
                sys.stdout.write(next(spinner))
                sys.stdout.flush()
                time.sleep(0.1)
                sys.stdout.write('\b')
            print("✔️")  # Lade erfolgreich

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

        print(f"[HuggingFaceClient] Modell '{model_name}' erfolgreich geladen.")

    def generate(self, prompt: str, max_length: int = 200) -> str:
        """
        Generiert Text für einen gegebenen Prompt.
        """
        if not self.model or not self.tokenizer:
            raise ValueError("Kein Modell geladen. Bitte set_model() vorher aufrufen.")
        print(f"[INFO] Generiere mit '{self.model_name}': {prompt}")

        inputs = self.tokenizer(prompt, return_tensors="pt", padding=True, truncation=True)
        outputs = self.model.generate(inputs["input_ids"], max_length=max_length, num_return_sequences=1)
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

  
    def get_available_models(
            self,
            model_filter: Optional[str] = None,
            language_keywords: Optional[List[str]] = None,
            name_filter: Optional[str] = None,
            limit: int = 5000
        ) -> List[str]:
        """
        Liefert eine Liste verfügbarer Modelle vom Hugging Face Hub,
        optional gefiltert nach Modell-, Sprach- und Namens-Keywords.
        """
        try:
            # Sicherstellen, dass model_filter kein "None"-String ist
            if model_filter is not None and model_filter.strip().lower() == "none":
                model_filter = None
            if model_filter == "":
                model_filter = None

            if language_keywords:
                language_keywords = [kw.lower() for kw in language_keywords if kw]

            print(f"[DEBUG] Suche Modelle mit filter={model_filter}, Sprache={language_keywords}, name_filter={name_filter}")

            models = list_models(filter=model_filter, limit=limit, full=True)

            names = []
            for m in models:
                model_id = m.modelId.lower()
                # Filter nach Sprache
                if language_keywords and not any(kw in model_id for kw in language_keywords):
                    continue
                # Filter nach Namen
                if name_filter and name_filter.lower() not in model_id:
                    continue
                names.append(m.modelId)

            unique_names = sorted(set(names))
            print(f"[DEBUG] Gefundene Modelle: {len(unique_names)}")
            return unique_names
        except Exception as e:
            print(f"[ERROR] Modelle konnten nicht geladen werden: {e}")
            return ["t5-small", "t5-base"]

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """
        Liefert Metadaten zu einem Modell.
        """
        try:
            model_info = self.hf_api.model_info(model_name)
            config = model_info.config

            if config is None:
                num_parameters = "Unbekannt"
                arch = ["Unbekannt"]
                tokenizer = "Unbekannt"
            elif not hasattr(config, "get"):
                # Falls config ein Objekt ist (kein Dict), greife direkt auf Attribute zu
                num_parameters = getattr(config, "num_parameters", "Unbekannt")
                arch = getattr(config, "architectures", ["Unbekannt"])
                tokenizer = getattr(config, "tokenizer_class", "Unbekannt")
            else:
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


    def get_installed_models(self) -> List[str]:
        """
        Gibt lokal gespeicherte Modelle zurück (Cache-Verzeichnisse).
        """
        model_names = set()
        try:
            hub_cache = Path.home() / ".cache" / "huggingface" / "hub"
            if hub_cache.exists():
                for model_dir in hub_cache.glob("models--*"):
                    if model_dir.is_dir():
                        model_name = model_dir.name.replace("models--", "").replace("--", "/")
                        model_names.add(model_name)

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
        """
        Lädt das Modell, falls noch nicht geladen.
        Gibt True zurück, wenn erfolgreich.
        """
        if self.model is not None and self.tokenizer is not None:
            return True
        if not self.model_name or not self.model_name.strip():
            raise ValueError("Kein Modell gesetzt oder leerer Modellname.")

        # Messagebox-Patch temporär deaktivieren
        self.log_manager.disable_messagebox_patch()

        try:
            self.set_model(self.model_name)
            return True
        except Exception as e:
            print(f"[ERROR] Fehler beim Laden des Modells '{self.model_name}': {e}")
            try:
                import tkinter.messagebox as messagebox
                messagebox.showerror("Fehler", f"Modell konnte nicht geladen werden:\n{e}")
            except Exception:
                pass  # Fallback für Headless-Umgebung
            return False
        finally:
            self.log_manager.enable_messagebox_patch()

    def run_model(self, prompt: str) -> str:
        """
        Generiert Text basierend auf einem Prompt.
        """
        self.check_and_load_model()
        return self.generate(prompt)

    def stop_model(self):
        """
        Optional: Stop-Logik für das Modell.
        """
        print(f"[INFO] Modell '{self.model_name}' benötigt keine Stop-Logik.")

    def __del__(self):
        """
        Säubert Model- und Tokenizer-Objekte beim Löschen der Instanz.
        """
        print(f"[INFO] Lösche Modell '{self.model_name}' ...")
        try:
            del self.model
            del self.tokenizer
        except Exception:
            pass

    def train_model_from_file(
        self,
        train_file_path: str,
        epochs: int = 1,
        batch_size: int = 4,
        learning_rate: float = 5e-5,
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        """
        Trainiert das aktuell geladene Modell mit einer lokalen Textdatei.
        :param train_file_path: Pfad zur Trainingsdatei (Textdatei)
        :param epochs: Anzahl der Trainingsdurchläufe
        :param batch_size: Batchgröße
        :param learning_rate: Lernrate
        :param progress_callback: Optionaler Callback für Fortschritt (float von 0 bis 1)
        """
        if self.model is None or self.tokenizer is None:
            raise ValueError("Kein Modell geladen. Bitte zuerst set_model() aufrufen.")

        if not os.path.isfile(train_file_path):
            raise FileNotFoundError(f"Trainingsdatei nicht gefunden: {train_file_path}")

        class TextDataset(Dataset):
            def __init__(self, texts: List[str], tokenizer: T5Tokenizer, max_length: int = 512):
                self.texts = texts
                self.tokenizer = tokenizer
                self.max_length = max_length

            def __len__(self):
                return len(self.texts)

            def __getitem__(self, idx):
                encodings = self.tokenizer(
                    self.texts[idx],
                    max_length=self.max_length,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt",
                )
                input_ids = encodings.input_ids.squeeze()
                attention_mask = encodings.attention_mask.squeeze()
                return input_ids, attention_mask

        print(f"[INFO] Lade Trainingsdaten aus '{train_file_path}'...")
        with open(train_file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        dataset = TextDataset(lines, self.tokenizer)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        optimizer = torch.optim.AdamW(self.model.parameters(), lr=learning_rate)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[INFO] Trainiere auf Gerät: {device}")
        self.model.to(device)
        self.model.train()

        for epoch in range(epochs):
            print(f"[INFO] Starte Epoche {epoch + 1}/{epochs}")
            total_batches = len(dataloader)
            for batch_idx, (input_ids, attention_mask) in enumerate(dataloader):
                input_ids = input_ids.to(device)
                attention_mask = attention_mask.to(device)
                labels = input_ids.clone()  # Für Autoencoder Training

                outputs = self.model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                loss = outputs.loss

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                if progress_callback:
                    progress = (epoch * total_batches + batch_idx + 1) / (epochs * total_batches)
                    progress_callback(progress)

                if (batch_idx + 1) % 10 == 0 or (batch_idx + 1) == total_batches:
                    print(f"Epoche {epoch + 1}/{epochs}, Batch {batch_idx + 1}/{total_batches}, Loss: {loss.item():.4f}")

        print("[INFO] Training abgeschlossen.")

    def get_model_filters(self, limit: int = 1000) -> list[str]:
        """
        Liest aus den verfügbaren HuggingFace-Modellen automatisch mögliche
        Filterbegriffe (z.B. Architektur, Pipeline-Tags, Modellnamen).
        Gibt eine sortierte Liste einzigartiger Filterbegriffe zurück, 
        wobei das erste Element "" (kein Filter = alle) ist.

        :param limit: Maximale Anzahl an Modellen, die abgefragt werden.
        """
        try:
            models = self.hf_api.list_models(limit=limit, full=True)

            filters = set()

            for m in models:
                # m ist ein ModelInfo-Objekt mit Metadaten

                if m.config and hasattr(m.config, "get"):
                    arch = m.config.get("architectures", [])
                else:
                    arch = []

                if isinstance(arch, str):
                    filters.add(arch.lower())
                elif isinstance(arch, (list, tuple)):
                    for a in arch:
                        if isinstance(a, str):
                            filters.add(a.lower())

                if hasattr(m, "pipeline_tag") and m.pipeline_tag:
                    filters.add(m.pipeline_tag.lower())

                model_id = getattr(m, "modelId", "").lower()
                known_models = ["t5", "bert", "gpt2", "gpt-neo", "gpt-j", "flan", "bart", "roberta",
                                "distilbert", "xlm", "xlnet", "gpt4", "bert-large", "bert-base"]
                for km in known_models:
                    if km in model_id:
                        filters.add(km)

            standard_filters = ["summarization", "translation", "classification",
                                "text-generation", "token-classification", "question-answering",
                                "conversational", "zero-shot-classification"]
            for sf in standard_filters:
                filters.add(sf)

            sorted_filters = sorted(filters)
            # Leerer Filter für "alle" an erste Stelle setzen
            return [""] + sorted_filters

        except Exception as e:
            print(f"[ERROR] Fehler beim Abrufen der Model-Filter: {e}")
            return [""] + ["summarization", "translation", "classification",
                        "text-generation", "token-classification", "question-answering",
                        "conversational", "zero-shot-classification"]
