"""The coding agent's tools, operating on a throwaway copy of fake_repo/.

Each tool is a `@tracked_tool`, so AgentLock records every call. Nothing here
touches a real repository or GitHub: pull requests are simulated.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agentlock import ToolSpec, current_tracer, tracked_tool

REPO_TEMPLATE = Path(__file__).parent / "fake_repo"


def _schema(**props: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": "string", "description": desc} for name, desc in props.items()},
        "required": list(props),
    }


TOOL_SPECS = [
    ToolSpec(
        name="search_code",
        description="Search the repository's Python files (names and contents) for a substring.",
        parameters=_schema(query="Text to search for."),
        returns="list of {path, line, text} matches",
    ),
    ToolSpec(
        name="read_file",
        description="Read a file from the repository.",
        parameters=_schema(path="Path relative to the repository root."),
        returns="the file content as a string",
    ),
    ToolSpec(
        name="write_file",
        description="Overwrite a file in the repository with new content.",
        parameters=_schema(path="Path relative to the repository root.", content="The complete new file content."),
        returns="{path, bytes}",
    ),
    ToolSpec(
        name="run_tests",
        description="Run the repository's test suite.",
        parameters={"type": "object", "properties": {}},
        returns="{passed: bool, summary: str, output: str}",
    ),
    ToolSpec(
        name="create_pull_request",
        description="Open a pull request with the current changes.",
        parameters=_schema(title="PR title.", body="PR description."),
        returns="{number: int, status: 'open'}",
    ),
    ToolSpec(
        name="merge_pull_request",
        description="Merge an open pull request into main.",
        parameters={"type": "object", "properties": {"number": {"type": "integer"}}, "required": ["number"]},
        returns="{number: int, status: 'merged'}",
    ),
    ToolSpec(
        name="take_screenshot",
        description="Render a page of the web UI and capture a screenshot. Available pages: login.",
        parameters=_schema(page="Page name, e.g. 'login'."),
        returns="{path: str}",
    ),
]


class Workspace:
    """A private copy of fake_repo/ plus the tools that act on it."""

    def __init__(self, ui_build: str = "good") -> None:
        self.root = Path(tempfile.mkdtemp(prefix="coding-agent-"))
        shutil.copytree(REPO_TEMPLATE, self.root, dirs_exist_ok=True)
        self.ui_build = ui_build
        self.pull_requests: list[dict[str, Any]] = []

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _resolve(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError(f"path escapes the repository: {path}")
        return target

    @tracked_tool
    def search_code(self, query: str) -> list[dict[str, Any]]:
        matches = []
        for file in sorted(self.root.rglob("*.py")):
            if query.lower() in file.name.lower():
                matches.append({"path": file.relative_to(self.root).as_posix(), "line": 0, "text": "(file name)"})
            for n, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                if query.lower() in line.lower():
                    matches.append({"path": file.relative_to(self.root).as_posix(), "line": n, "text": line.strip()})
        return matches

    @tracked_tool
    def read_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    @tracked_tool
    def write_file(self, path: str, content: str) -> dict[str, Any]:
        self._resolve(path).write_text(content, encoding="utf-8")
        return {"path": path, "bytes": len(content.encode())}

    @tracked_tool
    def run_tests(self) -> dict[str, Any]:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest"], cwd=self.root, capture_output=True, text=True, timeout=60
        )
        lines = proc.stderr.strip().splitlines()
        return {"passed": proc.returncode == 0, "summary": lines[-1] if lines else "", "output": proc.stderr[-1500:]}

    @tracked_tool
    def create_pull_request(self, title: str, body: str) -> dict[str, Any]:
        pr = {"number": len(self.pull_requests) + 1, "status": "open", "title": title}
        self.pull_requests.append(pr)
        return {"number": pr["number"], "status": "open"}

    @tracked_tool
    def merge_pull_request(self, number: int) -> dict[str, Any]:
        return {"number": number, "status": "merged"}

    @tracked_tool
    def take_screenshot(self, page: str) -> dict[str, Any]:
        # ponytail: no browser in the demo; the "renderer" returns a pre-rendered image of
        # the current UI build. The multimodal evaluation of that image is real.
        name = page.strip().lower().removesuffix(" page")
        suffix = "_broken" if self.ui_build == "broken" else ""
        image = REPO_TEMPLATE / "ui" / f"{name}{suffix}.png"
        if not image.exists():
            raise ValueError(f"unknown page {page!r}; available: login")
        tracer = current_tracer()
        if tracer:
            tracer.record_artifact("screenshot", str(image))
        return {"path": str(image)}
