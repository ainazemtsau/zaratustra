"""Reproduce T3 read/context behavior in a NEW selected fictional scratch workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from zaratustra.core import (
    ArtifactReference,
    ContextQuery,
    LocalAuthorization,
    MutationReceipt,
    MutationRequest,
    ProcessMetadata,
    ProcessQuery,
    ReceiptQuery,
    apply_mutation,
    authorize_local,
    migrate_workspace,
    prepare_authorization,
    read_history,
    read_records,
)
from zaratustra.process_packs import (
    CapabilitySelection,
    ContextRequirements,
    Notice,
    PackRegistration,
    PackRegistry,
    propose_result,
    read_capabilities,
)

from .probe_m1 import query_for, restore_snapshot, save, work_at
from .probe_packs import FictionalBatchAdapter, PacksTrial, reference, registry
from .retain_trial import retain_trial

ROOT = Path(__file__).resolve().parents[1]
CALL = "c-solmax-zaratustra-m1-capabilities-20260909-exec"


def confirm(
    path: Path, value: MutationRequest | ContextQuery | ReceiptQuery | ProcessQuery
) -> LocalAuthorization:
    return authorize_local(
        prepare_authorization(path, value),
        channel="local-chat",
        actor="T3-fictional-contract-adapter",
        source_ref=f"RUN {CALL}; explicitly selected fictional fixture; T3 acceptance pending",
    )


class CapabilitiesTrial(PacksTrial):
    """Reuse T2 fictional input mechanics with this CALL's exact authorization."""

    def request(self, identity: UUID, operation: str, **payload: Any) -> MutationRequest:
        request = super().request(identity, operation, **payload)
        return MutationRequest.model_validate(
            request.model_dump()
            | dict(provenance=f"Fictional read-contract fixture under RUN {CALL}")
        )

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


class FixtureReader:
    """A read-contract fixture, not either full M1 Process or a product template."""

    def __init__(self, references: tuple[ArtifactReference, ...] = ()) -> None:
        self.references = references

    def describe(self, metadata: ProcessMetadata) -> CapabilitySelection:
        active = [work for work in metadata.works if work.status not in ("done", "cancelled")]
        blocked = [work for work in active if "t3:needs-choice" in work.executor_requirements]
        notices = tuple(
            Notice(
                key=f"choice:{work.id}", work_id=work.id, text="Choose a fictional fixture branch"
            )
            for work in blocked
        )
        return CapabilitySelection(
            current_status="Fictional explicit scope; each submitted Result is important here",
            items_needing_attention=notices,
            open_decisions=notices,
            available_works=tuple(work.id for work in active if work not in blocked),
            blocked_works=notices,
            recent_important_results=tuple(row.id for row in metadata.results),
            context_requirements=ContextRequirements(
                notes=("Use selected Work and its exact Core-verified grounds",),
                references=self.references,
            ),
        )


def installed(reader: FixtureReader | None = None) -> PackRegistry:
    return PackRegistry(
        (PackRegistration(reference(), FictionalBatchAdapter(), reader or FixtureReader()),)
    )


def proposed(path: Path, identity: UUID, selected: PackRegistry) -> MutationRequest:
    query = query_for(path, identity)
    return propose_result(
        path,
        query,
        confirm(path, query),
        selected,
        operation_id=uuid4(),
        next_work_id=uuid4(),
        next_artifact_id=uuid4(),
    )


def process_query(
    path: Path, anchor: UUID, visible: tuple[UUID, ...], chosen: UUID | None = None
) -> ProcessQuery:
    state = read_records(path)
    return ProcessQuery(
        workspace_id=state.workspace_id,
        process_id=work_at(path, anchor).process_id,
        work_id=anchor,
        visible_work_ids=visible,
        selected_work_id=chosen,
        expected_revision=state.state_revision,
        max_bytes=1048576,
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
    trial = CapabilitiesTrial(base / "workspace", base / "events")
    identity = trial.bootstrap()
    migrate_workspace(trial.path, target_version=7)
    trial.execute(trial.bind(identity, reference(), registry(reference())))
    trial.observation(identity)
    before = retain_trial(trial.path, base / "before-result.zip")
    save(base / "before-result-manifest.json", before)

    def capture(
        name: str, query: ProcessQuery, *, content: bool = False, **options: Any
    ) -> dict[str, Any]:
        caller = confirm(trial.path, query)
        save(base / f"{name}.query.json", query.model_dump(mode="json"))
        save(base / f"{name}.authority.json", caller.confirmation.model_dump(mode="json"))
        if content:
            assert query.selected_work_id is not None
            context_query = query_for(trial.path, query.selected_work_id)
            context_caller = confirm(trial.path, context_query)
            options.update(context_query=context_query, context_caller=context_caller)
            save(base / f"{name}.context-query.json", context_query.model_dump(mode="json"))
            save(
                base / f"{name}.context-authority.json",
                context_caller.confirmation.model_dump(mode="json"),
            )
        if "caller" in options:
            caller = options.pop("caller")
        selected_registry = options.pop("registry", installed())
        state = read_records(trial.path)
        history = read_history(trial.path)
        result = read_capabilities(trial.path, query, caller, selected_registry, **options)
        assert read_records(trial.path) == state and read_history(trial.path) == history
        (base / f"{name}.response.json").write_bytes(result.output)
        save(base / f"{name}.state.json", state.model_dump(mode="json"))
        save(base / f"{name}.history.json", history.model_dump(mode="json"))
        decoded: dict[str, Any] = json.loads(result.output)
        return decoded

    first_query = process_query(trial.path, identity, (identity,), identity)
    ready = capture("ready", first_query, content=True)
    capture("empty-scope", process_query(trial.path, identity, ()))
    capture("denied", first_query, caller=None)
    capture("missing-pack", first_query, registry=PackRegistry())
    capture("missing-reader", first_query, registry=registry(reference()))
    trial.execute(
        trial.request(identity, "set_work_requirements", requirements=("t3:needs-choice",))
    )
    capture("stale", first_query)
    blocked = capture("blocked", process_query(trial.path, identity, (identity,), identity))
    trial.execute(
        trial.request(identity, "set_work_requirements", requirements=("probe.batch/v1",))
    )
    request = proposed(trial.path, identity, registry(reference()))
    trial.execute(request)
    assert request.submission is not None
    next_id = request.submission.next_work.work_id
    continued = capture(
        "continued", process_query(trial.path, next_id, (identity, next_id), next_id), content=True
    )
    scoped = capture(
        "next-only", process_query(trial.path, next_id, (next_id,), next_id), content=True
    )
    trial.execute(trial.request(next_id, "revoke_work"))
    capture("revoked", process_query(trial.path, next_id, (next_id,), next_id))
    retained = retain_trial(trial.path, base / "final-workspace.zip")
    save(base / "final-workspace-manifest.json", retained)
    restored = restore_snapshot(base / "before-result.zip", base / "restored-before-result", before)
    restored_query = process_query(restored, identity, (identity,), identity)
    restored_response = read_capabilities(
        restored, restored_query, confirm(restored, restored_query), installed()
    )
    (base / "restored.response.json").write_bytes(restored_response.output)
    replay_request = proposed(restored, identity, registry(reference()))
    replay = apply_mutation(restored, replay_request, confirm(restored, replay_request))
    save(base / "restored-result.request.json", replay_request.model_dump(mode="json"))
    save(base / "restored-result.receipt.json", replay.model_dump(mode="json"))
    summary = dict(
        ready_revision=ready["envelope"]["state_revision"],
        blocked_revision=blocked["envelope"]["state_revision"],
        continued_revision=continued["envelope"]["state_revision"],
        next_only_results=scoped["answers"]["recent_important_results"],
        ready_context=ready["answers"]["context_requirements"]["value"]["context"]["state"],
        inherited_context=scoped["answers"]["context_requirements"]["value"]["context"]["state"],
        restore="exact retained bytes/layout; real read and subsequent Core Result",
        restored_result_revision=replay.new_revision,
        manual_acceptance="pending",
        binding_g5="pending",
        next="solmax",
    )
    save(base / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            parser.error(f"Read and resolve {name}")
    base = args.output.resolve()
    if base.exists() or not base.is_relative_to((ROOT / "_scratch").resolve()):
        parser.error("Choose a NEW directory in this execution worktree's ignored _scratch")
    print(json.dumps(run(base), indent=2))


if __name__ == "__main__":
    main()
