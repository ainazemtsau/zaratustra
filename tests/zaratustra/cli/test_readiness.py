"""Common readiness does not weaken the exact authorized continuation read."""

from pathlib import Path
from uuid import uuid4

import pytest

import zaratustra.cli as cli
from tests.zaratustra.onboarding.test_onboarding import _activate, _confirm
from zaratustra.core import (
    AuthorizationPrompt,
    LocalAuthorization,
    MutationRequest,
    apply_mutation,
    read_records,
)


def test_unselected_read_does_not_create_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = tmp_path / "missing.json"
    assert cli.main(["entry", "ready", "--catalog", str(catalog)]) == 0
    assert not catalog.exists()
    assert "Current Work: unknown" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_absent_creation_and_missing_lock_refuse_without_repair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = tmp_path / "catalog.json"
    args = ["entry", "ready", "--catalog", str(catalog), "--designation", "Fictional simple prose"]
    assert cli.main(args) == 1
    assert list(tmp_path.iterdir()) == []
    _activate(tmp_path, "simple")
    lock = next(tmp_path.glob("*.process-creations/*.lock"))
    lock.unlink()
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert cli.main(args) == 1
    assert "journal_unavailable" in capsys.readouterr().err
    assert not lock.exists()
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("mode", ["missing", "wrong", "stale"])
def test_refusal_never_reports_no_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    catalog, workspace, _, activated = _activate(tmp_path, "simple")
    database = workspace / ".zara/state.sqlite3"
    before = database.read_bytes()

    def confirm(prompt: AuthorizationPrompt) -> LocalAuthorization | None:
        if mode == "missing":
            return None
        if mode == "wrong":
            return _confirm(
                workspace,
                prompt.request.model_copy(update=dict(expected_revision=0)),
            )
        state = read_records(workspace)
        assert activated.creation.first_work_id is not None
        cancel = MutationRequest(
            operation_id=uuid4(),
            workspace_id=state.workspace_id,
            work_id=activated.creation.first_work_id,
            expected_revision=state.state_revision,
            operation="cancel_work",
            provenance="Fictional intervening state change",
        )
        caller = _confirm(workspace, prompt.request)
        apply_mutation(workspace, cancel, _confirm(workspace, cancel))
        return caller

    monkeypatch.setattr(cli, "confirm_on_console", confirm)
    assert (
        cli.main(
            ["entry", "ready", "--catalog", str(catalog), "--designation", "Fictional simple prose"]
        )
        == 1
    )
    output = capsys.readouterr()
    assert "Current Work: unknown; read refused" in output.out
    assert "Stage: no_current_work" not in output.out
    assert output.err
    if mode != "stale":
        assert database.read_bytes() == before
