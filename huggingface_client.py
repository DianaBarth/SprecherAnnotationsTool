# huggingface_client.py

import gc
import os
import re
import sys
import time
import subprocess
import threading
import torch
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from huggingface_hub import HfApi, list_models
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    AutoModelForTokenClassification,
)

import Eingabe.config as config


class HuggingFaceClient:
    """
    Robuster HF-Client für lokale Generierung:
    - kleine Modelle normal
    - große Modelle automatisch 4bit, wenn CUDA + bitsandbytes verfügbar
    - CPU-Fallback
    - saubere Prompt/Antwort-Trennung
    """

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.model_name: Optional[str] = None
        self.model = None
        self.tokenizer = None
        self.task = "generation"
        self.hf_api = HfApi()
        self.log_callback = log_callback

        self.load_mode = None  # "normal", "4bit", "cpu"
        self.last_error = None

        if not self.is_huggingface_installed():
            self.log("[INFO] HuggingFace/Transformers nicht installiert. KI deaktiviert.")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, text: str):
        print(text)
        if self.log_callback:
            try:
                self.log_callback(text)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Installation / Checks
    # ------------------------------------------------------------------

    def is_huggingface_installed(self) -> bool:
        try:
            import transformers  # noqa
            return True
        except ImportError:
            return False

    def is_bitsandbytes_available(self) -> bool:
        try:
            import bitsandbytes  # noqa
            return True
        except Exception:
            return False

    def install_huggingface(self):
        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            "transformers",
            "torch",
            "accelerate",
            "bitsandbytes",
        ])

    def cuda_info(self) -> Dict[str, Any]:
        if not torch.cuda.is_available():
            return {
                "cuda": False,
                "device": "cpu",
                "vram_gb": 0,
            }

        props = torch.cuda.get_device_properties(0)
        return {
            "cuda": True,
            "device": torch.cuda.get_device_name(0),
            "vram_gb": round(props.total_memory / 1024**3, 2),
        }

    # ------------------------------------------------------------------
    # Modellentscheidung
    # ------------------------------------------------------------------

    def estimate_model_size_mb(self, model_name: str) -> float:
        """
        Nutzt HF-Metadaten. Funktioniert online.
        Falls nicht verfügbar: 0.0.
        """
        try:
            info = self.hf_api.model_info(model_name)
            total_size = 0
            for sibling in info.siblings or []:
                size = getattr(sibling, "size", 0) or 0
                filename = getattr(sibling, "rfilename", "") or ""
                if filename.endswith((".bin", ".safetensors")):
                    total_size += size
            return total_size / 1024**2
        except Exception as e:
            self.log(f"[WARN] Modellgröße konnte nicht ermittelt werden: {e}")
            return 0.0

    def should_use_4bit(self, model_name: str, force_quantization: Optional[bool] = None) -> bool:
        """
        Entscheidungsregel:
        - force_quantization überschreibt alles
        - ohne CUDA kein 4bit
        - ohne bitsandbytes kein 4bit
        - ab ca. 4 GB Modelldateien oder bekannten 7B/8B/13B-Modellen: 4bit
        """
        if force_quantization is not None:
            return bool(force_quantization)

        if not torch.cuda.is_available():
            return False

        if not self.is_bitsandbytes_available():
            return False

        name = model_name.lower()
        large_markers = [
            "7b", "8b", "9b", "10b", "11b", "12b", "13b",
            "mistral", "mixtral", "llama", "leo-mistral",
        ]
        if any(marker in name for marker in large_markers):
            return True

        size_mb = self.estimate_model_size_mb(model_name)
        return size_mb >= 4000

    # ------------------------------------------------------------------
    # Laden / Entladen
    # ------------------------------------------------------------------
    def unload_model(self, clear_model_name: bool = True):
        if self.model is None and self.tokenizer is None:
            return

        self.log("[INFO] Entlade aktuelles Modell...")

        try:
            del self.model
        except Exception:
            pass

        try:
            del self.tokenizer
        except Exception:
            pass

        self.model = None
        self.tokenizer = None

        if clear_model_name:
            self.model_name = None
            self.task = "generation"

        self.load_mode = None

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def check_and_set_model(self, model_name: str, task: str = "generation", force_quantization=None):
        model_name = self._normalize_model_name(model_name)

        self.log(f"[DEBUG] Modell prüfen/setzen: {model_name}")
        self.log(f"[DEBUG] Aktuell geladen: {self.model_name}")

        if (
            self.model is not None
            and self.tokenizer is not None
            and self.model_name == model_name
            and getattr(self, "task", "generation") == task
        ):
            self.log(f"[INFO] Modell bleibt geladen: {model_name}")
            return

        self.set_model(model_name, task=task, force_quantization=force_quantization)


    def set_model(self, model_name: str, task: str = "generation", force_quantization=None):
        if not model_name or not model_name.strip():
            raise ValueError("Leerer Modellname beim Laden.")

        model_name = self._normalize_model_name(model_name)
        task = task or "generation"

        if (
            self.model is not None
            and self.tokenizer is not None
            and self.model_name == model_name
            and getattr(self, "task", "generation") == task
        ):
            self.log(f"[INFO] Modell bereits geladen, überspringe Reload: {model_name}")
            return

        old_model_name = self.model_name
        old_task = self.task

        self.unload_model(clear_model_name=True)

        self.log(f"[INFO] Lade Modell: {model_name}")
        self.log(f"[INFO] CUDA: {self.cuda_info()}")

        self.last_error = None

        try:
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                use_fast=True,
                trust_remote_code=True,
            )

            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            self.tokenizer = tokenizer
            self.task = task

            if task == "generation":
                self._load_generation_model(model_name, force_quantization)
            elif task == "classification":
                self._load_classification_model(model_name)
            else:
                raise ValueError(f"Unbekannter task: {task}")

            if self.model is None:
                raise RuntimeError("Modell-Ladevorgang beendet, aber self.model ist None.")

            self.model_name = model_name
            self.model.eval()

            try:
                self.model.generation_config.do_sample = False
                self.model.generation_config.temperature = None
                self.model.generation_config.top_p = None
                self.model.generation_config.top_k = None
            except Exception:
                pass

            self._assert_model_ready()

            self.log(
                f"[OK] Modell geladen: {model_name} "
                f"(task={task}, mode={self.load_mode})"
            )

        except Exception as e:
            self.last_error = e
            self.log(f"[ERROR] Modell konnte nicht geladen werden: {e}")

            self.unload_model(clear_model_name=True)

            # Merken, was versucht wurde, damit check_and_load_model sinnvoll bleibt
            self.model_name = model_name or old_model_name
            self.task = task or old_task

            raise


    def print_gpu_status(self):
        if not torch.cuda.is_available():
            print("[GPU] CUDA nicht verfügbar")
            return

        props = torch.cuda.get_device_properties(0)
        print(f"[GPU] {torch.cuda.get_device_name(0)}")
        print(f"[GPU] VRAM: {props.total_memory / 1024**3:.2f} GB")

    def get_model_filters(self, limit: int = 1000) -> list[str]:
        """
        Liefert Filterbegriffe für die Modell-Auswahl in der GUI.
        """
        try:
            models = self.hf_api.list_models(limit=limit, full=True)

            filters = set()

            for m in models:
                config_data = getattr(m, "config", None) or {}

                if hasattr(config_data, "get"):
                    arch = config_data.get("architectures", [])
                else:
                    arch = []

                if isinstance(arch, str):
                    filters.add(arch.lower())
                elif isinstance(arch, (list, tuple)):
                    for a in arch:
                        if isinstance(a, str):
                            filters.add(a.lower())

                pipeline_tag = getattr(m, "pipeline_tag", None)
                if pipeline_tag:
                    filters.add(pipeline_tag.lower())

                model_id = getattr(m, "modelId", "").lower()
                known_models = [
                    "t5", "bert", "gpt2", "gpt-neo", "gpt-j",
                    "flan", "bart", "roberta", "distilbert",
                    "xlm", "xlnet", "mistral", "llama",
                    "gemma", "qwen", "phi"
                ]

                for km in known_models:
                    if km in model_id:
                        filters.add(km)

            standard_filters = [
                "summarization",
                "translation",
                "classification",
                "text-generation",
                "token-classification",
                "question-answering",
                "conversational",
                "zero-shot-classification",
            ]

            filters.update(standard_filters)

            return [""] + sorted(filters)

        except Exception as e:
            print(f"[ERROR] Fehler beim Abrufen der Model-Filter: {e}")

            return [
                "",
                "text-generation",
                "token-classification",
                "classification",
                "summarization",
                "translation",
                "question-answering",
                "zero-shot-classification",
        ]

    def _load_generation_model(self, model_name: str, force_quantization=None):
        gpu_ok = torch.cuda.is_available()
        gpu_can_handle = self._gpu_can_handle_model(model_name)
        bnb_ok = self.is_bitsandbytes_available()

        self.log(f"[DEBUG] GPU verfügbar: {gpu_ok}")
        self.log(f"[DEBUG] GPU ausreichend: {gpu_can_handle}")
        self.log(f"[DEBUG] bitsandbytes: {bnb_ok}")

        # --------------------------------------------------
        # 1. BEST CASE: GPU + 4bit
        # --------------------------------------------------
        if gpu_ok and gpu_can_handle and bnb_ok:
            try:
                from transformers import BitsAndBytesConfig

                self.log("[INFO] Lade Modell in 4bit auf GPU...")

                quant_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.float16,
                )
                
               

                torch.set_num_threads(getattr(config, "TORCH_NUM_THREADS", 12))



                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    quantization_config=quant_config,
                    device_map="auto",
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                )

                self.load_mode = "4bit_gpu"
                return

            except Exception as e:
                self.log(f"[WARN] 4bit fehlgeschlagen: {e}")

        # --------------------------------------------------
        # 2. FALLBACK: GPU normal (nur wenn sinnvoll!)
        # --------------------------------------------------
        if gpu_ok and gpu_can_handle:
            try:
                self.log("[INFO] Lade Modell normal auf GPU...")

                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16,
                    device_map="auto",
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                )

                self.load_mode = "gpu_fp16"
                return

            except Exception as e:
                self.log(f"[WARN] GPU normal fehlgeschlagen: {e}")

     
        # --------------------------------------------------
        # 3. LAST RESORT: CPU
        # --------------------------------------------------
        self.model = None
        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self.log("[INFO] Fallback → CPU")

        try:
            torch.set_num_threads(getattr(config, "TORCH_NUM_THREADS", 12))
        except RuntimeError as e:
            self.log(f"[WARNUNG] torch.set_num_threads fehlgeschlagen: {e}")

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float32,
            device_map=None,
            low_cpu_mem_usage=False,
            trust_remote_code=True,
            use_safetensors=True,
            local_files_only=False,
        )

        meta_params = [
            name for name, param in self.model.named_parameters()
            if getattr(param, "is_meta", False)
        ]

        if meta_params:
            raise RuntimeError(
                f"Modell enthält Meta-Tensoren nach CPU-Laden: {meta_params[:10]}"
            )

        self.load_mode = "cpu"
        return

    def _load_classification_model(self, model_name: str):
        self.log("[INFO] Lade Token-Classification-Modell...")
        self.model = AutoModelForTokenClassification.from_pretrained(model_name)

        if torch.cuda.is_available():
            self.model.to("cuda")
            self.load_mode = "classification_cuda"
        else:
            self.model.to("cpu")
            self.load_mode = "classification_cpu"


    def _assert_model_ready(self):
        if self.model is None:
            raise RuntimeError("Modell ist None nach dem Laden.")

        if self.tokenizer is None:
            raise RuntimeError("Tokenizer ist None nach dem Laden.")

        try:
            params = list(self.model.parameters())
        except Exception as e:
            raise RuntimeError(f"Modellparameter nicht lesbar: {e}")

        if not params:
            raise RuntimeError("Modell hat keine Parameter.")

        meta_params = [
            name for name, param in self.model.named_parameters()
            if getattr(param, "is_meta", False)
        ]

        if meta_params:
            raise RuntimeError(
                f"Modell enthält Meta-Tensoren: {meta_params[:10]}"
            )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------



    def get_model_device(self):
        """
        Bei 4bit/device_map='auto' darf man model.to(...) NICHT aufrufen.
        Für Inputs reicht das Device der ersten Parameter.
        """
        try:
            return next(self.model.parameters()).device
        except Exception:
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def calc_max_new_tokens(
       self,
        prompt_token_count: int,
        requested: Optional[int] = None,
        min_new_tokens: int = 32,
        hard_cap: int = 768,
    ) -> int:
        if requested is not None:
            return max(1, int(requested))

        total_limit = getattr(config, "MAX_TOTAL_TOKENS", 4096)
        available = total_limit - prompt_token_count

        if available <= 0:
            return min_new_tokens

        return int(max(1, min(available, hard_cap)))


    def generate(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        hard_cap: Optional[int] = None,
        temperature: float = 0.0,
        stop_strings: Optional[List[str]] = None,
    ) -> str:
        if hard_cap is None:
            hard_cap = getattr(config, "KI_MAX_NEW_TOKENS", 768)  

        if self.model is None or self.tokenizer is None:
            raise ValueError("Kein Modell geladen. Bitte set_model() aufrufen.")

        if not prompt or not prompt.strip():
            return ""

        # Safety: pad_token setzen
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # --------------------------------------------------
        # Tokenisierung
        # --------------------------------------------------
        max_input_tokens = getattr(config, "MAX_TOTAL_TOKENS", 4096)
        max_input_tokens = max(512, max_input_tokens - 512)

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_input_tokens,
            return_attention_mask=True,
        )

        prompt_len = inputs["input_ids"].shape[-1]

        new_tokens = self.calc_max_new_tokens(
            prompt_token_count=prompt_len,
            requested=max_new_tokens,
            hard_cap=hard_cap,
        )

        device = self.get_model_device()
        inputs = {k: v.to(device) for k, v in inputs.items()}

        do_sample = temperature > 0.0

        self.log(
            f"[INFO] generate(): prompt_tokens={prompt_len}, "
            f"max_new_tokens={new_tokens}, mode={self.load_mode}"
        )

        # --------------------------------------------------
        # 🔥 Qwen / Chat EOS Fix
        # --------------------------------------------------
        eos_token_id = self.tokenizer.eos_token_id

        try:
            im_end_id = self.tokenizer.convert_tokens_to_ids("<|im_end|>")
            if isinstance(im_end_id, int) and im_end_id != self.tokenizer.unk_token_id:
                eos_token_id = [self.tokenizer.eos_token_id, im_end_id]
        except Exception:
            pass

        # --------------------------------------------------
        # Generation kwargs sauber bauen
        # --------------------------------------------------
        gen_kwargs = dict(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            max_new_tokens=new_tokens,
            do_sample=do_sample,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=eos_token_id,
            repetition_penalty=1.05,
            use_cache=True,
        )

        if do_sample:
            gen_kwargs.update(dict(
                temperature=temperature,
                top_p=0.9,
                top_k=50,
            ))

        # --------------------------------------------------
        # Inferenz
        # --------------------------------------------------
        start = time.time()

        with torch.inference_mode():
            output_ids = self.model.generate(**gen_kwargs)

        self.log(f"[INFO] generate() fertig nach {time.time() - start:.2f}s")

        # --------------------------------------------------
        # Decode (nur neue Tokens!)
        # --------------------------------------------------
        generated_ids = output_ids[0][prompt_len:]

        text = self.tokenizer.decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        ).strip()

        # --------------------------------------------------
        # Stop-Strings
        # --------------------------------------------------
        if stop_strings:
            text = self.cut_at_stop_strings(text, stop_strings)

        return text.strip()


    def _normalize_model_name(self, name: str) -> str:
        return (name or "").strip().replace("\\", "/")

    def generate_stream(
        self,
        prompt: str,
        on_token: Callable[[str], None],
        max_new_tokens: Optional[int] = None,
        hard_cap: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        """
        Optional für GUI:
        on_token bekommt laufend Textstücke.
        Rückgabe ist der finale Text.
        """
        from transformers import TextIteratorStreamer

        if self.model is None or self.tokenizer is None:
            raise ValueError("Kein Modell geladen.")

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=getattr(config, "MAX_TOTAL_TOKENS", 4096) - 512,
        )

        prompt_len = inputs["input_ids"].shape[-1]
        new_tokens = self.calc_max_new_tokens(prompt_len, max_new_tokens, hard_cap=hard_cap)

        device = self.get_model_device()
        inputs = {k: v.to(device) for k, v in inputs.items()}

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        eos_token_id = self.tokenizer.eos_token_id

        try:
            im_end_id = self.tokenizer.convert_tokens_to_ids("<|im_end|>")
            if isinstance(im_end_id, int) and im_end_id != self.tokenizer.unk_token_id:
                eos_token_id = [self.tokenizer.eos_token_id, im_end_id]
        except Exception:
            pass

        do_sample = temperature > 0.0

        kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=new_tokens,
            do_sample=do_sample,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=eos_token_id,
            repetition_penalty=1.05,
            use_cache=True,
        )

        if do_sample:
            kwargs.update({
                "temperature": temperature,
                "top_p": 0.9,
                "top_k": 50,
            })

        thread = threading.Thread(target=self.model.generate, kwargs=kwargs)
        thread.start()

        parts = []
        for piece in streamer:
            parts.append(piece)
            on_token(piece)

        thread.join()
        return "".join(parts).strip()

    def cut_at_stop_strings(self, text: str, stop_strings: List[str]) -> str:
        cut_pos = None
        for s in stop_strings:
            pos = text.find(s)
            if pos != -1:
                cut_pos = pos if cut_pos is None else min(cut_pos, pos)
        return text[:cut_pos] if cut_pos is not None else text

    def run_model(self, prompt: str) -> str:
        self.check_and_load_model()
        return self.generate(prompt)

 
    def check_and_load_model(self) -> bool:
        if self.model is not None and self.tokenizer is not None:
            return True

        if not self.model_name:
            raise ValueError("Kein Modell gesetzt. Erst set_model(model_name) aufrufen.")

        model_name = self.model_name
        task = self.task or "generation"

        self.set_model(model_name, task=task)
        return True
    # ------------------------------------------------------------------
    # Chat- / Prompt-Helfer
    # ------------------------------------------------------------------

    def check_chat_model(self) -> bool:
        name = (self.model_name or "").lower()
        chat_keywords = [
            "chat", "instruct", "zephyr", "hermes", "openchat",
            "llama2-chat", "vicuna", "mistral-instruct",
            "command", "dialog", "assistant", "alpaca", "gpt", "xwin",
        ]
        return any(k in name for k in chat_keywords)

    def build_prompt(self, system_text: str, user_text: str) -> str:
        """
        Nutzt Chat-Template, falls verfügbar.
        Sonst einfacher Fallback.
        """
        if self.tokenizer is not None and hasattr(self.tokenizer, "apply_chat_template"):
            try:
                messages = [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_text},
                ]
                return self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            except Exception:
                pass

        return (
            f"### SYSTEM\n{system_text.strip()}\n\n"
            f"### USER\n{user_text.strip()}\n\n"
            f"### ASSISTANT\n"
        )

    # ------------------------------------------------------------------
    # Bestehende Hilfsfunktionen
    # ------------------------------------------------------------------

    def get_available_models(
        self,
        model_filter: Optional[str] = None,
        language_keywords: Optional[List[str]] = None,
        name_filter: Optional[str] = None,
        limit: int = 5000,
    ) -> List[str]:
        try:
            if model_filter and model_filter.strip().lower() == "none":
                model_filter = None
            if model_filter == "":
                model_filter = None

            if language_keywords:
                language_keywords = [kw.lower() for kw in language_keywords if kw]

            models = list_models(filter=model_filter, limit=limit, full=True)

            names = []
            for m in models:
                model_id = m.modelId.lower()
                if language_keywords and not any(kw in model_id for kw in language_keywords):
                    continue
                if name_filter and name_filter.lower() not in model_id:
                    continue
                names.append(m.modelId)

            return sorted(set(names))

        except Exception as e:
            self.log(f"[ERROR] Modelle konnten nicht geladen werden: {e}")
            return ["t5-small", "t5-base"]

    def get_model_info(self, model_name: str) -> dict:
        try:
            info = self.hf_api.model_info(model_name)
            cfg = info.config or {}

            total_size = 0
            if info.siblings:
                total_size = sum(getattr(s, "size", 0) or 0 for s in info.siblings)

            arch = cfg.get("architectures", ["Unbekannt"])
            if isinstance(arch, list):
                arch = arch[0] if arch else "Unbekannt"

            return {
                "Model Size (MB)": f"{total_size / 1024**2:.2f}",
                "Architecture": arch,
                "Tokenizer Class": cfg.get("tokenizer_class", "Unbekannt"),
                "Load Recommendation": (
                    "4bit empfohlen"
                    if self.should_use_4bit(model_name)
                    else "normal/CPU möglich"
                ),
            }

        except Exception as e:
            return {"Error": str(e)}

    def get_installed_models(self) -> List[str]:
        model_names = set()

        for cache in [
            Path.home() / ".cache" / "huggingface" / "hub",
            Path.home() / ".cache" / "huggingface" / "transformers",
        ]:
            if cache.exists():
                for model_dir in cache.glob("models--*"):
                    if model_dir.is_dir():
                        name = model_dir.name.replace("models--", "").replace("--", "/")
                        model_names.add(name)

        return sorted(model_names)

    def _gpu_can_handle_model(self, model_name: str) -> bool:
        """
        Prüft grob, ob GPU das Modell überhaupt stemmen kann.
        Heuristik:
        - VRAM < 6GB → eher kritisch für 7B
        - VRAM < 4GB → nur kleine Modelle
        """
        if not torch.cuda.is_available():
            return False

        try:
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / 1024**3

            name = model_name.lower()

            # harte Regeln
            if vram_gb < 4:
                return False

            if any(x in name for x in ["7b", "8b", "mistral", "llama"]):
                return vram_gb >= 6  # 8GB ideal, 6GB minimal mit 4bit

            return True

        except Exception as e:
            self.log(f"[WARN] GPU-Check fehlgeschlagen: {e}")
            return False


    def stop_model(self):
        self.log("[INFO] stop_model(): aktuell keine aktive Abbruchlogik.")

    def __del__(self):
        try:
            self.unload_model(clear_model_name=True)
        except Exception:
            pass