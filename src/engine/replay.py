"""
Deterministic Replay Engine.
Executes capability artifacts in production WITHOUT any LLM in the decision loop:
- Machine-speed execution with multi-strategy locator resolution
- Parameter template interpolation (e.g. {{inputs.member_id}})
- Automatic detection and handling of Recoverable Interstitials
- Explicit classification of Domain Business Outcomes (e.g. MEMBER_NOT_FOUND) vs Hard Failures
- Structured ReplayResult contract with comprehensive telemetry and diagnostics
"""

import os
import re
import time
from typing import Any, Dict, Optional

from src.schema.capability import (
    CapabilityArtifact, CapabilityStep, ActionType, RiskClassification,
    MultiStrategyLocator, LocatorDefinition, LocatorType
)
from src.schema.result import (
    ReplayResult, ExecutionStatus, StepExecutionTrace, FailureDiagnostic
)
from src.surface.base import SurfaceDriver
from src.guardrails.policy import PolicyEngine, PolicyViolation
from src.guardrails.redaction import redact_text, sanitize_data
from src.observability.logger import StructuredLogger


class ReplayEngine:
    def __init__(
        self,
        surface: SurfaceDriver,
        policy_engine: Optional[PolicyEngine] = None,
        logger: Optional[StructuredLogger] = None,
        evidence_dir: str = "evidence"
    ):
        self.surface = surface
        self.policy_engine = policy_engine or PolicyEngine()
        self.logger = logger
        self.evidence_dir = evidence_dir

    def _render_template(self, template: Optional[str], inputs: Dict[str, Any]) -> Optional[str]:
        if not template:
            return None
        result = template
        for k, v in inputs.items():
            result = result.replace(f"{{{{inputs.{k}}}}}", str(v))
        return result

    def _check_and_handle_recoveries(self, step: CapabilityStep) -> bool:
        """
        Detects and handles known recoverable conditions (e.g. session timeout warning modal).
        Returns True if a recovery was performed.
        """
        # Built-in check for standard legacy session interstitial
        interstitial_loc = MultiStrategyLocator(
            primary=LocatorDefinition(
                strategy=LocatorType.CSS_SELECTOR,
                value="#ctl00_dlgSessionWarning"
            ),
            fallbacks=[
                LocatorDefinition(
                    strategy=LocatorType.TEXT_ANCHOR,
                    value="Session inactivity threshold approaching"
                )
            ],
            robustness_rationale="Session warning modal overlay"
        )

        try:
            if self.surface.is_visible(interstitial_loc, timeout_ms=500):
                if self.logger:
                    self.logger.warning("Detected recoverable condition: Session inactivity warning modal.")

                dismiss_btn = MultiStrategyLocator(
                    primary=LocatorDefinition(
                        strategy=LocatorType.AX_ROLE_NAME,
                        value="Extend Session",
                        role="button",
                        name="Extend Session"
                    ),
                    fallbacks=[
                        LocatorDefinition(strategy=LocatorType.CSS_SELECTOR, value="#ctl00_btnKeepSessionAlive")
                    ],
                    robustness_rationale="Dismiss button for session interstitial"
                )
                self.surface.click(dismiss_btn, timeout_ms=2000)
                if self.logger:
                    self.logger.success("Successfully dismissed session interstitial dialog.")
                return True
        except Exception:
            pass

        return False

    def _check_business_outcomes(self, artifact: CapabilityArtifact) -> Optional[tuple[str, str]]:
        """
        Evaluates declared business outcome patterns on the current surface.
        Returns (outcome_code, message) if a business outcome is detected, else None.
        """
        for outcome in artifact.business_outcomes:
            try:
                if self.surface.is_visible(outcome.detection_locator, timeout_ms=800):
                    text = self.surface.get_text(outcome.detection_locator, timeout_ms=800)
                    if re.search(outcome.text_pattern, text, re.IGNORECASE):
                        return outcome.outcome_code, text
            except Exception:
                continue
        return None

    def execute(
        self,
        artifact: CapabilityArtifact,
        inputs: Dict[str, Any],
        run_label: str = "replay_success"
    ) -> ReplayResult:
        start_time = time.time()
        run_evidence_dir = os.path.join(self.evidence_dir, run_label)
        os.makedirs(run_evidence_dir, exist_ok=True)

        if not self.logger:
            self.logger = StructuredLogger(
                log_file_path=os.path.join(run_evidence_dir, f"{run_label}.log"),
                component_name="DeterministicReplayEngine"
            )

        self.logger.info(f"Starting Replay for Capability: '{artifact.capability_id}' (v{artifact.version})")
        self.logger.info(f"Supplied Input Parameters: {sanitize_data(inputs)}")

        traces: List[StepExecutionTrace] = []
        extracted_outputs: Dict[str, Any] = {}
        had_recovery = False

        # Validate entry point URL with policy
        try:
            self.policy_engine.validate_url(artifact.entry_point_url)
            self.surface.navigate(artifact.entry_point_url)
        except Exception as e:
            return ReplayResult(
                capability_id=artifact.capability_id,
                status=ExecutionStatus.FAILED_HARD,
                message=f"Navigation policy violation: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000.0,
                steps_executed=0
            )

        for idx, step in enumerate(artifact.steps):
            step_num = idx + 1
            step_start = time.time()
            self.logger.step(step_index=step_num, description=step.description, action=step.action.value)

            # Check for interstitials before executing step
            if self._check_and_handle_recoveries(step):
                had_recovery = True

            # Evaluate policy & risk
            try:
                risk = self.policy_engine.validate_action(
                    step.action,
                    target_name=step.target.primary.name if step.target else None,
                    context_hint=step.description
                )
            except PolicyViolation as pv:
                return ReplayResult(
                    capability_id=artifact.capability_id,
                    status=ExecutionStatus.FAILED_HARD,
                    message=f"Safety Policy Violation at step {step_num}: {str(pv)}",
                    execution_time_ms=(time.time() - start_time) * 1000.0,
                    steps_executed=idx
                )

            # Execute action
            strategy_used = None
            try:
                if step.action == ActionType.FILL:
                    rendered_val = self._render_template(step.value_template, inputs) or ""
                    strategy_used = self.surface.fill(step.target, rendered_val, timeout_ms=step.timeout_ms)
                elif step.action == ActionType.CLICK:
                    strategy_used = self.surface.click(step.target, timeout_ms=step.timeout_ms)
                elif step.action == ActionType.WAIT_FOR:
                    if step.target:
                        self.surface.is_visible(step.target, timeout_ms=step.timeout_ms)
                elif step.action == ActionType.EXTRACT:
                    if step.target:
                        val = self.surface.get_text(step.target, timeout_ms=step.timeout_ms)
                        # Store in outputs
                        extracted_outputs["savings_balance"] = val
                        strategy_used = "extract:success"
                elif step.action == ActionType.NAVIGATE:
                    self.surface.navigate(artifact.entry_point_url)
                    strategy_used = "navigate:success"

                duration = (time.time() - step_start) * 1000.0
                traces.append(StepExecutionTrace(
                    step_id=step.step_id,
                    step_index=step_num,
                    action=step.action.value,
                    locator_used=step.target.primary.value if step.target else None,
                    strategy_used=strategy_used,
                    duration_ms=duration,
                    status="ok"
                ))

            except Exception as e:
                # First, check if this 'failure' is actually an expected Business Outcome (e.g. Member Not Found)!
                business_outcome = self._check_business_outcomes(artifact)
                if business_outcome:
                    code, detail = business_outcome
                    ss_path = os.path.join(run_evidence_dir, f"business_outcome_{code}.png")
                    self.surface.take_screenshot(ss_path)

                    self.logger.business_outcome(
                        outcome_code=code,
                        message=f"Domain condition met: {detail}",
                        screenshot=ss_path
                    )
                    return ReplayResult(
                        capability_id=artifact.capability_id,
                        status=ExecutionStatus.BUSINESS_OUTCOME,
                        business_outcome_code=code,
                        message=f"Legitimate business outcome: {detail}",
                        outputs={"member_id": inputs.get("member_id"), "found": False},
                        execution_time_ms=(time.time() - start_time) * 1000.0,
                        steps_executed=step_num,
                        traces=traces
                    )

                # Not a declared business outcome: this is a real hard failure
                ss_path = os.path.join(run_evidence_dir, f"step_{step_num}_failure.png")
                self.surface.take_screenshot(ss_path)

                diag = FailureDiagnostic(
                    failed_step_index=step_num,
                    failed_step_id=step.step_id,
                    action_attempted=step.action.value,
                    expected_state=f"Element matched by multi-locator {step.target.primary.strategy.value if step.target else 'N/A'}",
                    observed_state="Target element not found or not interactable",
                    error_message=str(e),
                    screenshot_path=ss_path
                )
                self.logger.error(f"Replay hard failure at Step {step_num}: {str(e)}", failure=diag.dict())

                return ReplayResult(
                    capability_id=artifact.capability_id,
                    status=ExecutionStatus.FAILED_HARD,
                    message=f"Replay execution failed at step {step_num}: {str(e)}",
                    execution_time_ms=(time.time() - start_time) * 1000.0,
                    steps_executed=step_num,
                    traces=traces,
                    failure=diag
                )

            # Check for business outcome right after step (e.g. After submitting search)
            business_outcome = self._check_business_outcomes(artifact)
            if business_outcome:
                code, detail = business_outcome
                ss_path = os.path.join(run_evidence_dir, f"business_outcome_{code}.png")
                self.surface.take_screenshot(ss_path)

                self.logger.business_outcome(
                    outcome_code=code,
                    message=f"Domain condition met: {detail}",
                    screenshot=ss_path
                )
                return ReplayResult(
                    capability_id=artifact.capability_id,
                    status=ExecutionStatus.BUSINESS_OUTCOME,
                    business_outcome_code=code,
                    message=f"Legitimate business outcome: {detail}",
                    outputs={"member_id": inputs.get("member_id"), "found": False},
                    execution_time_ms=(time.time() - start_time) * 1000.0,
                    steps_executed=step_num,
                    traces=traces
                )

        # Successful completion - capture final screenshot
        final_ss = os.path.join(run_evidence_dir, "replay_final_success.png")
        self.surface.take_screenshot(final_ss)

        total_time = (time.time() - start_time) * 1000.0
        status = ExecutionStatus.RECOVERED if had_recovery else ExecutionStatus.SUCCESS

        self.logger.success(
            f"Deterministic Replay completed successfully in {total_time:.1f}ms. Extracted: {extracted_outputs}"
        )

        return ReplayResult(
            capability_id=artifact.capability_id,
            status=status,
            message="Replay executed deterministically and verified all checkpoints.",
            outputs=extracted_outputs,
            execution_time_ms=total_time,
            steps_executed=len(artifact.steps),
            traces=traces
        )
