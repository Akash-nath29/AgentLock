"""Abstract Framework Adapter Interface for AgentLock."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from agentlock.events import RawEvent


class BaseAdapter(ABC):
    """Abstract framework adapter interface."""

    @abstractmethod
    def load(self, entrypoint: str, options: dict[str, Any] | None = None) -> None:
        """Load and initialize agent from entrypoint callable."""
        pass

    @abstractmethod
    def discover(self) -> dict[str, Any]:
        """Discover tools, models, and system prompts dynamically or statically."""
        pass

    @abstractmethod
    def run(self, scenario_input: str, scenario_id: str = "", sample_index: int = 0) -> tuple[list[RawEvent], str]:
        """Execute one scenario run and return L0 event stream plus final reply."""
        pass

    @abstractmethod
    def override(self, overrides: dict[str, Any]) -> None:
        """Apply temporary dependency overrides for bisect or verify --with."""
        pass

    def reset(self) -> None:
        """Reset agent state between scenario runs if needed."""
        pass
