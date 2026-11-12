#!/usr/bin/env python3
"""Prepare an upstream merge for review without changing the current checkout."""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, text=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Committed fork branch/ref to sync")
    parser.add_argument("--upstream", required=True, help="Upstream branch, tag, or commit")
    parser.add_argument("--worktree", required=True, type=Path, help="New worktree directory")
    parser.add_argument("--branch", default=None, help="New local sync branch name")
    parser.add_argument("--no-fetch", action="store_true", help="Use existing upstream refs")
    args = parser.parse_args()
    root = git("rev-parse", "--show-toplevel").stdout.strip()
    destination = args.worktree.resolve()
    if destination.exists():
        parser.error("--worktree must not already exist")
    branch = args.branch or datetime.now(timezone.utc).strftime("sync/upstream-%Y%m%d-%H%M%S")
    git("check-ref-format", "--branch", branch)
    base = git("rev-parse", "--verify", "--end-of-options", args.base + "^{commit}").stdout.strip()
    if not args.no_fetch:
        git("fetch", "--no-tags", "upstream", cwd=root)
    target = git(
        "rev-parse", "--verify", "--end-of-options", args.upstream + "^{commit}"
    ).stdout.strip()
    ancestor = git("merge-base", base, target).stdout.strip()
    if git("merge-base", "--is-ancestor", target, base, check=False).returncode == 0:
        print("Selected upstream commit is already included; no sync needed.")
        return 0
    git("worktree", "add", "-b", branch, str(destination), base, cwd=root)
    result = git("merge", "--no-commit", "--no-ff", target, cwd=destination, check=False)
    conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=destination).stdout
    report = "\n".join(
        [
            "# Upstream sync context",
            "",
            f"Base: {args.base} ({base})",
            f"Upstream: {args.upstream} ({target})",
            f"Merge base: {ancestor}",
            f"Branch: {branch}",
            f"Worktree: {destination}",
            "",
            "## Incoming change summary",
            "",
            git("diff", "--stat", ancestor, target).stdout,
            "## Unresolved paths (including reused resolutions awaiting review)",
            "",
            conflicts or "None",
            "",
            "## Merge output",
            "",
            result.stdout,
            result.stderr,
            "Read UPSTREAM_SYNC.md. Inspect conflicts and failed checks first; expand context as needed.",
        ]
    )
    report_path = (
        Path(git("rev-parse", "--absolute-git-dir", cwd=destination).stdout.strip())
        / "upstream-sync.md"
    )
    report_path.write_text(report)
    print(f"Sync branch: {branch}\nWorktree: {destination}\nContext: {report_path}")
    print("Merge left uncommitted. Review resolutions, run checks, then commit and open a PR.")
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1 if conflicts else result.returncode
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        print(error.stderr or str(error), file=sys.stderr)
        sys.exit(error.returncode)
