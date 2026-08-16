import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from archon.pipeline.analysis.git_analyzer import GitAnalyzer


@pytest.fixture
def analyzer():
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    # Using a dummy path; the tests will mock GitPython
    return GitAnalyzer(
        repository_id=repo_id,
        snapshot_id=snapshot_id,
        managed_path="/tmp/dummy",
        snapshot_commit_sha="abcd123"
    )


def test_infer_change_type_initial_commit(analyzer):
    mock_commit = MagicMock()
    mock_commit.parents = []  # No parents = initial commit
    change_type = analyzer._infer_change_type(mock_commit, "main.py")
    assert change_type == "A"


def test_normalize_path(analyzer):
    assert analyzer._normalize_path("src\\main.py") == "src/main.py"
    assert analyzer._normalize_path("src/main.py") == "src/main.py"


def test_aggregate_churn(analyzer):
    file_changes = [
        {"commit_sha": "c1", "file_path": "a.py", "insertions": 10, "deletions": 5},
        {"commit_sha": "c2", "file_path": "a.py", "insertions": 20, "deletions": 0},
        {"commit_sha": "c3", "file_path": "b.py", "insertions": 50, "deletions": 50},
    ]

    churn_results = analyzer._aggregate_churn(file_changes)

    # a.py churn = 10+5+20 = 35
    # b.py churn = 50+50 = 100
    # max churn = 100

    assert "a.py" in churn_results
    assert churn_results["a.py"]["churn"] == 35
    assert churn_results["a.py"]["commit_count"] == 2
    assert churn_results["a.py"]["normalized_churn"] == 0.35

    assert "b.py" in churn_results
    assert churn_results["b.py"]["churn"] == 100
    assert churn_results["b.py"]["commit_count"] == 1
    assert churn_results["b.py"]["normalized_churn"] == 1.0


def test_aggregate_contributors(analyzer):
    dt1 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    dt2 = datetime(2026, 8, 2, tzinfo=timezone.utc)
    
    commits = [
        {
            "commit_sha": "c1", "author_name": "Alice", "author_email": "a@example.com",
            "committed_at": dt1, "message": "msg1"
        },
        {
            "commit_sha": "c2", "author_name": "Alice", "author_email": "a@example.com",
            "committed_at": dt2, "message": "msg2"
        },
    ]

    file_changes = [
        {"commit_sha": "c1", "file_path": "a.py", "insertions": 10, "deletions": 5},
        {"commit_sha": "c2", "file_path": "b.py", "insertions": 20, "deletions": 0},
    ]

    contributors = analyzer._aggregate_contributors(commits, file_changes)

    assert len(contributors) == 1
    alice = contributors[0]
    assert alice["author_email"] == "a@example.com"
    assert alice["commit_count"] == 2
    assert alice["files_touched"] == 2
    assert alice["total_insertions"] == 30
    assert alice["total_deletions"] == 5
    assert alice["first_commit_at"] == dt1
    assert alice["last_commit_at"] == dt2


def test_git_analyzer_snapshot_cutoff(analyzer):
    """
    Verifies that the GitAnalyzer limits its search to start from
    the snapshot_commit_sha.
    """
    mock_repo = MagicMock()
    mock_repo.iter_commits.return_value = []

    # _extract_history calls iter_commits with rev=analyzer.snapshot_commit_sha
    commits, changes = analyzer._extract_history(mock_repo)

    mock_repo.iter_commits.assert_called_once()
    kwargs = mock_repo.iter_commits.call_args.kwargs
    assert kwargs.get("rev") == "abcd123"
