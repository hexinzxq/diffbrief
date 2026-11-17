"""Turn `git diff` output into files, hunks and lines.

Only the unified format matters here: the rules read added and removed lines
and their line numbers in the new file, and nothing else.
"""
from __future__ import annotations

import fnmatch

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
NO_NEWLINE = "\\ No newline at end of file"


class GitError(RuntimeError):
    """git could not answer: not a repository, a bad ref, no git at all."""


def _git(args: list[str], cwd: Path) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        raise GitError("git is not installed — diffbrief reads a diff by running it")
    if done.returncode != 0:
        reason = (done.stderr or done.stdout).strip().splitlines()
        raise GitError(reason[0] if reason else f"git {' '.join(args)} failed")
    return done.stdout


@dataclass
class Line:
    kind: str  # "+", "-" or " "
    text: str  # the line without its marker
    new_no: int | None  # line number in the new file; None for a removal
    old_no: int | None  # line number in the old file; None for an addition


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    header: str
    lines: list[Line] = field(default_factory=list)


@dataclass
class FileDiff:
    path: str
    new: bool = False
    deleted: bool = False
    binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    def added(self) -> list[Line]:
        return [line for hunk in self.hunks for line in hunk.lines if line.kind == "+"]

    def removed(self) -> list[Line]:
        return [line for hunk in self.hunks for line in hunk.lines if line.kind == "-"]

    def changed(self) -> int:
        return len(self.added()) + len(self.removed())


def _path_of(line: str, prefix: str) -> str:
    """`--- a/x` / `+++ b/x` -> `x`, keeping `/dev/null` out of the answer."""
    rest = line[len(prefix):].strip()
    if rest.startswith('"') and rest.endswith('"'):
        rest = rest[1:-1]
    if rest == "/dev/null":
        return ""
    if "\t" in rest:
        rest = rest.split("\t", 1)[0]
    if rest.startswith(("a/", "b/")):
        rest = rest[2:]
    return rest


def parse(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    new_no = old_no = 0

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            head = raw[len("diff --git "):]
            path = head.split(" b/")[-1] if " b/" in head else head
            current = FileDiff(path=path)
            files.append(current)
            hunk = None
            continue
        if current is None:
            continue
        if raw.startswith("new file mode"):
            current.new = True
            continue
        if raw.startswith("deleted file mode"):
            current.deleted = True
            continue
        if raw.startswith("rename from ") or raw.startswith("rename to "):
            current.path = raw.split(" ", 2)[2].strip()
            continue
        if raw.startswith("Binary files "):
            current.binary = True
            continue
        if raw.startswith("--- "):
            continue
        if raw.startswith("+++ "):
            path = _path_of(raw, "+++ ")
            if path:
                current.path = path
            continue
        match = HUNK.match(raw)
        if match:
            old_start = int(match.group(1))
            old_len = int(match.group(2) or 1)
            new_start = int(match.group(3))
            new_len = int(match.group(4) or 1)
            hunk = Hunk(old_start, old_len, new_start, new_len, match.group(5).strip())
            current.hunks.append(hunk)
            new_no, old_no = new_start, old_start
            continue
        if hunk is None:
            continue  # mode lines, index lines, "similarity index"
        if raw == NO_NEWLINE:
            continue
        if raw.startswith("+"):
            hunk.lines.append(Line("+", raw[1:], new_no, None))
            new_no += 1
        elif raw.startswith("-"):
            hunk.lines.append(Line("-", raw[1:], None, old_no))
            old_no += 1
        elif raw.startswith(" ") or raw == "":
            hunk.lines.append(Line(" ", raw[1:] if raw else "", new_no, old_no))
            new_no += 1
            old_no += 1
    return files


def repo_root(path: Path) -> Path:
    if not path.exists():
        raise GitError(f"{path} does not exist — pass an existing path")
    if not path.is_dir():
        raise GitError(f"{path} is not a directory")
    return Path(_git(["rev-parse", "--show-toplevel"], path).strip())


def _exists(root: Path, ref: str) -> bool:
    done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref],
                          cwd=root, capture_output=True, text=True)
    return done.returncode == 0


def resolve_base(root: Path, base: str | None) -> str:
    """What to diff against.

    The promise is "what you are about to push", so an upstream is not enough:
    a branch that has never been pushed (or a fresh clone using `git push origin
    main` without -u) has no upstream, and falling straight back to HEAD then
    reports "nothing to read" while the commits are still local. In that case
    the remote's own copy of the branch is the honest base.
    """
    if base:
        return base
    done = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=root, capture_output=True, text=True,
    )
    if done.returncode == 0:
        return "@{upstream}"
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=root, capture_output=True, text=True).stdout.strip()
    if branch and branch != "HEAD":
        for remote in ("origin",):
            candidate = f"{remote}/{branch}"
            if _exists(root, candidate):
                return candidate
    # A branch that has never been pushed has no upstream and no remote copy,
    # but its commits are still unpushed: everything after where the remote's
    # default branch is. Without this the hook reads HEAD...HEAD and passes a
    # brand-new branch silently.
    if _exists(root, "origin/HEAD"):
        return "origin/HEAD"
    return "HEAD"


def excluded(path: str, patterns: tuple[str, ...]) -> bool:
    """Whether a path matches one of the --exclude globs.

    fnmatch on the path as git prints it: patterns are about what you can see in
    the diff, not about where the file resolves on disk.
    """
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def read_diff(root: Path, base: str | None = None, staged: bool = False,
              paths: list[str] | None = None,
              exclude: tuple[str, ...] = (),
              committed: bool = False) -> list[FileDiff]:
    # core.quotePath would turn `üñí çode.py` into \303\274... in the header,
    # and that is the path a person then has to type to find the file.
    args = ["-c", "core.quotePath=false", "diff", "--no-color",
            "--find-renames", "--unified=3"]
    if committed:
        # Only the commits: a secret you pasted into the working copy while
        # debugging is not part of the push, and blocking on it is a lie.
        args.append(f"{resolve_base(root, base)}...HEAD")
    elif staged:
        args.append("--cached")
    else:
        args.append(resolve_base(root, base))
    if paths:
        args.extend(["--", *paths])
    files = parse(_git(args, root))
    if not exclude:
        return files
    return [file for file in files if not excluded(file.path, exclude)]
