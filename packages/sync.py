"""Sync backend/app/logic -> packages/kessler-toolkit/kessler_toolkit.

The backend logic layer is the source of truth. This script copies its modules
into the installable package, rewriting imports so the package is standalone.

Usage:
    python packages/sync.py           # regenerate package modules
    python packages/sync.py --check   # CI: fail if package is out of sync
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGIC = ROOT / "backend" / "app" / "logic"
CORE = ROOT / "backend" / "app" / "core"
PKG = ROOT / "packages" / "kessler-toolkit" / "kessler_toolkit"

MODULES = [
    "cdm_parser.py",
    "collision_probability.py",
    "propagation.py",
    "screening.py",
    "risk_engine.py",
]

REWRITES = [
    ("from app.core.exceptions import", "from kessler_toolkit.exceptions import"),
    ("from app.logic.", "from kessler_toolkit."),
    ("from app.logic import", "from kessler_toolkit import"),
]

HEADER = "# GENERATED from backend/app/logic — edit there, then run packages/sync.py\n"


def render(src: Path) -> str:
    text = src.read_text(encoding="utf-8")
    for old, new in REWRITES:
        text = text.replace(old, new)
    return HEADER + text


def render_exceptions() -> str:
    text = (CORE / "exceptions.py").read_text(encoding="utf-8")
    return HEADER + text


def main() -> int:
    check = "--check" in sys.argv
    PKG.mkdir(parents=True, exist_ok=True)
    targets = {PKG / name: render(LOGIC / name) for name in MODULES}
    targets[PKG / "exceptions.py"] = render_exceptions()

    stale = []
    for path, content in targets.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            if check:
                stale.append(path.name)
            else:
                with path.open("w", encoding="utf-8", newline="\n") as fh:
                    fh.write(content)
                print(f"synced {path.name}")

    if check and stale:
        print(f"OUT OF SYNC: {', '.join(stale)} — run: python packages/sync.py")
        return 1
    print("package in sync" if check else "done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
