"""
Playwright-based Web Surface Driver.
Drives Chrome using Accessibility Tree inspection and Multi-Strategy Locators.
Handles hostile legacy surfaces (nested tables, no test-ids, dynamic IDs).
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
            raise RuntimeError("Browser not initialized")
        self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        self.wait_for_idle(500)

    def get_current_url(self) -> str:
        return self.page.url if self.page else ""

    def get_accessibility_snapshot(self) -> AXNode:
        """Capture the semantic accessibility tree of the current page."""
        try:
            aria_text = self.page.locator("body").aria_snapshot()
            return AXNode(
                role="document",
                name=self.page.title(),
                description=aria_text
            )
        except Exception:
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
        """Resolve a single LocatorDefinition to a Playwright Locator."""
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
                # Structural Table Cell Relative Strategy
                # E.g. find row matching row_match, then extract column
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

            # Check if at least one matching element exists within short timeout
            count = loc.count()
            if count > 0 and loc.first.is_visible(timeout=timeout_ms):
                return loc.first
            return None
        except Exception:
            return None

    def find_robust_locator(self, multi_locator: MultiStrategyLocator, timeout_ms: int = 5000) -> tuple[Locator, str]:
        """
        Tries primary strategy first, then cycles through fallbacks until an element is matched.
        Returns (Playwright Locator, strategy_name_used).
        """
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            # 1. Try Primary
            loc = self._resolve_locator(multi_locator.primary, timeout_ms=500)
            if loc:
                return loc, f"primary:{multi_locator.primary.strategy.value}"

            # 2. Try Fallbacks in declared sequence
            for idx, fallback in enumerate(multi_locator.fallbacks):
                loc = self._resolve_locator(fallback, timeout_ms=500)
                if loc:
                    return loc, f"fallback_{idx+1}:{fallback.strategy.value}"

            time.sleep(0.2)

        # Final attempt with primary to raise the informative error
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
