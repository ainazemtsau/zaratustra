"""Development-only host for explicit external packages using public Core APIs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

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
from zaratustra.process_packs import (
    PackError,
    PackRegistration,
    PackRegistry,
    binding_request,
    propose_result,
    read_capabilities,
)

from .probe_m1 import query_for, restore_snapshot, save, work_at
from .retain_trial import retain_trial

ROOT = Path(__file__).resolve().parents[1]


def wire(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + chr(10)).encode()


def confirm(
    path: Path, value: MutationRequest | ContextQuery | ReceiptQuery | ProcessQuery, *, call: str
) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="fictional-process-host",
        source_ref=f"RUN {call}; selected fictional workspace only; not product owner acceptance",
    )


def footprint(path: Path) -> dict[str, str | None]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        if item.is_file()
        else None
        for item in sorted(path.rglob("*"))
    }


class ProcessTrial:
    """Record explicit host actions; package proposals never grant their own authority."""

    def __init__(
        self,
        path: Path,
        evidence: Path,
        *,
        package: PackRegistration,
        initial: InitialRecords,
        requirements: tuple[str, ...],
        call: str,
        registry: PackRegistry | None = None,
    ) -> None:
        self.path = path
        self.evidence = evidence
        evidence.mkdir(parents=True)
        self.sequence = 0
        self.reference = package.reference
        self.initial = initial
        self.requirements = requirements
        self.call = call
        self.registry = PackRegistry((package,)) if registry is None else registry
        self.registry.resolve(self.reference)

    def confirm(
        self,
        path: Path,
        value: MutationRequest | ContextQuery | ReceiptQuery | ProcessQuery,
    ) -> LocalAuthorization:
        return confirm(path, value, call=self.call)

    def request(self, identity: UUID, operation: str, **payload: Any) -> MutationRequest:
        snapshot = read_records(self.path)
        fields: dict[str, Any] = dict(
            operation=operation,
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=identity,
            expected_revision=snapshot.state_revision,
            provenance=f"Selected fictional Process under RUN {self.call}",
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
        if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
            raise RuntimeError("Read and resolve STOP/STEER before mutation")
        self.sequence += 1
        prefix = self.evidence / f"{self.sequence:03d}-{request.operation}"
        caller = self.confirm(self.path, request)
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
        if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
            raise RuntimeError("Read and resolve STOP/STEER before initialization")
        self.path.mkdir(parents=True)
        init_workspace(self.path)
        migrate_workspace(self.path, target_version=7)
        initial = self.initial
        save(self.evidence / "bootstrap.json", initial.model_dump(mode="json"))
        create_initial_records(self.path, initial)
        identity = work_at(self.path).id
        self.execute(self.request(identity, "authorize_work"))
        self.execute(
            self.request(identity, "set_work_requirements", requirements=self.requirements)
        )
        save(self.evidence / "registration.json", self.reference.model_dump(mode="json"))
        self.execute(
            binding_request(
                self.registry,
                self.reference,
                operation_id=uuid4(),
                workspace_id=read_records(self.path).workspace_id,
                work_id=identity,
                expected_revision=read_records(self.path).state_revision,
                provenance=f"Explicit fictional pack binding under RUN {self.call}",
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
            provenance="Fictional input; no product owner acceptance claim",
            created_by=f"Fictional host under RUN {self.call}",
        )
        self.execute(handoff_request(handoff.model_dump_json().encode(), source_ref=self.call))
        return result

    def proposal(
        self, identity: UUID, name: str, registry: PackRegistry | None = None
    ) -> MutationRequest:
        query = query_for(self.path, identity)
        caller = self.confirm(self.path, query)
        save(self.evidence / f"{name}.query.json", query.model_dump(mode="json"))
        save(self.evidence / f"{name}.authority.json", caller.confirmation.model_dump(mode="json"))
        (self.evidence / f"{name}.context.json").write_bytes(
            open_work(self.path, query, caller).output
        )
        return propose_result(
            self.path,
            query,
            caller,
            self.registry if registry is None else registry,
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
        caller = self.confirm(self.path, query)
        prefix = self.evidence / name
        save(prefix.with_suffix(".process-query.json"), query.model_dump(mode="json"))
        save(
            prefix.with_suffix(".process-authority.json"),
            caller.confirmation.model_dump(mode="json"),
        )
        result = read_capabilities(self.path, query, caller, self.registry)
        prefix.with_suffix(".metadata.json").write_bytes(result.output)
        if selected and content:
            decoded = json.loads(result.output)
            refs = decoded["answers"]["context_requirements"]["value"]["references"]
            context = query_for(self.path, identity).model_copy(
                update=dict(references=tuple(ArtifactReference.model_validate(row) for row in refs))
            )
            context_caller = self.confirm(self.path, context)
            save(prefix.with_suffix(".context-query.json"), context.model_dump(mode="json"))
            save(
                prefix.with_suffix(".context-authority.json"),
                context_caller.confirmation.model_dump(mode="json"),
            )
            result = read_capabilities(
                self.path,
                query,
                caller,
                self.registry,
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
        result_caller = self.confirm(self.path, saved_query)
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
        context_caller = self.confirm(restored, context_query)
        save(
            prefix.with_suffix(".restore-context-authority.json"),
            context_caller.confirmation.model_dump(mode="json"),
        )
        assert (
            open_work(restored, context_query, context_caller).output
            == prefix.with_suffix(".context.json").read_bytes()
        )
        restored_caller = self.confirm(restored, request)
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
        assert work_at(restored, next_id).pack_binding == self.reference
        return next_id


def refused(
    trial: ProcessTrial, identity: UUID, name: str, registry: PackRegistry | None = None
) -> str:
    before = footprint(trial.path)
    try:
        trial.proposal(identity, name, registry)
    except PackError as error:
        assert footprint(trial.path) == before
        save(trial.evidence / f"{name}.refusal.json", dict(code=error.code, unchanged=True))
        return error.code
    raise AssertionError("Expected package refusal")
