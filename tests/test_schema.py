"""
Tests for Capability Artifact Schema and Result Contracts.
"""

import json
from src.schema.capability import (
    CapabilityArtifact, CapabilityStep, InputParameter, OutputField,
    ParameterType, ActionType, RiskClassification, MultiStrategyLocator,
    LocatorDefinition, LocatorType, BusinessOutcomeDeclaration
)
from src.schema.result import ReplayResult, ExecutionStatus


def test_capability_artifact_serialization():
    step = CapabilityStep(
        step_id="step_1",
        description="Type Member ID",
        action=ActionType.FILL,
        target=MultiStrategyLocator(
            primary=LocatorDefinition(
                strategy=LocatorType.AX_ROLE_NAME,
                value="Member ID",
                role="textbox",
                name="Member ID"
            ),
            robustness_rationale="Uses accessibility role and name"
        ),
        value_template="{{inputs.member_id}}"
    )

    artifact = CapabilityArtifact(
        capability_id="test.capability",
        name="Test Capability",
        description="A test capability",
        target_app="Test Banking App",
        entry_point_url="http://localhost:8088/apexcore",
        inputs={
            "member_id": InputParameter(
                name="member_id",
                type=ParameterType.STRING,
                description="Member ID"
            )
        },
        outputs={
            "balance": OutputField(
                name="balance",
                type=ParameterType.STRING,
                description="Savings Balance"
            )
        },
        steps=[step]
    )

    from src.schema.capability import serialize_artifact, deserialize_artifact
    serialized = serialize_artifact(artifact)
    assert "test.capability" in serialized
    assert "Member ID" in serialized

    # Deserialize back
    parsed = deserialize_artifact(serialized)
    assert parsed.capability_id == "test.capability"
    assert len(parsed.steps) == 1
    assert parsed.steps[0].action == ActionType.FILL


def test_replay_result_structure():
    res = ReplayResult(
        capability_id="test.cap",
        status=ExecutionStatus.BUSINESS_OUTCOME,
        business_outcome_code="MEMBER_NOT_FOUND",
        message="Record not found in core database",
        outputs={"member_id": "MEM-9999"}
    )
    assert res.status == ExecutionStatus.BUSINESS_OUTCOME
    assert res.business_outcome_code == "MEMBER_NOT_FOUND"
    assert res.outputs["member_id"] == "MEM-9999"
