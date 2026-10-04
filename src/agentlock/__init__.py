"""AgentLock v0.2 — package-lock.json for AI agents."""

__version__ = "0.2.0"

from agentlock.adapters import BaseAdapter, LangGraphAdapter, PythonAdapter, get_adapter
from agentlock.behavior import BehaviorBasis, BehaviorState, ScenarioBehavior
from agentlock.deps import DependencyChange, DependencyClosure, ModelDep, PromptDep, SkillDep, ToolDep
from agentlock.diff import BehaviorChange, DiffReport, compute_diff
from agentlock.events import NormalizedTrace, RawEvent, normalize_event_stream
from agentlock.invariants import MinedRule, evaluate_contract, mine_invariants
from agentlock.judge import GemmaJudge
from agentlock.lockfile import LockfileV2, load_lockfile, write_lockfile
from agentlock.manifest import AgentManifest, ScenarioSpec, load_manifest
from agentlock.models import (
    AgentEvent,
    AgentSpec,
    Condition,
    ConditionalContract,
    ContractResult,
    EvaluationResult,
    ForbiddenContract,
    ModelSpec,
    MultimodalContract,
    OrderingContract,
    RequiredContract,
    SemanticContract,
    SkillSpec,
    ToolCall,
    ToolSpec,
    Trace,
)
from agentlock.objects import ObjectStore
from agentlock.restore import RestorePlan, execute_restore
from agentlock.tracer import AgentLockTracer, current_tracer, tracked_tool
from agentlock.verify import VerificationResult, verify_agent

__all__ = [
    "AgentEvent",
    "AgentLockTracer",
    "AgentManifest",
    "AgentSpec",
    "BaseAdapter",
    "BehaviorBasis",
    "BehaviorChange",
    "BehaviorState",
    "Condition",
    "ConditionalContract",
    "ContractResult",
    "DependencyChange",
    "DependencyClosure",
    "DiffReport",
    "EvaluationResult",
    "ForbiddenContract",
    "GemmaJudge",
    "LangGraphAdapter",
    "LockfileV2",
    "MinedRule",
    "ModelDep",
    "ModelSpec",
    "MultimodalContract",
    "NormalizedTrace",
    "ObjectStore",
    "OrderingContract",
    "PromptDep",
    "PythonAdapter",
    "RawEvent",
    "RequiredContract",
    "RestorePlan",
    "ScenarioBehavior",
    "ScenarioSpec",
    "SemanticContract",
    "SkillDep",
    "SkillSpec",
    "ToolCall",
    "ToolDep",
    "ToolSpec",
    "Trace",
    "VerificationResult",
    "compute_diff",
    "current_tracer",
    "evaluate_contract",
    "execute_restore",
    "get_adapter",
    "load_lockfile",
    "load_manifest",
    "mine_invariants",
    "normalize_event_stream",
    "tracked_tool",
    "verify_agent",
    "write_lockfile",
]
