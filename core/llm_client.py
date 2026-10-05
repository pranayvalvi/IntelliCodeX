import json
import requests
from typing import Generator


import os

class OllamaLLM:
    def __init__(self, model: str = "qwen2.5-coder", host: str = None):
        self.model = model
        
        env_host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
        if not env_host.startswith("http"):
            env_host = f"http://{env_host}"
            
        self.host = (host or env_host).rstrip("/")

    def set_model(self, model: str):
        """Dynamically switches active Ollama LLM model."""
        self.model = model

    def generate(self, prompt: str, system: str = "", temperature: float = 0.2) -> str:
        try:
            resp = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=300,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except requests.exceptions.Timeout:
            return "Local Ollama AI generation timed out (exceeded 300s). Try asking a more targeted question."
        except Exception as e:
            return f"Error communicating with local Ollama AI model: {e}"

    def stream_generate(self, prompt: str, system: str = "", temperature: float = 0.2) -> Generator[str, None, None]:
        """Yields response text tokens in real-time streaming chunks."""
        try:
            resp = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": True,
                    "options": {"temperature": temperature},
                },
                stream=True,
                timeout=300,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("response", "")
                    if token:
                        yield token
        except Exception as e:
            yield f"\n[Error streaming from Ollama AI model: {e}]"

