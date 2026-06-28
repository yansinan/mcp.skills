#!/usr/bin/env python3
"""Batch reset all bundled skills.

This script is intended to live under the skill as a reusable helper.
It supports dry-run, restore-vs-rebaseline modes, and targets the bundled
skills currently discoverable in the installed Hermes bundle.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch reset bundled skills")
    parser.add_argument("--restore", action="store_true", help="Delete user copies and restore bundled versions (default)")
    parser.add_argument("--rebaseline", action="store_true", help="Only clear manifest entries and rebaseline without deleting user copies")
    parser.add_argument("--dry-run", action="store_true", help="List matching bundled skills without changing anything")
    parser.add_argument("--name", action="append", default=[], help="Only reset specific bundled skill names; repeatable")
    args = parser.parse_args()

    # Default to restore=True unless explicitly rebaseline was requested.
    restore = True
    if args.rebaseline:
        restore = False
    if args.restore:
        restore = True

    # Hermes imports live from its venv/wrapper; keep import local.
    from tools.skills_sync import _discover_bundled_skills, _get_bundled_dir, reset_bundled_skill

    bundled_dir = _get_bundled_dir()
    bundled = [name for name, _ in _discover_bundled_skills(bundled_dir)]
    target_names = args.name or bundled

    if args.dry_run:
        for name in sorted(target_names):
            print(name)
        return 0

    ok = True
    for name in sorted(target_names):
        result = reset_bundled_skill(name, restore=restore)
        status = "OK" if result.get("ok") else "FAIL"
        action = result.get("action")
        print(f"{status}\t{name}\t{action}")
        if not result.get("ok"):
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
