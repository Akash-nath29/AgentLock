import urllib.error
import urllib.request

import pytest

from agentlock.gemma import API_KEY_VARS

UNREACHABLE = "http://ollama.invalid"
_real_urlopen = urllib.request.urlopen


def _urlopen(request, *args, **kwargs):
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    if url.startswith(UNREACHABLE):  # fail instantly; a closed port takes ~2s to refuse on Windows
        raise urllib.error.URLError("connection refused (test)")
    return _real_urlopen(request, *args, **kwargs)


@pytest.fixture(autouse=True)
def no_real_models(monkeypatch):
    """Unit tests never talk to a real model: no Gemini keys, and Ollama is 'not running'."""
    for var in (*API_KEY_VARS, "OLLAMA_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OLLAMA_HOST", UNREACHABLE)
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
