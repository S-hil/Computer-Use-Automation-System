"""
Observability and Structured Logging System.
Produces auditable execution logs with automatic financial PII redaction.
Outputs both human-readable Rich console messages and structured JSONL.
"""

import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.guardrails.redaction import redact_text, sanitize_data

console = Console()


class StructuredLogger:
    def __init__(self, log_file_path: Optional[str] = None, component_name: str = "System"):
        self.component_name = component_name
        self.log_file_path = log_file_path
        if log_file_path:
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    def _write_jsonl(self, event_type: str, payload: Dict[str, Any]):
        if not self.log_file_path:
            return
        entry = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "component": self.component_name,
            "event": event_type,
            "data": sanitize_data(payload)
        }
        with open(self.log_file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def info(self, message: str, **kwargs):
        clean_msg = redact_text(message)
        console.print(f"[bold cyan][{self.component_name}][/bold cyan] {clean_msg}")
        self._write_jsonl("INFO", {"message": clean_msg, **kwargs})

    def step(self, step_index: int, description: str, action: str, **kwargs):
        clean_desc = redact_text(description)
        console.print(f"[bold green]▶ Step {step_index}:[/bold green] [yellow]{action}[/yellow] - {clean_desc}")
        self._write_jsonl("STEP_EXECUTION", {
            "step_index": step_index,
            "action": action,
            "description": clean_desc,
            **kwargs
        })

    def success(self, message: str, **kwargs):
        clean_msg = redact_text(message)
        console.print(f"[bold green]✔ {clean_msg}[/bold green]")
        self._write_jsonl("SUCCESS", {"message": clean_msg, **kwargs})

    def warning(self, message: str, **kwargs):
        clean_msg = redact_text(message)
        console.print(f"[bold yellow]⚠ {clean_msg}[/bold yellow]")
        self._write_jsonl("WARNING", {"message": clean_msg, **kwargs})

    def business_outcome(self, outcome_code: str, message: str, **kwargs):
        clean_msg = redact_text(message)
        panel = Panel(
            Text(f"Business Outcome: {outcome_code}\n{clean_msg}", style="bold yellow"),
            title="[yellow]Legitimate Domain Outcome[/yellow]",
            border_style="yellow"
        )
        console.print(panel)
        self._write_jsonl("BUSINESS_OUTCOME", {
            "outcome_code": outcome_code,
            "message": clean_msg,
            **kwargs
        })

    def error(self, message: str, **kwargs):
        clean_msg = redact_text(message)
        console.print(f"[bold red]✖ {clean_msg}[/bold red]")
        self._write_jsonl("ERROR", {"message": clean_msg, **kwargs})

    def escalation(self, incident_id: str, reason: str, **kwargs):
        clean_reason = redact_text(reason)
        panel = Panel(
            Text(f"INCIDENT: {incident_id}\nREASON: {clean_reason}\nLive session paused. Control transferred to human operator.", style="bold red"),
            title="[red]Human-in-the-Loop Escalation[/red]",
            border_style="red"
        )
        console.print(panel)
        self._write_jsonl("ESCALATION_TRIGGERED", {
            "incident_id": incident_id,
            "reason": clean_reason,
            **kwargs
        })
