import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]

MAIN_TAG_REGEX = r"^(?:upstream-)?v(?P<version>[0-9]+(?:\.[0-9]+)*)$"
MAIN_DESCRIBE_COMMAND = (
    "git describe --dirty --tags --long --match v[0-9]* --match upstream-v[0-9]*"
)


def test_main_package_versioning_ignores_non_main_release_tags() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()

    assert 'tag_regex = "^(?:upstream-)?v(?P<version>[0-9]+(?:\\\\.[0-9]+)*)$"' in pyproject
    assert f'git_describe_command = "{MAIN_DESCRIBE_COMMAND}"' in pyproject


def test_main_tag_regex_accepts_release_and_upstream_base_tags() -> None:
    """Fork builds version from `upstream-vX.Y.Z` base tags, which do not fire
    the `v*.*.*` image publish workflow, as well as from regular `v` tags."""
    pattern = re.compile(MAIN_TAG_REGEX)

    assert pattern.match("v0.4.21").group("version") == "0.4.21"
    assert pattern.match("upstream-v0.4.21").group("version") == "0.4.21"
    assert pattern.match("python-sdk@0.1.12") is None
    assert pattern.match("langchain-openviking@0.1.0") is None


def test_python_sdk_versioning_uses_sdk_only_at_sign_tags() -> None:
    pyproject = (ROOT / "sdk/python/pyproject.toml").read_text()

    assert 'tag_regex = "^python-sdk@(?P<version>[0-9]+(?:\\\\.[0-9]+)*)$"' in pyproject
    assert (
        'git_describe_command = "git describe --dirty --tags --long --match python-sdk@*"'
        in pyproject
    )
    assert "python-sdk/v" not in pyproject


def test_build_support_versioning_uses_main_release_tags_only(monkeypatch) -> None:
    from scripts.build_support import versioning

    captured_kwargs = {}
    fake_setuptools_scm = ModuleType("setuptools_scm")

    def fake_get_version(**kwargs):
        captured_kwargs.update(kwargs)
        return "0.3.18"

    fake_setuptools_scm.get_version = fake_get_version
    monkeypatch.setitem(sys.modules, "setuptools_scm", fake_setuptools_scm)

    assert versioning._get_scm_version(ROOT) == "0.3.18"
    assert captured_kwargs["tag_regex"] == MAIN_TAG_REGEX
    assert captured_kwargs["git_describe_command"] == MAIN_DESCRIBE_COMMAND
