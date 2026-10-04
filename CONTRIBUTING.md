# Contributing to AgentLock

Thanks for helping. AgentLock is small on purpose. Keep changes focused.

## Setup

```bash
pip install -e ".[dev]"
pytest
```

The test suite needs no network, no Ollama and no API key. A fixture makes Ollama look unreachable and strips Gemini keys. The Ollama evaluator is tested against a local fake server, and the Gemini evaluator against a fake client.

To try the real model, run `ollama pull gemma4:31b-cloud`, then run `agentlock generate` and `agentlock test` in `demo/`.

## Ground rules

- **Use Python whenever Python can decide.** If a rule is about tool calls, arguments or results, write a deterministic contract type for it. Only content that needs judgment goes to a model.
- **Never trust model output.** Validate every model response (`parse_contracts`, `parse_verdict`). Malformed output is an `error`, never a pass.
- **No faked model results.** Mocks belong in tests only, and they must say so in their output.
- **Few dependencies.** Ask in an issue before adding one.

## Adding a contract type

1. Add a model in `src/agentlock/models.py` and include it in the `Contract` union.
2. If it's deterministic, add a checker in `validators.py`, register it in `check()`, describe it in `describe_rule()`, and add the type to `DETERMINISTIC_TYPES`.
3. If models should generate it, describe it in `CONTRACT_SYSTEM` and add its fields to `CONTRACTS_SCHEMA` in `gemma.py`.
4. Add tests to `tests/test_validators.py` covering pass, fail, and "not triggered".

## Adding a model provider

Implement the `ModelEvaluator` protocol in `evaluator.py` (`generate_contracts`, `evaluate`, `evaluate_image`), pass every response through `parse_contracts` / `parse_verdict`, and register it in `core.build_evaluator`.

## Pull requests

- `pytest` passes.
- New behavior has a test.
- User-facing changes are reflected in `README.md`.
