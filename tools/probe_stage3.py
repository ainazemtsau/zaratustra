"""Synthetic Activity/Work proof across two processes, without a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]


def _new_output(path: Path) -> Path:
    output = path.expanduser().resolve()
    scratch = (ROOT / "_scratch").resolve()
    if output == scratch or not output.is_relative_to(scratch) or output.exists():
        raise ValueError("Choose a NEW output directory inside this checkout's _scratch")
    output.mkdir(parents=True)
    return output


def read_again(workspace: Path, activity_id: UUID, work_id: UUID) -> dict[str, Any]:
    from zaratustra.foundation import (
        authorize_local,
        read_activity,
        read_artifact,
        read_operation_audit,
        read_receipt,
        read_space,
        read_work,
    )

    owner = authorize_local(
        workspace, actor="synthetic-owner", source_ref="new-process-confirmation"
    )
    activity = read_activity(workspace, activity_id, owner)
    work = read_work(workspace, work_id, owner)
    assert work.state.acceptance is not None
    result_ref = work.state.linked_outputs[0].artifact
    result = read_artifact(workspace, result_ref.artifact_id, owner, revision=result_ref.revision)
    receipt = read_receipt(workspace, work.state.acceptance.operation_id, owner)
    audit = read_operation_audit(workspace, work.state.acceptance.operation_id, owner)
    return {
        "space_id": str(read_space(workspace).space_id),
        "activity": {
            "id": str(activity_id),
            "revision": activity.revision,
            "title": activity.state.title,
            "status": activity.state.status,
        },
        "work": {
            "id": str(work_id),
            "revision": work.revision,
            "goal": work.state.goal,
            "method": work.state.method,
            "status": work.state.status,
            "inputs": [ref.model_dump(mode="json") for ref in work.state.inputs],
            "expected_outputs": [
                item.model_dump(mode="json") for item in work.state.expected_outputs
            ],
            "linked_outputs": [item.model_dump(mode="json") for item in work.state.linked_outputs],
            "acceptance_operation": str(work.state.acceptance.operation_id),
            "acceptance_basis": work.state.acceptance.basis,
            "authority_source": work.state.acceptance.authority_source,
            "unavailable_refs": [item.model_dump(mode="json") for item in work.unavailable_refs],
        },
        "result_sha256": hashlib.sha256(result.content or b"").hexdigest().upper(),
        "acceptance_receipt_kind": receipt.kind,
        "acceptance_audit": audit.model_dump(mode="json"),
    }


def run(output: Path) -> dict[str, Any]:
    from zaratustra.foundation import (
        AcceptWorkRequest,
        ActivityState,
        ArtifactRef,
        BootstrapRequest,
        CreateActivityRequest,
        CreateArtifactRequest,
        CreateWorkRequest,
        LinkedOutput,
        LinkWorkOutputRequest,
        OutputContract,
        ProvenanceRef,
        WorkState,
        apply_operation,
        authorize_local,
        initialize_space,
        read_work,
        upgrade_space,
    )

    output = _new_output(output)
    workspace = output / "workspace"
    workspace.mkdir()
    info = initialize_space(workspace)
    owner = authorize_local(workspace, actor="synthetic-owner", source_ref="probe-confirmation")
    apply_operation(
        workspace,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        owner,
    )
    assert upgrade_space(workspace, owner).schema_version == 2

    input_id = uuid4()
    result_id = uuid4()
    for artifact_id, content, relation in (
        (input_id, b"synthetic-stage2-contract", "synthetic-input"),
        (result_id, b"synthetic-stage3-result", "synthetic-result"),
    ):
        apply_operation(
            workspace,
            CreateArtifactRequest(
                operation_id=uuid4(),
                space_id=info.space_id,
                actor=owner.actor,
                artifact_id=artifact_id,
                media_type="text/plain",
                content=content,
                provenance=(ProvenanceRef(relation=relation, external_ref="probe:synthetic"),),
            ),
            owner,
        )

    activity_id = uuid4()
    work_id = uuid4()
    apply_operation(
        workspace,
        CreateActivityRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            activity_id=activity_id,
            state=ActivityState(
                title="Разработка Заратустры",
                goal="Синтетическая проверка предметного контракта",
            ),
        ),
        owner,
    )
    apply_operation(
        workspace,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Проверить явное принятие синтетического результата Stage 3",
                inputs=(ArtifactRef(artifact_id=input_id, revision=1),),
                constraints=("Не применять модель и не читать личные данные",),
                expected_outputs=(OutputContract(slot="report", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    assert read_work(workspace, work_id, owner).state.status == "proposed"
    apply_operation(
        workspace,
        LinkWorkOutputRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=1,
            output=LinkedOutput(
                slot="report", artifact=ArtifactRef(artifact_id=result_id, revision=1)
            ),
        ),
        owner,
    )
    assert read_work(workspace, work_id, owner).state.status == "proposed"
    apply_operation(
        workspace,
        AcceptWorkRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=owner.actor,
            work_id=work_id,
            expected_revision=2,
            basis="Синтетический результат проверен по именованному выходу и точной редакции",
        ),
        owner,
    )
    child = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.probe_stage3",
            "read",
            str(workspace),
            str(activity_id),
            str(work_id),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    observed = cast(dict[str, Any], json.loads(child.stdout))
    assert observed["activity"]["status"] == "ongoing"
    assert observed["work"]["status"] == "succeeded"
    assert observed["work"]["method"] == "none"
    assert observed["acceptance_receipt_kind"] == "accept_work"
    (output / "summary.json").write_text(
        json.dumps(observed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return observed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    create = subcommands.add_parser("run")
    create.add_argument("--output", type=Path, required=True)
    read = subcommands.add_parser("read")
    read.add_argument("workspace", type=Path)
    read.add_argument("activity_id", type=UUID)
    read.add_argument("work_id", type=UUID)
    args = parser.parse_args()
    if args.command == "run":
        observed = run(args.output)
    else:
        observed = read_again(args.workspace, args.activity_id, args.work_id)
    print(json.dumps(observed, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
