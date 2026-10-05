import pytest
import os
from core.llm_client import OllamaLLM
from core.embedder import OllamaEmbedder

def test_ollama_host_normalization_llm():
    # Test without scheme
    llm1 = OllamaLLM(host="127.0.0.1:11434")
    assert llm1.host == "http://127.0.0.1:11434"

    # Test with scheme
    llm2 = OllamaLLM(host="http://127.0.0.1:11434")
    assert llm2.host == "http://127.0.0.1:11434"
    
    # Test fallback to env if host is None
    os.environ["OLLAMA_HOST"] = "192.168.1.100:11434"
    llm3 = OllamaLLM(host=None)
    assert llm3.host == "http://192.168.1.100:11434"
    
    os.environ["OLLAMA_HOST"] = "https://my-secure-ollama.com"
    llm4 = OllamaLLM(host=None)
    assert llm4.host == "https://my-secure-ollama.com"
    
    # Test trailing slash removal
    llm5 = OllamaLLM(host="http://127.0.0.1:11434/")
    assert llm5.host == "http://127.0.0.1:11434"
    
    # Test trailing slash removal via env var
    os.environ["OLLAMA_HOST"] = "192.168.1.100/"
    llm6 = OllamaLLM(host=None)
    assert llm6.host == "http://192.168.1.100"

def test_ollama_host_normalization_embedder():
    # Test without scheme
    emb1 = OllamaEmbedder(host="127.0.0.1:11434")
    assert emb1.host == "http://127.0.0.1:11434"

    # Test with scheme
    emb2 = OllamaEmbedder(host="http://127.0.0.1:11434")
    assert emb2.host == "http://127.0.0.1:11434"
