"""`diffbrief` — one command: read what you are about to push.

Exit codes: 0 clean, 1 a fail finding, 2 nothing to read (or a git error).
The exit code is the contract a pre-push hook or CI job would use.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .diff import GitError, excluded, read_diff, repo_root, resolve_base
from .hook import install as install_hook
from .report import build, render, worst
from .server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="diffbrief",
        description="Read your unpushed diff: keys, debug output, TODOs, deletions.",
    )
    parser.add_argument("-C", "--root", default=".", metavar="PATH",
                        help="any path inside the repository")
    parser.add_argument("--base", metavar="REF",
                        help="diff against REF (default: the upstream, else HEAD)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip files whose path matches this glob (repeatable)")
    parser.add_argument("--committed", action="store_true",
                        help="read only the commits, not the working copy "
                             "(what a pre-push hook should check)")
    parser.add_argument("--staged", action="store_true",
                        help="read the index instead of the unpushed commits")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--install-hook", action="store_true",
                        help="write a pre-push hook that runs diffbrief")
    parser.add_argument("--serve", action="store_true", help="open the report in a page")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    try:
        root = repo_root(Path(args.root).resolve())
        if args.install_hook:
            target, wrote = install_hook(root)
            if wrote:
                print(f"installed {target} — every git push now reads the diff first")
            else:
                print(f"{target} is already there")
            return 0
        if args.serve:
            httpd = serve(root, args.base, args.staged, args.host, args.port,
                          tuple(args.exclude), args.committed)
            print(f"diffbrief  http://{args.host}:{httpd.server_address[1]}  ({root})",
                  flush=True)
            print("ctrl-c to stop", flush=True)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                httpd.server_close()
            return 0
        # Label what was actually read: --staged diffs the index, and calling
        # that "against @{upstream}" is the kind of label that hides a mistake.
        resolved = "the index" if args.staged else resolve_base(root, args.base)
        all_files = read_diff(root, args.base, args.staged, committed=args.committed)
        files = [file for file in all_files
                 if not excluded(file.path, tuple(args.exclude))]
        data = build(files, str(root), resolved, excluded=len(all_files) - len(files))
    except GitError as error:
        print(f"diffbrief: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        reason = error.strerror or str(error)
        print(f"diffbrief: cannot listen on {args.host}:{args.port} — {reason}. "
              f"Pass --port to pick another.", file=sys.stderr)
        return 2

    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else render(data))
    return worst(data)


if __name__ == "__main__":
    raise SystemExit(main())
