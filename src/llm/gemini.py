"""
Google Gemini LLM Provider.
Connects to Google Gemini API (gemini-2.5-flash or gemini-1.5-pro) when GEMINI_API_KEY is present.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional
from src.llm.provider import LLMProvider, AgentActionDecision

SYSTEM_PROMPT = """You are an expert Computer-Use Automation Discovery Agent for enterprise banking systems.
Your task is to examine the current UI Accessibility Tree and decide the single next action to make progress toward the user's goal.
You must return valid JSON only matching this format:
{
  "action_type": "navigate" | "fill" | "click" | "extract" | "finish",
  "target_description": "short description",
  "target_role": "textbox" | "button" | "tab" | null,
  "target_name": "Accessible label or null",
  "target_text": "Text anchor or null",
  "value": "text to type or URL or null",
  "field_name": "extracted variable name or null",
  "reasoning": "Explicit explanation of why this control was chosen and why it is robust"
}
"""


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.model_name = model_name

    def is_available(self) -> bool:
        return bool(self.api_key)

    def decide_next_action(
        self,
        goal: str,
        current_url: str,
        accessibility_tree_text: str,
        action_history: List[Dict[str, Any]]
    ) -> AgentActionDecision:
        if not self.is_available():
            raise RuntimeError("GEMINI_API_KEY not set in environment.")

        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model_name, system_instruction=SYSTEM_PROMPT)

        prompt = f"""
Goal: {goal}
Current URL: {current_url}

Previous Actions Taken:
{json.dumps(action_history, indent=2)}

Current Accessibility Tree Snapshot:
{accessibility_tree_text}

What is the next action to take? Provide JSON only:
"""
        response = model.generate_content(prompt)
        text = response.text.strip()

        # Extract JSON from potential code fences
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            return AgentActionDecision(**parsed)
        raise ValueError(f"Failed to parse LLM JSON response: {text}")
