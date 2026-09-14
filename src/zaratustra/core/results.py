"""Result value reconstruction and finite historical grants; no alternate writer."""

from uuid import UUID

from .artifacts import current_artifact, resolve_version
from .protocol import (
    ArtifactReference,
    ArtifactVersion,
    MutationEvent,
    MutationRequest,
)
from .records import Artifact, RecordsSnapshot


def incoming_events(events: tuple[MutationEvent, ...], work_id: UUID) -> tuple[MutationEvent, ...]:
    """Only explicit committed next edges; never follow text or arbitrary Work ids."""
    found = [e for e in events if e.next_work is not None and e.next_work.id == work_id]
    if not found:
        return ()
    if len(found) != 1:
        raise ValueError("A continuation must have one incoming Result")
    event = found[0]
    earlier = tuple(e for e in events if e.state_revision < event.state_revision)
    return (*incoming_events(earlier, event.before.id), event)


def result_basis(
    request: MutationRequest,
    snapshot: RecordsSnapshot,
    events: tuple[MutationEvent, ...],
    versions: tuple[ArtifactVersion, ...],
) -> tuple[ArtifactReference, ...]:
    """Re-derive exact ids, scope and complete closure; caller verifies physical bytes."""
    submission = request.submission or request.terminal_submission
    if submission is None or submission.source_revision != snapshot.state_revision:
        raise ValueError("Result source revision is not current")
    artifact = current_artifact(snapshot, request.work_id)
    acceptances = [
        e.request.handoff
        for e in events
        if e.request.work_id == request.work_id and e.request.handoff is not None
    ]
    if tuple(h.handoff_id for h in acceptances) != submission.acceptance_ids:
        raise ValueError("Result must retain ALL current Work acceptances in journal order")
    ids = {r.id for r in snapshot.records}
    if request.submission is not None and (
        request.submission.next_work.work_id in ids
        or request.submission.next_work.artifact_id in ids
    ):
        raise ValueError("Next Work and Artifact identities must be new")
    if any(
        e.request.work_id == request.work_id and e.request.submission is not None for e in events
    ):
        raise ValueError("Work already has a committed Result")
    own_result = resolve_version(versions, artifact, submission.result.version_id)
    if (submission.result.artifact_id, submission.result.sha256) != (
        artifact.id,
        own_result.sha256,
    ):
        raise ValueError("Submitted result is outside this Work or has changed hash")
    inherited = {
        ref.version_id: ref
        for e in incoming_events(events, request.work_id)
        for ref in e.result_references
    }
    refs = [submission.result, *inherited.values()]
    for handoff in acceptances:
        refs.extend((handoff.result, *handoff.basis))
    active = resolve_version(versions, artifact)
    refs.append(
        ArtifactReference(artifact_id=artifact.id, version_id=active.id, sha256=active.sha256)
    )
    publications = {e.artifact_version.id: e for e in events if e.artifact_version is not None}
    artifacts = {r.id: r for r in snapshot.records if isinstance(r, Artifact)}
    seen: dict[UUID, ArtifactReference] = {}
    for ref in refs:
        if ref.artifact_id != artifact.id and inherited.get(ref.version_id) != ref:
            raise ValueError("Result reference is outside current scope and inherited grant")
        descriptor = resolve_version(versions, artifacts[ref.artifact_id], ref.version_id)
        if descriptor.sha256 != ref.sha256:
            raise ValueError("Result reference hash differs from registered bytes")
        if ref.version_id in seen:
            if seen[ref.version_id] != ref:
                raise ValueError("Conflicting reference identity")
            continue
        seen[ref.version_id] = ref
        refs.extend(publications[descriptor.id].request.references)
    return tuple(seen.values())
