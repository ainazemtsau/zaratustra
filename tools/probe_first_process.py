"""Run the single T4 fictional lot through public Core and T2/T3 contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from zaratustra.core import (
    ArtifactReference,
    ContextQuery,
    Handoff,
    LocalAuthorization,
    MutationError,
    MutationReceipt,
    MutationRequest,
    ProcessQuery,
    ReceiptQuery,
    apply_mutation,
    authorize_local,
    create_initial_records,
    handoff_request,
    init_workspace,
    migrate_workspace,
    open_work,
    prepare_authorization,
    read_history,
    read_records,
    read_result,
)
from zaratustra.fictional_lot import initial_records, initial_requirements, reference, registration
from zaratustra.process_packs import (
    PackError,
    PackRegistry,
    binding_request,
    propose_result,
    read_capabilities,
)

from .probe_m1 import query_for, restore_snapshot, save, work_at
from .probe_packs import PacksTrial
from .retain_trial import retain_trial

ROOT = Path(__file__).resolve().parents[1]
CALL = "c-solmax-zaratustra-m1-first-process-20260910-exec"


def wire(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + chr(10)).encode()


def confirm(
    path: Path, value: MutationRequest | ContextQuery | ReceiptQuery | ProcessQuery
) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="T4-fictional-host",
        source_ref=f"RUN {CALL}; selected fictional workspace only; not T4 owner acceptance",
    )


def installed() -> PackRegistry:
    return PackRegistry((registration(),))


def footprint(path: Path) -> dict[str, str | None]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        if item.is_file()
        else None
        for item in sorted(path.rglob("*"))
    }


class LotTrial(PacksTrial):
    """Reuse only request construction; every write/confirmation has this CALL's provenance."""

    def request(self, identity: UUID, operation: str, **payload: Any) -> MutationRequest:
        request = super().request(identity, operation, **payload)
        return MutationRequest.model_validate(
            request.model_dump() | dict(provenance=f"Selected fictional T4 under RUN {CALL}")
        )

    def execute(self, request: MutationRequest, content: bytes | None = None) -> MutationReceipt:
        if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
            raise RuntimeError("Read and resolve STOP/STEER before mutation")
        self.sequence += 1
        prefix = self.evidence / f"{self.sequence:03d}-{request.operation}"
        caller = confirm(self.path, request)
        save(prefix.with_suffix(".request.json"), request.model_dump(mode="json"))
        save(prefix.with_suffix(".authority.json"), caller.confirmation.model_dump(mode="json"))
        if content is not None:
            prefix.with_suffix(".input.json").write_bytes(content)
        save(
            prefix.with_suffix(".before-manifest.json"),
            retain_trial(self.path, prefix.with_suffix(".before.zip")),
        )
        receipt = apply_mutation(self.path, request, caller, content=content)
        save(prefix.with_suffix(".receipt.json"), receipt.model_dump(mode="json"))
        return receipt

    def bootstrap(self) -> UUID:
        self.path.mkdir(parents=True)
        init_workspace(self.path)
        migrate_workspace(self.path, target_version=7)
        initial = initial_records()
        save(self.evidence / "bootstrap.json", initial.model_dump(mode="json"))
        create_initial_records(self.path, initial)
        identity = work_at(self.path).id
        self.execute(self.request(identity, "authorize_work"))
        self.execute(
            self.request(identity, "set_work_requirements", requirements=initial_requirements())
        )
        save(self.evidence / "registration.json", reference().model_dump(mode="json"))
        self.execute(
            binding_request(
                installed(),
                reference(),
                operation_id=uuid4(),
                workspace_id=read_records(self.path).workspace_id,
                work_id=identity,
                expected_revision=read_records(self.path).state_revision,
                provenance=f"Explicit fictional lot binding under RUN {CALL}",
            )
        )
        return identity

    def accept(self, identity: UUID, content: bytes) -> ArtifactReference:
        self.execute(self.request(identity, "authorize_artifact"))
        publication = self.request(
            identity,
            "publish_artifact",
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_size=len(content),
        )
        self.execute(publication, content)
        assert publication.artifact_id is not None
        result = ArtifactReference(
            artifact_id=publication.artifact_id,
            version_id=publication.operation_id,
            sha256=hashlib.sha256(content).hexdigest(),
        )
        snapshot = read_records(self.path)
        handoff = Handoff(
            kind="handoff",
            version=1,
            handoff_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            process=work_at(self.path, identity).process_id,
            related_work=identity,
            intent="accepted_result",
            source_revision=snapshot.state_revision,
            result=result,
            provenance="Fictional observation/disposition; no real owner acceptance claim",
            created_by="T4 fictional host",
        )
        self.execute(handoff_request(handoff.model_dump_json().encode(), source_ref=CALL))
        return result

    def proposal(
        self, identity: UUID, name: str, registry: PackRegistry | None = None
    ) -> MutationRequest:
        query = query_for(self.path, identity)
        caller = confirm(self.path, query)
        save(self.evidence / f"{name}.query.json", query.model_dump(mode="json"))
        save(self.evidence / f"{name}.authority.json", caller.confirmation.model_dump(mode="json"))
        (self.evidence / f"{name}.context.json").write_bytes(
            open_work(self.path, query, caller).output
        )
        return propose_result(
            self.path,
            query,
            caller,
            installed() if registry is None else registry,
            operation_id=uuid4(),
            next_work_id=uuid4(),
            next_artifact_id=uuid4(),
        )

    def capture(
        self,
        name: str,
        identity: UUID,
        visible: tuple[UUID, ...],
        *,
        selected: bool = True,
        content: bool = True,
    ) -> dict[str, Any]:
        before = footprint(self.path)
        state = read_records(self.path)
        query = ProcessQuery(
            workspace_id=state.workspace_id,
            process_id=work_at(self.path, identity).process_id,
            work_id=identity,
            expected_revision=state.state_revision,
            visible_work_ids=visible,
            selected_work_id=identity if selected else None,
            max_bytes=1048576,
        )
        caller = confirm(self.path, query)
        prefix = self.evidence / name
        save(prefix.with_suffix(".process-query.json"), query.model_dump(mode="json"))
        save(
            prefix.with_suffix(".process-authority.json"),
            caller.confirmation.model_dump(mode="json"),
        )
        result = read_capabilities(self.path, query, caller, installed())
        prefix.with_suffix(".metadata.json").write_bytes(result.output)
        if selected and content:
            decoded = json.loads(result.output)
            refs = decoded["answers"]["context_requirements"]["value"]["references"]
            context = query_for(self.path, identity).model_copy(
                update=dict(references=tuple(ArtifactReference.model_validate(row) for row in refs))
            )
            context_caller = confirm(self.path, context)
            save(prefix.with_suffix(".context-query.json"), context.model_dump(mode="json"))
            save(
                prefix.with_suffix(".context-authority.json"),
                context_caller.confirmation.model_dump(mode="json"),
            )
            result = read_capabilities(
                self.path,
                query,
                caller,
                installed(),
                context_query=context,
                context_caller=context_caller,
            )
        prefix.with_suffix(".response.json").write_bytes(result.output)
        save(prefix.with_suffix(".state.json"), state.model_dump(mode="json"))
        save(prefix.with_suffix(".history.json"), read_history(self.path).model_dump(mode="json"))
        assert footprint(self.path) == before
        decoded_result: dict[str, Any] = json.loads(result.output)
        return decoded_result

    def finish(self, identity: UUID, name: str) -> UUID:
        request = self.proposal(identity, name)
        prefix = self.evidence / name
        save(prefix.with_suffix(".proposal.json"), request.model_dump(mode="json"))
        before = footprint(self.path)
        try:
            apply_mutation(self.path, request)
        except MutationError as error:
            assert error.code == "permission_denied" and footprint(self.path) == before
            save(prefix.with_suffix(".no-authority.json"), dict(code=error.code, unchanged=True))
        else:
            raise AssertionError("Pack proposal unexpectedly granted authority")
        manifest = retain_trial(self.path, prefix.with_suffix(".snapshot.zip"))
        save(prefix.with_suffix(".snapshot-manifest.json"), manifest)
        receipt = self.execute(request)
        assert request.submission is not None
        next_id = request.submission.next_work.work_id
        saved_query = ReceiptQuery(
            workspace_id=request.workspace_id, work_id=identity, operation_id=request.operation_id
        )
        result_caller = confirm(self.path, saved_query)
        save(prefix.with_suffix(".result-query.json"), saved_query.model_dump(mode="json"))
        save(
            prefix.with_suffix(".result-authority.json"),
            result_caller.confirmation.model_dump(mode="json"),
        )
        save(
            prefix.with_suffix(".saved-result.json"),
            read_result(self.path, saved_query, result_caller).model_dump(mode="json"),
        )
        restored = restore_snapshot(
            prefix.with_suffix(".snapshot.zip"), self.evidence / f"{name}-restored", manifest
        )
        context_query = query_for(restored, identity)
        context_caller = confirm(restored, context_query)
        save(
            prefix.with_suffix(".restore-context-authority.json"),
            context_caller.confirmation.model_dump(mode="json"),
        )
        assert (
            open_work(restored, context_query, context_caller).output
            == prefix.with_suffix(".context.json").read_bytes()
        )
        restored_caller = confirm(restored, request)
        save(
            prefix.with_suffix(".restore-authority.json"),
            restored_caller.confirmation.model_dump(mode="json"),
        )
        replay = apply_mutation(restored, request, restored_caller)
        save(prefix.with_suffix(".restore-receipt.json"), replay.model_dump(mode="json"))
        assert (
            replay.fingerprint == receipt.fingerprint
            and replay.new_revision == receipt.new_revision
        )
        assert work_at(restored, next_id).pack_binding == reference()
        return next_id


def refused(
    trial: LotTrial, identity: UUID, name: str, registry: PackRegistry | None = None
) -> str:
    before = footprint(trial.path)
    try:
        trial.proposal(identity, name, registry)
    except PackError as error:
        assert footprint(trial.path) == before
        save(trial.evidence / f"{name}.refusal.json", dict(code=error.code, unchanged=True))
        return error.code
    raise AssertionError("Expected package refusal")


def run(base: Path, inputs: Path) -> dict[str, Any]:
    base.mkdir()
    raw_inputs = inputs.read_bytes()
    (base / "inputs.json").write_bytes(raw_inputs)
    data = json.loads(raw_inputs)
    save(
        base / "runtime.json",
        dict(
            call=CALL,
            python=sys.version,
            executable=sys.executable,
            argv=sys.argv,
            commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
            ).strip(),
            source_diff=subprocess.check_output(
                ["git", "diff", "HEAD", "--", "src", "tools", "tests", "pyproject.toml", "uv.lock"],
                cwd=ROOT,
                encoding="utf-8",
            ),
            inputs_sha256=hashlib.sha256(raw_inputs).hexdigest(),
        ),
    )
    trial = LotTrial(base / "workspace", base / "events")
    inspection_id = trial.bootstrap()
    trial.capture("initial", inspection_id, (inspection_id,))
    trial.accept(inspection_id, wire(data["incomplete_inspection"]))
    incomplete = refused(trial, inspection_id, "incomplete")
    inspection = trial.accept(inspection_id, wire(data["inspection"]))
    missing = refused(trial, inspection_id, "missing-pack", PackRegistry())
    decision_id = trial.finish(inspection_id, "inspection")
    decision = trial.capture("decision", decision_id, (inspection_id, decision_id))
    scoped = trial.capture("selected-only", decision_id, (decision_id,))
    invalid = data["disposition"] | dict(inspection_sha256="0" * 64)
    trial.accept(decision_id, wire(invalid))
    wrong_basis = refused(trial, decision_id, "wrong-basis")
    disposition_input = data["disposition"] | dict(inspection_sha256=inspection.sha256)
    disposition = trial.accept(decision_id, wire(disposition_input))
    closed_id = trial.finish(decision_id, "disposition")
    trial.capture("closed-before-cancel", closed_id, (inspection_id, decision_id, closed_id))
    trial.execute(trial.request(closed_id, "cancel_work"))
    final = trial.capture(
        "final", closed_id, (inspection_id, decision_id, closed_id), selected=False
    )
    save(
        base / "final-workspace-manifest.json",
        retain_trial(trial.path, base / "final-workspace.zip"),
    )
    summary = dict(
        process="fictional.lot-release",
        pack=reference().model_dump(mode="json"),
        inspection=inspection.model_dump(mode="json"),
        disposition=disposition.model_dump(mode="json"),
        outcome=disposition_input["decision"],
        work_ids=[str(inspection_id), str(decision_id), str(closed_id)],
        expected_refusals=dict(
            incomplete=incomplete, missing_pack=missing, wrong_basis=wrong_basis
        ),
        decision_revision=decision["envelope"]["state_revision"],
        selected_context=scoped["answers"]["context_requirements"]["value"]["context"]["state"],
        selected_only_result_headers=scoped["answers"]["recent_important_results"],
        final_revision=final["envelope"]["state_revision"],
        final_answers=final["answers"],
        rollback="Two exact pre-Result snapshots restored and same requests replayed through Core",
        manual_acceptance="pending",
        binding_fresh_G5="pending",
        next="solmax",
    )
    save(base / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--inputs", type=Path, default=ROOT / "docs/m1-first-process/inputs.json")
    args = parser.parse_args()
    if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
        parser.error("Read and resolve STOP/STEER before running")
    base = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if base == scratch or not base.is_relative_to(scratch) or base.exists():
        parser.error("Choose a NEW directory inside this execution worktree's ignored _scratch")
    summary = run(base, args.inputs)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
