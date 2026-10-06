# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Memory regression: large uploads must not be buffered whole on the server.

Slow and Linux-only, so opt-in: ``OV_MEMORY_TEST=1``. The S3 variant also needs
``OV_S3_TEST_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY`` (writes only under ``_it/memory/``
and removes it afterwards).

File sizes: ``OV_MEMORY_TEST_BYTES`` (local, default 1 GiB) and ``OV_MEMORY_TEST_S3_BYTES``
(S3, default 256 MiB). An S3 run writes about four times the file size; a small dev
SeaweedFS with no free volume slots has rejected writes after ~2 GiB, and deleted bytes
only come back after a vacuum, so keep the S3 size modest there.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MIB = 1024 * 1024
LIMIT_MIB = 128
PROBE = Path(__file__).with_name("upload_memory_probe.py")
SIZES = {
    "local": int(os.environ.get("OV_MEMORY_TEST_BYTES", str(1024 * MIB))),
    "s3": int(os.environ.get("OV_MEMORY_TEST_S3_BYTES", str(256 * MIB))),
}
S3_ENV = (
    "OV_S3_TEST_ENDPOINT",
    "OV_S3_TEST_BUCKET",
    "OV_S3_TEST_ACCESS_KEY",
    "OV_S3_TEST_SECRET_KEY",
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("OV_MEMORY_TEST") != "1", reason="set OV_MEMORY_TEST=1"),
    pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs /proc"),
]


def _probe(backend: str) -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(filter(None, [str(repo_root), os.environ.get("PYTHONPATH")])),
    )
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--backend", backend, "--size", str(SIZES[backend])],
        capture_output=True,
        text=True,
        env=env,
        timeout=1800,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    "backend",
    [
        "local",
        pytest.param(
            "s3",
            marks=pytest.mark.skipif(
                not all(os.environ.get(name) for name in S3_ENV), reason="OV_S3_TEST_* not set"
            ),
        ),
    ],
)
def test_large_upload_paths_keep_memory_flat(backend):
    results = _probe(backend)

    # The control buffers the whole file, so the probe must be able to see it.
    assert results["control_buffered"] >= SIZES[backend] / MIB * 0.9, results
    for scenario in ("stage_and_materialize", "shared_temp_upload", "parse_artifact_write"):
        assert results[scenario] <= LIMIT_MIB, results
