"""Rules that read a diff the way a careful reviewer skims it.

Each rule is deliberately dumb and loud: a regular expression over added or
removed lines, or a count. Nothing here needs a model, a key or a network.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .diff import FileDiff

# Most severe first: the CLI sorts by this and the page filters on it.
ORDER = {"fail": 0, "warn": 1, "note": 2}

SECRET_NAME = re.compile(
    r"(?i)\b(api[_-]?key|apikey|secret|token|password|passwd|pwd|access[_-]?key)\b"
    r"\s*[:=]\s*[\"'][^\"']{8,}[\"']"
)
SECRET_SHAPE = [
    re.compile(r"\b(ghp|gho|ghs|ghu)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
DEBUG = re.compile(
    r"(\bconsole\.log\s*\(|\bdebugger\b|\bpdb\.set_trace\s*\(|\bbreakpoint\s*\(\s*\)"
    r"|\bbinding\.pry\b|\bprintln!\s*\(|\bdbg!\s*\()"
)
TODO = re.compile(r"\b(TODO|FIXME|XXX)\b")
LOCKFILES = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock"
    r"|uv\.lock|go\.sum|Gemfile\.lock|composer\.lock)$"
)
CODE = re.compile(r"\.(py|js|mjs|cjs|ts|tsx|jsx|go|rs|java|rb|kt|swift|php|c|h|cc|cpp|cs)$")
TESTING = {"py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "rb", "kt", "swift", "php"}
TESTISH = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)(test_[^/]+|[^/]+_test\.(py|go)|[^/]+\.(test|spec)\.[jt]sx?)$"
)

BIG_DELETION = 30  # removed lines, with almost nothing added back
LOCK_CHURN = 200  # changed lines in a lockfile is noise, not a review item
MASK_KEEP = 4  # how many characters of a secret stay visible


@dataclass
class Finding:
    path: str
    line: int | None
    severity: str  # fail | warn | note
    rule: str
    message: str
    evidence: str = ""

    def as_json(self) -> dict:
        return {"path": self.path, "line": self.line, "severity": self.severity,
                "rule": self.rule, "message": self.message, "evidence": self.evidence}


def _mask(text: str) -> str:
    """Show enough to find the line, not enough to use the key."""
    stripped = text.strip()
    if len(stripped) <= MASK_KEEP:
        return "*" * len(stripped)
    return stripped[:MASK_KEEP] + "…" + "*" * 6


def is_test(path: str) -> bool:
    return bool(TESTISH.search(path))


def look(files: list[FileDiff]) -> list[Finding]:
    findings: list[Finding] = []
    for file in files:
        if file.binary:
            continue
        for line in file.added():
            text = line.text
            if SECRET_NAME.search(text) or any(shape.search(text) for shape in SECRET_SHAPE):
                findings.append(Finding(
                    file.path, line.new_no, "fail", "secret-literal",
                    "a key-shaped literal is being added", _mask(text)))
                continue  # one finding per line, the worst one wins
            if DEBUG.search(text):
                findings.append(Finding(
                    file.path, line.new_no, "warn", "debug-statement",
                    "debug output left in a diff", text.strip()[:120]))
                continue
            if TODO.search(text):
                findings.append(Finding(
                    file.path, line.new_no, "note", "todo-added",
                    "a TODO/FIXME is entering the tree", text.strip()[:120]))
        removed, added = len(file.removed()), len(file.added())
        if removed >= BIG_DELETION and added <= 5 and not LOCKFILES.search(file.path):
            findings.append(Finding(
                file.path, None, "warn", "large-deletion",
                f"{removed} lines removed and {added} added — was this on purpose?",
                ""))
        if LOCKFILES.search(file.path) and file.changed() >= LOCK_CHURN:
            findings.append(Finding(
                file.path, None, "note", "lockfile-churn",
                f"{file.changed()} lines moved in a lockfile — skim for a bad version bump",
                ""))
    findings.extend(_tests_missing(files))
    findings.sort(key=lambda finding: (ORDER[finding.severity], finding.path, finding.line or 0))
    return findings


def _tests_missing(files: list[FileDiff]) -> list[Finding]:
    """Code moved, no test moved with it: say so once, on the biggest file."""
    code = [file for file in files
            if not file.deleted and CODE.search(file.path) and not is_test(file.path)
            and file.path.rsplit(".", 1)[-1] in TESTING]
    if not code:
        return []
    if any(is_test(file.path) for file in files):
        return []
    biggest = max(code, key=lambda file: file.changed())
    return [Finding(
        biggest.path, None, "warn", "tests-missing",
        f"{len(code)} source file(s) changed and no test did",
        "")]
