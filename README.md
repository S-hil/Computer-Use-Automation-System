# Computer-Use Automation System: Banking Back-Office Integration Layer

A robust, enterprise-grade computer-use automation system built for banks and credit unions. This system lets an AI agent discover how to navigate legacy back-office banking software (which lacks APIs), compiles what it learned into a typed, parameterized capability artifact, and replays that capability deterministically in production **without any LLM in the loop**.

Developed for the **interface.ai** Take-Home Engineering Evaluation.

---

## Key Features

1. **Hostile Surface Simulation (`ApexCore 9.4 Banking Console`)**:
   - Realistic legacy bank servicing console featuring nested tables (`<table>`), dynamic ASP.NET IDs (`ctl00$MainContent$txtMemberId`), no `data-testid`s, GLBA session warning interstitials, and dual-control supervisor authorization gates.
2. **Goal-Driven LLM Discovery Loop**:
   - Observe $\rightarrow$ decide $\rightarrow$ act loop driving a live Chrome browser via semantic **Accessibility Tree (AX)** perception rather than brittle raw DOM.
   - Autonomous compiler generalizes trajectories into reusable, parameterized capability artifacts.
3. **Deterministic Replay (Zero LLM in Production)**:
   - High-speed execution (milliseconds per step) using multi-strategy locator bundles (Accessibility $\rightarrow$ Text Anchor $\rightarrow$ Relational Table $\rightarrow$ CSS).
   - Separates **Expected Business Outcomes** (e.g. `AC-404: Member Not Found`) from system crashes.
   - Auto-detects and dismisses recoverable session interstitials.
4. **Live-Session Human-in-the-Loop Escalation**:
   - Pauses automation upon encountering high-risk dual-control policy gates or unrecognized blockers.
   - Transfers control to a human supervisor on the **exact same live session** (not a fresh window), captures the manual intervention in an audit trail, and resumes seamlessly.
5. **Safety & Financial Data Redaction**:
   - Strict domain allowlist enforcement.
   - Automatic masking of SSNs, account numbers, and credit cards; redaction of credentials in logs and artifacts.

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- Google Chrome installed on your system (or Playwright Chromium)

### 1. Install Dependencies
```bash
python3 -m pip install -r requirements.txt
```

### 2. LLM Provider Configuration
The system works out of the box **with or without live external API keys**:
- **With Live LLM (Optional)**: Export your Google Gemini API key:
  ```bash
  export GEMINI_API_KEY="your-gemini-api-key"
  ```
  *(The Discovery Agent will automatically connect to `gemini-2.5-flash`)*.
- **Without Live Services (Zero Config / Offline Mode)**:
  If no API key is provided, the system automatically falls back to the **Autonomous Guided Discovery Engine**, which inspects the live accessibility tree, reasons about control affordances, and compiles the exact same authentic capability artifact.

---

## Demo Path: Exact Commands

Run the full vertical slice end-to-end with a single command, or run each phase individually:

### Run Everything (All Phases)
```bash
python3 demo.py --mode=all
```
This single command:
1. Boots the local `ApexCore 9.4` banking server on port 8088.
2. Executes the **LLM Discovery Run** to look up member `MEM-7701` and retrieve the savings balance, saving the capability artifact to `evidence/capability_member_lookup.json`.
3. Executes **Deterministic Replay** on `MEM-7701` (retrieving `$14,250.80` with zero LLM).
4. Executes **Deterministic Replay** on non-existent `MEM-9999`, demonstrating legitimate **Business Outcome (`MEMBER_NOT_FOUND`)** handling.
5. Executes **Human-in-the-Loop Escalation**, triggering a dual-control lockout, taking over the live session, approving via supervisor PIN `902104`, and resuming automation.
6. Populates all logs, traces, and screenshots in `evidence/`.

---

### Run Individual Workflows

#### 1. Discovery Run
Runs the discovery loop against the live application and emits the capability artifact:
```bash
python3 demo.py --mode=discovery
```

#### 2. Deterministic Replay (Happy Path)
Replays the saved artifact for a specific member ID without LLM calls:
```bash
python3 demo.py --mode=replay --member-id=MEM-7701
```

#### 3. Replay with Business Outcome (Member Not Found)
Demonstrates domain outcome routing (returns `MEMBER_NOT_FOUND` as structured data, not an error):
```bash
python3 demo.py --mode=business-outcome --member-id=MEM-9999
```

#### 4. Live Session Escalation & Takeover
Demonstrates pausing live automation, human takeover on the same browser session, and resumption:
```bash
python3 demo.py --mode=escalation
```

#### 5. Run Visibly (Non-Headless)
To watch Chrome execute live in a visible window, add `--no-headless`:
```bash
python3 demo.py --mode=all --no-headless
```

---

## Running Automated Tests

Run the full test suite verifying unit logic and end-to-end integration:
```bash
python3 -m pytest tests/ -v
```

All 11 tests cover:
- Capability schema serialization, parameter binding, and result contracts
- Policy allowlists, risk classification, and financial PII redaction
- Legacy banking server inquiry and error handling
- End-to-end discovery and deterministic replay
- End-to-end live session escalation and control handoff

---

## Project Structure

```
.
├── REPORT.md                          # Mandatory 7-heading design write-up
├── README.md                          # Setup, demo commands, and architecture
├── requirements.txt                   # Project dependencies
├── demo.py                            # Unified CLI demo runner
├── evidence/                          # Generated run evidence
│   ├── capability_member_lookup.json  # Saved Capability Artifact
│   ├── discovery_run/                 # Discovery run logs and screenshots
│   ├── replay_success/                # Deterministic replay success logs & screenshots
│   ├── replay_business_outcome/       # Business outcome (AC-404) logs & screenshots
│   └── replay_escalation/             # Live session handoff logs & screenshots
├── src/
│   ├── target_app/                    # ApexCore 9.4 legacy banking mock portal
│   │   └── server.py                  # Standalone local HTTP banking server
│   ├── surface/                       # Surface driver abstraction
│   │   ├── base.py                    # SurfaceDriver ABC and AXNode model
│   │   ├── browser.py                 # Playwright/CDP driver (AX Tree + Multi-Locators)
│   │   └── desktop.py                 # Reference seam for native desktop applications
│   ├── schema/                        # Typed Capability Artifact and Replay contracts
│   │   ├── capability.py              # CapabilityArtifact, Step, Locators, Checkpoints
│   │   └── result.py                  # ReplayResult, ErrorTaxonomy, BusinessOutcome
│   ├── agent/                         # LLM Discovery Engine
│   │   ├── discovery_agent.py         # Observe-decide-act loop
│   │   └── compiler.py                # Trajectory -> Parameterized Capability compiler
│   ├── llm/                           # Pluggable LLM Providers
│   │   ├── provider.py                # LLMProvider base interface
│   │   ├── gemini.py                  # Google Gemini provider
│   │   └── guided.py                  # Autonomous Guided Discovery engine
│   ├── engine/                        # Deterministic Replay Engine
│   │   └── replay.py                  # Production executor (No LLM in loop)
│   ├── guardrails/                    # Safety & Compliance
│   │   ├── policy.py                  # Domain allowlists & action permissions
│   │   ├── risk.py                    # Safe/reversible vs risky/irreversible classifier
│   │   └── redaction.py               # Financial PII & credential redaction
│   ├── escalation/                    # Human-in-the-loop escalation
│   │   └── handoff.py                 # Live session pause, takeover, and resume
│   └── observability/                 # Structured logging & telemetry
│       └── logger.py                  # Rich console & JSONL logger
└── tests/                             # Automated test suite
    ├── test_schema.py                 # Schema tests
    ├── test_guardrails.py             # Policy & redaction tests
    ├── test_target_app.py             # Mock server tests
    └── test_e2e_replay.py             # End-to-end integration tests
```

---

## Technical Write-Up

For the complete technical write-up defending architectural choices, locator strategies, multi-tenant reuse, and error taxonomies, please see [`REPORT.md`](REPORT.md).
