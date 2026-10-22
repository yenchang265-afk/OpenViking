"""Finalize guard when upstream pipeline jobs fail."""

import pytest
from vikingbot.compile.pipeline import check_final_inputs


def test_no_failures_leaves_warnings_untouched():
    warnings = []
    check_final_inputs([], [], warnings)
    assert warnings == []


def test_failed_jobs_with_remaining_artifacts_warn_partial_output():
    warnings = []
    check_final_inputs(["outputs/a"], ["1 pipeline jobs failed: ['timeout']"], warnings)
    assert warnings == ["Partial output; unfinished jobs: 1 pipeline jobs failed: ['timeout']"]


def test_failed_jobs_without_artifacts_report_the_root_cause():
    failures = ["3 pipeline jobs failed: ['Model call failed: 401 Unauthorized']", "later"]
    with pytest.raises(ValueError) as raised:
        check_final_inputs([], failures, [])
    assert str(raised.value) == (
        "No accepted final artifacts remain after failed jobs: "
        "3 pipeline jobs failed: ['Model call failed: 401 Unauthorized']"
    )
