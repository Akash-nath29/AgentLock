"""Framework Adapters subpackage."""

from agentlock.adapters.base import BaseAdapter
from agentlock.adapters.langgraph import LangGraphAdapter
from agentlock.adapters.python import PythonAdapter


def get_adapter(adapter_name: str) -> BaseAdapter:
    """Factory function for loading a framework adapter by name."""
    if adapter_name == "langgraph":
        return LangGraphAdapter()
    elif adapter_name == "python":
        return PythonAdapter()
    else:
        raise ValueError(f"Unknown adapter {adapter_name!r}. Supported adapters: 'langgraph', 'python'.")


__all__ = ["BaseAdapter", "LangGraphAdapter", "PythonAdapter", "get_adapter"]
