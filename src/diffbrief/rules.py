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
# A template config says CHANGE_ME, <token>, ${API_KEY}: those are instructions
# to the reader, and every repo with an example config has them. Failing on them
# trains people to ignore the rule by the third one.
SECRET_VALUE = re.compile(
    r"(?i)\b(?:api[_-]?key|apikey|secret|token|password|passwd|pwd|access[_-]?key)\b"
    r"\s*[:=]\s*[\"']([^\"']{8,})[\"']")
PLACEHOLDER = re.compile(
    r"(?i)^(<[^>]*>|\$\{[^}]*\}|\*+|x{3,}|\.\.\.|"
    r"change[-_ ]?me|your[-_ ][\w .-]*|example[a-z_-]*|placeholder|dummy|fake|sample|redacted|todo)$")
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
# A TODO is a marker you write in a comment, not the word appearing inside a
# string of data. dsh-daily-lab's state files quote the tool's own description,
# which contains "TODO", and the rule used to call that a new TODO entering the
# tree - noise about content nobody is going to act on.
TODO_MARK = re.compile(r"\b(TODO|FIXME|XXX)\b")
TODO_IN_COMMENT = re.compile(
    r"^\s*(?://|/\*|\*|#|<!--|--|;|%)"          # a comment marker first
    r"|^\s*(TODO|FIXME|XXX)\b"                   # or the marker starts the line
    r"|^\s*[-*+]\s+(TODO|FIXME|XXX)\b"          # or a list item in a doc
)
LOCKFILES = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock"
    r"|uv\.lock|go\.sum|Gemfile\.lock|composer\.lock)$"
)
CODE = re.compile(r"\.(py|js|mjs|cjs|ts|tsx|jsx|go|rs|java|rb|kt|swift|php|c|h|cc|cpp|cs)$")
# Debug output only gets left behind in something that runs. A reference doc or
# a JSON fixture quoting `console.log(x)` is an example, not a stray statement.
EXECUTABLE = re.compile(
    r"\.(py|js|mjs|cjs|ts|tsx|jsx|go|rs|java|rb|kt|swift|php|c|h|cc|cpp|cs"
    r"|sh|bash|zsh|pl|lua|r|ex|exs|clj|scala|dart|vue|svelte)$")
# `config.example.py` is the thing you copy, not the thing that runs: asking it
# to bring a test along is asking a template to be tested.
TEMPLATE = re.compile(
    r"(^|/)([^/]*\.)?(example|sample|template|dist|skeleton)\.(py|js|mjs|cjs|ts|tsx|jsx"
    r"|go|rs|java|rb|kt|swift|php|json|ya?ml|toml|ini|env|conf)$", re.I)
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


def look(files: list[FileDiff], excluded: int = 0) -> list[Finding]:
    findings: list[Finding] = []
    for file in files:
        if file.binary:
            continue
        for line in file.added():
            text = line.text
            value = SECRET_VALUE.search(text)
            placeholder = bool(value and PLACEHOLDER.match(value.group(1).strip()))
            if (SECRET_NAME.search(text) and not placeholder) or any(
                    shape.search(text) for shape in SECRET_SHAPE):
                findings.append(Finding(
                    file.path, line.new_no, "fail", "secret-literal",
                    "a key-shaped literal is being added", _mask(text)))
                continue  # one finding per line, the worst one wins
            if EXECUTABLE.search(file.path) and DEBUG.search(text):
                findings.append(Finding(
                    file.path, line.new_no, "warn", "debug-statement",
                    "debug output left in a diff", text.strip()[:120]))
                continue
            if TODO_MARK.search(text) and TODO_IN_COMMENT.search(text):
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
    findings.extend(_tests_missing(files, excluded))
    findings.sort(key=lambda finding: (ORDER[finding.severity], finding.path, finding.line or 0))
    return findings


def _tests_missing(files: list[FileDiff], excluded: int = 0) -> list[Finding]:
    """Code moved, no test moved with it: say so once, on the biggest file."""
    code = [file for file in files
            if (not file.deleted and CODE.search(file.path) and not is_test(file.path)
                and not TEMPLATE.search(file.path))
            and file.changed()  # a pure rename or mode change moves no line
            and file.path.rsplit(".", 1)[-1] in TESTING]
    if not code:
        return []
    if any(is_test(file.path) for file in files):
        return []
    biggest = max(code, key=lambda file: file.changed())
    said = f"{len(code)} source file(s) changed and no test did"
    if excluded:
        # A test may well have changed in a file --exclude took away; claiming
        # "no test did" would be a statement about files we never read.
        said += (f" (among the {len(files)} file(s) read; "
                 f"{excluded} skipped by --exclude)")
    return [Finding(biggest.path, None, "warn", "tests-missing", said, "")]
