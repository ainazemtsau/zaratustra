"""Run an explicitly selected fictional T1 trial in a NEW ignored workspace tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
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
from zaratustra.process_probe import BatchRule, CycleRule, Rule, RuleBlocked, propose_result

from .retain_trial import retain_trial

ROOT = Path(__file__).resolve().parents[1]
CALL = "c-solmax-zaratustra-m1-probe-admission-20260909-exec"


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + chr(10), encoding="utf-8")


def confirm(path: Path, value: MutationRequest | ContextQuery | ReceiptQuery) -> LocalAuthorization:
    """Trusted fictional adapter under the RUN/CALL; no runtime acceptance claim."""
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="T1-fictional-probe-adapter",
        source_ref=f"RUN {CALL}; only newly selected fictional probe workspace",
    )


def work_at(path: Path, identity: UUID | None = None) -> Work:
    return next(
        row
        for row in read_records(path).records
        if isinstance(row, Work) and (identity is None or row.id == identity)
    )


def query_for(path: Path, identity: UUID) -> ContextQuery:
    snapshot = read_records(path)
    work = work_at(path, identity)
    return ContextQuery(
        workspace_id=snapshot.workspace_id,
        work_id=identity,
        process_id=work.process_id,
        expected_revision=snapshot.state_revision,
        max_bytes=1048576,
    )


class Trial:
    """Development-only recorder; production authority/mutations stay in Core."""

    def __init__(self, path: Path, evidence: Path) -> None:
        self.path = path
        self.evidence = evidence
        evidence.mkdir(parents=True)
        self.sequence = 0

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

    def request(self, identity: UUID, operation: str, **payload: Any) -> MutationRequest:
        snapshot = read_records(self.path)
        fields: dict[str, Any] = dict(
            operation=operation,
            operation_id=uuid4(),
            workspace_id=snapshot.workspace_id,
            work_id=identity,
            expected_revision=snapshot.state_revision,
            provenance=f"Fictional T1 fixture authorized by RUN {CALL}",
        )
        if operation in ("authorize_artifact", "publish_artifact"):
            artifact = next(
                row
                for row in snapshot.records
                if isinstance(row, Artifact) and row.work_id == identity
            )
            fields.update(version=2, artifact_id=artifact.id, artifact_revision=artifact.revision)
        return MutationRequest.model_validate(fields | payload)

    def bootstrap(self, binding: str) -> UUID:
        self.path.mkdir(parents=True)
        init_workspace(self.path)
        migrate_workspace(self.path, target_version=6)
        initial = InitialRecords(
            process_title=f"Fictional {binding}",
            goal="Evaluate the selected fictional rule",
            expected_result="Exact recorded observation and permitted continuation",
            acceptance=("Only explicitly selected fictional inputs",),
            boundaries=("Local fictional workspace only",),
            budget="One minimal rule contrast",
            artifact_title="Fictional observation",
        )
        save(self.evidence / "bootstrap.json", initial.model_dump(mode="json"))
        create_initial_records(self.path, initial)
        identity = work_at(self.path).id
        self.execute(self.request(identity, "authorize_work"))
        self.execute(self.request(identity, "set_work_requirements", requirements=(binding,)))
        return identity

    def observation(self, identity: UUID, value: dict[str, bool]) -> None:
        content = (json.dumps(value, sort_keys=True) + chr(10)).encode("utf-8")
        self.execute(self.request(identity, "authorize_artifact"))
        request = self.request(
            identity,
            "publish_artifact",
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_size=len(content),
        )
        self.execute(request, content)
        assert request.artifact_id is not None
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
                artifact_id=request.artifact_id,
                version_id=request.operation_id,
                sha256=hashlib.sha256(content).hexdigest(),
            ),
            provenance="Explicit fictional observation, not owner product acceptance",
            created_by="T1 fictional adapter",
        )
        self.execute(handoff_request(handoff.model_dump_json().encode(), source_ref=CALL))


def proposed(path: Path, identity: UUID, rule: Rule) -> MutationRequest:
    query = query_for(path, identity)
    return propose_result(
        path,
        query,
        confirm(path, query),
        rule,
        operation_id=uuid4(),
        next_work_id=uuid4(),
        next_artifact_id=uuid4(),
    )


def restore_snapshot(archive: Path, target: Path, manifest: dict[str, Any]) -> Path:
    """Execute retain_trial's documented restore into a fresh directory, preserving bytes."""
    target.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not (target / member.filename).resolve().is_relative_to(target.resolve()):
                raise ValueError("Unsafe retained member")
        bundle.extractall(target)
    actual = {
        p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in target.rglob("*")
        if p.is_file()
    }
    directories = sorted(
        p.relative_to(target).as_posix() + "/" for p in target.rglob("*") if p.is_dir()
    )
    if actual != manifest["files"] or directories != manifest["directories"]:
        raise ValueError("Restore differs from retained bytes/layout")
    return target


def run_case(
    base: Path, name: str, rule: Rule, binding: str, values: list[dict[str, bool]]
) -> dict[str, Any]:
    trial = Trial(base / name / "workspace", base / name / "evidence")
    identity = trial.bootstrap(binding)
    outcomes: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        trial.observation(identity, value)
        stage = base / name / f"step-{index}"
        stage.mkdir()
        before = read_records(trial.path)
        history_before = read_history(trial.path)
        query = query_for(trial.path, identity)
        save(stage / "query.json", query.model_dump(mode="json"))
        (stage / "context-before.json").write_bytes(
            open_work(trial.path, query, confirm(trial.path, query)).output
        )
        save(stage / "state-before.json", before.model_dump(mode="json"))
        save(stage / "history-before.json", history_before.model_dump(mode="json"))
        manifest = retain_trial(trial.path, stage / "before.zip")
        save(stage / "before-manifest.json", manifest)
        database = read_workspace(trial.path).database
        before_bytes = database.read_bytes()
        try:
            request = proposed(trial.path, identity, rule)
        except RuleBlocked as error:
            assert database.read_bytes() == before_bytes
            assert read_history(trial.path) == history_before
            outcome = dict(input=value, disposition="blocked", reason=str(error), no_write=True)
        else:
            assert database.read_bytes() == before_bytes
            save(stage / "proposal.json", request.model_dump(mode="json"))
            # The proposal itself confers no authority.
            try:
                submit_result(trial.path, request)
            except MutationError as error:
                assert error.code == "permission_denied"
                assert database.read_bytes() == before_bytes
                save(stage / "denied.json", dict(code=error.code, no_write=True))
            else:
                raise AssertionError("Unconfirmed rule proposal gained authority")
            receipt = trial.execute(request)
            assert request.submission is not None
            target = request.submission.next_work
            source = work_at(trial.path, identity)
            next_work = work_at(trial.path, target.work_id)
            assert source.status == "done" and source.completion_id == request.operation_id
            assert next_work.executor_requirements == target.executor_requirements
            assert next_work.goal == target.goal and next_work.process_id == source.process_id
            assert len(read_records(trial.path).records) == len(before.records) + 2
            assert read_records(trial.path).state_revision == before.state_revision + 1
            q = ReceiptQuery(
                workspace_id=request.workspace_id,
                work_id=identity,
                operation_id=request.operation_id,
            )
            saved = read_result(trial.path, q, confirm(trial.path, q))
            assert saved.event.request == request and saved.receipt == receipt
            save(stage / "saved-result.json", saved.model_dump(mode="json"))
            next_query = query_for(trial.path, target.work_id)
            wire = open_work(trial.path, next_query, confirm(trial.path, next_query)).output
            (stage / "context-after.json").write_bytes(wire)
            sources = {s["locator"]: s["data"] for s in json.loads(wire)["context"]["sources"]}
            assert sources[f"result:{request.operation_id}"] == saved.model_dump(mode="json")
            assert sources[f"work:{target.work_id}"] == next_work.model_dump(mode="json")
            # Restore the pre-submit copy, open it using newly bound path authority,
            # and execute the SAME exact request through the same Core.
            restored = restore_snapshot(stage / "before.zip", stage / "restored", manifest)
            assert read_records(restored) == before and read_history(restored) == history_before
            restored_wire = open_work(restored, query, confirm(restored, query)).output
            assert restored_wire == (stage / "context-before.json").read_bytes()
            replay_receipt = submit_result(restored, request, confirm(restored, request))
            assert replay_receipt.fingerprint == receipt.fingerprint
            assert replay_receipt.new_revision == receipt.new_revision
            assert (
                work_at(restored, target.work_id).executor_requirements
                == target.executor_requirements
            )
            save(stage / "restore-receipt.json", replay_receipt.model_dump(mode="json"))
            outcome = dict(
                input=value,
                disposition="continued",
                before_revision=before.state_revision,
                after_revision=receipt.new_revision,
                next_work_id=str(target.work_id),
                next_requirements=list(target.executor_requirements),
                backup_restored_exactly=True,
                restored_request_fingerprint=replay_receipt.fingerprint,
            )
            identity = target.work_id
        save(stage / "state-after.json", read_records(trial.path).model_dump(mode="json"))
        save(stage / "history-after.json", read_history(trial.path).model_dump(mode="json"))
        save(stage / "outcome.json", outcome)
        outcomes.append(outcome)
    result = dict(case=name, initial_binding=binding, outcomes=outcomes)
    save(base / name / "summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (ROOT / "STOP").exists() or (ROOT / "STEER.md").exists():
        parser.error("Read and resolve STOP/STEER before running")
    base = args.output.resolve()
    scratch = (ROOT / "_scratch").resolve()
    if base == scratch or not base.is_relative_to(scratch) or base.exists():
        parser.error("Output must be a NEW directory inside this worktree's _scratch")
    base.mkdir(parents=True)
    save(
        base / "runtime.json",
        dict(
            python=sys.version,
            executable=sys.executable,
            product_root=str(ROOT),
            commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8"
            ).strip(),
            dirty=subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, encoding="utf-8"
            ),
            call=CALL,
            owner_acceptance="pending",
        ),
    )
    results = [
        run_case(
            base,
            "batch",
            BatchRule(),
            "probe.batch/v1",
            [dict(observed=True, recorded=False), dict(observed=True, recorded=True)],
        ),
        run_case(
            base,
            "cycle",
            CycleRule(),
            "probe.cycle/v1:observe",
            [
                dict(observed=True, recorded=False),
                dict(observed=True, recorded=False),
                dict(observed=False, recorded=True),
            ],
        ),
    ]
    save(base / "summary.json", results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
