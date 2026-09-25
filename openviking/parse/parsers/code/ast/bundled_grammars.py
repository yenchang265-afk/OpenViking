# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Code skeleton extraction from grammars bundled as pip dependencies.

Fallback for when tree-sitter-language-pack cannot download its parsers (for
example behind a firewall). Grammars and tags queries come from the pinned
``tree-sitter-<language>`` packages, so this route never touches the network.
"""

import importlib
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Optional

from tree_sitter import Language, Parser, Query, QueryCursor

from openviking_cli.utils import get_logger

logger = get_logger(__name__)

_LOCAL_QUERY_DIR = Path(__file__).with_name("queries") / "bundled"
_MAX_LINE_CHARS = 240


@dataclass(frozen=True)
class _GrammarSpec:
    module: str
    language_fn: str
    display: str
    # Packages whose queries/tags.scm are concatenated, in order.
    query_packages: tuple[str, ...] = ()
    # Query file under queries/bundled/ for grammars that ship no tags.scm.
    local_query: Optional[str] = None


_TS_QUERIES = ("tree_sitter_javascript", "tree_sitter_typescript")

_GRAMMARS = {
    "python": _GrammarSpec("tree_sitter_python", "language", "Python", ("tree_sitter_python",)),
    "javascript": _GrammarSpec(
        "tree_sitter_javascript", "language", "JavaScript", ("tree_sitter_javascript",)
    ),
    "typescript": _GrammarSpec(
        "tree_sitter_typescript", "language_typescript", "TypeScript", _TS_QUERIES
    ),
    "tsx": _GrammarSpec("tree_sitter_typescript", "language_tsx", "TSX", _TS_QUERIES),
    "java": _GrammarSpec("tree_sitter_java", "language", "Java", ("tree_sitter_java",)),
    # C has no bundled grammar; the C++ grammar parses C definitions correctly.
    "cpp": _GrammarSpec("tree_sitter_cpp", "language", "C/C++", ("tree_sitter_cpp",)),
    "rust": _GrammarSpec("tree_sitter_rust", "language", "Rust", ("tree_sitter_rust",)),
    "go": _GrammarSpec("tree_sitter_go", "language", "Go", ("tree_sitter_go",)),
    "c_sharp": _GrammarSpec(
        "tree_sitter_c_sharp", "language", "C#", local_query="c_sharp-tags.scm"
    ),
    "php": _GrammarSpec("tree_sitter_php", "language_php", "PHP", ("tree_sitter_php",)),
    "lua": _GrammarSpec("tree_sitter_lua", "language", "Lua", ("tree_sitter_lua",)),
}

_SUFFIX_TO_GRAMMAR = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".c": "cpp",
    ".h": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".cs": "c_sharp",
    ".php": "php",
    ".lua": "lua",
}


def _grammar_for(file_name: str) -> Optional[str]:
    return _SUFFIX_TO_GRAMMAR.get(Path(file_name).suffix.lower())


def _read_query(spec: _GrammarSpec) -> str:
    if spec.local_query:
        return (_LOCAL_QUERY_DIR / spec.local_query).read_text(encoding="utf-8")
    return "\n".join(
        resources.files(package).joinpath("queries", "tags.scm").read_text(encoding="utf-8")
        for package in spec.query_packages
    )


@lru_cache(maxsize=None)
def _load_grammar(grammar: str) -> Optional[tuple[Language, Query]]:
    spec = _GRAMMARS[grammar]
    try:
        module = importlib.import_module(spec.module)
        language = Language(getattr(module, spec.language_fn)())
        return language, Query(language, _read_query(spec))
    except Exception as exc:
        logger.warning("Bundled grammar '%s' unavailable: %s", grammar, exc)
        return None


def _definition_rows(query: Query, tree) -> list[int]:
    rows: set[int] = set()
    for _, captures in QueryCursor(query).matches(tree.root_node):
        if "name" in captures and any(tag.startswith("definition.") for tag in captures):
            rows.update(node.start_point[0] for node in captures["name"])
    return sorted(rows)


def _truncate(line: str) -> str:
    if len(line) <= _MAX_LINE_CHARS:
        return line
    return line[:_MAX_LINE_CHARS] + " …"


def supports_bundled_skeleton(file_name: str) -> bool:
    """Return whether a bundled grammar covers the file."""

    return _grammar_for(file_name) is not None


def extract_bundled_skeleton(file_name: str, content: str) -> Optional[str]:
    """Return definition lines found with a bundled grammar, or None."""

    grammar = _grammar_for(file_name)
    if grammar is None or not content:
        return None
    loaded = _load_grammar(grammar)
    if loaded is None:
        return None
    language, query = loaded

    try:
        tree = Parser(language).parse(content.encode("utf-8"))
        rows = _definition_rows(query, tree)
    except Exception as exc:
        logger.warning("Bundled grammar extraction failed for '%s': %s", file_name, exc)
        return None
    if not rows:
        return None

    # Split on "\n" only so rows match tree-sitter's line numbering; str.splitlines()
    # also breaks on characters such as U+2028 and would misalign them.
    lines = content.split("\n")
    body = [_truncate(lines[row].rstrip()) for row in rows if row < len(lines)]
    display = _GRAMMARS[grammar].display
    return f"# {file_name} [{display}, bundled grammar]\n\n" + "\n".join(body)
