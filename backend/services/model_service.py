"""
Centralized Model Service for FAIA
Singleton pattern to load Qwen model once and share across all services
"""

import os
import logging
import multiprocessing
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class ModelService:
    """Singleton service for managing Qwen model loading and access"""
    
    _instance = None
    _model = None
    _tokenizer = None
    _generation_config = None
    _model_loaded = False
    _loading_error = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.model_path = self._get_model_path()
            provider = os.getenv("MODEL_PROVIDER", "local").lower()
            logger.info("Model service initialized with provider: %s and path: %s", provider, self.model_path)
    
    def _get_model_path(self) -> Optional[str]:
        """Get model path from QWEN_MODEL_PATH environment variable when local mode is used."""
        provider = os.getenv("MODEL_PROVIDER", "local").lower()
        if provider != "local":
            return None

        model_path = os.getenv("QWEN_MODEL_PATH")
        if model_path and os.path.isdir(model_path):
            return model_path

        raise FileNotFoundError(
            "Qwen model path not found. "
            "Set QWEN_MODEL_PATH in your .env file to the directory containing the model. "
            "See .env.example for details."
        )
    
    def _load_model(self) -> bool:
        """Load Qwen model and tokenizer"""
        if self._model_loaded:
            return True
        
        if self._loading_error:
            logger.error("Previous loading error: %s", self._loading_error)
            return False
        
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM, GenerationConfig

            logger.info("Loading Qwen model and tokenizer...")
            
            # Check if loading is enabled
            load_qwen = os.getenv("LOAD_QWEN", "true").lower() == "true"
            if not load_qwen:
                logger.info("Qwen loading disabled (LOAD_QWEN=false)")
                self._loading_error = "Qwen loading disabled"
                return False
            
            # Load tokenizer
            logger.info("Loading tokenizer from: %s", self.model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )
            
            # Set pad token if not present
            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token
            
            if hasattr(self._tokenizer, 'model_max_length'):
                self._tokenizer.model_max_length = 3072
            
            logger.info("Tokenizer loaded successfully")
            
            # Load generation config
            try:
                self._generation_config = GenerationConfig.from_pretrained(self.model_path)
                logger.info("Generation config loaded from model folder")
            except Exception as e:
                logger.warning("No generation config found, using defaults: %s", e)
                self._generation_config = None
            
            # Load model with GPU optimization
            logger.info("Loading Qwen model from: %s", self.model_path)
            
            # Check GPU availability and load accordingly
            if torch.cuda.is_available():
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
                logger.info("GPU detected: %.1f GB VRAM available", gpu_memory)
                logger.info("Loading model on GPU with 8-bit quantization")
                self._model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float16,
                    device_map="auto",
                    trust_remote_code=True,
                    load_in_8bit=True,       # Reduces VRAM from ~8GB to ~4GB
                    low_cpu_mem_usage=False  # Preserved from working config
                )
            else:
                # No GPU — CPU loading
                logger.info("No GPU detected, using CPU loading")

                num_threads = max(1, int((multiprocessing.cpu_count() or 1) * 0.75))
                torch.set_num_threads(num_threads)
                logger.info("CPU threads set to %s (of %s available)", num_threads, multiprocessing.cpu_count() or 1)

                self._model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float16,  # FP16 to reduce RAM — works on this CPU
                    device_map="cpu",
                    trust_remote_code=True,
                    low_cpu_mem_usage=True
                )
            
            # Check actual device placement
            if hasattr(self._model, 'device'):
                actual_device = self._model.device
            else:
                actual_device = next(self._model.parameters()).device
            
            logger.info("Model loaded on device: %s", actual_device)
            
            try:
                memory_footprint = self._model.get_memory_footprint() / 1e9
                logger.info("Model memory footprint: ~%.2f GB", memory_footprint)
            except Exception as e:
                logger.warning("Could not get memory footprint: %s", e)
            
            logger.info("Qwen model loaded successfully!")
            self._model_loaded = True
            return True
            
        except Exception as e:
            error_msg = "Failed to load Qwen model: %s" % str(e)
            logger.error(error_msg)
            self._loading_error = error_msg
            return False
    
    def get_model(self) -> Tuple[Optional[object], Optional[object]]:
        """Get Qwen model and tokenizer"""
        if not self._model_loaded:
            if not self._load_model():
                return None, None
        
        return self._model, self._tokenizer
    
    def get_tokenizer(self) -> Optional[object]:
        """Get Qwen tokenizer only"""
        if not self._model_loaded:
            if not self._load_model():
                return None
        
        return self._tokenizer
    
    def get_generation_config(self) -> Optional[object]:
        """Get generation configuration"""
        if not self._model_loaded:
            if not self._load_model():
                return None
        
        return self._generation_config
    
    def is_model_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._model_loaded
    
    def get_loading_error(self) -> Optional[str]:
        """Get loading error if any"""
        return self._loading_error
    
    def get_model_info(self) -> dict:
        """Get model information"""
        return {
            "model_path": self.model_path,
            "model_loaded": self._model_loaded,
            "loading_error": self._loading_error,
            "has_generation_config": self._generation_config is not None,
            "tokenizer_loaded": self._tokenizer is not None
        }
    
    def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate a response using the configured model provider.

        MODEL_PROVIDER env var controls which backend is used:
          local  (default) — HuggingFace transformers, requires QWEN_MODEL_PATH
          ollama            — Ollama API, requires OLLAMA_BASE_URL (default: http://localhost:11434)
          openai            — OpenAI API, requires OPENAI_API_KEY and OPENAI_MODEL
        """
        provider = os.getenv("MODEL_PROVIDER", "local").lower()

        if provider == "ollama":
            return self._generate_ollama(prompt, **kwargs)
        elif provider == "openai":
            return self._generate_openai(prompt, **kwargs)
        else:
            return self._generate_local(prompt, **kwargs)

    def _generate_ollama(self, prompt: str, **kwargs) -> str:
        """Generate response via Ollama API."""
        import requests as _req
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

        system_message = kwargs.get("system_message",
            "You are FAIA, an educational AI assistant. Be helpful, accurate, and concise.")
        conversation_history = kwargs.get("conversation_history", [])

        messages = [{"role": "system", "content": system_message}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": prompt})

        try:
            resp = _req.post(
                "%s/api/chat" % base_url,
                json={"model": model, "messages": messages, "stream": False},
                timeout=(5, 120)
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception as e:
            raise RuntimeError("Ollama generation failed: %s" % e)

    def _generate_openai(self, prompt: str, **kwargs) -> str:
        """Generate response via OpenAI-compatible API."""
        try:
            import openai as _openai
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        base_url = os.getenv("OPENAI_BASE_URL")  # Optional — for Azure or other compatible APIs

        client = _openai.OpenAI(api_key=api_key, base_url=base_url)

        system_message = kwargs.get("system_message",
            "You are FAIA, an educational AI assistant. Be helpful, accurate, and concise.")
        conversation_history = kwargs.get("conversation_history", [])

        messages = [{"role": "system", "content": system_message}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=kwargs.get("max_new_tokens", 500),
                temperature=kwargs.get("temperature", 0.7),
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError("OpenAI generation failed: %s" % e)

    def _generate_local(self, prompt: str, **kwargs) -> str:
        """Generate response using local HuggingFace transformers (original method)."""
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("Local model dependencies unavailable: %s" % exc)

        model, tokenizer = self.get_model()

        if model is None or tokenizer is None:
            raise RuntimeError("Qwen model not available: %s" % self._loading_error)
        
        try:
            generation_params = {
                "max_new_tokens": kwargs.get("max_new_tokens", 150),
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 0.8),
                "top_k": kwargs.get("top_k", 50),
                "repetition_penalty": kwargs.get("repetition_penalty", 1.1),
                "do_sample": kwargs.get("do_sample", True),
                "max_input_length": kwargs.get("max_input_length", 4096)
            }
            
            conversation_history = kwargs.get("conversation_history", [])
            max_input_length = generation_params["max_input_length"]

            # Validate conversation history format
            for i, msg in enumerate(conversation_history):
                if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                    raise ValueError("Invalid conversation_history entry at index %d: %s" % (i, msg))
            
            system_message = kwargs.get("system_message", 
                "You are FAIA (Focused Academic Information Assistant), an educational AI assistant created specifically for this university. "
                "You are NOT developed by Microsoft, OpenAI, Anthropic, or any other company - you are FAIA, built for this campus community. "
                "You help students with learning, coursework, and academic questions. "
                "You have access to the conversation history and can reference previous messages when asked."
            )
            
            messages = [{"role": "system", "content": system_message}]
            messages.extend(conversation_history)
            messages.append({"role": "user", "content": prompt})
            
            # Smart truncation: remove oldest turns until we fit within token limit
            pre_truncation_tokens = None
            while True:
                formatted_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                test_inputs = tokenizer(formatted_prompt, return_tensors="pt", truncation=False)
                token_count = test_inputs["input_ids"].shape[1]
                pre_truncation_tokens = token_count

                if token_count <= max_input_length:
                    break

                if len(messages) > 2:
                    messages.pop(1)
                else:
                    break

            inputs = tokenizer(
                formatted_prompt,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=generation_params["max_input_length"]
            )

            input_token_count = inputs["input_ids"].shape[1]
            if input_token_count < pre_truncation_tokens:
                logger.warning(
                    "Prompt truncated from %s to %s tokens (max: %s)",
                    pre_truncation_tokens, input_token_count, generation_params["max_input_length"]
                )

            # Cap max_new_tokens to available context window space
            model_max_length = getattr(tokenizer, 'model_max_length', 3072)
            safe_max_new = min(generation_params["max_new_tokens"], model_max_length - input_token_count)
            if safe_max_new <= 0:
                raise ValueError(
                    "Input too long (%s tokens) — no room for generation (model max: %s)" % (input_token_count, model_max_length)
                )
            
            with torch.no_grad():
                outputs = model.generate(
                    inputs["input_ids"],
                    max_new_tokens=safe_max_new,
                    temperature=generation_params["temperature"],
                    top_p=generation_params["top_p"],
                    top_k=generation_params["top_k"],
                    repetition_penalty=generation_params["repetition_penalty"],
                    do_sample=generation_params["do_sample"],
                    pad_token_id=tokenizer.eos_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    use_cache=True,
                )
            
            input_length = inputs["input_ids"].shape[1]
            generated_tokens = outputs[0][input_length:]
            response = tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
            
            # Trim to last complete sentence to avoid mid-sentence cut-off
            # Only trim if response doesn't already end with sentence-ending punctuation
            if response and response[-1] not in '.?!':
                last_end = max(
                    response.rfind('.'),
                    response.rfind('?'),
                    response.rfind('!')
                )
                if last_end > len(response) // 2:  # Only trim if we keep at least half
                    response = response[:last_end + 1]
            
            return response
            
        except Exception as e:
            logger.error("Error generating response: %s", e)
            raise RuntimeError("Failed to generate response: %s" % str(e))
    
# Global model service instance
model_service = ModelService()

# Convenience functions
def get_qwen_model():
    """Get Qwen model and tokenizer"""
    return model_service.get_model()

def get_qwen_tokenizer():
    """Get Qwen tokenizer"""
    return model_service.get_tokenizer()

def is_qwen_available():
    """Check if Qwen is available"""
    return model_service.is_model_loaded()

def generate_qwen_response(prompt: str, **kwargs):
    """Generate response using Qwen"""
    return model_service.generate_response(prompt, **kwargs)