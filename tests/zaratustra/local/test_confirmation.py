"""Authority delivery and lost reply checks, without asserting presentation wording."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

from zaratustra.cli import main
from zaratustra.core import (
    InitialRecords,
    MutationError,
    MutationRequest,
    ReceiptQuery,
    Work,
    apply_mutation,
    create_initial_records,
    init_workspace,
    migrate_workspace,
    prepare_authorization,
    read_history,
    read_receipt,
    read_records,
)
from zaratustra.local import confirm_on_console


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_console_confirmation_pipe_denial_and_lost_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    info = init_workspace(tmp_path)
    migrate_workspace(tmp_path, target_version=3)
    snapshot = create_initial_records(
        tmp_path,
        InitialRecords(
            process_title="Fictional observatory",
            goal="Inspect a fictional moon",
            expected_result="A note",
            acceptance=("Saved",),
            boundaries=("Fictional only",),
            budget="Local trial",
            artifact_title="Draft",
        ),
    )
    from uuid import uuid4

    work = next(record for record in snapshot.records if isinstance(record, Work))
    request = MutationRequest(
        operation_id=uuid4(),
        workspace_id=info.workspace_id,
        work_id=work.id,
        operation="authorize_work",
        expected_revision=1,
        provenance="Fictional console trial",
    )
    prompt = prepare_authorization(tmp_path, request)
    before = info.database.read_bytes()
    monkeypatch.setattr("sys.stdin", io.StringIO("approve " + prompt.request_sha256))
    monkeypatch.setattr("sys.stderr", Terminal())
    with pytest.raises(MutationError, match="permission_denied"):
        confirm_on_console(prompt)
    monkeypatch.setattr("sys.stdin", Terminal("no"))
    with pytest.raises(MutationError, match="permission_denied"):
        confirm_on_console(prompt)
    assert info.database.read_bytes() == before
    monkeypatch.setattr("sys.stdin", Terminal("approve " + prompt.request_sha256))
    caller = confirm_on_console(prompt)
    assert caller.confirmation.channel == "local-console"
    # A real CLI output failure after Core commits must not undo/repeat the effect.
    monkeypatch.setattr("zaratustra.cli.confirm_on_console", lambda _: caller)

    def lost_reply(*args: Any, **kwargs: Any) -> None:
        raise BrokenPipeError("simulated disconnected reply")

    with monkeypatch.context() as patch:
        patch.setattr("builtins.print", lost_reply)
        with pytest.raises(BrokenPipeError):
            main(["mutate", str(tmp_path), request.model_dump_json()])
    committed = info.database.read_bytes()
    with pytest.raises(MutationError, match="conflict"):
        apply_mutation(tmp_path, request, caller)
    assert read_records(tmp_path).state_revision == 2
    assert len(read_history(tmp_path).events) == 1
    query = ReceiptQuery(
        workspace_id=info.workspace_id, work_id=work.id, operation_id=request.operation_id
    )
    read_prompt = prepare_authorization(tmp_path, query)
    monkeypatch.setattr("sys.stdin", Terminal("approve " + read_prompt.request_sha256))
    receipt = read_receipt(tmp_path, query, confirm_on_console(read_prompt))
    assert receipt.operation_id == request.operation_id and receipt.new_revision == 2
    assert info.database.read_bytes() == committed
