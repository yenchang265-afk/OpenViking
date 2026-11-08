#!/usr/bin/env python3
"""Keep in-server Compile (openviking/compile) in step with upstream's bot Compile.

Upstream runs Compile inside VikingBot (``bot/vikingbot/compile``); this fork runs
it in the server. The pipeline files are shared: each one is upstream's file put
through a fixed transform (module paths rewritten to ``openviking.compile``, bot
helpers mapped to ``openviking.compile._compat``, then ``ruff`` import sorting and
formatting), plus fork changes in the few files listed under ``diverged`` in
``openviking/compile/UPSTREAM.json``.

Commands:

  check  Every shared file must equal the transformed upstream file at the pinned
         commit, except the listed diverged files. Exit 1 on drift.
  diff   Show how each diverged file differs from transformed upstream.
  sync   Three-way merge upstream changes from the pinned commit to ``--to`` into
         the shared files (``git merge-file``), then move the pin. Conflicts are
         left as markers to resolve by hand; new and removed upstream files are
         listed for a decision.

Upstream sync workflow: a plain ``git merge upstream/main`` still deletes
``bot/vikingbot/compile`` (the fork removed it). After resolving that, run
``sync --to upstream/main``. A conflict inside code the fork removed (for example
the AgentLoop adapter in ``pipeline_agent.py``) means upstream changed something
the fork replaces: keep the removal and port the change to ``agent_loop.py`` or
``runner.py`` by hand. Then run ``check`` and the Compile tests.

The transform needs ``ruff`` on PATH. Its output depends on the ruff version, so
CI pins the version this script was last run with (``ruff_version``).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "openviking" / "compile"
MANIFEST = TARGET / "UPSTREAM.json"

# Upstream bot modules whose names the fork provides in openviking.compile._compat.
COMPAT_MODULES = (
    "vikingbot.agent.loop",
    "vikingbot.agent.tools.base",
    "vikingbot.agent.tools.ov_file",
    "vikingbot.utils.helpers",
)


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def save_manifest(manifest: dict) -> None:
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, check=check, capture_output=True, text=True)


def ensure_commit(manifest: dict, ref: str) -> str:
    """Resolve ``ref`` locally, fetching it from the upstream repository if needed."""
    resolved = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    if resolved.returncode != 0:
        git("fetch", "--quiet", "--depth=1", manifest["repository"], ref)
        resolved = git("rev-parse", "--verify", "FETCH_HEAD^{commit}")
    return resolved.stdout.strip()


def upstream_files(manifest: dict, commit: str) -> list[str]:
    """Return upstream Python files under the Compile path, relative to it."""
    root = manifest["path"].rstrip("/") + "/"
    listing = git("ls-tree", "-r", "--name-only", commit, root).stdout.split()
    return sorted(
        name[len(root) :] for name in listing if name.endswith(".py") and "/tests/" not in name
    )


def upstream_text(manifest: dict, commit: str, name: str) -> str:
    return git("show", f"{commit}:{manifest['path'].rstrip('/')}/{name}").stdout


def transform(text: str, name: str) -> str:
    """Map an upstream bot Compile file onto openviking.compile."""
    text = text.replace("vikingbot.compile", "openviking.compile")
    for module in COMPAT_MODULES:
        text = re.sub(
            rf"^(\s*)from {re.escape(module)} import ",
            r"\1from openviking.compile._compat import ",
            text,
            flags=re.M,
        )
    return ruff_normalize(text, name)


def ruff_normalize(text: str, name: str) -> str:
    """Sort imports and format the way the repository does, without touching TARGET."""
    with tempfile.TemporaryDirectory() as directory:
        # Use the repository's ruff settings and import sections for a file
        # outside the tree.
        scratch = Path(directory) / Path(name).name
        scratch.write_text(text)
        settings = ["--config", str(REPO / "pyproject.toml")]
        known = ["--config", "lint.isort.known-first-party=['openviking','openviking_cli']"]
        run_ruff("check", "--quiet", "--select", "I", "--fix", *settings, *known, str(scratch))
        run_ruff("format", "--quiet", *settings, str(scratch))
        return scratch.read_text()


def run_ruff(*args: str) -> None:
    ruff = shutil.which("ruff")
    if ruff is None:
        sys.exit("ruff is required on PATH")
    result = subprocess.run([ruff, *args], capture_output=True, text=True)
    # `ruff check --fix` exits 1 when unfixable findings remain; only sorting matters here.
    if result.returncode not in (0, 1):
        sys.exit(result.stderr or result.stdout)


def shared_names(manifest: dict, commit: str) -> list[str]:
    excluded = set(manifest.get("upstream_only", {}))
    return [name for name in upstream_files(manifest, commit) if name not in excluded]


def ruff_version() -> str:
    ruff = shutil.which("ruff")
    if ruff is None:
        sys.exit("ruff is required on PATH")
    return subprocess.run([ruff, "--version"], capture_output=True, text=True).stdout.split()[-1]


def check_ruff_version(manifest: dict) -> None:
    current = ruff_version()
    if current != manifest["ruff_version"]:
        print(
            f"warning: ruff {current} differs from the pinned {manifest['ruff_version']}; "
            "formatting differences may show up as drift",
            file=sys.stderr,
        )


def command_check(manifest: dict) -> int:
    check_ruff_version(manifest)
    commit = ensure_commit(manifest, manifest["commit"])
    diverged = manifest.get("diverged", {})
    problems = []
    for name in shared_names(manifest, commit):
        local = TARGET / name
        if not local.exists():
            problems.append(f"{name}: missing (add it, or list it under upstream_only)")
            continue
        if name in diverged:
            continue
        if local.read_text() != transform(upstream_text(manifest, commit, name), name):
            problems.append(f"{name}: differs from upstream (sync it, or list it under diverged)")
    for name in diverged:
        if name not in shared_names(manifest, commit):
            problems.append(f"{name}: listed as diverged but not an upstream file")
    for problem in problems:
        print(problem)
    if not problems:
        print(
            f"openviking/compile matches upstream {commit[:12]} outside {len(diverged)} diverged files"
        )
    return 1 if problems else 0


def command_diff(manifest: dict, names: list[str]) -> int:
    commit = ensure_commit(manifest, manifest["commit"])
    for name in names or list(manifest.get("diverged", {})):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
            handle.write(transform(upstream_text(manifest, commit, name), name))
        result = subprocess.run(
            ["git", "diff", "--no-index", "--", handle.name, str(TARGET / name)],
            capture_output=True,
            text=True,
        )
        Path(handle.name).unlink()
        print(f"### {name}: {manifest.get('diverged', {}).get(name, 'shared')}")
        print(result.stdout)
    return 0


def command_sync(manifest: dict, ref: str) -> int:
    check_ruff_version(manifest)
    base = ensure_commit(manifest, manifest["commit"])
    new = ensure_commit(manifest, ref)
    if base == new:
        print("already at", new[:12])
        return 0
    old_names = set(shared_names(manifest, base))
    new_names = set(shared_names(manifest, new))
    conflicts, changed = [], []
    for name in sorted(old_names & new_names):
        base_text = transform(upstream_text(manifest, base, name), name)
        new_text = transform(upstream_text(manifest, new, name), name)
        if base_text == new_text:
            continue
        local = TARGET / name
        with tempfile.TemporaryDirectory() as directory:
            base_file = Path(directory) / "base"
            new_file = Path(directory) / "upstream"
            base_file.write_text(base_text)
            new_file.write_text(new_text)
            result = subprocess.run(
                [
                    "git",
                    "merge-file",
                    "-L",
                    "openviking/compile",
                    "-L",
                    f"upstream {base[:12]}",
                    "-L",
                    f"upstream {new[:12]}",
                    str(local),
                    str(base_file),
                    str(new_file),
                ],
                capture_output=True,
                text=True,
            )
        (conflicts if result.returncode else changed).append(name)
    manifest["commit"] = new
    manifest["ruff_version"] = ruff_version()
    save_manifest(manifest)
    print(f"merged upstream {base[:12]}..{new[:12]}")
    for label, names in (
        ("updated", changed),
        ("CONFLICTS (resolve the markers)", conflicts),
        (
            "new upstream files (copy with a transform, or list under upstream_only)",
            sorted(new_names - old_names),
        ),
        ("removed upstream (delete here, or keep as fork-only)", sorted(old_names - new_names)),
    ):
        if names:
            print(f"{label}:")
            for name in names:
                print("  ", name)
    print("Then run: scripts/compile_upstream_sync.py check, and the Compile tests.")
    return 1 if conflicts else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="fail when shared files drift from upstream")
    diff = commands.add_parser("diff", help="show fork changes against upstream")
    diff.add_argument("files", nargs="*", help="files relative to openviking/compile")
    sync = commands.add_parser("sync", help="merge upstream changes and move the pin")
    sync.add_argument("--to", required=True, help="upstream commit or ref, e.g. upstream/main")
    args = parser.parse_args()
    manifest = load_manifest()
    if args.command == "check":
        return command_check(manifest)
    if args.command == "diff":
        return command_diff(manifest, args.files)
    return command_sync(manifest, args.to)


if __name__ == "__main__":
    sys.exit(main())
