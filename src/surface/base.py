"""
Surface Driver Abstraction.
Defines the boundary between 'how we perceive and act on an interface'
and 'the recorded flow'.

By abstracting interaction to Accessibility Nodes and Multi-Strategy Locators,
the exact same replay engine and capability artifacts run whether driving:
1. A modern web app (DOM + AX Tree)
2. A legacy web app (Frames, tables, generated IDs, no data-testid)
3. A native desktop app (OS Accessibility API / Windows UIA / macOS AXUIElement)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from src.schema.capability import MultiStrategyLocator


class AXNode(BaseModel):
    """Normalized Accessibility Tree Node."""
    role: str
    name: str = ""
    value: Optional[str] = None
    description: Optional[str] = None
    focused: bool = False
    disabled: bool = False
    bounds: Optional[Dict[str, float]] = None    # x, y, width, height
    children: List["AXNode"] = Field(default_factory=list)

    def to_tree_string(self, depth: int = 0) -> str:
        """Render a readable indented string representation for LLM perception."""
        if self.description:
            return self.description
        indent = "  " * depth
        val_str = f" value='{self.value}'" if self.value is not None else ""
        name_str = f" '{self.name}'" if self.name else ""
        lines = [f"{indent}- [{self.role}]{name_str}{val_str}"]
        for child in self.children:
            lines.append(child.to_tree_string(depth + 1))
        return "\n".join(lines)


try:
    AXNode.model_rebuild()
except AttributeError:
    AXNode.update_forward_refs()


class SurfaceDriver(ABC):
    """Abstract interface for all surface automation technologies."""

    @abstractmethod
    def navigate(self, url: str) -> None:
        """Navigate to target entry point or URL."""
        pass

    @abstractmethod
    def get_current_url(self) -> str:
        """Return the current active URL or screen identifier."""
        pass

    @abstractmethod
    def get_accessibility_snapshot(self) -> AXNode:
        """Capture the full semantic accessibility tree of the current surface."""
        pass

    @abstractmethod
    def take_screenshot(self, output_path: str) -> str:
        """Capture a visual screenshot for observability and diagnostics."""
        pass

    @abstractmethod
    def click(self, locator: MultiStrategyLocator, timeout_ms: int = 5000) -> str:
        """Click on the target control using multi-strategy resolution. Returns strategy used."""
        pass

    @abstractmethod
    def fill(self, locator: MultiStrategyLocator, text: str, timeout_ms: int = 5000) -> str:
        """Fill / type text into an input control. Returns strategy used."""
        pass

    @abstractmethod
    def get_text(self, locator: MultiStrategyLocator, timeout_ms: int = 5000) -> str:
        """Read text content or value from a target control."""
        pass

    @abstractmethod
    def is_visible(self, locator: MultiStrategyLocator, timeout_ms: int = 2000) -> bool:
        """Check if target control is currently present and visible on screen."""
        pass

    @abstractmethod
    def wait_for_idle(self, timeout_ms: int = 3000) -> None:
        """Wait for transient loading, animations, or DOM churn to settle."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release surface resources."""
        pass
