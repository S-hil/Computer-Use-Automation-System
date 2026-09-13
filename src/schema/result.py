"""
Execution Result and Error Taxonomy Schema.
Defines the production result contract returned to callers:
- SUCCESS: Happy path execution with extracted typed data
- BUSINESS_OUTCOME: Expected domain condition (e.g. Member Not Found)
- RECOVERED: Successfully recovered from an interstitial or transient event
- FAILED_HARD: Unrecoverable failure with rich debugging context
- ESCALATED: Paused and routed to human operator
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    SUCCESS = "success"                          # Complete success, outputs extracted
    BUSINESS_OUTCOME = "business_outcome"        # Legitimate domain outcome (e.g. Member Not Found)
    RECOVERED = "recovered"                      # Completed after handling an interstitial/recovery
    FAILED_RETRYABLE = "failed_retryable"        # Transient issue (load timeout), caller may retry
    FAILED_HARD = "failed_hard"                  # Fatal error / selector missing / assertion broken
    ESCALATED = "escalated"                      # Live session transferred to human operator


class StepExecutionTrace(BaseModel):
    step_id: str
    step_index: int
    action: str
    locator_used: Optional[str] = None
    strategy_used: Optional[str] = None
    duration_ms: float
    status: str                                  # "ok", "recovered", "failed", "escalated"
    detail: Optional[str] = None
    screenshot_path: Optional[str] = None


class FailureDiagnostic(BaseModel):
    failed_step_index: int
    failed_step_id: str
    action_attempted: str
    expected_state: str
    observed_state: str
    error_message: str
    screenshot_path: Optional[str] = None
    dom_snapshot_path: Optional[str] = None
    ax_tree_snapshot_path: Optional[str] = None


class ReplayResult(BaseModel):
    """
    Standard production response object returned to AI agent or caller.
    """
    capability_id: str
    status: ExecutionStatus
    business_outcome_code: Optional[str] = None  # E.g. "MEMBER_NOT_FOUND"
    message: str
    outputs: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = 0.0
    steps_executed: int = 0
    traces: List[StepExecutionTrace] = Field(default_factory=list)
    failure: Optional[FailureDiagnostic] = None
    escalation_incident_id: Optional[str] = None
    redacted_keys: List[str] = Field(default_factory=list)
