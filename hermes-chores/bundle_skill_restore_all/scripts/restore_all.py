#!/usr/bin/env python3
"""
Batch-restore all user-modified bundled skills to their original bundled version.

Usage:
    python3 restore_all.py              # restore all modified bundled skills
    python3 restore_all.py --dry-run    # show what would be restored
    python3 restore_all.py --check      # only list modified skills, don't restore

Requires Hermes venv active and PYTHONPATH pointing to hermes-agent root.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── hermès imports ──────────────────────────────────────────────────────────
HERMES_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES_ROOT / "hermes-agent"))

from tools.skills_sync import reset_bundled_skill, sync_skills


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-restore user-modified bundled skills"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be restored without modifying anything",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only list modified bundled skills, don't restore",
    )
    args = parser.parse_args()

    result = sync_skills(quiet=True)
    modified: list[str] = result.get("user_modified", [])
    total: int = result.get("total_bundled", 0)

    if not modified:
        print(f"✓ All {total} bundled skills are in sync. Nothing to restore.")
        return

    print(f"Found {len(modified)} user-modified skill(s) out of {total} bundled:")
    for name in modified:
        print(f"   ~ {name}")

    if args.check:
        return

    if args.dry_run:
        print("\n[Dry-run] Would restore the above skills. Pass --dry-run to see, omit to execute.")
        return

    print()
    ok: list[str] = []
    fail: list[tuple[str, str]] = []
    for name in modified:
        r = reset_bundled_skill(name, restore=True)
        if r.get("ok"):
            ok.append(name)
            print(f"  ✔ {name} — restored")
        else:
            msg = r.get("message", "unknown error")
            fail.append((name, msg))
            print(f"  ✘ {name} — {msg}")

    print(f"\nRestored: {len(ok)}, Failed: {len(fail)}")
    if fail:
        for name, msg in fail:
            print(f"  {name}: {msg}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
