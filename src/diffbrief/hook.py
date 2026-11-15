"""Install a pre-push hook that runs diffbrief.

A tool whose whole pitch is "look before you push" is useless if nothing makes
you look; this writes the smallest hook that does, and refuses to clobber one
somebody already wrote.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .diff import GitError

SCRIPT = """#!/bin/sh
# Installed by `diffbrief --install-hook`.
#
# Runs the same report you can run by hand. Exit 1 stops the push when the
# report has a `fail`; anything the tool cannot run is not a reason to block a
# push, so a missing command only prints a note and lets it through.
if command -v diffbrief >/dev/null 2>&1; then
    exec diffbrief
fi
echo "diffbrief: not on PATH, so this hook is not checking anything" >&2
echo "diffbrief: pip install -e . , or rm $(git rev-parse --git-path hooks)/pre-push" >&2
exit 0
"""


def hooks_dir(root: Path) -> Path:
    try:
        raw = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root,
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise GitError(f"cannot find the hooks directory: {error}") from error
    path = Path(raw)
    return path if path.is_absolute() else (root / path)


def install(root: Path) -> tuple[Path, bool]:
    """Write the hook. Returns (path, wrote) — wrote is False when it was already ours."""
    target = hooks_dir(root) / "pre-push"
    if target.exists():
        current = target.read_text()
        if "Installed by `diffbrief --install-hook`" in current:
            return target, False
        raise GitError(f"{target} already exists and was not written by diffbrief — "
                       "move it aside first, this will not overwrite your hook")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SCRIPT)
    os.chmod(target, 0o755)
    return target, True
