"""L2 Semantic actions vocabulary mapping tools to effect classes."""

from __future__ import annotations

import fnmatch
from typing import Any, Literal
from pydantic import BaseModel, Field

EffectClass = Literal["read", "write", "external", "irreversible"]


class ActionCondition(BaseModel):
    tool: str
    arguments: dict[str, str] = Field(default_factory=dict)

    def matches(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        if tool_name != self.tool:
            return False
        for k, pattern in self.arguments.items():
            val = str(arguments.get(k, ""))
            if not fnmatch.fnmatch(val, pattern):
                return False
        return True


class ActionDef(BaseModel):
    tool: str
    effect: EffectClass = "read"
    when: dict[str, str] = Field(default_factory=dict)

    def matches(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        if tool_name != self.tool:
            return False
        for k, pattern in self.when.items():
            val = str(arguments.get(k, ""))
            if not fnmatch.fnmatch(val, pattern):
                return False
        return True


class ActionVocabulary(BaseModel):
    """Vocabulary mapping tool invocations to semantic actions."""

    actions: dict[str, ActionDef] = Field(default_factory=dict)

    def resolve_action(self, tool_name: str, arguments: dict[str, Any]) -> tuple[str, EffectClass]:
        """Resolve a tool call to its action name and effect class. Default fallback is action=tool_name, effect=write."""
        for action_name, action_def in self.actions.items():
            if action_def.matches(tool_name, arguments):
                return action_name, action_def.effect

        # Direct match by tool name if present without 'when'
        for action_name, action_def in self.actions.items():
            if action_def.tool == tool_name and not action_def.when:
                return action_name, action_def.effect

        # Default fallback
        return tool_name, "write"

    def register(self, action_name: str, tool_name: str, effect: EffectClass = "write", when: dict[str, str] | None = None) -> None:
        self.actions[action_name] = ActionDef(tool=tool_name, effect=effect, when=when or {})
