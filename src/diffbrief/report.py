"""One shape for the CLI, the JSON endpoint and the page."""
from __future__ import annotations

from .diff import FileDiff
from .rules import ORDER, Finding, look


def build(files: list[FileDiff], root: str, base: str, excluded: int = 0,
          only: tuple[str, ...] = (), unmatched: tuple[str, ...] = ()) -> dict:
    findings = look(files, excluded)
    # Read a file top to bottom: rules fire in their own order, but a person
    # scrolling the report wants the lines in the order they appear, with the
    # whole-file verdicts after them.
    findings.sort(key=lambda finding: (finding.path,
                                       10 ** 9 if finding.line is None else finding.line,
                                       ORDER[finding.severity]))
    binaries = [file.path for file in files if file.binary]
    totals = {name: sum(1 for finding in findings if finding.severity == name) for name in ORDER}
    return {
        "root": root,
        "base": base,
        "files": len(files),
        "excluded": excluded,
        "only": list(only),
        "binary": binaries,
        "unmatched": list(unmatched),
        "changed_lines": sum(file.changed() for file in files),
        "findings": [finding.as_json() for finding in findings],
        "totals": totals,
    }


def worst(data: dict) -> int:
    """0 clean (or nothing to read), 1 something that should stop a push.

    A pre-push hook runs this on every push: an empty diff is not a failure.
    """
    return 1 if data["totals"]["fail"] else 0


def render(data: dict) -> str:
    lines = []
    for finding in data["findings"]:
        where = finding["path"] + (f":{finding['line']}" if finding["line"] else "")
        lines.append(f"{finding['severity'].upper():<4}  {where}")
        lines.append(f"      {finding['rule']}: {finding['message']}")
        if finding["evidence"]:
            lines.append(f"      {finding['evidence']}")
    scope = f" (only {', '.join(data['only'])})" if data.get("only") else ""
    if not data["files"]:
        lines.append(f"no changes against {data['base']}{scope} — nothing to read")
        if data.get("hint"):
            lines.append(data["hint"])
    elif not data["findings"]:
        lines.append("clean — nothing worth flagging")
    for pattern in data.get("unmatched", []):
        # `--exclude vendor` matches no path: git prints `vendor/lib.py`, so a
        # directory has to be spelled `vendor/*` — and that is worth a sentence.
        looks_like_a_dir = "/" not in pattern.strip("*/")
        lines.append(f"note: --exclude {pattern} matched nothing in this diff"
                     + (" — a directory needs `" + pattern.rstrip("/") + "/*`"
                        if looks_like_a_dir else ""))
    if data.get("binary"):
        shown = ", ".join(data["binary"][:3])
        more = f" and {len(data['binary']) - 3} more" if len(data["binary"]) > 3 else ""
        lines.append(f"note: {len(data['binary'])} binary file(s) not read — {shown}{more}")
    totals = data["totals"]
    lines.append("")
    summary = (f"{data['files']} file(s), {data['changed_lines']} changed line(s) "
               f"against {data['base']} — {totals['fail']} fail, "
               f"{totals['warn']} warn, {totals['note']} note")
    if data.get("excluded"):
        summary += f" ({data['excluded']} file(s) skipped by --exclude)"
    summary += scope
    lines.append(summary)
    return "\n".join(lines)
