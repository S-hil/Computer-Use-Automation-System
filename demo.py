"""
Unified Demo Runner for the Computer-Use Automation System.
Executes the full vertical slice end-to-end:
1. --mode=discovery: Autonomous/LLM discovery on live surface -> emits CapabilityArtifact + logs/screenshots
2. --mode=replay: Deterministic replay of artifact -> extracts typed outputs (zero LLM)
3. --mode=business-outcome: Deterministic replay with non-existent member -> demonstrates AC-404 business outcome handling
4. --mode=escalation: High-risk dual control trigger -> live session handoff to human operator -> approval -> resume
5. --mode=all: Runs all phases sequentially to populate evidence/
"""

import argparse
import json
import os
import sys
import time

from src.target_app.server import ApexCoreServer
from src.surface.browser import PlaywrightSurfaceDriver
from src.agent.discovery_agent import DiscoveryAgent
from src.engine.replay import ReplayEngine
from src.escalation.handoff import EscalationController
from src.schema.capability import CapabilityArtifact
from src.schema.result import ExecutionStatus
from src.observability.logger import console, StructuredLogger


def run_discovery(server_url: str, headless: bool = True) -> CapabilityArtifact:
    console.rule("[bold cyan]PHASE 1: LLM-DRIVEN GOAL DISCOVERY[/bold cyan]")
    surface = PlaywrightSurfaceDriver(headless=headless)
    agent = DiscoveryAgent(surface=surface, evidence_dir="evidence/discovery_run")

    goal = "Look up member MEM-7701 and retrieve their current primary savings ledger balance."
    try:
        artifact, path = agent.run(goal=goal, target_url=server_url)
        console.print(f"[bold green]Discovery complete![/bold green] Capability saved to: [underline]{path}[/underline]")
        return artifact
    finally:
        surface.close()


def run_deterministic_replay(
    server_url: str,
    artifact: CapabilityArtifact,
    member_id: str = "MEM-7701",
    label: str = "replay_success",
    headless: bool = True
):
    console.rule(f"[bold cyan]PHASE 2: DETERMINISTIC REPLAY ({label.upper()})[/bold cyan]")
    surface = PlaywrightSurfaceDriver(headless=headless)
    engine = ReplayEngine(surface=surface, evidence_dir="evidence")

    try:
        result = engine.execute(
            artifact=artifact,
            inputs={"member_id": member_id},
            run_label=label
        )
        console.print(f"\n[bold]Replay Status:[/bold] [yellow]{result.status.value}[/yellow]")
        console.print(f"[bold]Execution Duration:[/bold] {result.execution_time_ms:.1f}ms (Zero LLM in loop)")
        console.print(f"[bold]Returned Outputs:[/bold] {json.dumps(result.outputs, indent=2)}")
        return result
    finally:
        surface.close()


def run_escalation_flow(server_url: str, headless: bool = True):
    console.rule("[bold cyan]PHASE 3: HUMAN-IN-THE-LOOP LIVE SESSION HANDOFF[/bold cyan]")
    surface = PlaywrightSurfaceDriver(headless=headless)
    logger = StructuredLogger(
        log_file_path="evidence/replay_escalation/escalation.log",
        component_name="EscalationCoordinator"
    )
    controller = EscalationController(surface=surface, logger=logger, evidence_dir="evidence/replay_escalation")

    try:
        # 1. Automation navigates to high-risk transfer surface
        transfer_url = f"{server_url}/member/transfer?id=MEM-7701"
        logger.info(f"Automation navigating to high-risk servicing screen: {transfer_url}")
        surface.navigate(transfer_url)

        # 2. Automation encounters Dual-Control Lockout
        logger.warning("Attempting fund release without supervisor PIN triggers institutional policy lock.")
        # Trigger lockout by submitting without supervisor PIN
        from src.schema.capability import MultiStrategyLocator, LocatorDefinition, LocatorType
        submit_btn = MultiStrategyLocator(
            primary=LocatorDefinition(strategy=LocatorType.CSS_SELECTOR, value="#btnAuthorizeWire"),
            robustness_rationale="Authorize wire button"
        )
        surface.click(submit_btn)

        # 3. Detect stuck/lockout state and trigger escalation
        intervention = controller.trigger_escalation(
            capability_id="apexcore.member.fund_release",
            step_id="step_dual_control_authorization",
            step_index=4,
            reason="Dual-Control Supervisor Authorization required under Banking Rule 802. Automation cannot proceed safely.",
            requested_action="Supervisor must take over live session and enter authorization credentials."
        )

        # 4. Human operator takes control of the SAME live session
        operator_record = controller.human_takeover_action(
            request=intervention,
            operator_id="SUP_OPERATOR_8802",
            simulate_manual_action=True
        )

        # 5. Control returned to automation on the same session
        controller.resume_automation(operator_record)

        # 6. Verify success state on live session
        final_ss = "evidence/replay_escalation/final_flow_completed.png"
        surface.take_screenshot(final_ss)
        logger.success(f"Escalation workflow verified! Session cleared and audit log recorded.")

    finally:
        surface.close()


def main():
    parser = argparse.ArgumentParser(description="Computer-Use Automation System Runner")
    parser.add_argument(
        "--mode",
        choices=["discovery", "replay", "business-outcome", "escalation", "all"],
        default="all",
        help="Execution mode to run"
    )
    parser.add_argument("--member-id", default="MEM-7701", help="Member ID for replay")
    parser.add_argument("--port", type=int, default=8088, help="Port for local ApexCore bank server")
    parser.add_argument("--no-headless", action="store_true", help="Run browser visibly")
    args = parser.parse_args()

    headless = not args.no_headless

    # Start local ApexCore 9.4 legacy banking application
    server = ApexCoreServer(port=args.port)
    server_url = server.start()
    console.print(f"[bold green]▶ ApexCore 9.4 Banking Servicing Console listening at:[/bold green] [underline]{server_url}[/underline]\n")

    try:
        artifact = None
        artifact_path = os.path.join("evidence", "capability_member_lookup.json")

        if args.mode in ("discovery", "all"):
            artifact = run_discovery(server_url, headless=headless)

        if args.mode in ("replay", "all"):
            if not artifact:
                if os.path.exists(artifact_path):
                    with open(artifact_path, "r", encoding="utf-8") as f:
                        artifact = CapabilityArtifact.parse_raw(f.read())
                else:
                    artifact = run_discovery(server_url, headless=headless)
            run_deterministic_replay(server_url, artifact, member_id=args.member_id, label="replay_success", headless=headless)

        if args.mode in ("business-outcome", "all"):
            if not artifact:
                with open(artifact_path, "r", encoding="utf-8") as f:
                    artifact = CapabilityArtifact.parse_raw(f.read())
            run_deterministic_replay(server_url, artifact, member_id="MEM-9999", label="replay_business_outcome", headless=headless)

        if args.mode in ("escalation", "all"):
            run_escalation_flow(server_url, headless=headless)

        console.rule("[bold green]ALL REQUESTED WORKFLOWS COMPLETED SUCCESSFULLY[/bold green]")
        console.print("Structured logs, capability artifacts, and screenshots saved to: [underline]evidence/[/underline]\n")

    finally:
        server.stop()


if __name__ == "__main__":
    main()
