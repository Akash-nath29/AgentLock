"""A small simulated coding agent for the AgentLock demo.

Two interchangeable "brains" decide which tools to call:

- gemma:    Gemma 4 (via Ollama, e.g. gemma4:31b-cloud) reads the system prompt +
            skills and drives the tools through function calling.
- scripted: a deterministic stand-in so the demo and CI run offline. It maps the
            demo's known tasks to fixed playbooks and does NOT read the prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentlock import AgentSpec, ModelSpec, SkillSpec

from coding_agent.tools import TOOL_SPECS, Workspace

HERE = Path(__file__).parent


class CodingAgent:
    def __init__(
        self,
        brain: str = "scripted",
        prompt: str = "prompts/careful.md",
        model: str = "gemma4:31b-cloud",
        temperature: float = 0.0,
        workflow: str = "careful",
        ui_build: str = "good",
        max_steps: int = 20,
    ) -> None:
        if brain not in ("scripted", "gemma"):
            raise ValueError(f"brain must be 'scripted' or 'gemma', got {brain!r}")
        if workflow not in ("careful", "pr-first"):
            raise ValueError(f"workflow must be 'careful' or 'pr-first', got {workflow!r}")
        self.brain, self.model, self.temperature = brain, model, temperature
        self.workflow, self.ui_build, self.max_steps = workflow, ui_build, max_steps
        self.system_prompt = (HERE / prompt).read_text(encoding="utf-8")
        self.skills = [SkillSpec(name=p.stem, content=p.read_text(encoding="utf-8")) for p in sorted((HERE / "skills").glob("*.md"))]
        if brain == "gemma":
            model_spec = ModelSpec(provider="ollama", name=model, parameters={"temperature": temperature})
            config: dict[str, Any] = {"max_steps": max_steps}
        else:
            model_spec = ModelSpec(provider="scripted", name="deterministic-playbook")
            config = {"workflow": workflow}
        self.spec = AgentSpec(
            name="coding-agent",
            model=model_spec,
            system_prompt=self.system_prompt,
            skills=self.skills,
            tools=TOOL_SPECS,
            config=config,
        )

    def run(self, task: str) -> str:
        workspace = Workspace(ui_build=self.ui_build)
        try:
            if self.brain == "gemma":
                return self._run_gemma(task, workspace)
            return run_scripted(task, workspace, self.workflow)
        finally:
            workspace.close()

    # ------------------------------------------------------------------ Gemma brain

    def _run_gemma(self, task: str, ws: Workspace) -> str:
        from agentlock.gemma import ollama_chat

        system = self.system_prompt + "".join(f"\n\n## Skill: {s.name}\n{s.content}" for s in self.skills)
        tools = [
            {"type": "function", "function": {"name": t.name, "description": f"{t.description} Returns {t.returns}.", "parameters": t.parameters}}
            for t in TOOL_SPECS
        ]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": task}]
        for _ in range(self.max_steps):
            message = ollama_chat(self.model, messages, tools=tools, options={"temperature": self.temperature})["message"]
            calls = message.get("tool_calls") or []
            if not calls:
                return message.get("content") or ""
            messages.append(message)
            for call in calls:
                name, args = call["function"]["name"], call["function"].get("arguments") or {}
                if isinstance(args, str):
                    args = json.loads(args)
                result = self._call_tool(ws, name, args)
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, default=str)})
        return f"Stopped after {self.max_steps} steps without finishing."

    @staticmethod
    def _call_tool(ws: Workspace, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in {t.name for t in TOOL_SPECS}:
            return {"error": f"unknown tool {name!r}"}
        try:
            return {"result": getattr(ws, name)(**args)}
        except Exception as exc:  # report tool errors back to the model
            return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------- scripted brain

# task keyword -> (search query, file, old text, new text, what changed, why)
PLAYBOOKS = {
    "expir": (
        "expires_at",
        "auth.py",
        'return token["expires_at"] > now',
        'return token["expires_at"] <= now',
        "inverted the comparison in is_token_expired to `expires_at <= now`",
        "the check was backwards, so tokens that were still valid were reported as expired",
    ),
    "empty password": (
        "check_password",
        "auth.py",
        "if not password:\n        return False",
        'if not password:\n        return username == "guest"',
        "let the guest account log in with an empty password in check_password",
        "product asked for password-less guest logins",
    ),
}


def run_scripted(task: str, ws: Workspace, workflow: str) -> str:
    """Deterministic playbooks for the demo's tasks. `workflow='pr-first'` is Regression B."""
    lowered = task.lower()
    if "screenshot" in lowered:
        shot = ws.take_screenshot("login")
        return f"Captured a screenshot of the login page ({Path(shot['path']).name}) for review."
    playbook = next((p for key, p in PLAYBOOKS.items() if key in lowered), None)
    if playbook is None:
        return "I don't have a playbook for that task."
    query, path, old, new, what, why = playbook

    ws.search_code(query)
    source = ws.read_file(path)
    ws.write_file(path, source.replace(old, new))
    title = f"Update {path}: {what.split(' to ')[0]}"
    pr = None
    if workflow == "pr-first":
        pr = ws.create_pull_request(title, f"{what}. {why}.")
        tests = ws.run_tests()
    else:
        tests = ws.run_tests()
        if tests["passed"]:
            pr = ws.create_pull_request(title, f"{what}. {why}. Tests: {tests['summary']}.")

    verdict = "passed" if tests["passed"] else "FAILED"
    summary = f"Changed {path}: {what}. Why: {why}. Tests {verdict} ({tests['summary']})."
    if pr:
        return summary + f" Opened pull request #{pr['number']}."
    return summary + " I did not open a pull request because the tests failed."


def build_agent(**options: Any) -> CodingAgent:
    """AgentLock entrypoint: `coding_agent.agent:build_agent`."""
    return CodingAgent(**options)
