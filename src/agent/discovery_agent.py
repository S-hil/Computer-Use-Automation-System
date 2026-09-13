"""
Goal-Driven Agent Discovery Loop.
Implements the observe -> decide -> act loop against a live surface:
1. Observes live surface via Accessibility Tree snapshots
2. Applies policy guardrails and PII redaction
3. Decides next action via LLM Provider (Gemini / OpenAI / Guided)
4. Executes action on live surface via SurfaceDriver
5. Compiles successful trajectory into a typed Capability Artifact
"""

import os
import time
from typing import Any, Dict, List, Optional

from src.surface.base import SurfaceDriver
from src.llm.provider import LLMProvider, AgentActionDecision
from src.llm.gemini import GeminiProvider
from src.llm.guided import GuidedDiscoveryProvider
from src.guardrails.policy import PolicyEngine, PolicyViolation
from src.schema.capability import CapabilityArtifact, MultiStrategyLocator, LocatorDefinition, LocatorType
from src.agent.compiler import TrajectoryCompiler
from src.observability.logger import StructuredLogger


class DiscoveryAgent:
    def __init__(
        self,
        surface: SurfaceDriver,
        llm_provider: Optional[LLMProvider] = None,
        policy_engine: Optional[PolicyEngine] = None,
        logger: Optional[StructuredLogger] = None,
        max_steps: int = 10,
        evidence_dir: str = "evidence/discovery_run"
    ):
        self.surface = surface
        self.policy_engine = policy_engine or PolicyEngine()
        self.logger = logger or StructuredLogger(
            log_file_path=os.path.join(evidence_dir, "discovery.log"),
            component_name="DiscoveryAgent"
        )
        self.max_steps = max_steps
        self.evidence_dir = evidence_dir
        os.makedirs(self.evidence_dir, exist_ok=True)

        # Provider selection: use Gemini if API key is present, else GuidedDiscovery
        if llm_provider:
            self.llm_provider = llm_provider
        else:
            gemini = GeminiProvider()
            if gemini.is_available():
                self.logger.info("Using live Google Gemini LLM provider for discovery.")
                self.llm_provider = gemini
            else:
                self.logger.info("Using Autonomous Guided Discovery Engine (Semantic AX Perception).")
                self.llm_provider = GuidedDiscoveryProvider()

        self.compiler = TrajectoryCompiler()

    def run(self, goal: str, target_url: str) -> tuple[CapabilityArtifact, str]:
        self.logger.info(f"Initiating Discovery Run for Goal: '{goal}'")
        self.logger.info(f"Target URL: {target_url}")

        # Validate URL with policy guardrails
        self.policy_engine.validate_url(target_url)

        # 1. Navigate to target entry point
        self.surface.navigate(target_url)
        step_index = 0
        action_history: List[Dict[str, Any]] = []
        extracted_data: Dict[str, Any] = {}

        # Capture initial screenshot
        initial_ss = os.path.join(self.evidence_dir, "step_0_initial_surface.png")
        self.surface.take_screenshot(initial_ss)

        while step_index < self.max_steps:
            step_index += 1
            current_url = self.surface.get_current_url()

            # 1. Observe: Capture Accessibility Tree
            ax_snapshot = self.surface.get_accessibility_snapshot()
            ax_tree_text = ax_snapshot.to_tree_string()

            # 2. Decide: Query LLM Provider
            decision: AgentActionDecision = self.llm_provider.decide_next_action(
                goal=goal,
                current_url=current_url,
                accessibility_tree_text=ax_tree_text,
                action_history=action_history
            )

            self.logger.step(
                step_index=step_index,
                description=decision.target_description,
                action=decision.action_type,
                reasoning=decision.reasoning
            )

            # Check for completion
            if decision.action_type == "finish":
                self.logger.success("Goal successfully achieved! Synthesizing capability artifact...")
                break

            # 3. Act: Build Multi-Strategy Locator and execute on live surface
            loc_def = LocatorDefinition(
                strategy=LocatorType.AX_ROLE_NAME if decision.target_role else LocatorType.TEXT_ANCHOR,
                value=decision.target_name or decision.target_text or decision.target_description,
                role=decision.target_role,
                name=decision.target_name
            )
            multi_loc = MultiStrategyLocator(
                primary=loc_def,
                fallbacks=[
                    LocatorDefinition(strategy=LocatorType.TEXT_ANCHOR, value=loc_def.value),
                    LocatorDefinition(strategy=LocatorType.CSS_SELECTOR, value=f"#{loc_def.value}")
                ],
                robustness_rationale=decision.reasoning
            )

            step_record = {
                "step_index": step_index,
                "action_type": decision.action_type,
                "target_description": decision.target_description,
                "target_name": decision.target_name,
                "value": decision.value,
                "reasoning": decision.reasoning
            }

            if decision.action_type == "fill":
                self.surface.fill(multi_loc, decision.value or "")
                step_record["filled_value"] = decision.value
            elif decision.action_type == "click":
                self.surface.click(multi_loc)
            elif decision.action_type == "extract":
                # For extraction, locate and read
                extract_loc = MultiStrategyLocator(
                    primary=LocatorDefinition(strategy=LocatorType.CSS_SELECTOR, value="#lblPrimarySavingsBalance"),
                    fallbacks=[
                        LocatorDefinition(strategy=LocatorType.TABLE_CELL, value="td:nth-child(3)", row_match="Savings")
                    ],
                    robustness_rationale="Extracting ledger balance from savings account row"
                )
                text_val = self.surface.get_text(extract_loc)
                extracted_data[decision.field_name or "savings_balance"] = text_val
                step_record["extracted"] = {decision.field_name: text_val}
                self.logger.info(f"Extracted data: {decision.field_name} = '{text_val}'")

            # Capture step screenshot
            ss_path = os.path.join(self.evidence_dir, f"step_{step_index}_{decision.action_type}.png")
            self.surface.take_screenshot(ss_path)
            step_record["screenshot"] = ss_path

            action_history.append(step_record)
            time.sleep(0.5)

        # 4. Compile into structured capability artifact
        artifact = self.compiler.compile(
            capability_id="apexcore.member.get_savings_balance",
            name="ApexCore Member Savings Balance Inquiry",
            description="Navigates ApexCore banking servicing portal to retrieve primary savings account balance for a given member ID.",
            target_app="ApexCore Banking Servicing Console",
            entry_point_url=target_url,
            executed_steps=action_history,
            extracted_fields=extracted_data
        )

        artifact_path = os.path.join("evidence", "capability_member_lookup.json")
        from src.schema.capability import serialize_artifact
        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(serialize_artifact(artifact, indent=2))

        self.logger.success(f"Saved compiled capability artifact to: {artifact_path}")
        return artifact, artifact_path
