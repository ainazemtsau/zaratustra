"""Pass 4 package 1: Core failures are distinct from subject refusals."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from tests.zaratustra.foundation.test_child_execution import (
    _assign,
    _assignment_revision,
    _claim,
    _invocation,
    _issue,
    _resource,
    _stop,
)
from tests.zaratustra.foundation.test_composition import _apply, _seed
from tests.zaratustra.foundation.test_parent_execution import _ready_two_output_parent
from zaratustra.foundation import (
    AcceptWorkRequest,
    ArtifactRef,
    ClaimAttemptLaunchRequest,
    ConfirmObligationRequest,
    CreateGrantRequest,
    FoundationError,
    GrantState,
    PrepareInvocationRequest,
    PublishAttemptOutputRequest,
    RevokeGrantRequest,
    apply_operation,
    authorize_local,
    read_obligation,
    read_work,
    upgrade_child_execution_space,
)
from zaratustra.foundation import operations as operation_module


def _fresh_view(
    root: Path, work: UUID, receipts: tuple[UUID, ...], obligations: tuple[str, ...]
) -> dict[str, Any]:
    """Read the committed Core state from an isolated new Python process."""

    script = chr(10).join(
        (
            "import json, sys",
            "from pathlib import Path",
            "from uuid import UUID",
            "from zaratustra.foundation import FoundationError, authorize_local, read_execution",
            "from zaratustra.foundation import read_obligation, read_receipt, read_work",
            "p = Path(sys.argv[1])",
            "w = UUID(sys.argv[2])",
            "o = authorize_local(p, actor='owner', source_ref='pass4-fresh-reader')",
            "def receipt(name):",
            "    try:",
            "        return read_receipt(p, UUID(name), o).model_dump(mode='json')",
            "    except FoundationError as error:",
            "        return {'error': error.code}",
            "r = {name: receipt(name) for name in json.loads(sys.argv[3])}",
            "obligations = {key: read_obligation(p, w, key, o).model_dump(mode='json') "
            "for key in json.loads(sys.argv[4])}",
            "print(json.dumps({'work': read_work(p, w, o).model_dump(mode='json'), "
            "'execution': read_execution(p, w, o).model_dump(mode='json'), "
            "'receipts': r, 'obligations': obligations}))",
        )
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            script,
            str(root),
            str(work),
            json.dumps([str(item) for item in receipts]),
            json.dumps(obligations),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return cast(dict[str, Any], json.loads(completed.stdout))


def test_parent_multi_output_rolls_back_exception_and_process_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, space, owner, parent, resource = _ready_two_output_parent(
        tmp_path, obligation_slots=("final", "extra")
    )
    attempt, session, _request, assignment_receipt = _assign(root, space, owner, parent, resource)
    _claim(root, space, owner, parent, attempt, session)
    _invocation(root, space, owner, parent, attempt, session)
    final_request = PublishAttemptOutputRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        slot="final",
        media_type="text/plain",
        content=b"fictional final",
    )
    extra_request = final_request.model_copy(
        update={"operation_id": uuid4(), "slot": "extra", "content": b"fictional extra"}
    )
    receipt_ids = (
        assignment_receipt.operation_id,
        final_request.operation_id,
        extra_request.operation_id,
    )
    keys = ("summary_checked", "extra_checked")
    before = _fresh_view(root, parent, receipt_ids, keys)
    assert before["work"]["revision"] == 1
    assert before["work"]["state"]["linked_outputs"] == []
    assert before["execution"]["held_units"] == 0
    assert [before["obligations"][key]["status"] for key in keys] == ["open", "open"]
    assert before["receipts"][str(assignment_receipt.operation_id)]["kind"] == "assign_attempt"

    fired = False

    def fail_receipt(_connection: object, _receipt: object) -> None:
        nonlocal fired
        fired = True
        raise sqlite3.OperationalError("synthetic receipt fault after parent writes")

    with monkeypatch.context() as fault:
        fault.setattr(operation_module, "_write_receipt", fail_receipt)
        with pytest.raises(FoundationError, match="storage"):
            apply_operation(root, final_request, owner)
    assert fired, "The exception injection did not reach the receipt seam"
    after_exception = _fresh_view(root, parent, receipt_ids, keys)
    assert after_exception == before
    assert after_exception["receipts"][str(final_request.operation_id)] == {"error": "not_found"}

    final_receipt = apply_operation(root, final_request, owner)
    assert apply_operation(root, final_request, owner) == final_receipt
    final_ref = ArtifactRef(artifact_id=UUID(str(final_receipt.result["artifact_id"])), revision=1)
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key="summary_checked",
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=final_ref,
        basis="Final reviewed separately",
    )
    before_exit = _fresh_view(root, parent, receipt_ids, keys)
    assert [item["slot"] for item in before_exit["work"]["state"]["linked_outputs"]] == ["final"]
    assert before_exit["obligations"]["summary_checked"]["status"] == "satisfied"
    assert before_exit["obligations"]["extra_checked"]["status"] == "open"

    crash_script = (
        "import os,sys; from pathlib import Path; from uuid import UUID; "
        "import zaratustra.foundation.operations as operations; "
        "from zaratustra.foundation import "
        "PublishAttemptOutputRequest,apply_operation,authorize_local; "
        "def_die=lambda *_:os._exit(73); operations._write_receipt=def_die; "
        "p=Path(sys.argv[1]); o=authorize_local(p,actor='owner',source_ref='pass4-crash'); "
        "r=PublishAttemptOutputRequest(operation_id=UUID(sys.argv[2]),"
        "space_id=UUID(sys.argv[3]),actor='owner',attempt_id=UUID(sys.argv[4]),"
        "work_id=UUID(sys.argv[5]),session_id=UUID(sys.argv[6]),slot='extra',"
        "media_type='text/plain',content=b'fictional extra'); apply_operation(p,r,o)"
    )
    crashed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            crash_script,
            str(root),
            str(extra_request.operation_id),
            str(space),
            str(attempt),
            str(parent),
            str(session),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert crashed.returncode == 73, (
        f"Process-exit injection did not fire: {crashed.returncode}: {crashed.stderr}"
    )
    after_exit = _fresh_view(root, parent, receipt_ids, keys)
    assert after_exit == before_exit
    assert after_exit["receipts"][str(extra_request.operation_id)] == {"error": "not_found"}

    extra_receipt = apply_operation(root, extra_request, owner)
    assert apply_operation(root, extra_request, owner) == extra_receipt
    extra_ref = ArtifactRef(artifact_id=UUID(str(extra_receipt.result["artifact_id"])), revision=1)
    _apply(
        root,
        space,
        owner,
        ConfirmObligationRequest,
        work_id=parent,
        key="extra_checked",
        expected_plan_revision=1,
        expected_obligation_revision=1,
        evidence=extra_ref,
        basis="Extra reviewed separately",
    )
    _stop(root, space, owner, parent, attempt, session)
    _apply(
        root,
        space,
        owner,
        AcceptWorkRequest,
        work_id=parent,
        expected_revision=read_work(root, parent, owner).revision,
        basis="Both own outputs checked",
    )
    completed = _fresh_view(root, parent, receipt_ids, keys)
    assert completed["work"]["state"]["status"] == "succeeded"
    assert {item["slot"] for item in completed["work"]["state"]["linked_outputs"]} == {
        "final",
        "extra",
    }
    assert [completed["obligations"][key]["status"] for key in keys] == [
        "satisfied",
        "satisfied",
    ]
    assert completed["execution"]["held_units"] == 0
    assert completed["receipts"][str(final_request.operation_id)]["kind"] == (
        "publish_attempt_output"
    )
    assert completed["receipts"][str(extra_request.operation_id)]["kind"] == (
        "publish_attempt_output"
    )


def test_parent_launch_and_invocation_recheck_current_rights(tmp_path: Path) -> None:
    root, space, owner, parent, resource = _ready_two_output_parent(tmp_path)
    attempt, session, _request, assignment = _assign(root, space, owner, parent, resource)
    grant_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=grant_id,
        state=GrantState(
            grantee="worker",
            actions=("work.execute", "method.use", "model.invoke", "record.read", "receipt.read"),
        ),
    )
    worker = authorize_local(root, actor="worker", source_ref="pass4-worker")
    claim = ClaimAttemptLaunchRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="worker",
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        expected_assignment_revision=_assignment_revision(root, owner, parent, attempt),
        claim_nonce=uuid4(),
    )
    _apply(root, space, owner, RevokeGrantRequest, grant_id=grant_id, expected_revision=1)
    receipt_ids = (assignment.operation_id, claim.operation_id)
    before = _fresh_view(root, parent, receipt_ids, ())
    assert before["execution"]["assignments"][0]["status"] == "assigned"
    assert before["execution"]["held_units"] == 0
    assert before["work"]["state"]["linked_outputs"] == []
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(root, claim, worker)
    assert _fresh_view(root, parent, receipt_ids, ()) == before
    assert before["receipts"][str(claim.operation_id)] == {"error": "not_found"}

    renewed_grant_id = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateGrantRequest,
        grant_id=renewed_grant_id,
        state=GrantState(
            grantee="worker",
            actions=("work.execute", "method.use", "model.invoke", "record.read", "receipt.read"),
        ),
    )
    claim_receipt = apply_operation(root, claim, worker)
    assert apply_operation(root, claim, worker) == claim_receipt
    prepare = PrepareInvocationRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="worker",
        invocation_id=uuid4(),
        attempt_id=attempt,
        work_id=parent,
        session_id=session,
        purpose="content",
        provider="synthetic",
        model="synthetic",
        transport="http-sse",
        request_sha256="A" * 64,
        request_bytes=10,
        reserve_units=5,
    )
    current_assignment = next(
        item
        for item in _fresh_view(root, parent, (), ())["execution"]["assignments"]
        if item["attempt_id"] == str(attempt)
    )
    assert current_assignment["status"] == "assigned"
    # Revocation after the claim is checked again at the next subject effect.
    _apply(root, space, owner, RevokeGrantRequest, grant_id=renewed_grant_id, expected_revision=1)
    before_prepare = _fresh_view(root, parent, receipt_ids + (prepare.operation_id,), ())
    with pytest.raises(FoundationError, match="permission_denied"):
        apply_operation(root, prepare, worker)
    assert _fresh_view(root, parent, receipt_ids + (prepare.operation_id,), ()) == before_prepare
    assert before_prepare["receipts"][str(prepare.operation_id)] == {"error": "not_found"}
    assert before_prepare["execution"]["held_units"] == 0
    assert before_prepare["work"]["state"]["linked_outputs"] == []
    assert before_prepare["receipts"][str(claim.operation_id)] == claim_receipt.model_dump(
        mode="json"
    )


def test_child_publication_exception_rolls_back_and_replays_after_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, space, owner, _activity, _source, _method, parent, child, _b, _plan, _create = _seed(
        tmp_path
    )
    assert upgrade_child_execution_space(root, owner).schema_version == 6
    _issue(root, space, owner, parent, child)
    resource = _resource(root, space, owner, child, "pass4-child-resource")
    attempt, session, _request, assignment = _assign(root, space, owner, child, resource)
    _claim(root, space, owner, child, attempt, session)
    _invocation(root, space, owner, child, attempt, session)
    publication = PublishAttemptOutputRequest(
        operation_id=uuid4(),
        space_id=space,
        actor="owner",
        attempt_id=attempt,
        work_id=child,
        session_id=session,
        slot="checked",
        media_type="text/plain",
        content=b"synthetic child result",
    )
    receipts = (assignment.operation_id, publication.operation_id)
    before = _fresh_view(root, child, receipts, ())
    parent_before = read_obligation(root, parent, "final", owner)
    assert before["work"]["state"]["linked_outputs"] == []
    assert before["execution"]["held_units"] == 0
    fired = False

    def fail_receipt(_connection: object, _receipt: object) -> None:
        nonlocal fired
        fired = True
        raise sqlite3.OperationalError("synthetic child receipt fault")

    with monkeypatch.context() as fault:
        fault.setattr(operation_module, "_write_receipt", fail_receipt)
        with pytest.raises(FoundationError, match="storage"):
            apply_operation(root, publication, owner)
    assert fired, "The child exception injection did not reach the receipt seam"
    assert _fresh_view(root, child, receipts, ()) == before
    assert read_obligation(root, parent, "final", owner) == parent_before
    assert before["receipts"][str(publication.operation_id)] == {"error": "not_found"}

    published = apply_operation(root, publication, owner)
    assert apply_operation(root, publication, owner) == published
    after = _fresh_view(root, child, receipts, ())
    assert after["receipts"][str(publication.operation_id)] == published.model_dump(mode="json")
    assert [item["slot"] for item in after["work"]["state"]["linked_outputs"]] == ["checked"]
    assert after["execution"]["held_units"] == 0
    assert read_obligation(root, parent, "final", owner) == parent_before
