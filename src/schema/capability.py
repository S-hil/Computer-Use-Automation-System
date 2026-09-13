"""
Structured Capability Artifact Schema.
Implements the typed, versioned capability contract required by interface.ai:
- Decoupled from raw LLM reasoning transcripts
- Agent-invocable with typed input parameters and typed output schemas
- Multi-strategy locator bundles with robustness rationale (Accessibility, Text, Relative Table, CSS)
- Explicit business outcome conditions and checkpoint assertions
- Risk classification (safe/reversible vs risky/irreversible)
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ParameterType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    WAIT_FOR = "wait_for"
    EXTRACT = "extract"
    ASSERT = "assert"


class RiskClassification(str, Enum):
    SAFE_REVERSIBLE = "safe_reversible"          # Reads, navigations, form filling before submission
    RISKY_MUTATION = "risky_mutation"            # Form submission, non-financial updates
    RISKY_IRREVERSIBLE = "risky_irreversible"    # Wire release, account freeze, deletions


class LocatorType(str, Enum):
    AX_ROLE_NAME = "ax_role_name"                # Primary: Accessibility Tree (role + accessible name)
    TEXT_ANCHOR = "text_anchor"                  # Fallback 1: Visible text anchor
    TABLE_CELL = "table_cell"                    # Fallback 2: Structural table cell relative locator
    CSS_SELECTOR = "css_selector"                # Fallback 3: CSS selector
    XPATH = "xpath"                              # Fallback 4: XPath


class LocatorDefinition(BaseModel):
    strategy: LocatorType
    value: str
    role: Optional[str] = None                   # E.g. "textbox", "button", "tab", "row"
    name: Optional[str] = None                   # Accessible name or label
    parent_context: Optional[str] = None         # Container or table header anchor
    column_header: Optional[str] = None          # For table relative locators
    row_match: Optional[str] = None              # For table relative locators


class MultiStrategyLocator(BaseModel):
    """
    Robust locator bundle combining multiple complementary strategies.
    Enterprise apps lack data-testids and use dynamic generated IDs;
    Accessibility nodes + text anchors survive UI updates and re-renders.
    """
    primary: LocatorDefinition
    fallbacks: List[LocatorDefinition] = Field(default_factory=list)
    robustness_rationale: str = Field(
        ...,
        description="Engineering reasoning on why this locator strategy survives UI drift on legacy surfaces."
    )


class InputParameter(BaseModel):
    name: str
    type: ParameterType = ParameterType.STRING
    description: str
    required: bool = True
    default: Optional[Any] = None
    example: Optional[Any] = None


class OutputField(BaseModel):
    name: str
    type: ParameterType = ParameterType.STRING
    description: str
    target_locator: Optional[MultiStrategyLocator] = None
    extract_attribute: str = "inner_text"        # "inner_text", "value", or custom regex
    regex_pattern: Optional[str] = None          # E.g. r"\$([0-9,]+\.[0-9]{2})"


class RecoveryAction(BaseModel):
    condition_description: str
    detect_locator: MultiStrategyLocator
    dismiss_action: ActionType = ActionType.CLICK
    dismiss_locator: MultiStrategyLocator
    max_retries: int = 2


class CapabilityStep(BaseModel):
    step_id: str
    description: str
    action: ActionType
    target: Optional[MultiStrategyLocator] = None
    value_template: Optional[str] = None         # Parameterized value e.g. "{{inputs.member_id}}"
    risk_level: RiskClassification = RiskClassification.SAFE_REVERSIBLE
    timeout_ms: int = 5000
    checkpoint_assertion: Optional[str] = None   # Post-step verification e.g. "url_contains:detail"
    known_recoveries: List[RecoveryAction] = Field(default_factory=list)


class BusinessOutcomeDeclaration(BaseModel):
    """
    Declares expected domain conditions that represent business outcomes rather than errors
    (e.g., 'Member Not Found' is a legitimate operational outcome).
    """
    outcome_code: str                            # E.g. "MEMBER_NOT_FOUND", "ACCOUNT_RESTRICTED"
    description: str
    detection_locator: MultiStrategyLocator
    text_pattern: str                            # E.g. "AC-404: Member Record.*not found"
    mapped_return_status: str = "business_outcome"


class CheckpointAssertion(BaseModel):
    assertion_type: str                          # "text_contains", "element_visible", "url_matches"
    expected_value: str
    target: Optional[MultiStrategyLocator] = None


class CapabilityArtifact(BaseModel):
    """
    Typed, versioned capability artifact.
    Callable by AI agents in production without LLM re-reasoning.
    """
    schema_version: str = "1.0.0"
    capability_id: str                           # E.g. "apexcore.member.get_savings_balance"
    name: str
    version: str = "1.0.0"
    description: str
    target_app: str                              # E.g. "ApexCore Banking Servicing Console"
    entry_point_url: str                         # E.g. "http://localhost:8088/apexcore"
    inputs: Dict[str, InputParameter] = Field(default_factory=dict)
    outputs: Dict[str, OutputField] = Field(default_factory=dict)
    success_checkpoints: List[CheckpointAssertion] = Field(default_factory=list)
    business_outcomes: List[BusinessOutcomeDeclaration] = Field(default_factory=list)
    steps: List[CapabilityStep] = Field(default_factory=list)
    created_at: Optional[str] = None
    created_by: str = "AutonomousDiscoveryAgent/1.0"
    tags: List[str] = Field(default_factory=list)


def serialize_artifact(model: BaseModel, indent: int = 2) -> str:
    """Serialize Pydantic model compatible with both v1 and v2."""
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json(indent=indent)
    return model.json(indent=indent)


def deserialize_artifact(json_str: str) -> CapabilityArtifact:
    """Deserialize CapabilityArtifact compatible with both v1 and v2."""
    if hasattr(CapabilityArtifact, "model_validate_json"):
        return CapabilityArtifact.model_validate_json(json_str)
    return CapabilityArtifact.parse_raw(json_str)


def model_to_dict(model: BaseModel) -> Dict[str, Any]:
    """Convert Pydantic model to dict compatible with both v1 and v2."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
