import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest
from google.genai import errors

from agentlock import AgentLockTracer, AgentSpec, ModelSpec, MultimodalContract, SemanticContract, ToolSpec
from agentlock.evaluator import EvaluatorUnavailable, extract_json, parse_contracts, parse_verdict
from agentlock.gemma import GeminiEvaluator, OllamaEvaluator

SPEC = AgentSpec(
    name="a",
    model=ModelSpec(name="m"),
    tools=[ToolSpec(name=n) for n in ("read_file", "write_file", "run_tests", "create_pull_request")],
)


# ------------------------------------------------------------------ JSON recovery


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Sure, here is the result:\n{"a": 1}\nHope that helps.',
    ],
)
def test_extract_json_recovers_common_wrappers(text):
    assert extract_json(text) == {"a": 1}


def test_extract_json_raises_on_garbage():
    with pytest.raises(ValueError):
        extract_json("I think it passed.")


# ------------------------------------------------------------------ contracts


def test_parse_contracts_validates_and_rejects():
    data = {
        "contracts": [
            # unused fields of the flat schema come back as null / "" / []
            {"id": "read-first", "type": "ordering", "before": "read_file", "after": "write_file",
             "tool": None, "criteria": [], "match_argument": ""},
            {"id": "no-pr", "type": "conditional", "forbidden": ["create_pull_request"],
             "when": {"tool": "run_tests", "field": "passed", "equals": False}},
            {"id": "explain", "type": "semantic", "criteria": ["Explains the change"]},
            {"id": "ghost", "type": "forbidden", "tool": "delete_repo"},
            {"id": "bad-type", "type": "vibes"},
            {"id": "missing", "type": "ordering", "before": "read_file"},
            {"id": "shot", "type": "multimodal", "artifact": "s", "criteria": ["x"]},
            {"id": "read-first", "type": "forbidden", "tool": "write_file"},
        ]
    }
    result = parse_contracts(data, SPEC, source="generated:test")
    assert [c.id for c in result.contracts] == ["read-first", "no-pr", "explain"]
    assert all(c.source == "generated:test" for c in result.contracts)
    assert result.contracts[0].match_argument is None
    rejected = "\n".join(result.rejected)
    assert "unknown tool(s) delete_repo" in rejected
    assert "bad-type" in rejected and "missing" in rejected
    assert "written by hand" in rejected and "duplicate id" in rejected


def test_parse_contracts_requires_a_list():
    with pytest.raises(ValueError):
        parse_contracts({"rules": []}, SPEC, source="x")


# ------------------------------------------------------------------ verdicts

CRITERIA = ["mentions the file", "states test result"]


def test_parse_verdict_computes_pass_itself():
    data = {
        "passed": True,  # the model's own overall verdict is ignored
        "criteria": [{"criterion": "x", "passed": True, "reason": ""}, {"criterion": "y", "passed": False, "reason": "no"}],
        "score": 0.5,
        "explanation": "half",
    }
    result = parse_verdict(data, CRITERIA)
    assert result.status == "failed"
    assert [c.criterion for c in result.criteria] == CRITERIA


@pytest.mark.parametrize(
    "data",
    [
        {"criteria": [{"passed": True}]},  # wrong count
        {"criteria": [{"passed": "yes"}, {"passed": True}]},  # not a bool
        {"criteria": [{"passed": True}, {"passed": True}], "score": 7},  # score out of range
        {"verdict": "pass"},  # missing criteria
        ["not", "an", "object"],
    ],
)
def test_malformed_verdict_is_an_error_never_a_pass(data):
    assert parse_verdict(data, CRITERIA).status == "error"


# ------------------------------------------------------------------ shared fixtures


def _trace():
    tracer = AgentLockTracer()
    with tracer.trace("fix the bug") as trace:
        tracer.record_tool_call("run_tests", {}, {"passed": True})
        trace.output = "Changed auth.py; tests passed."
    return trace


VERDICT = json.dumps(
    {"criteria": [{"criterion": c, "passed": True, "reason": "ok"} for c in CRITERIA], "score": 0.9, "explanation": "good"}
)
SEMANTIC = SemanticContract(id="s", criteria=CRITERIA)


# ------------------------------------------------------------------ Ollama evaluator (local fake server)


@pytest.fixture
def ollama(monkeypatch):
    """A fake Ollama server. Queue (status, content) replies in `.replies`; inspect `.requests`."""
    state = SimpleNamespace(requests=[], replies=[], models=["gemma4:31b-cloud"])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(200, {"models": [{"name": m} for m in state.models]})

        def do_POST(self):
            state.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            code, content = state.replies.pop(0)
            self._send(code, {"message": {"role": "assistant", "content": content}} if code == 200 else {"error": content})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    monkeypatch.setenv("OLLAMA_HOST", f"127.0.0.1:{server.server_port}")
    monkeypatch.setattr("agentlock.gemma.time.sleep", lambda s: None)
    yield state
    server.shutdown()


def test_ollama_semantic_evaluation_request(ollama):
    ollama.replies.append((200, VERDICT))
    result = OllamaEvaluator(model="gemma4:31b-cloud").evaluate(SEMANTIC, _trace())
    assert result.status == "passed" and result.score == 0.9
    body = ollama.requests[0]
    assert body["model"] == "gemma4:31b-cloud" and body["stream"] is False
    assert body["format"]["required"] == ["criteria", "score", "explanation"]
    assert body["options"] == {"temperature": 0.0}
    system, user = body["messages"]
    assert system["role"] == "system" and "strict evaluator" in system["content"]
    assert "run_tests() -> " in user["content"] and "tests passed" in user["content"]


def test_ollama_recovers_fenced_json(ollama):
    # Ollama cloud models may ignore `format` and wrap JSON in a code fence.
    ollama.replies.append((200, "```json\n" + VERDICT + "\n```"))
    assert OllamaEvaluator().evaluate(SEMANTIC, _trace()).status == "passed"


def test_ollama_sends_images_as_base64(ollama, tmp_path):
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG fake")
    ollama.replies.append((200, VERDICT))
    contract = MultimodalContract(id="m", artifact="screenshot", criteria=CRITERIA)
    assert OllamaEvaluator().evaluate_image(contract, image).status == "passed"
    user = ollama.requests[0]["messages"][1]
    assert base64.b64decode(user["images"][0]) == b"\x89PNG fake"


def test_ollama_retries_rate_limits(ollama):
    ollama.replies += [(429, "slow down"), (503, "busy"), (200, VERDICT)]
    assert OllamaEvaluator().evaluate(SEMANTIC, _trace()).status == "passed"
    assert len(ollama.requests) == 3


def test_ollama_http_error_is_an_error_result(ollama):
    ollama.replies.append((400, "bad request"))
    result = OllamaEvaluator().evaluate(SEMANTIC, _trace())
    assert result.status == "error" and "HTTP 400" in result.explanation


def test_ollama_generates_validated_contracts(ollama):
    ollama.replies.append((200, json.dumps({"contracts": [
        {"id": "read-first", "description": "d", "type": "ordering", "before": "read_file", "after": "write_file"},
        {"id": "hallucinated", "description": "d", "type": "forbidden", "tool": "rm_rf"},
    ]})))
    result = OllamaEvaluator().generate_contracts(SPEC, ["fix a bug"])
    assert [c.id for c in result.contracts] == ["read-first"]
    assert result.contracts[0].source == "generated:gemma4:31b-cloud"
    assert len(result.rejected) == 1
    assert "fix a bug" in ollama.requests[0]["messages"][1]["content"]


def test_ollama_missing_model(ollama):
    with pytest.raises(EvaluatorUnavailable, match="ollama pull gemma4:e4b"):
        OllamaEvaluator(model="gemma4:e4b")


def test_ollama_not_running():
    with pytest.raises(EvaluatorUnavailable, match="ollama serve"):
        OllamaEvaluator()


# ------------------------------------------------------------------ Gemini evaluator (fake client)


class FakeClient:
    """Stands in for google.genai.Client: `client.models.generate_content(...)`."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(text=response)


def _api_error(cls, code, message):
    return cls(code, {"error": {"code": code, "message": message, "status": "X"}})


def test_gemini_semantic_evaluation_uses_structured_output():
    client = FakeClient(VERDICT)
    result = GeminiEvaluator(model="gemma-4-26b-a4b-it", client=client).evaluate(SEMANTIC, _trace())
    assert result.status == "passed" and result.score == 0.9
    request = client.requests[0]
    assert request["model"] == "gemma-4-26b-a4b-it"
    assert request["config"].response_mime_type == "application/json"
    assert request["config"].response_json_schema is not None
    assert "run_tests() -> " in request["contents"] and "tests passed" in request["contents"]


def test_gemini_falls_back_when_structured_output_is_rejected():
    client = FakeClient(_api_error(errors.ClientError, 400, "JSON mode is not enabled"), "```json\n" + VERDICT + "\n```", VERDICT)
    evaluator = GeminiEvaluator(client=client)
    assert evaluator.evaluate(SEMANTIC, _trace()).status == "passed"
    assert client.requests[1]["config"].response_mime_type is None
    evaluator.evaluate(SEMANTIC, _trace())
    assert len(client.requests) == 3  # remembered: no second structured attempt


def test_gemini_malformed_output_is_an_error():
    result = GeminiEvaluator(client=FakeClient("Looks great to me!")).evaluate(SEMANTIC, _trace())
    assert result.status == "error"


def test_gemini_api_failure_is_an_error():
    client = FakeClient(_api_error(errors.ServerError, 503, "overloaded"))
    result = GeminiEvaluator(client=client).evaluate(SEMANTIC, _trace())
    assert result.status == "error" and "overloaded" in result.explanation


def test_gemini_image_evaluation_sends_image_bytes(tmp_path):
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG fake")
    client = FakeClient(VERDICT)
    contract = MultimodalContract(id="m", artifact="screenshot", criteria=CRITERIA)
    assert GeminiEvaluator(client=client).evaluate_image(contract, image).status == "passed"
    part = client.requests[0]["contents"][0]
    assert part.inline_data.mime_type == "image/png" and part.inline_data.data == b"\x89PNG fake"


def test_gemini_requires_credentials():
    with pytest.raises(EvaluatorUnavailable, match="GEMINI_API_KEY"):
        GeminiEvaluator()
