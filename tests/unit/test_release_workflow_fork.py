import re
from pathlib import Path

RELEASE_WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "release.yml"


def _job_block(job_name: str) -> str:
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    start_match = re.search(rf"^  {re.escape(job_name)}:\n", text, re.MULTILINE)
    assert start_match is not None
    next_job_match = re.search(r"^  [A-Za-z0-9_-]+:\n", text[start_match.end() :], re.MULTILINE)
    if next_job_match is None:
        return text[start_match.start() :]
    return text[start_match.start() : start_match.end() + next_job_match.start()]


def test_forks_skip_pypi_publishing() -> None:
    assert "if: ${{ github.event.repository.fork != true }}" in _job_block("publish-to-pypi")


def test_github_release_runs_when_pypi_was_skipped_but_not_when_it_failed() -> None:
    job = _job_block("create-github-release")

    assert "!cancelled()" in job
    assert "needs.docker-image.result == 'success'" in job
    assert "needs.helm-chart.result == 'success'" in job
    assert "(needs.publish-to-pypi.result == 'success' || needs.publish-to-pypi.result == 'skipped')" in job


def test_release_notes_list_pypi_only_when_published_and_use_the_publishing_owner() -> None:
    job = _job_block("create-github-release")

    assert "PYPI_PUBLISHED: ${{ needs.publish-to-pypi.result == 'success' }}" in job
    assert job.count('if [ "${PYPI_PUBLISHED}" = "true" ]; then') == 2
    assert 'CHARTS="oci://ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/charts"' in job
    assert "ghcr.io/soju06/charts" not in job


def test_failed_publishing_still_withdraws_the_release() -> None:
    job = _job_block("withdraw-failed-release")

    assert "contains(needs.*.result, 'failure')" in job
    assert "contains(needs.*.result, 'cancelled')" in job
