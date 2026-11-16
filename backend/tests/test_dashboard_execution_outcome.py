"""Final execution status must distinguish recovered retries from unresolved errors."""
from types import SimpleNamespace

import pytest

from app.platform.summary import _execution_outcome


def step(agent, index, status, iteration=0):
    return SimpleNamespace(agent_name=agent, step_index=index, iteration=iteration, status=status)


@pytest.mark.parametrize("statuses,expected,recovered", [
    (["completed"], "completed", 0),
    (["failed", "failed", "completed"], "completed", 2),
    (["failed", "completed", "failed"], "failed", 0),
    (["failed", "running"], "running", 0),
    (["failed"], "failed", 0),
])
def test_last_retry_decides_status_without_losing_errors(statuses, expected, recovered):
    result = _execution_outcome([step("redactor", 1, status) for status in statuses])
    assert result == {"status": expected, "failed": expected == "failed",
                      "failed_steps": statuses.count("failed"), "recovered_failures": recovered}


def test_later_agent_success_does_not_hide_an_unresolved_failure():
    result = _execution_outcome([step("redactor", 1, "failed"), step("publicador", 4, "completed")])
    assert result["status"] == "failed"
    assert result["recovered_failures"] == 0


def test_retry_recovery_allows_pipeline_to_complete():
    result = _execution_outcome([
        step("investigador", 0, "completed"), step("redactor", 1, "failed"),
        step("redactor", 1, "failed"), step("redactor", 1, "completed"),
        step("revisor", 2, "completed"), step("formateador", 3, "completed"),
        step("publicador", 4, "completed"),
    ])
    assert result["status"] == "completed"
    assert result["failed_steps"] == result["recovered_failures"] == 2


def test_different_review_iteration_does_not_overwrite_another_step():
    result = _execution_outcome([step("redactor", 1, "failed", 0), step("redactor", 1, "completed", 1)])
    assert result["status"] == "failed"
