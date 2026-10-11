import io
import json
from urllib.error import HTTPError, URLError

import pytest

from src.llm.__main__ import main
from src.llm.evaluate import scenarios
from src.llm.evaluate import main as evaluate_main
from src.llm.providers import OllamaProvider, ProviderError
from src.llm.verifier import strict_json_loads


@pytest.mark.parametrize("url", ["https://api.example.com", "https://ollama.com/path", "http://127.0.0.1:11434/path",
                                "http://user:password@localhost", "http://localhost?token=secret"])
def test_provider_rejects_nonlocal_or_ambiguous_origins(url):
    with pytest.raises(ValueError):
        OllamaProvider("my-local-model", url)


def test_provider_requires_model_and_bounded_timeout(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ValueError):
        OllamaProvider.from_env()
    with pytest.raises(ValueError):
        OllamaProvider("model", timeout=float("nan"))
    monkeypatch.setenv("OLLAMA_MODEL", "installed-model:latest")
    assert OllamaProvider.from_env().model == "installed-model:latest"


def mock_response(monkeypatch, envelope):
    raw = envelope if isinstance(envelope, bytes) else json.dumps(envelope).encode()
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            return io.BytesIO(raw)
    monkeypatch.setattr("src.llm.providers.build_opener", lambda *args: Opener())
    return calls


def test_local_chat_request_uses_structured_schema(monkeypatch):
    plan = {"headline_variant": None, "customer": [], "manager": []}
    calls = mock_response(monkeypatch, {"done": True, "message": {"content": json.dumps(plan)}})
    schema = {"type": "object"}
    assert OllamaProvider("installed-model").generate([{"role": "user", "content": "approved facts"}], schema) == plan
    request, timeout = calls[0]
    body = json.loads(request.data)
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    assert body["stream"] is False and body["format"] == schema
    assert body["options"]["temperature"] == 0 and timeout == 90


def test_cloud_chat_request_uses_bearer_key(monkeypatch):
    plan = {"headline_variant": None, "customer": [], "manager": []}
    calls = mock_response(monkeypatch, {"done": True, "message": {"content": json.dumps(plan)}})
    provider = OllamaProvider("gemma4:31b", "https://ollama.com", api_key="private-key")
    assert provider.generate([], {"type": "object"}) == plan
    request, _ = calls[0]
    assert request.full_url == "https://ollama.com/api/chat"
    assert request.get_header("Authorization") == "Bearer private-key"


def test_cloud_chat_requires_key():
    with pytest.raises(ValueError):
        OllamaProvider("gemma4:31b", "https://ollama.com")


@pytest.mark.parametrize("envelope", [
    {"done": False, "message": {"content": "{}"}},
    {"done": True, "done_reason": "length", "message": {"content": "{}"}},
    {"done": True, "message": {"content": "not JSON"}},
    {"done": True, "message": {"content": '{"id":1,"id":2}'}},
    {"done": True, "message": None},
    b"not json", b"x" * 1_048_577,
])
def test_invalid_transport_output_is_rejected(monkeypatch, envelope):
    mock_response(monkeypatch, envelope)
    with pytest.raises(ProviderError):
        OllamaProvider("model").generate([], {})


@pytest.mark.parametrize("error", [TimeoutError("private data"), URLError("private data"),
                                   HTTPError("local", 500, "private data", {}, None)])
def test_network_errors_do_not_expose_provider_body(monkeypatch, error):
    class Opener:
        def open(self, *args, **kwargs):
            raise error
    monkeypatch.setattr("src.llm.providers.build_opener", lambda *args: Opener())
    with pytest.raises(ProviderError) as caught:
        OllamaProvider("model").generate([], {})
    assert "private data" not in str(caught.value)


@pytest.mark.parametrize("value", ['{"key":1,"key":2}', '{"key": NaN}', '{"key": Infinity}'])
def test_json_parser_rejects_ambiguous_or_nonfinite_values(value):
    with pytest.raises(ValueError):
        strict_json_loads(value)


def test_cli_jsonl_and_input_preservation(tmp_path, capsys):
    source, output = tmp_path / "input.jsonl", tmp_path / "output.jsonl"
    source.write_text("\n".join(json.dumps(r) for _, r in scenarios()))
    before = source.read_bytes()
    assert main(["--records", str(source), "--output", str(output)]) == 0
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(records) == 8 and source.read_bytes() == before
    assert "C10001" not in capsys.readouterr().out
    assert main(["--records", str(source), "--output", str(output)]) == 1
    assert main(["--records", str(source), "--output", str(source)]) == 1


def test_cli_invalid_batch_writes_nothing(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text(json.dumps([scenarios()[0][1], {"malformed": "private data"}]))
    assert main(["--records", str(source), "--output", str(output)]) == 1
    assert not output.exists()


def test_cli_strict_mode_reports_fallback(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text(json.dumps(scenarios()[0][1]))
    assert main(["--records", str(source), "--output", str(output), "--require-llm"]) == 1
    assert json.loads(output.read_text())["explanation"]["status"] == "FALLBACK_USED"


def test_evaluation_configuration_error_does_not_expose_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "private configuration")
    output = tmp_path / "evaluation.json"
    assert evaluate_main(["--provider", "ollama", "--output", str(output)]) == 1
    assert "private configuration" not in capsys.readouterr().err
    assert not output.exists()
