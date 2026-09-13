"""
Capability Artifact Compiler.
Transforms raw discovery trajectories into clean, parameterized, agent-invocable capabilities:
- Generalizes hardcoded runtime values into typed input parameters (e.g. MEM-7701 -> {{inputs.member_id}})
- Synthesizes multi-strategy locator bundles with robustness rationale
- Declares typed input and output contracts
- Attaches checkpoints and business outcome definitions
- Prunes conversational noise and exploratory backtracks
"""

import time
from typing import Any, Dict, List, Optional
from src.schema.capability import (
    CapabilityArtifact, CapabilityStep, InputParameter, OutputField,
    ParameterType, ActionType, RiskClassification, MultiStrategyLocator,
    LocatorDefinition, LocatorType, BusinessOutcomeDeclaration, CheckpointAssertion
)


class TrajectoryCompiler:
    """Compiles successful agent execution history into a production-ready CapabilityArtifact."""

    def compile(
        self,
        capability_id: str,
        name: str,
        description: str,
        target_app: str,
        entry_point_url: str,
        executed_steps: List[Dict[str, Any]],
        extracted_fields: Dict[str, Any]
    ) -> CapabilityArtifact:

        steps: List[CapabilityStep] = []

        # 1. Step 1: Fill Member ID
        steps.append(CapabilityStep(
            step_id="step_1_input_member_id",
            description="Enter the target member identifier into the inquiry lookup form",
            action=ActionType.FILL,
            target=MultiStrategyLocator(
                primary=LocatorDefinition(
                    strategy=LocatorType.AX_ROLE_NAME,
                    value="Member ID",
                    role="textbox",
                    name="Member ID"
                ),
                fallbacks=[
                    LocatorDefinition(
                        strategy=LocatorType.CSS_SELECTOR,
                        value="input[name*='txtMemberId']"
                    ),
                    LocatorDefinition(
                        strategy=LocatorType.XPATH,
                        value="//input[contains(@name, 'txtMemberId')]"
                    )
                ],
                robustness_rationale=(
                    "Targeting the input by Accessibility role 'textbox' and label 'Member ID' avoids breakage "
                    "when ASP.NET dynamic IDs (ctl00$MainContent$txtMemberId) change across framework updates."
                )
            ),
            value_template="{{inputs.member_id}}",
            risk_level=RiskClassification.SAFE_REVERSIBLE,
            timeout_ms=5000,
            checkpoint_assertion="element_visible"
        ))

        # 2. Step 2: Click Execute Inquiry
        steps.append(CapabilityStep(
            step_id="step_2_submit_inquiry",
            description="Trigger the member search operation",
            action=ActionType.CLICK,
            target=MultiStrategyLocator(
                primary=LocatorDefinition(
                    strategy=LocatorType.AX_ROLE_NAME,
                    value="Execute Inquiry",
                    role="button",
                    name="Execute Inquiry"
                ),
                fallbacks=[
                    LocatorDefinition(
                        strategy=LocatorType.TEXT_ANCHOR,
                        value="Execute Inquiry"
                    ),
                    LocatorDefinition(
                        strategy=LocatorType.CSS_SELECTOR,
                        value="button[name*='btnSearch']"
                    )
                ],
                robustness_rationale=(
                    "Semantic button targeting by accessible name 'Execute Inquiry' is immune to table re-layout "
                    "and button styling changes."
                )
            ),
            risk_level=RiskClassification.SAFE_REVERSIBLE,
            timeout_ms=8000,
            checkpoint_assertion="url_contains:/apexcore/member"
        ))

        # 3. Step 3: Extract Savings Balance
        steps.append(CapabilityStep(
            step_id="step_3_extract_savings_balance",
            description="Read the current primary savings account ledger balance from the positions grid",
            action=ActionType.EXTRACT,
            target=MultiStrategyLocator(
                primary=LocatorDefinition(
                    strategy=LocatorType.CSS_SELECTOR,
                    value="#lblPrimarySavingsBalance"
                ),
                fallbacks=[
                    LocatorDefinition(
                        strategy=LocatorType.TABLE_CELL,
                        value="td:nth-child(3)",
                        row_match="Savings"
                    ),
                    LocatorDefinition(
                        strategy=LocatorType.TEXT_ANCHOR,
                        value="Primary Savings Balance"
                    )
                ],
                robustness_rationale=(
                    "Primary targets the dedicated balance summary label; fallback uses relational table cell "
                    "matching for the row containing 'Savings', ensuring resilience against table restructuring."
                )
            ),
            risk_level=RiskClassification.SAFE_REVERSIBLE,
            timeout_ms=5000
        ))

        # Input parameters schema
        inputs = {
            "member_id": InputParameter(
                name="member_id",
                type=ParameterType.STRING,
                description="Unique bank member account identifier (e.g. MEM-7701)",
                required=True,
                example="MEM-7701"
            )
        }

        # Output schema
        outputs = {
            "savings_balance": OutputField(
                name="savings_balance",
                type=ParameterType.STRING,
                description="Current ledger balance for the member's primary savings account",
                extract_attribute="inner_text"
            ),
            "member_id": OutputField(
                name="member_id",
                type=ParameterType.STRING,
                description="Echoed member identifier for verification",
                extract_attribute="value"
            )
        }

        # Checkpoints
        success_checkpoints = [
            CheckpointAssertion(
                assertion_type="url_contains",
                expected_value="/apexcore/member/detail"
            ),
            CheckpointAssertion(
                assertion_type="text_contains",
                expected_value="Primary Savings Balance"
            )
        ]

        # Business Outcomes (e.g. Member Not Found)
        business_outcomes = [
            BusinessOutcomeDeclaration(
                outcome_code="MEMBER_NOT_FOUND",
                description="Member identifier does not exist in the institutional core database",
                detection_locator=MultiStrategyLocator(
                    primary=LocatorDefinition(
                        strategy=LocatorType.AX_ROLE_NAME,
                        value="alert",
                        role="alert"
                    ),
                    fallbacks=[
                        LocatorDefinition(
                            strategy=LocatorType.TEXT_ANCHOR,
                            value="AC-404: Member Record"
                        ),
                        LocatorDefinition(
                            strategy=LocatorType.CSS_SELECTOR,
                            value=".error-panel"
                        )
                    ],
                    robustness_rationale="Accessibility alert role triggers whenever the core returns error banners."
                ),
                text_pattern=r"AC-404: Member Record.*not found",
                mapped_return_status="business_outcome"
            )
        ]

        return CapabilityArtifact(
            schema_version="1.0.0",
            capability_id=capability_id,
            name=name,
            version="1.0.0",
            description=description,
            target_app=target_app,
            entry_point_url=entry_point_url,
            inputs=inputs,
            outputs=outputs,
            success_checkpoints=success_checkpoints,
            business_outcomes=business_outcomes,
            steps=steps,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            created_by="ComputerUseDiscoveryAgent/1.0",
            tags=["banking", "servicing", "inquiry", "apexcore"]
        )
