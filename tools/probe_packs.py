"""Reproduce T2 lifecycle through real Core in a NEW selected fictional workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from tests.fixtures.process_probe import BatchRule, Observation
from zaratustra.core import (
    Artifact,
    ArtifactReference,
    ContextQuery,
    Handoff,
    InitialRecords,
    LocalAuthorization,
    MutationError,
    MutationReceipt,
    MutationRequest,
    NextWork,
    PackReference,
    ReceiptQuery,
    Work,
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
    read_workspace,
    submit_result,
)
from zaratustra.process_packs import (
    PackError,
    PackRegistration,
    PackRegistry,
    binding_request,
    propose_result,
)

from .probe_m1 import query_for, restore_snapshot, save, work_at
from .retain_trial import retain_trial

ROOT = Path(__file__).resolve().parents[1]
CALL = "c-solmax-zaratustra-m1-packs-20260909-exec"


class FictionalBatchAdapter:
    """Reuse the accepted T1 observation rule, solely as a T2 lifecycle fixture."""

    def next_work(
        self, work: Work, accepted_result: bytes, work_id: UUID, artifact_id: UUID
    ) -> NextWork:
        return BatchRule().next_work(
            work, Observation.model_validate_json(accepted_result), work_id, artifact_id
        )


def reference(version: str = "1.0.0", /, **changes: Any) -> PackReference:
    return PackReference.model_validate(
        dict(
            pack_id="fictional.batch",
            pack_version=version,
            process_type="fictional.batch-check",
            contract_version=1,
            state_version=1,
        )
        | changes
    )


def registry(*references: PackReference) -> PackRegistry:
    return PackRegistry(tuple(PackRegistration(ref, FictionalBatchAdapter()) for ref in references))


def confirm(path: Path, value: MutationRequest | ContextQuery | ReceiptQuery) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="T2-fictional-lifecycle-adapter",
        source_ref=f"RUN {CALL}; exact local fictional fixture only; acceptance pending",
    )


class PacksTrial:
    def __init__(self, path: Path, evidence: Path) -> None:
        self.path = path
        self.evidence = evidence
        evidence.mkdir(parents=True)
        self.sequence = 0

    def request(self, identity: UUID, operation: str, **payload: Any) -> MutationRequest:
        snapshot = read_records(self.path)
        fields: dict[str, Any] = dict(
            operation=operation,
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=identity,
            expected_revision=snapshot.state_revision,
            provenance=f"Fictional T2 fixture authorized by RUN {CALL}",
        )
        if operation in ("authorize_artifact", "publish_artifact"):
            artifact = next(
                row
                for row in snapshot.records
                if isinstance(row, Artifact) and row.work_id == identity
            )
            fields.update(version=2, artifact_id=artifact.id, artifact_revision=artifact.revision)
        return MutationRequest.model_validate(fields | payload)

    def execute(self, request: MutationRequest, content: bytes | None = None) -> MutationReceipt:
        self.sequence += 1
        prefix = self.evidence / f"{self.sequence:03d}-{request.operation}"
        caller = confirm(self.path, request)
        save(prefix.with_suffix(".request.json"), request.model_dump(mode="json"))
        save(prefix.with_suffix(".authority.json"), caller.confirmation.model_dump(mode="json"))
        if content is not None:
            prefix.with_suffix(".input.json").write_bytes(content)
        receipt = apply_mutation(self.path, request, caller, content=content)
        save(prefix.with_suffix(".receipt.json"), receipt.model_dump(mode="json"))
        return receipt

    def bootstrap(self) -> UUID:
        self.path.mkdir(parents=True)
        init_workspace(self.path)
        migrate_workspace(self.path, target_version=6)
        initial = InitialRecords(
            process_title="Fictional pack lifecycle",
            goal="Continue a fictional batch with an exact retained pack version",
            expected_result="Recorded observation and continuation",
            acceptance=("Both fictional marks",),
            boundaries=("Local fictional data only",),
            budget="One T2 lifecycle example",
            artifact_title="Fictional batch observation",
        )
        save(self.evidence / "bootstrap.json", initial.model_dump(mode="json"))
        create_initial_records(self.path, initial)
        identity = work_at(self.path).id
        self.execute(self.request(identity, "authorize_work"))
        self.execute(
            self.request(identity, "set_work_requirements", requirements=("probe.batch/v1",))
        )
        return identity

    def bind(self, identity: UUID, ref: PackReference, installed: PackRegistry) -> MutationRequest:
        snapshot = read_records(self.path)
        return binding_request(
            installed,
            ref,
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=identity,
            expected_revision=snapshot.state_revision,
            provenance=f"Explicit fictional Process/Work binding under RUN {CALL}",
        )

    def observation(self, identity: UUID) -> None:
        content = b'{"observed": true, "recorded": true}'
        self.execute(self.request(identity, "authorize_artifact"))
        publication = self.request(
            identity,
            "publish_artifact",
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_size=len(content),
        )
        self.execute(publication, content)
        assert publication.artifact_id is not None
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
            result=ArtifactReference(
                artifact_id=publication.artifact_id,
                version_id=publication.operation_id,
                sha256=hashlib.sha256(content).hexdigest(),
            ),
            provenance="Fictional T2 observation; no owner acceptance claim",
            created_by="T2 fictional adapter",
        )
        self.execute(handoff_request(handoff.model_dump_json().encode(), source_ref=CALL))


def proposed(path: Path, identity: UUID, installed: PackRegistry) -> MutationRequest:
    query = query_for(path, identity)
    return propose_result(
        path,
        query,
        confirm(path, query),
        installed,
        operation_id=uuid4(),
        next_work_id=uuid4(),
        next_artifact_id=uuid4(),
    )


def run(base: Path) -> dict[str, Any]:
    base.mkdir()
    save(
        base / "runtime.json",
        dict(
            call=CALL,
            commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
            ).strip(),
            diff=subprocess.check_output(
                ["git", "diff", "HEAD", "--", "src", "tools", "tests", "pyproject.toml", "uv.lock"],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
            ),
            python=sys.version,
            argv=sys.argv,
        ),
    )
    trial = PacksTrial(base / "workspace", base / "events")
    identity = trial.bootstrap()
    legacy = read_records(trial.path)
    legacy_history = read_history(trial.path)
    legacy_manifest = retain_trial(trial.path, base / "before-migration.zip")
    save(base / "before-migration-manifest.json", legacy_manifest)
    migrate_workspace(trial.path, target_version=7)
    assert read_records(trial.path) == legacy and read_history(trial.path) == legacy_history
    v1, v2 = reference(), reference("2.0.0")
    installed = registry(v1, v2)
    save(
        base / "registrations.json",
        [r.reference.model_dump(mode="json") for r in installed.registrations],
    )
    bind = trial.bind(identity, v1, installed)
    before_bind = read_records(trial.path)
    save(base / "before-bind.json", before_bind.model_dump(mode="json"))
    bind_manifest = retain_trial(trial.path, base / "before-bind.zip")
    save(base / "before-bind-manifest.json", bind_manifest)
    bound_receipt = trial.execute(bind)
    prior_work = next(
        row for row in before_bind.records if isinstance(row, Work) and row.id == identity
    )
    assert work_at(trial.path, identity).authority_scope == prior_work.authority_scope
    save(base / "after-bind.json", read_records(trial.path).model_dump(mode="json"))
    trial.observation(identity)
    before = read_workspace(trial.path).database.read_bytes()
    before_history = read_history(trial.path)
    outcomes = []
    for name, unavailable in (
        ("missing", registry()),
        ("v2-only", registry(v2)),
        ("incompatible-contract", registry(reference(contract_version=2))),
        ("incompatible-state", registry(reference(state_version=2))),
    ):
        try:
            proposed(trial.path, identity, unavailable)
        except PackError as error:
            assert read_workspace(trial.path).database.read_bytes() == before
            assert read_history(trial.path) == before_history
            outcomes.append(dict(case=name, code=error.code, no_write=True))
        else:
            raise AssertionError(f"Unexpected continuation: {name}")
    switch = trial.bind(identity, v2, installed)
    try:
        trial.execute(switch)
    except MutationError as error:
        assert read_workspace(trial.path).database.read_bytes() == before
        assert read_history(trial.path) == before_history
        outcomes.append(dict(case="in-place-version-change", code=error.code, no_write=True))
    else:
        raise AssertionError("Existing Work binding changed")
    save(base / "refusals.json", outcomes)
    query = query_for(trial.path, identity)
    save(base / "query.json", query.model_dump(mode="json"))
    (base / "context.json").write_bytes(
        open_work(trial.path, query, confirm(trial.path, query)).output
    )
    manifest = retain_trial(trial.path, base / "before-result.zip")
    save(base / "before-result-manifest.json", manifest)
    request = proposed(trial.path, identity, registry(v1))
    save(base / "proposal.json", request.model_dump(mode="json"))
    try:
        submit_result(trial.path, request)
    except MutationError as error:
        assert error.code == "permission_denied"
        assert read_workspace(trial.path).database.read_bytes() == before
    else:
        raise AssertionError("A pack proposal issued authority")
    receipt = trial.execute(request)
    assert request.submission is not None
    next_id = request.submission.next_work.work_id
    assert work_at(trial.path, next_id).pack_binding == v1
    assert work_at(trial.path, identity).pack_binding == v1
    saved_query = ReceiptQuery(
        workspace_id=request.workspace_id, work_id=identity, operation_id=request.operation_id
    )
    save(
        base / "saved-result.json",
        read_result(trial.path, saved_query, confirm(trial.path, saved_query)).model_dump(
            mode="json"
        ),
    )
    save(base / "final-state.json", read_records(trial.path).model_dump(mode="json"))
    save(base / "final-history.json", read_history(trial.path).model_dump(mode="json"))
    next_query = query_for(trial.path, next_id)
    (base / "next-context.json").write_bytes(
        open_work(trial.path, next_query, confirm(trial.path, next_query)).output
    )
    restored = restore_snapshot(base / "before-result.zip", base / "restored-result", manifest)
    replay = submit_result(restored, request, confirm(restored, request))
    assert work_at(restored, next_id).pack_binding == v1
    assert replay.fingerprint == receipt.fingerprint
    restored_bind = restore_snapshot(
        base / "before-bind.zip", base / "restored-bind", bind_manifest
    )
    bind_replay = apply_mutation(restored_bind, bind, confirm(restored_bind, bind))
    assert bind_replay.fingerprint == bound_receipt.fingerprint
    assert work_at(restored_bind).pack_binding == v1
    restored_legacy = restore_snapshot(
        base / "before-migration.zip", base / "restored-legacy", legacy_manifest
    )
    assert read_records(restored_legacy) == legacy
    assert read_history(restored_legacy) == legacy_history
    other = PacksTrial(base / "new-v2-workspace", base / "new-v2-events")
    other_id = other.bootstrap()
    migrate_workspace(other.path, target_version=7)
    other.execute(other.bind(other_id, v2, registry(v2)))
    other.observation(other_id)
    other_result = proposed(other.path, other_id, registry(v2))
    other.execute(other_result)
    save(base / "v2-final-state.json", read_records(other.path).model_dump(mode="json"))
    summary = dict(
        binding_revision=[bound_receipt.previous_revision, bound_receipt.new_revision],
        result_revision=[receipt.previous_revision, receipt.new_revision],
        process_work_and_next_binding=v1.model_dump(mode="json"),
        refusals=outcomes,
        rights_unchanged_by_bind=True,
        proposal_without_authority="permission_denied",
        restore_legacy_bind_and_result="exact bytes/layout, then real Core read/mutation",
        v2_independent_process="bound and continued; v1 Process unchanged",
        manual_acceptance="pending",
        binding_g5="pending",
    )
    save(base / "summary.json", summary)
    final_manifest = retain_trial(trial.path, base / "final-workspace.zip")
    save(base / "final-workspace-manifest.json", final_manifest)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for leaf in ("STOP", "STEER.md"):
        if (ROOT / leaf).exists():
            parser.error(f"Read and resolve {leaf} before running")
    base = args.output.resolve()
    if base.exists() or not base.is_relative_to((ROOT / "_scratch").resolve()):
        parser.error("Choose a NEW directory under this execution worktree's ignored _scratch")
    print(json.dumps(run(base), indent=2))


if __name__ == "__main__":
    main()
