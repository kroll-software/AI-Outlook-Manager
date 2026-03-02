# core/model_provider.py

import os
import json
import logging
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel, tracing, TracingProcessor
from core.setting_manager import get_setting
import ollama
import openai
import threading
from core.local_trace_processor import LocalTraceProcessor

_tracing_processor = LocalTraceProcessor()
tracing.set_trace_processors([_tracing_processor])
tracing.set_tracing_disabled(False)

def get_tracing_processor():
    return _tracing_processor

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai.agents").setLevel(logging.CRITICAL)

LLM_REQUEST_TIMEOUT = 1200  # Seconds
CONTEXT_LENGTH = 48 * 1024

def fetch_openai_models(api_key):
    openai.api_key = api_key
    resp = openai.Model.list()
    return [m["id"] for m in resp["data"]]

# sinnvoller Grenzwert je nach Modell
openai_max_context = {
    "gpt-3.5-turbo": 16_384,
    "gpt-4": 8_192,
    "gpt-4-32k": 32_768,
    "gpt-4-turbo": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-5": 128_000,
    "gpt-5-mini": 128_000,
    "gpt-5-nano": 128_000,    
}

def list_tool_capable_ollama_models():
    tool_models = []
    response = ollama.list()
    for model in response.models:
        try:
            details = ollama.show(model.model)
            if "tools" in details.capabilities:
                tool_models.append(model.model)
        except Exception as e:
            print(f"⚠️ Fehler bei {model.model}: {e}")
    return tool_models

def _parse_parameters(params_str: str):
    lines = params_str.strip().splitlines()
    result = {}
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            key, value = parts
            result[key] = value.strip()
    return result

def _load_openai_models() -> list:
    try:
        path = "openai-models.json"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

class ModelProvider:
    def __init__(self):
        self.model = None
        self.client = None
        self.num_ctx = 4096
        self.openai_models = _load_openai_models()        

    def list_openai_models(self) -> list:
        return [m.get("model") for m in self.openai_models]   

    def get_num_ctx(self) -> int:
        return self.num_ctx

    def load(self):        
        provider = get_setting("provider", "openai")        
        timeout = LLM_REQUEST_TIMEOUT

        if provider == "openai":
            model_name = get_setting("openai_model", "gpt-4o")
            api_key = get_setting("openai_api_key", "", encrypted=True)
            self.client = AsyncOpenAI(api_key=api_key, timeout=timeout)            

            for m in self.openai_models:
                if (m.get("model") == model_name):
                    self.num_ctx = m.get("n_ctx") 
                    break
        elif provider == "ollama":
            # Default: Ollama            
            model_name = get_setting("ollama_model", "gpt-oss:20b")
            base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")            
            self.client = AsyncOpenAI(api_key="ollama", base_url=base_url, timeout=timeout)
            
            try:
                response = ollama.show(model_name)        
                params = _parse_parameters(response.parameters)
                self.num_ctx = int(params.get("num_ctx", 4096))
            except:
                self.num_ctx = 4096

        else:
            #Generic Model
            model_name = get_setting("generic_model", "")
            base_url = get_setting("generic_endpoint", "")
            api_key = get_setting("generic_api_key", "", encrypted=True)
            try:
                self.num_ctx = int(get_setting("generic_num_ctx", 4096))
            except:
                self.num_ctx = 4096
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        
        self.model = OpenAIChatCompletionsModel(
            model=model_name,
            openai_client=self.client
        )        

    def get_model(self):
        if not self.model:
            self.load()
        return self.model

# Singleton

_model_provider = None

def reset_model():
    global _model_provider
    if _model_provider:
        _model_provider.load()

def get_model():
    global _model_provider
    if not _model_provider:
        _model_provider = ModelProvider()
    return _model_provider.get_model()
    
def get_model_ctx_size() -> int:
    global _model_provider
    if not _model_provider:
        _model_provider = ModelProvider()
    return _model_provider.get_num_ctx()    

def list_openai_models() -> list:
    global _model_provider
    if not _model_provider:
        _model_provider = ModelProvider()
    return _model_provider.list_openai_models()