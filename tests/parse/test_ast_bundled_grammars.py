# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

import pytest

from openviking.parse.parsers.code.ast.bundled_grammars import (
    extract_bundled_skeleton,
    supports_bundled_skeleton,
)

SAMPLES = [
    (
        "sample.py",
        "import os\n\nclass Order:\n    def total(self):\n        return 1\n\ndef build():\n    pass\n",
        ["class Order:", "    def total(self):", "def build():"],
    ),
    (
        "sample.js",
        "class Order {\n  total() { return 1; }\n}\nfunction build() {}\n",
        ["class Order {", "function build() {}"],
    ),
    (
        "sample.ts",
        "interface Item { id: string }\nexport class Order {\n  total(): number { return 1; }\n}\n",
        ["interface Item { id: string }", "export class Order {"],
    ),
    (
        "App.tsx",
        "export function App(): JSX.Element {\n  return <div />;\n}\n",
        ["export function App(): JSX.Element {"],
    ),
    (
        "Order.java",
        "package shop;\npublic class Order {\n  public int total() { return 1; }\n}\n",
        ["public class Order {", "  public int total() { return 1; }"],
    ),
    (
        "sample.cpp",
        "#include <vector>\nstruct Widget { int x; };\nint add(int a, int b) { return a + b; }\n",
        ["struct Widget { int x; };", "int add(int a, int b) { return a + b; }"],
    ),
    (
        "sample.c",
        "#include <stdio.h>\nstatic int add(int a, int b) {\n    return a + b;\n}\n",
        ["static int add(int a, int b) {"],
    ),
    (
        "lib.rs",
        "struct Order;\nimpl Order {\n    fn total(&self) -> i32 { 1 }\n}\nfn build() {}\n",
        ["struct Order;", "    fn total(&self) -> i32 { 1 }", "fn build() {}"],
    ),
    (
        "main.go",
        "package shop\n\ntype Order struct{}\n\nfunc (o Order) Total() int { return 1 }\n",
        ["type Order struct{}", "func (o Order) Total() int { return 1 }"],
    ),
    (
        "Order.cs",
        "namespace Shop;\npublic class Order {\n    public int Total() { return 1; }\n}\n",
        ["public class Order {", "    public int Total() { return 1; }"],
    ),
    (
        "order.php",
        "<?php\nclass Order {\n  public function total() { return 1; }\n}\n",
        ["class Order {", "  public function total() { return 1; }"],
    ),
    (
        "init.lua",
        "local M = {}\nfunction M.build() end\nreturn M\n",
        ["function M.build() end"],
    ),
]


@pytest.fixture
def language_pack_blocked(monkeypatch):
    """Fail loudly if the bundled route touches tree-sitter-language-pack."""

    import tree_sitter_language_pack

    def _blocked(*_args, **_kwargs):
        raise AssertionError("bundled route must not use tree-sitter-language-pack")

    for name in ("get_parser", "get_language", "process", "download"):
        monkeypatch.setattr(tree_sitter_language_pack, name, _blocked)


@pytest.mark.parametrize(("file_name", "content", "expected_lines"), SAMPLES)
def test_bundled_skeleton_lists_definitions(
    language_pack_blocked, file_name, content, expected_lines
):
    text = extract_bundled_skeleton(file_name, content)

    assert text is not None
    header, _, body = text.partition("\n\n")
    assert header.startswith(f"# {file_name} [")
    for line in expected_lines:
        assert line in body.splitlines()


def test_bundled_skeleton_keeps_line_numbers_aligned_with_unicode_separators():
    content = 'NOTE = "a b"\n\ndef build():\n    pass\n'

    text = extract_bundled_skeleton("sample.py", content)

    assert text is not None
    assert "def build():" in text.splitlines()


def test_bundled_skeleton_truncates_very_long_definition_lines():
    content = "function build() { return " + "1 + " * 500 + "1; }\n"

    text = extract_bundled_skeleton("bundle.min.js", content)

    assert text is not None
    assert max(len(line) for line in text.splitlines()) < 300


def test_bundled_skeleton_returns_none_without_definitions():
    assert extract_bundled_skeleton("sample.py", "print('hello')\n") is None


@pytest.mark.parametrize("file_name", ["sample.py", "a.tsx", "a.h", "a.cs", "a.lua"])
def test_supports_bundled_languages(file_name):
    assert supports_bundled_skeleton(file_name)


@pytest.mark.parametrize("file_name", ["sample.rb", "a.kt", "README.md", "Makefile"])
def test_rejects_languages_without_bundled_grammar(file_name):
    assert not supports_bundled_skeleton(file_name)
    assert extract_bundled_skeleton(file_name, "anything") is None
