"""
Pluggable LLM Provider Interface.
Allows swapping between Gemini, OpenAI, Anthropic, or Guided Autonomous Discovery.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentActionDecision(BaseModel):
    action_type: str                             # "navigate", "fill", "click", "extract", "finish"
    target_description: str
    target_role: Optional[str] = None
    target_name: Optional[str] = None
    target_text: Optional[str] = None
    value: Optional[str] = None
    field_name: Optional[str] = None
    reasoning: str
    confidence: float = 1.0


class LLMProvider(ABC):
    @abstractmethod
    def decide_next_action(
        self,
        goal: str,
        current_url: str,
        accessibility_tree_text: str,
        action_history: List[Dict[str, Any]]
    ) -> AgentActionDecision:
        """Analyze current perception and history to choose the next UI action."""
        pass
