"""
Playwright-based Web Surface Driver.

================================================================================
ENGINEERING DESIGN CHOICES & TRADE-OFFS:
================================================================================
1. Semantic Accessibility Perception over Raw DOM:
   - Trade-off: Inspecting raw DOM HTML gives complete source visibility, but in legacy
     enterprise banking applications it floods LLM context with tens of thousands of tokens
     of non-semantic table layouts (`<table cellpadding="3">`), script tags, and generated
     framework markup.
   - Decision: Perceive the surface through the Browser Accessibility Tree (via Playwright
     `aria_snapshot` / CDP `Accessibility.getFullAXTree`). The AX tree strips styling noise,
     normalizes nested table cells to semantic data rows, and exposes interactive controls
     by their functional role and accessible name. Crucially, this representation is identical
     to what native desktop screen-readers and OS automation frameworks perceive.

2. Sequential Fallback Cascade:
   - Trade-off: Single-point CSS or XPath selectors break whenever server-side form generation
     updates IDs or wraps elements in new container divs.
   - Decision: `find_robust_locator()` tries the primary Accessibility Role/Name first. If not
     immediately found (e.g. during DOM transition), it falls back sequentially through text
     anchors, relational table cells, and structural selectors. The exact strategy that
     resolved the element is logged for telemetry and drift detection.

3. Live Session Preservation for Escalation:
   - Trade-off: Closing a blocked session and opening a new one is easier to manage, but kills
     in-flight transactions, expires session tokens, and forces users to repeat MFA.
   - Decision: Maintain a persistent browser context (`BrowserContext`) that can be paused,
     transferred to an operator, and resumed in-place.
================================================================================
"""

import os
import time
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Locator

from src.schema.capability import MultiStrategyLocator, LocatorDefinition, LocatorType
from src.surface.base import SurfaceDriver, AXNode


class PlaywrightSurfaceDriver(SurfaceDriver):
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._initialize_browser()

    def _initialize_browser(self):
        self.playwright = sync_playwright().start()
        # Launch installed system Chrome or fallback to bundled Chromium
        try:
            self.browser = self.playwright.chromium.launch(
                channel="chrome",
                headless=self.headless,
                args=["--no-first-run", "--no-default-browser-check"]
            )
        except Exception:
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=["--no-first-run", "--no-default-browser-check"]
            )

        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True
        )
        self.page = self.context.new_page()

    def navigate(self, url: str) -> None:
        if not self.page:
            raise RuntimeError("Browser instance has not been initialized.")
        self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        self.wait_for_idle(500)

    def get_current_url(self) -> str:
        return self.page.url if self.page else ""

    def get_accessibility_snapshot(self) -> AXNode:
        """
        Capture the semantic accessibility tree of the current page.
        Prioritizes Playwright aria_snapshot, falling back to direct Chrome DevTools Protocol (CDP).
        """
        try:
            aria_text = self.page.locator("body").aria_snapshot()
            return AXNode(
                role="document",
                name=self.page.title(),
                description=aria_text
            )
        except Exception:
            # Fallback to direct CDP session
            try:
                cdp = self.page.context.new_cdp_session(self.page)
                tree = cdp.send("Accessibility.getFullAXTree")
                nodes = tree.get("nodes", [])
                lines = []
                for n in nodes:
                    role = n.get("role", {}).get("value", "")
                    name = n.get("name", {}).get("value", "")
                    if role and role not in ("none", "GenericContainer"):
                        lines.append(f"- [{role}] '{name}'")
                desc = "\n".join(lines)
                return AXNode(role="document", name=self.page.title(), description=desc)
            except Exception:
                return AXNode(role="document", name=self.page.title(), description="document")

    def _resolve_locator(self, loc_def: LocatorDefinition, timeout_ms: int = 2000) -> Optional[Locator]:
        """Resolve a single LocatorDefinition using Playwright's semantic and structural selectors."""
        try:
            if loc_def.strategy == LocatorType.AX_ROLE_NAME:
                # Primary: Semantic Accessibility role & name
                if loc_def.role and loc_def.name:
                    loc = self.page.get_by_role(loc_def.role, name=loc_def.name, exact=False)
                elif loc_def.role:
                    loc = self.page.get_by_role(loc_def.role)
                else:
                    loc = self.page.get_by_label(loc_def.name or loc_def.value)
            elif loc_def.strategy == LocatorType.TEXT_ANCHOR:
                # Visible Text Anchor
                loc = self.page.get_by_text(loc_def.value, exact=False)
            elif loc_def.strategy == LocatorType.TABLE_CELL:
                # Structural Table Cell Relative Strategy (handles legacy HTML tables without IDs)
                if loc_def.row_match:
                    row = self.page.locator(f"tr:has-text('{loc_def.row_match}')")
                    if loc_def.column_header:
                        loc = row.locator(f"td:has-text('{loc_def.column_header}')")
                    else:
                        loc = row.locator(loc_def.value or "td")
                else:
                    loc = self.page.locator(loc_def.value)
            elif loc_def.strategy == LocatorType.CSS_SELECTOR:
                loc = self.page.locator(loc_def.value)
            elif loc_def.strategy == LocatorType.XPATH:
                loc = self.page.locator(f"xpath={loc_def.value}")
            else:
                loc = self.page.locator(loc_def.value)

            # Confirm element is visible and interactable before returning
            if loc.count() > 0 and loc.first.is_visible(timeout=timeout_ms):
                return loc.first
            return None
        except Exception:
            return None

    def find_robust_locator(self, multi_locator: MultiStrategyLocator, timeout_ms: int = 5000) -> tuple[Locator, str]:
        """
        Executes cascading locator resolution:
        1. Tries primary semantic locator (AX Role/Name).
        2. If unresolvable within 500ms, cycles through declared fallbacks.
        Returns resolved Playwright Locator and telemetry label of the strategy used.
        """
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            # 1. Primary Strategy
            loc = self._resolve_locator(multi_locator.primary, timeout_ms=500)
            if loc:
                return loc, f"primary:{multi_locator.primary.strategy.value}"

            # 2. Fallbacks in declared sequence
            for idx, fallback in enumerate(multi_locator.fallbacks):
                loc = self._resolve_locator(fallback, timeout_ms=500)
                if loc:
                    return loc, f"fallback_{idx+1}:{fallback.strategy.value}"

            time.sleep(0.2)

        primary_def = multi_locator.primary
        raise TimeoutError(
            f"Failed to find element using primary ({primary_def.strategy.value}='{primary_def.value}') "
            f"or any of the {len(multi_locator.fallbacks)} fallbacks within {timeout_ms}ms."
        )

    def click(self, locator: MultiStrategyLocator, timeout_ms: int = 5000) -> str:
        loc, strategy = self.find_robust_locator(locator, timeout_ms)
        loc.scroll_into_view_if_needed(timeout=timeout_ms)
        loc.click(timeout=timeout_ms)
        self.wait_for_idle(300)
        return strategy

    def fill(self, locator: MultiStrategyLocator, text: str, timeout_ms: int = 5000) -> str:
        loc, strategy = self.find_robust_locator(locator, timeout_ms)
        loc.scroll_into_view_if_needed(timeout=timeout_ms)
        loc.fill(text, timeout=timeout_ms)
        self.wait_for_idle(200)
        return strategy

    def get_text(self, locator: MultiStrategyLocator, timeout_ms: int = 5000) -> str:
        loc, _ = self.find_robust_locator(locator, timeout_ms)
        return loc.inner_text(timeout=timeout_ms).strip()

    def is_visible(self, locator: MultiStrategyLocator, timeout_ms: int = 2000) -> bool:
        try:
            loc, _ = self.find_robust_locator(locator, timeout_ms)
            return loc.is_visible(timeout=timeout_ms)
        except Exception:
            return False

    def take_screenshot(self, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self.page.screenshot(path=output_path, full_page=True)
        return output_path

    def get_dom_content(self) -> str:
        return self.page.content() if self.page else ""

    def wait_for_idle(self, timeout_ms: int = 3000) -> None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass
        time.sleep(timeout_ms / 1000.0)

    def close(self) -> None:
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
