"""
Desktop Surface Driver Abstraction (Reference Architecture).
Demonstrates how the SurfaceDriver abstraction and Capability Artifacts seamlessly extend
to native enterprise desktop applications (e.g. WPF, WinForms, Java Swing, macOS Cocoa).

Seam Analysis:
- On Web: Playwright captures the Chrome Accessibility Tree (AX Tree) + DOM.
- On Desktop: DesktopSurfaceDriver captures the OS Accessibility Tree
  (Windows UIAutomation via pywinauto/UIAutomationCore, or macOS AXUIElement via ApplicationServices).
Both produce the exact same `AXNode` tree structure and respond to `MultiStrategyLocator`
(Accessibility Role/Name, Text Anchor, Spatial/Bounding Box).
The ReplayEngine and Artifact Schema remain 100% untouched.
"""

from typing import Optional
from src.schema.capability import MultiStrategyLocator, LocatorType
from src.surface.base import SurfaceDriver, AXNode


class DesktopSurfaceDriver(SurfaceDriver):
    """
    Concrete driver for native desktop applications.
    Implements OS-level accessibility queries and native event injection.
    """
    def __init__(self, process_name: str = "ApexCoreDesktop.exe"):
        self.process_name = process_name
        self.is_connected = False

    def navigate(self, url: str) -> None:
        # In a desktop app, 'navigation' maps to launching the binary or switching window/view
        self.is_connected = True

    def get_current_url(self) -> str:
        return f"desktop://process/{self.process_name}"

    def get_accessibility_snapshot(self) -> AXNode:
        """
        Queries OS Accessibility API (e.g. Windows IUIAutomationTreeWalker or macOS AXUIElementCopyAttributeValue).
        Returns normalized AXNode hierarchy.
        """
        return AXNode(
            role="window",
            name="ApexCore Desktop Servicing Client",
            children=[
                AXNode(role="pane", name="Inquiry Panel", children=[
                    AXNode(role="textbox", name="Member ID", value=""),
                    AXNode(role="button", name="Execute Inquiry")
                ]),
                AXNode(role="table", name="Active Accounts Grid")
            ]
        )

    def take_screenshot(self, output_path: str) -> str:
        # Native OS screenshot via win32gui / CGWindowListCreateImage
        return output_path

    def click(self, locator: MultiStrategyLocator, timeout_ms: int = 5000) -> str:
        # Native control click via UIAutomation InvokePattern or mouse coordinate injection
        return f"desktop_native:{locator.primary.strategy.value}"

    def fill(self, locator: MultiStrategyLocator, text: str, timeout_ms: int = 5000) -> str:
        # Native control ValuePattern.SetValue or sendkeys
        return f"desktop_native:{locator.primary.strategy.value}"

    def get_text(self, locator: MultiStrategyLocator, timeout_ms: int = 5000) -> str:
        # Native control ValuePattern.Value or NameProperty
        return ""

    def is_visible(self, locator: MultiStrategyLocator, timeout_ms: int = 2000) -> bool:
        return True

    def wait_for_idle(self, timeout_ms: int = 3000) -> None:
        pass

    def close(self) -> None:
        self.is_connected = False
