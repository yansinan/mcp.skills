"""Test web extract plugin — register the test provider.

Deploy to ~/.hermes/plugins/web/<name>/ and use RELATIVE imports.
"""

from __future__ import annotations

# IMPORTANT: Use RELATIVE imports for user plugins (~/.hermes/plugins/).
# Relative imports correctly resolve from the plugin's own directory.
# Absolute imports like `from plugins.web.<name>.provider import ...`
# only work for bundled plugins in the hermes-agent repo.
from .provider import TestWebProvider  # ✅ correct for user plugins


def register(ctx) -> None:
    """Register the test web search provider."""
    ctx.register_web_search_provider(TestWebProvider())
