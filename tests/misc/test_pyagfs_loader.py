import importlib.util
import sysconfig

import pytest

import openviking.pyagfs as pyagfs


def test_find_ragfs_so_rejects_mismatched_cpython_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(pyagfs, "_LIB_DIR", tmp_path)
    monkeypatch.setattr(
        sysconfig, "get_config_var", lambda name: ".cpython-312-x86_64-linux-gnu.so"
    )

    (tmp_path / "ragfs_python.cpython-310-x86_64-linux-gnu.so").touch()

    assert pyagfs._find_ragfs_so() is None


def test_find_ragfs_so_prefers_exact_cpython_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(pyagfs, "_LIB_DIR", tmp_path)
    monkeypatch.setattr(
        sysconfig, "get_config_var", lambda name: ".cpython-312-x86_64-linux-gnu.so"
    )
    exact = tmp_path / "ragfs_python.cpython-312-x86_64-linux-gnu.so"
    exact.touch()
    (tmp_path / "ragfs_python.cpython-310-x86_64-linux-gnu.so").touch()

    assert pyagfs._find_ragfs_so() == str(exact)


def test_find_ragfs_so_rejects_mismatched_windows_cpython_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(pyagfs, "_LIB_DIR", tmp_path)
    monkeypatch.setattr(sysconfig, "get_config_var", lambda name: ".cp312-win_amd64.pyd")

    (tmp_path / "ragfs_python.cp310-win_amd64.pyd").touch()

    assert pyagfs._find_ragfs_so() is None


def test_find_ragfs_so_prefers_exact_windows_cpython_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(pyagfs, "_LIB_DIR", tmp_path)
    monkeypatch.setattr(sysconfig, "get_config_var", lambda name: ".cp312-win_amd64.pyd")
    exact = tmp_path / "ragfs_python.cp312-win_amd64.pyd"
    exact.touch()
    (tmp_path / "ragfs_python.cp310-win_amd64.pyd").touch()

    assert pyagfs._find_ragfs_so() == str(exact)


def test_find_ragfs_so_allows_stable_abi_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(pyagfs, "_LIB_DIR", tmp_path)
    monkeypatch.setattr(
        sysconfig, "get_config_var", lambda name: ".cpython-312-x86_64-linux-gnu.so"
    )
    abi3 = tmp_path / "ragfs_python.abi3.so"
    abi3.touch()

    assert pyagfs._find_ragfs_so() == str(abi3)


def test_rust_module_survives_repeated_loads():
    # PyO3 builds the module with multi-phase init (PEP 489), so every load from
    # the vendored file re-runs its init. openviking.pyagfs already loaded it once
    # at import; each further load must succeed rather than fail on state the
    # first init stored.
    so_path = pyagfs._find_ragfs_so()
    if so_path is None:
        pytest.skip("ragfs_python binding not built into openviking/lib")

    for _ in range(2):
        spec = importlib.util.spec_from_file_location("ragfs_python", so_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.RAGFSBindingClient is not None

    client, _ = pyagfs.get_binding_client()
    assert client is not None
