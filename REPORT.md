# System Architecture & Design Report: Computer-Use Automation System

**Interface.ai Take-Home Engineering Evaluation**  
**Author / Engineer**: Antigravity Engineering Candidate  
**Domain**: Backend Integration Layer & Computer-Use Automation for Legacy Banking Software  

---

## 1. Architecture

### 1.1 Core Problem & Architecture Inversion
In US banks and credit unions, core banking systems (e.g., Fiserv, FIS, Jack Henry) and servicing portals lack modern REST/GraphQL APIs. Driving these systems via full computer-use (invoking an LLM per click/keystroke) in production is slow, prohibitively expensive (\$0.05–\$0.20 per transaction), non-deterministic, and prone to hallucinations.

Our architecture implements an **asymmetric two-phase lifecycle**:
1. **Discovery Phase (LLM-in-the-Loop Exploration)**: An autonomous agent observes the live interface, navigates non-semantic layouts, reasons about control affordances, extracts data, and compiles the discovered trajectory into a structured, parameterized, versioned capability artifact.
2. **Production Execution Phase (Deterministic Replay Engine)**: Calling AI agents in production invoke the capability by name with typed arguments (e.g., `member_id = "MEM-7701"`). The replay engine executes at machine speed (milliseconds per step) with **zero LLM involvement in the decision loop**, using multi-strategy locator resolution, active checkpoint assertions, and an explicit business outcome router.

```
+-----------------------------------------------------------------------------------+
|                                1. DISCOVERY PHASE                                 |
|                                                                                   |
|  [Natural Language Goal]                                                          |
|           │                                                                       |
|           ▼                                                                       |
|  [Discovery Agent] ──(Perceives)──► [SurfaceDriver: Chrome / OS Accessibility]    |
|           │                                      │                                |
|     (Observe-Decide-Act)                         ▼                                |
|           │                         [Accessibility Tree (AXNode)]                 |
|           ▼                                                                       |
|  [LLM Provider: Gemini / Guided] ──(Trajectory)──► [Trajectory Compiler]          |
+──────────────────────────────────────────────────────────┼────────────────────────+
                                                           │ Emits
                                                           ▼
+───────────────────────────────────────────────────────────────────────────────────+
|                      2. PRODUCTION DETERMINISTIC REPLAY                           |
|                                                                                   |
|  [Caller AI Agent] ──(member_id="MEM-7701")──► [ReplayEngine (NO LLM)]            |
|                                                        │                          |
|                       ┌────────────────────────────────┴────────────────────────┐ |
|                       ▼                                                         ▼ |
|             [Multi-Strategy Locators]                                [Safety Policy]
|           (AX Role/Name -> Text -> CSS)                          (Allowlist + Redaction)
|                       │                                                         │ |
|                       ▼                                                         ▼ |
|             [Target Banking Console]                                 [Risk Classifier]
|                       │                                                           |
|        ┌──────────────┴──────────────────────────┐                                |
|        ▼                                         ▼                                |
| [Outcome Router]                       [Dual-Control Gate]                        |
|   ├── Success ($14,250.80)                       │                                |
|   ├── Business Outcome (AC-404 Not Found)        ▼                                |
|   └── Interstitial Recovery            [Human-in-the-Loop Escalation]             |
|                                        (Session Pause -> Same Session Takeover)   |
+───────────────────────────────────────────────────────────────────────────────────+
```

### 1.2 Key Architectural Decisions & Trade-offs

| Decision | Alternative Considered | Rationale & Trade-off |
| :--- | :--- | :--- |
| **Accessibility Tree over Raw DOM** | Full DOM HTML parsing or Raw Vision Coordinates | Legacy banking screens consist of deeply nested tables (`<table>`), framesets, dynamic IDs (`ctl00$MainContent$txtMemberId`), and non-semantic divs without `data-testid` attributes. Raw DOM floods the LLM context with noise. Vision-only coordinates break upon resolution changes. The **Accessibility Tree (AX)** filters visual clutter, exposes exact interactive roles (`textbox`, `button`), semantic names, and state (`disabled`, `focused`), and unifies Web and Desktop perception under a single model. |
| **Two-Phase Separation (Discovery vs Replay)** | Pure LLM Agent on every invocation | Eliminates latency (5,000ms LLM round-trip $\rightarrow$ 50ms deterministic replay), slashes inference costs to zero in production, and provides regulatory determinism required by bank auditors. Replay will not hallucinate clicks. |
| **In-Process Engine with Pluggable Drivers** | Distributed microservices / message queues | Per the assignment brief, premature scaling infrastructure (Kafka, Kubernetes, Celery) adds operational overhead without improving the core problem. The engine is modular, synchronous-capable, and embeddable directly as an agent tool or wrapped behind a lightweight FastAPI endpoint. |
| **Local Hostile Target Surface (`ApexCore 9.4`)** | Public demo sites (e.g., SauceDemo, TodoMVC) | Public sites change without warning, experience network flakiness, and fail to reflect the hostile reality of banking cores (non-semantic table layouts, dynamic ASP.NET IDs, GLBA session warning modals, and dual-control supervisor overrides). |

---

## 2. Artifact Schema

The capability artifact (`src/schema/capability.py`) is a typed, versioned specification designed to be both machine-executable by the replay engine and auditable by bank compliance officers.

### 2.1 Schema Design Principles
1. **Contract-First, Not a Raw Transcript**: The raw LLM transcript contains conversational filler, token tokens, exploratory backtracks, and dead-ends. The capability artifact prunes this into an optimal, ordered execution pipeline.
2. **Parameterized Generalization**: Hardcoded discovery literals (e.g., `"MEM-7701"`) are compiled into mustache template bindings (`"{{inputs.member_id}}"`) backed by typed input schemas (`InputParameter`).
3. **Multi-Strategy Locator Bundles**: Controls are never identified by a single fragile selector. Every step carries a `MultiStrategyLocator` containing:
   - `primary`: Accessibility Role & Accessible Name (`getByRole("textbox", name="Member ID")`).
   - `fallbacks`: Visible text anchor (`getByText("Execute Inquiry")`), relational table cell anchor (`tr:has-text('Savings') >> td:nth-child(3)`), and CSS/XPath fallbacks.
   - `robustness_rationale`: An explicit engineering justification recorded during discovery detailing why this targeting survives layout churn.
4. **Explicit Checkpoints & Success Assertions**: Assertions confirm that a step actually transitioned application state (e.g., verifying `url_contains:/apexcore/member/detail`) rather than blindly assuming a click succeeded.
5. **Declared Business Outcomes**: Legitimate business exceptions (such as `AC-404: Member Record Not Found`) are formally declared with detection rules and mapped return codes.

---

## 3. Determinism & Error Handling

### 3.1 Eliminating Replay Non-Determinism
Replay achieves determinism through three load-bearing mechanisms:
1. **Zero LLM In Loop**: Decisions are driven strictly by the serialized capability contract.
2. **Sequential Multi-Strategy Resolution**: The driver tries the primary accessibility locator. If delayed by rendering or DOM hydration, it systematically evaluates fallbacks. If an element shifts in the DOM tree but retains its accessible role and text label, resolution succeeds without intervention.
3. **Auto-Waiting & Settling**: Built-in micro-waits poll for DOM churn and network quiescence (`domcontentloaded` + frame settling) before dispatching events, preventing race conditions on slow legacy enterprise servers.

### 3.2 Error & Outcome Taxonomy
The most critical defect in enterprise automation is treating domain conditions as crashes. Our `ReplayResult` contract (`src/schema/result.py`) establishes an explicit 4-tier taxonomy:

```
                            [Event Encountered]
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
[Expected Business Outcome]   [Recoverable State]         [Hard Failure]
 - AC-404: Member Not Found    - Session Inactivity Modal  - Selector Missing
 - Insufficient Funds          - Daily Compliance Banner   - Server 500
 - Account Inactive            - Transient Latency         - Checkpoint Failed
         │                           │                           │
         ▼                           ▼                           ▼
 Status: BUSINESS_OUTCOME       Action: Auto-Dismiss & Retry  Status: FAILED_HARD
 Returns structured data to    Logs: RECOVERED status        Captures screenshot,
 caller; NO crash alert.       Continues execution.          traces, & diagnostics.
```

1. **Expected Business Outcomes (`ExecutionStatus.BUSINESS_OUTCOME`)**:
   - *Example*: Inquiring on member `MEM-9999` renders an alert: `"AC-404: Member Record [MEM-9999] not found"`.
   - *Behavior*: Replay detects the pattern matching `artifact.business_outcomes`. It returns `{"status": "business_outcome", "business_outcome_code": "MEMBER_NOT_FOUND", "outputs": {"found": false}}`. The calling agent receives an actionable answer rather than a pipeline error.
2. **Recoverable Conditions (`ExecutionStatus.RECOVERED`)**:
   - *Example*: Legacy banking cores often spawn periodic compliance prompts (e.g., `"Session inactivity warning - Click 'Extend Session'"`).
   - *Behavior*: Replay scans for known interstitials before executing each step. Upon detection, it clicks the dismissal control, verifies clearance, and proceeds. The run completes with status `RECOVERED` and telemetry in the execution trace.
3. **Hard Failures (`ExecutionStatus.FAILED_HARD`)**:
   - *Example*: Target element missing after all fallbacks or server returning an unhandled 500 error.
   - *Behavior*: Immediate fail-stop. The engine captures a high-resolution screenshot (`step_N_failure.png`), DOM snapshot, and generates a structured `FailureDiagnostic` indicating expected vs. observed state.

---

## 4. Heterogeneity & Multi-Tenant

### 4.1 Surface Abstraction (Web vs. Legacy Web vs. Desktop)
Enterprise back-offices run heterogeneous surfaces: modern React portals, legacy ASP.NET/JSP framesets, and native Windows desktop clients (WinForms, WPF, terminal emulators).

We enforce a strict boundary via the `SurfaceDriver` abstraction (`src/surface/base.py`):
- **Perception Seam**: The surface driver normalizes the visual interface into an `AXNode` tree. Whether querying Chrome via Playwright/CDP (`Accessibility.getFullAXTree`) or native Windows via UI Automation (`IUIAutomationTreeWalker`), both emit the identical hierarchical tree of roles, names, and states.
- **Action Seam**: High-level actions (`click`, `fill`, `get_text`) map to standard OS or browser events. The `ReplayEngine` and `CapabilityArtifact` schemas contain **zero DOM-specific or browser-specific primitives**.
- **Desktop Extension**: As demonstrated in `src/surface/desktop.py`, driving a native desktop app requires only swapping `PlaywrightSurfaceDriver` for `DesktopSurfaceDriver` (which dispatches Windows UIA `InvokePattern` / `ValuePattern`). The recorded flow remains identical.

### 4.2 Multi-Tenant Reuse at Scale
In banking SaaS, hundreds of institutions run the same underlying software (e.g., Fiserv Signature or Jack Henry SilverLake) with differing CSS themes, custom branding, localized field labels, and minor version variances.

To prevent re-recording artifacts per institution, our architecture uses a **Base Template + Tenant Overlay** model:
1. **Base Capability**: Defines the core invariant workflow (e.g., `member_lookup_base.json`: Steps 1–3, inputs, outputs, and primary semantic locators).
2. **Tenant Overlays**: A lightweight configuration file per institution specifying:
   - Route/URL patterns: `https://{tenant_slug}.corebanking.com/servicing`
   - Selector overrides: If Tenant B replaced `"Member ID"` with `"Customer CIF"`, the tenant overlay injects `"Customer CIF"` into the locator fallback sequence.
   - Parameter transformers: Custom date formats or branch codes.
3. **Drift Detection**: When replay runs across tenants, telemetry tracks which fallback strategy succeeded. If a tenant consistently relies on Fallback 3 rather than the Primary locator, the system flags **Tenant Drift** for review, allowing proactive updates without downtime.

---

## 5. Escalation & Handoff

### 5.1 Stuck State & Policy Blocker Detection
Escalation is triggered automatically under three conditions:
1. **High-Risk Dual-Control Gate**: Reaching an irreversible operation (e.g., wire transfer, account freeze) that policy mandates requires human supervisor override.
2. **Unrecognized Security Gate**: Encountering a dual-control challenge (e.g., Supervisor PIN prompt `902104` or CAPTCHA).
3. **Loop / Dead-End Detection**: Repeating an action without observing a corresponding state change.

### 5.2 Control-Transfer Model on the Live Session
A common design flaw is abandoning the current session and asking a human to start over in a fresh window. In banking, restarting requires re-authentication, MFA re-entry, and losing transactional state.

Our `EscalationController` (`src/escalation/handoff.py`) manages a stateful handover on the **exact same live session**:

```
[AUTOMATION_ACTIVE]
       │
       │ (High-risk gate / Lockout encountered)
       ▼
[HANDOFF_PENDING]
  ├── Pause automation event loop
  ├── Generate InterventionRequest (Incident ID, context, blockage screenshot)
  └── Acquire session control mutex
       │
       ▼
[HUMAN_CONTROL]
  ├── Live browser session remains open on same page
  ├── Human supervisor enters authorization PIN (e.g. 902104) and clicks approve
  └── Operator records action and signals resolution
       │
       ▼
[HANDOFF_RETURN]
  ├── Verification of post-operator state (cleared lock banner)
  ├── Audit trail logged with operator ID and timestamp
  └── Release mutex
       │
       ▼
[AUTOMATION_RESUMED]
  └── Deterministic replay completes remaining steps
```

---

## 6. Safety

### 6.1 Policy Guardrails (`src/guardrails/policy.py`)
- **Strict Host/Route Allowlisting**: Navigation is validated against configurable regex patterns. Navigation to arbitrary external domains is blocked at the driver boundary before any socket is opened.
- **Action Whitelisting**: Restricts execution to non-destructive interactions (`navigate`, `fill`, `click`, `extract`, `assert`), prohibiting arbitrary code evaluation or OS file drops.

### 6.2 Action Risk Classification (`src/guardrails/risk.py`)
Actions are classified into:
- `SAFE_REVERSIBLE`: Page navigation, read/inquiry operations, text field entry prior to submission.
- `RISKY_MUTATION`: Standard form submissions that update non-financial records.
- `RISKY_IRREVERSIBLE`: High-risk financial operations (FedWire release, ACH transfer, account closure). Under banking compliance, these actions trigger mandatory human supervisor confirmation.

### 6.3 Regulated Financial PII Redaction (`src/guardrails/redaction.py`)
Banking compliance (GLBA, PCI-DSS) strictly forbids logging unmasked financial secrets. Our redaction engine:
- Intercepts all strings, dictionaries, error logs, and execution traces.
- Masks Social Security Numbers (`***-**-8821`), account numbers (`SAV-****-88`), and card numbers (`****-****-****-4444`).
- Completely redacts passwords, PINs, and authentication tokens (`[REDACTED_SECRET]`).

### 6.4 Guardrail Limits
- **Visual PII in Full Screenshots**: Redaction currently operates on DOM and string telemetry. Full-page raster screenshots may contain visible unmasked customer addresses unless server-side layout masks or canvas blurring are applied. In high-security environments, screenshot capture should be restricted to bounding boxes excluding sensitive PII regions.

---

## 7. Cuts

To deliver a production-grade, end-to-end working vertical slice, depth was prioritized over superficial breadth:

### What Was Cut & Why
1. **Real-Time Co-Browsing Operator UI**: Building a WebRTC / VNC remote canvas streaming server was omitted in favor of a clean, robust CLI/API control-transfer model that pauses and drives the live browser session. The control-transfer mutex and state machine are real and verified; the operator interface was kept minimal.
2. **Native Windows Desktop Implementation**: Building a C# / Win32 hook for desktop was stubbed via `DesktopSurfaceDriver` in `src/surface/desktop.py`. The interface seam and accessibility mapping are fully specified and architected.
3. **Multi-Tenant Routing Microservice**: Tenant config overlays were designed and documented, but runtime tenant routing plumbing was kept in-process.

### What to Build Next
1. **Self-Healing Locator Drift Optimizer**: An asynchronous worker that analyzes fallback usage logs and updates primary locators when layout shifts occur, without requiring re-discovery.
2. **Pixel-Level PII Redaction Filter**: An OpenCV image processing pass applied to diagnostic screenshots before disk persistence to blur SSN and balance bounding boxes.
3. **Agent Capability Registry (MCP Server)**: Exposing saved capabilities over the Model Context Protocol (MCP) or OpenAPI schema so conversational agents (e.g. Gemini, Claude) can dynamically discover and invoke capabilities as tools.
