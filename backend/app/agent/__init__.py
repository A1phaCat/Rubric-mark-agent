"""Evidence-check agent: tool use over the full submission text, bounded and read-only."""

from .loop import AgentStep, EvidenceCheck, run_evidence_check, system_message
from .tools import TOOL_SPECS, EvidenceWorkspace

__all__ = ["AgentStep", "EvidenceCheck", "EvidenceWorkspace", "TOOL_SPECS", "run_evidence_check", "system_message"]
