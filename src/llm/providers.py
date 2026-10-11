"""Ollama local chat API with JSON Schema constrained output, no SDK needed."""

from dataclasses import dataclass
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .verifier import strict_json_loads


class ProviderError(RuntimeError):
    """Safe diagnostic codes; never include prompt, response or network body."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class OllamaProvider:
    model: str
    base_url: str = "http://127.0.0.1:11434"
    timeout: float = 90.0
    name: str = "OLLAMA"

    def __post_init__(self):
        parsed = urlsplit(self.base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise ValueError("Ollama URL must be a local HTTP origin")
        if not isinstance(self.model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", self.model):
            raise ValueError("Set a valid local Ollama model name")
        if not math.isfinite(self.timeout) or not 1 <= self.timeout <= 300:
            raise ValueError("Ollama timeout must be between 1 and 300 seconds")

    @classmethod
    def from_env(cls):
        return cls(model=os.environ.get("OLLAMA_MODEL", ""),
                   base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                   timeout=float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "90")))

    def generate(self, messages, schema):
        body = json.dumps({"model": self.model, "messages": messages, "stream": False,
                           "format": schema, "options": {"temperature": 0, "seed": 2026,
                                                         "num_ctx": 8192, "num_predict": 4096}}, allow_nan=False).encode()
        request = Request(self.base_url.rstrip("/") + "/api/chat", body,
                          {"Content-Type": "application/json"}, method="POST")
        # Local requests bypass environment proxy settings and never redirect.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ProviderError("OLLAMA_RESPONSE_TOO_LARGE")
            result = strict_json_loads(raw)
            if not isinstance(result, dict) or result.get("done") is not True:
                raise ProviderError("OLLAMA_RESPONSE_INCOMPLETE")
            if result.get("done_reason") not in (None, "stop"):
                raise ProviderError("OLLAMA_RESPONSE_INCOMPLETE")
            content = result.get("message", {}).get("content")
            if not isinstance(content, str):
                raise ProviderError("OLLAMA_RESPONSE_INVALID")
            return strict_json_loads(content)
        except HTTPError:
            raise ProviderError("OLLAMA_HTTP_ERROR") from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("OLLAMA_UNAVAILABLE") from None
        except (ValueError, TypeError, AttributeError):
            raise ProviderError("OLLAMA_RESPONSE_INVALID") from None
