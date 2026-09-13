"""
End-to-End Integration Tests for Deterministic Replay and Escalation.
"""

import pytest
from src.target_app.server import ApexCoreServer
from src.surface.browser import PlaywrightSurfaceDriver
from src.agent.discovery_agent import DiscoveryAgent
from src.engine.replay import ReplayEngine
from src.escalation.handoff import EscalationController
from src.schema.result import ExecutionStatus


@pytest.fixture(scope="module")
def live_server():
    server = ApexCoreServer(port=8092)
    url = server.start()
    yield url
    server.stop()


def test_discovery_and_replay_e2e(live_server):
    surface = PlaywrightSurfaceDriver(headless=True)
    try:
        # Run Discovery
        agent = DiscoveryAgent(surface=surface, evidence_dir="/tmp/evidence_tests/discovery")
        artifact, _ = agent.run(
            goal="Look up member MEM-7701 and read savings balance",
            target_url=live_server
        )
        assert artifact.capability_id == "apexcore.member.get_savings_balance"
        assert len(artifact.steps) >= 3

        # Run Deterministic Replay (Happy Path)
        engine = ReplayEngine(surface=surface, evidence_dir="/tmp/evidence_tests/replay")
        res = engine.execute(
            artifact=artifact,
            inputs={"member_id": "MEM-7701"},
            run_label="test_replay_success"
        )
        assert res.status == ExecutionStatus.SUCCESS
        assert "savings_balance" in res.outputs
        assert "$14,250.80" in res.outputs["savings_balance"]

        # Run Replay (Business Outcome: Member Not Found)
        res_not_found = engine.execute(
            artifact=artifact,
            inputs={"member_id": "MEM-9999"},
            run_label="test_replay_not_found"
        )
        assert res_not_found.status == ExecutionStatus.BUSINESS_OUTCOME
        assert res_not_found.business_outcome_code == "MEMBER_NOT_FOUND"

    finally:
        surface.close()


def test_escalation_workflow_e2e(live_server):
    surface = PlaywrightSurfaceDriver(headless=True)
    try:
        controller = EscalationController(surface=surface, evidence_dir="/tmp/evidence_tests/escalation")
        surface.navigate(f"{live_server}/member/transfer?id=MEM-7701")

        # Automation triggers lockout
        from src.schema.capability import MultiStrategyLocator, LocatorDefinition, LocatorType
        submit_btn = MultiStrategyLocator(
            primary=LocatorDefinition(strategy=LocatorType.CSS_SELECTOR, value="#btnAuthorizeWire"),
            robustness_rationale="Authorize wire button"
        )
        surface.click(submit_btn)

        # Trigger escalation
        req = controller.trigger_escalation(
            capability_id="test.transfer",
            step_id="step_auth",
            step_index=2,
            reason="Dual-control authorization required."
        )
        assert req.incident_id.startswith("ESC-")

        # Human operator takes control on SAME session
        rec = controller.human_takeover_action(req, operator_id="TEST_SUPERVISOR")
        assert rec.outcome == "resolved"

        # Resume automation
        resumed = controller.resume_automation(rec)
        assert resumed is True
        assert "SUPERVISOR OVERRIDE VERIFIED" in surface.get_dom_content()

    finally:
        surface.close()
