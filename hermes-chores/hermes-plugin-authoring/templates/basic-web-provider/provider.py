"""Minimal test web search provider — for proving plugin load + override works."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)


class TestWebProvider(WebSearchProvider):
    """A minimal provider that returns mock data for testing.

    Replace the implementation with real logic (API calls, scraping, etc.).
    """

    @property
    def name(self) -> str:
        return "test-extract"

    @property
    def display_name(self) -> str:
        return "Test Extract Provider"

    def is_available(self) -> bool:
        """Cheap check — always available for dev/testing."""
        return True

    def supports_search(self) -> bool:
        return False   # Start with extract-only

    def supports_extract(self) -> bool:
        return True

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Return mock content for testing plugin routing.

        NOTE: extract() returns a flat list of per-URL results (NOT wrapped
        in success/data). For real implementation, it can be async def.
        """
        results: List[Dict[str, Any]] = []
        for url in urls:
            logger.info("Test extract: %s", url)
            results.append({
                "url": url,
                "title": "Mock Page Title",
                "content": f"# Mock Content\n\nThis is mock content from {url}\n\nTest paragraph.",
                "raw_content": f"Mock raw content from {url}",
                "metadata": {"source": "test-extract", "mock": True},
            })
        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Test Extract Provider",
            "badge": "dev · mock data · extract only",
            "tag": "Returns mock content for testing plugin registration and routing.",
            "env_vars": [],
        }
