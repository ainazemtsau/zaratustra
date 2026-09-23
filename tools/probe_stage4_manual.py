"""Create one new synthetic proposed Work for manual interactive Pi acceptance."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
from uuid import uuid4

from zaratustra.foundation import (
    ActivityState,
    ArtifactRef,
    BootstrapRequest,
    CreateActivityRequest,
    CreateArtifactRequest,
    CreateWorkRequest,
    OutputContract,
    WorkState,
    apply_operation,
    authorize_local,
    initialize_space,
    upgrade_execution_space,
    upgrade_space,
)

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_NOTE = "Fictional project: a blue kite crossed a quiet field on Tuesday.\n"


def run(output: Path) -> dict[str, str]:
    scratch = (ROOT / "_scratch").resolve()
    target = output.expanduser().resolve()
    if target == scratch or not target.is_relative_to(scratch) or target.exists():
        raise ValueError("Choose a NEW directory inside this checkout's _scratch")
    target.mkdir(parents=True)
    space = target / "space"
    workspace = target / "working"
    space.mkdir()
    workspace.mkdir()
    (workspace / "synthetic-note.txt").write_text(SYNTHETIC_NOTE, encoding="utf-8", newline="\n")
    info = initialize_space(space)
    actor = getpass.getuser()
    authority = authorize_local(space, actor=actor, source_ref="manual-synthetic-setup")
    apply_operation(
        space,
        BootstrapRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=actor,
            decision_id=uuid4(),
            grant_id=uuid4(),
        ),
        authority,
    )
    upgrade_space(space, authority)
    upgrade_execution_space(space, authority)
    input_id, activity_id, work_id = uuid4(), uuid4(), uuid4()
    apply_operation(
        space,
        CreateArtifactRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=actor,
            artifact_id=input_id,
            media_type="text/plain",
            content=SYNTHETIC_NOTE.encode("utf-8"),
        ),
        authority,
    )
    apply_operation(
        space,
        CreateActivityRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=actor,
            activity_id=activity_id,
            state=ActivityState(title="Synthetic Stage 4", goal="Inspect one fictional result"),
        ),
        authority,
    )
    apply_operation(
        space,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=info.space_id,
            actor=actor,
            work_id=work_id,
            state=WorkState(
                activity_id=activity_id,
                goal="Briefly summarize the fictional note and save the result",
                inputs=(ArtifactRef(artifact_id=input_id, revision=1),),
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        authority,
    )
    return {
        "space": str(space),
        "workspace": str(workspace),
        "activity_id": str(activity_id),
        "work_id": str(work_id),
        "input_id": str(input_id),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
