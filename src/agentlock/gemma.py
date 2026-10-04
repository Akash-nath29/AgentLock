"""Gemma 4 evaluators: Ollama (default) and the Gemini API.

Gemma does the two jobs Python can't: turning an agent's instructions into
contracts, and judging semantic / multimodal criteria. Prompts spell out the
JSON shape and requests also pass a JSON schema (some backends ignore it); either
way the output is validated before use.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agentlock.evaluator import EvaluatorUnavailable, GenerationResult, extract_json, parse_contracts, parse_verdict
from agentlock.models import AgentSpec, EvaluationResult, MultimodalContract, SemanticContract, Trace

OLLAMA_DEFAULT_MODEL = "gemma4:31b-cloud"
GEMINI_DEFAULT_MODEL = "gemma-4-26b-a4b-it"
API_KEY_VARS = ("GEMMA_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")

# --------------------------------------------------------------------------- transports


def ollama_host() -> str:
    host = os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    return (host if "://" in host else f"http://{host}").rstrip("/")


def _ollama_request(path: str, body: dict[str, Any] | None = None, timeout: float = 300) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if os.environ.get("OLLAMA_API_KEY"):  # only needed when calling https://ollama.com directly
        headers["Authorization"] = f"Bearer {os.environ['OLLAMA_API_KEY']}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(ollama_host() + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def ollama_chat(model: str, messages: list[dict[str, Any]], **fields: Any) -> dict[str, Any]:
    """POST /api/chat without streaming. Retries rate limits and server errors twice."""
    body = {"model": model, "messages": messages, "stream": False, **fields}
    for attempt in range(3):
        try:
            return _ollama_request("/api/chat", body)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            detail = exc.read().decode(errors="replace")[:300]
            raise RuntimeError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise EvaluatorUnavailable(
                f"Ollama is not reachable at {ollama_host()} ({exc.reason}). Start it with `ollama serve`."
            ) from exc
    raise AssertionError("unreachable")


def make_client() -> Any:
    """A google-genai client authenticated from the environment."""
    key = next((os.environ[v] for v in API_KEY_VARS if os.environ.get(v)), None)
    if not key:
        raise EvaluatorUnavailable(
            "No Gemini API key found. Set GEMINI_API_KEY (or GEMMA_API_KEY); "
            "get one at https://aistudio.google.com/apikey"
        )
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise EvaluatorUnavailable("The gemini provider needs google-genai: pip install 'agentlock[gemini]'") from exc

    return genai.Client(api_key=key, http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=5)))


# --------------------------------------------------------------------------- prompts

CONTRACT_SYSTEM = """\
You are AgentLock's contract generator. You read an AI agent's configuration and \
write behavioral contracts: testable rules about how the agent must behave.

Contract types (use these exact field names):
- ordering: every call to `after` must be preceded by a call to `before`. Fields: before, after, \
optional match_argument (an argument name both tools take, e.g. "path", when the earlier call must \
target the same thing).
- required: `tool` must be called. With `after`, it must be called after the last call to `after`. \
Fields: tool, optional after.
- forbidden: `tool` must never be called. Fields: tool, optional arguments (a glob pattern per \
argument, e.g. {"path": "tests/*"}, to forbid only matching calls).
- conditional: when the most recent call to `when.tool` returned a result whose `when.field` equals \
`when.equals`, none of the `forbidden` tools may be called. Fields: when {tool, field, equals}, forbidden.
- semantic: criteria about the content of the agent's final response that need judgment. \
Fields: criteria (short statements, each independently checkable).

Rules:
1. Only encode requirements the configuration states or clearly implies. Do not invent policy.
2. If a rule is about tool calls, use ordering/required/forbidden/conditional. Use semantic only for \
the content of the final response.
   - "Do X before Y" (Y is not allowed until X happened) -> ordering, before=X, after=Y.
   - "After X, do Y" (Y must follow X) -> required, tool=Y, after=X. Not ordering: running Y \
earlier is fine.
3. Use only tool names from the tool list, and only result fields documented in a tool's `returns`.
4. Every contract is checked on every example task, so it must hold for all of them. Skip rules that \
only apply to some tasks (e.g. "opens a PR" when some tasks must not open one), and phrase semantic \
criteria conditionally when needed (e.g. "If code was changed, says what changed").
5. id: short kebab-case, unique. description: one plain-English sentence.

Respond with JSON only, in exactly this shape (tool names here are placeholders):
{"contracts": [
  {"id": "fetch-before-update", "description": "...", "type": "ordering", "before": "fetch_record", "after": "update_record"},
  {"id": "no-send-on-error", "description": "...", "type": "conditional", \
"when": {"tool": "validate", "field": "ok", "equals": false}, "forbidden": ["send_email"]},
  {"id": "summarizes-result", "description": "...", "type": "semantic", \
"criteria": ["If a record was updated, says which one", "States whether validation passed"]}
]}"""

CONTRACTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contracts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "type": {"type": "string", "enum": ["ordering", "required", "forbidden", "conditional", "semantic"]},
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "match_argument": {"type": "string"},
                    "tool": {"type": "string"},
                    "arguments": {"type": "object", "additionalProperties": {"type": "string"}},
                    "when": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string"},
                            "field": {"type": "string"},
                            "equals": {"anyOf": [{"type": "boolean"}, {"type": "number"}, {"type": "string"}]},
                        },
                        "required": ["tool", "field", "equals"],
                    },
                    "forbidden": {"type": "array", "items": {"type": "string"}},
                    "criteria": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "description", "type"],
            },
        }
    },
    "required": ["contracts"],
}

_VERDICT_FORMAT = (
    'Respond with JSON only: {"criteria": [{"criterion": str, "passed": bool, "reason": str}, ...], '
    '"score": number between 0 and 1, "explanation": str}. Give exactly one criteria entry per '
    "criterion, in the order given."
)

SEMANTIC_SYSTEM = f"""\
You are a strict evaluator for AgentLock. Judge whether an AI agent's final response meets each \
criterion. A criterion passes only if the response clearly satisfies it. The tool trace is ground \
truth for what actually happened: if the response claims something the trace contradicts (e.g. says \
tests passed when they failed), the related criterion fails.
{_VERDICT_FORMAT}"""

IMAGE_SYSTEM = f"""\
You are a strict visual QA evaluator for AgentLock. Inspect the screenshot and judge each criterion \
from what is visible. A criterion passes only if the image clearly satisfies it.
{_VERDICT_FORMAT}"""

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "passed": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["criterion", "passed", "reason"],
            },
        },
        "score": {"type": "number"},
        "explanation": {"type": "string"},
    },
    "required": ["criteria", "score", "explanation"],
}


def _short(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_trace(trace: Trace) -> str:
    """A compact, model-readable rendering of the tool calls in a trace."""
    lines = []
    for i, call in enumerate(trace.tool_calls, 1):
        args = ", ".join(f"{k}={_short(v, 60)}" for k, v in call.arguments.items())
        outcome = f"ERROR {call.error}" if call.error else _short(call.result, 240)
        lines.append(f"{i}. {call.name}({args}) -> {outcome}")
    return "\n".join(lines) or "(no tool calls)"


def _numbered(criteria: list[str]) -> str:
    return "\n".join(f"{i}. {c}" for i, c in enumerate(criteria, 1))


# --------------------------------------------------------------------------- evaluators

Image = tuple[bytes, str]  # (data, mime type)


class GemmaEvaluator:
    """`ModelEvaluator` for Gemma 4. Subclasses implement `_complete` for one API."""

    name: str
    temperature: float

    def _complete(self, system: str, text: str, schema: dict[str, Any], image: Image | None = None) -> str:
        raise NotImplementedError

    def generate_contracts(self, spec: AgentSpec, examples: list[str]) -> GenerationResult:
        agent = {
            "system_prompt": spec.system_prompt,
            "skills": [s.model_dump() for s in spec.skills],
            "tools": [t.model_dump() for t in spec.tools],
            "example_tasks": examples,
        }
        prompt = "Agent configuration:\n" + json.dumps(agent, indent=2)
        data = extract_json(self._complete(CONTRACT_SYSTEM, prompt, CONTRACTS_SCHEMA))
        return parse_contracts(data, spec, source=f"generated:{self.name}")

    def evaluate(self, contract: SemanticContract, trace: Trace) -> EvaluationResult:
        prompt = (
            f"Task given to the agent:\n{trace.task}\n\n"
            f"Criteria:\n{_numbered(contract.criteria)}\n\n"
            f"Tool trace:\n{format_trace(trace)}\n\n"
            f"Final response:\n{trace.output or '(empty)'}"
        )
        return self._judge(SEMANTIC_SYSTEM, prompt, contract.criteria)

    def evaluate_image(self, contract: MultimodalContract, image: Path) -> EvaluationResult:
        mime = mimetypes.guess_type(image.name)[0] or "image/png"
        return self._judge(IMAGE_SYSTEM, f"Criteria:\n{_numbered(contract.criteria)}", contract.criteria, (image.read_bytes(), mime))

    def _judge(self, system: str, text: str, criteria: list[str], image: Image | None = None) -> EvaluationResult:
        try:
            data = extract_json(self._complete(system, text, VERDICT_SCHEMA, image))
        except Exception as exc:  # API or parse failure is an error, never a pass
            return EvaluationResult(status="error", explanation=f"{type(exc).__name__}: {exc}")
        return parse_verdict(data, criteria)


class OllamaEvaluator(GemmaEvaluator):
    """Gemma 4 through Ollama's /api/chat: a local model or an Ollama cloud model such as gemma4:31b-cloud."""

    def __init__(self, model: str = OLLAMA_DEFAULT_MODEL, temperature: float = 0.0, check: bool = True) -> None:
        self.model = self.name = model
        self.temperature = temperature
        if check:
            try:
                available = {m["name"] for m in _ollama_request("/api/tags", timeout=5).get("models", [])}
            except (urllib.error.URLError, OSError) as exc:
                raise EvaluatorUnavailable(
                    f"Ollama is not reachable at {ollama_host()}. Start it with `ollama serve` (or set OLLAMA_HOST)."
                ) from exc
            if model not in available and f"{model}:latest" not in available:
                raise EvaluatorUnavailable(f"Ollama has no model {model!r}. Run `ollama pull {model}`.")

    def _complete(self, system: str, text: str, schema: dict[str, Any], image: Image | None = None) -> str:
        user: dict[str, Any] = {"role": "user", "content": text}
        if image:
            user["images"] = [base64.b64encode(image[0]).decode()]
        messages = [{"role": "system", "content": system}, user]
        response = ollama_chat(self.model, messages, format=schema, options={"temperature": self.temperature})
        return response["message"].get("content") or ""


class GeminiEvaluator(GemmaEvaluator):
    """Gemma 4 through the Gemini API (google-genai). Falls back to prompt-only JSON
    if the model rejects structured output."""

    def __init__(self, model: str = GEMINI_DEFAULT_MODEL, temperature: float = 0.0, client: Any = None) -> None:
        self.model = self.name = model
        self.temperature = temperature
        self.client = client or make_client()
        self._structured = True

    def _complete(self, system: str, text: str, schema: dict[str, Any], image: Image | None = None) -> str:
        from google.genai import errors, types

        contents: Any = [types.Part.from_bytes(data=image[0], mime_type=image[1]), text] if image else text
        base = {"system_instruction": system, "temperature": self.temperature}
        if self._structured:
            try:
                config = types.GenerateContentConfig(**base, response_mime_type="application/json", response_json_schema=schema)
                return self.client.models.generate_content(model=self.model, contents=contents, config=config).text or ""
            except errors.ClientError as exc:
                if exc.code != 400:
                    raise
                # ponytail: treat any 400 as "structured output unsupported"; a real bad request fails again below.
                self._structured = False
        config = types.GenerateContentConfig(**base)
        return self.client.models.generate_content(model=self.model, contents=contents, config=config).text or ""
