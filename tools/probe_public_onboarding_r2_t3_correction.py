"""Retain fresh-process installed CLI evidence for the two R2 T3 corrections."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def _save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _cli_child(mode: str, evidence: Path, product_root: Path, arguments: list[str]) -> int:
    import zaratustra.cli as cli
    from zaratustra.core import (
        AuthorizationPrompt,
        LocalAuthorization,
        MutationRequest,
        authorize_local,
        prepare_authorization,
    )

    prompts: list[str] = []

    def confirm(prompt: AuthorizationPrompt) -> LocalAuthorization:
        prompts.append(prompt.request_sha256)
        if mode == "wrong":
            assert isinstance(prompt.request, MutationRequest)
            prompt = prepare_authorization(
                Path(prompt.workspace_path),
                prompt.request.model_copy(update=dict(operation_id=uuid4())),
            )
        return authorize_local(
            prompt,
            channel="local-chat",
            actor="fictional-correction-probe",
            source_ref="synthetic exact confirmation; not owner acceptance",
        )

    entrypoint = next(row for row in distribution("zaratustra").entry_points if row.name == "zara")
    sys.argv = ["zara", *arguments]
    if mode == "missing":
        result = int(entrypoint.load()())
    else:
        with patch.object(cli, "confirm_on_console", confirm):
            result = int(entrypoint.load()())
    modules = {
        name: str(module.__file__)
        for name, module in sys.modules.items()
        if (name == "zaratustra" or name.startswith("zaratustra."))
        and getattr(module, "__file__", None)
    }
    assert all(Path(path).resolve().is_relative_to(product_root) for path in modules.values())
    _save(evidence, dict(pid=os.getpid(), prompts=prompts, product_modules=modules))
    return result


def _cli(output: Path, name: str, arguments: list[str], mode: str = "exact") -> dict[str, Any]:
    import zaratustra

    evidence = output / f"{name}-runtime.json"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            str(Path(__file__).resolve()),
            "--cli-child",
            mode,
            str(evidence),
            str(Path(zaratustra.__file__).resolve().parent),
            *arguments,
        ],
        cwd=output,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    (output / f"{name}-stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / f"{name}-stderr.txt").write_text(result.stderr, encoding="utf-8")
    return dict(
        rc=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        runtime=json.loads(evidence.read_bytes()),
    )


def _change(output: Path) -> dict[str, Any]:
    from tools.probe_process_t3 import _accept_result, _activate, _changed, _confirm, _review
    from zaratustra.core import read_history, read_records
    from zaratustra.process_change import (
        authorize_process_change,
        decide_process_change,
        execute_process_change_continuation,
        prepare_process_change_continuation,
    )

    designation = "Fictional fresh CLI safe change"
    catalog, workspace, definition, work = _activate(output / "change", "project", designation)
    review = _review(catalog, workspace, designation, _changed(definition, "project"), "project")
    decide_process_change(
        review,
        authorize_process_change(
            review,
            decision="approve",
            channel="local-chat",
            actor="fictional-correction-probe",
            source_ref="synthetic reviewed change; not owner acceptance",
        ),
    )
    _accept_result(workspace, work, definition, "project")
    arguments = ["entry", "change", "apply", str(catalog), designation]
    revision_before = read_records(workspace).state_revision
    history_before = len(read_history(workspace).events)
    first = _cli(output, "apply-first", arguments)
    assert first["rc"] == 0, first
    after = _hashes(output / "change")
    revision_after = read_records(workspace).state_revision
    history_after = len(read_history(workspace).events)
    retry = _cli(output, "apply-retry", arguments)
    assert _hashes(output / "change") == after
    missing = _cli(output, "apply-missing", arguments, "missing")
    wrong = _cli(output, "apply-wrong", arguments, "wrong")
    assert missing["rc"] == wrong["rc"] == 1
    assert _hashes(output / "change") == after
    recovered = prepare_process_change_continuation(catalog, designation, None)
    api = execute_process_change_continuation(
        recovered, _confirm(workspace, recovered.request, "project")
    )
    original = json.loads(first["stdout"])
    assert api.receipt.model_dump(mode="json") == original["receipt"]
    assert _hashes(output / "change") == after
    events = read_history(workspace).events
    _save(output / "change-state-hashes.json", after)
    return dict(
        first=first,
        retry=retry,
        missing=missing,
        wrong=wrong,
        exact_stdout_replay=first["stdout"] == retry["stdout"],
        api_recovers_original_receipt=True,
        replay_and_refusals_byte_stable=True,
        revision_delta=revision_after - revision_before,
        history_delta=history_after - history_before,
        operation_id=str(recovered.request.operation_id),
        operation_events=sum(
            row.request.operation_id == recovered.request.operation_id for row in events
        ),
    )


def _stages(output: Path) -> list[dict[str, Any]]:
    from tests.fixtures.process_creation import creation_research
    from tools.probe_public_onboarding_r2_t3 import _definition
    from zaratustra.onboarding import (
        prepare_onboarding_read,
        read_onboarding,
        save_prose_creation_draft,
    )
    from zaratustra.process_creation import (
        create_research_request,
        prepare_process_activation,
        receive_research_return,
        save_research_request,
        save_supported_proposal,
    )

    state = output / "stages"
    state.mkdir()
    catalog = state / "catalog.json"
    designation = "Fictional retained proposal"
    rows: list[dict[str, Any]] = []

    def observe() -> None:
        resumed = read_onboarding(prepare_onboarding_read(catalog, designation))
        before = _hashes(state)
        first = _cli(
            output, f"resume-{resumed.stage}", ["entry", "resume", str(catalog), designation]
        )
        second = _cli(
            output, f"resume-{resumed.stage}-retry", ["entry", "resume", str(catalog), designation]
        )
        assert first["rc"] == second["rc"] == 0
        assert first["stdout"] == second["stdout"] and _hashes(state) == before
        assert resumed.creation is not None
        rows.append(
            dict(
                stage=resumed.stage,
                next_action=resumed.next_action,
                proposal_retained=resumed.creation.proposal is not None,
                byte_stable=True,
                first=first,
                retry=second,
            )
        )

    save_prose_creation_draft(
        catalog,
        designation,
        process_title="Fictional saved proposal",
        need="Keep one note.",
        desired_outcomes=("One fictional note.",),
        constraints=("No provider call.",),
        created_by="fictional-correction-probe",
    )
    observe()
    request = create_research_request(catalog, designation)
    request_file = state / "manual-request.json"
    save_research_request(request_file, request)
    observe()
    research = creation_research("small")
    receive_research_return(
        catalog,
        designation,
        request_file.read_bytes(),
        research,
        created_by="fictional-manual-research",
        source_ref="fictional manual return",
    )
    observe()
    definition = _definition(
        "simple",
        hashlib.sha256(request_file.read_bytes()).hexdigest(),
        hashlib.sha256(research).hexdigest(),
    )
    save_supported_proposal(catalog, designation, definition.model_dump_json().encode())
    observe()
    prepare_process_activation(catalog, designation, state / "workspace")
    observe()
    _save(output / "stage-state-hashes.json", _hashes(state))
    return rows


def run(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True)
    summary = dict(
        change=_change(output),
        stages=_stages(output),
        synthetic_confirmation_not_owner_acceptance=True,
    )
    _save(output / "correction.json", summary)
    return summary


def main() -> None:
    for name in ("STOP", "STEER.md"):
        if (ROOT / name).exists():
            raise SystemExit(f"Read and resolve {name} before running")
    if len(sys.argv) > 1 and sys.argv[1] == "--cli-child":
        raise SystemExit(
            _cli_child(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5:])
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT / "_scratch" or not output.is_relative_to(ROOT / "_scratch"):
        parser.error("Choose a NEW directory inside this worktree's ignored _scratch")
    if args.child:
        import zaratustra

        assert Path(zaratustra.__file__).resolve().is_relative_to(output / "installed" / "venv")
        assert not any(Path(item).resolve() in {ROOT, ROOT / "src"} for item in sys.path if item)
        sys.path.append(str(ROOT))
        run(output / "fresh-cli")
    else:
        if output.exists():
            parser.error("Choose a NEW directory; retained evidence is never overwritten")
        from tools.probe_process_t3_install import verify

        verify(output / "installed")
        python = (
            output
            / "installed"
            / "venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-X",
                "utf8",
                str(Path(__file__).resolve()),
                "--output",
                str(output),
                "--child",
            ],
            cwd=output / "installed" / "empty-cwd",
            check=True,
        )
        print(f"Retained installed observations: {output / 'fresh-cli' / 'correction.json'}")


if __name__ == "__main__":
    main()
