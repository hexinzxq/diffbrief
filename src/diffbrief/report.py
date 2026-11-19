"""One shape for the CLI, the JSON endpoint and the page."""
from __future__ import annotations

from .diff import FileDiff
from .rules import ORDER, Finding, look


def build(files: list[FileDiff], root: str, base: str, excluded: int = 0,
          only: tuple[str, ...] = ()) -> dict:
    findings = look(files, excluded)
    totals = {name: sum(1 for finding in findings if finding.severity == name) for name in ORDER}
    return {
        "root": root,
        "base": base,
        "files": len(files),
        "excluded": excluded,
        "only": list(only),
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
    elif not lines:
        lines.append("clean — nothing worth flagging")
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
