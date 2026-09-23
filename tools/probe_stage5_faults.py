"""Crash and replay observations for Core, DBOS 3.0.0 and ordinary Pi RPC."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from tests.zaratustra.foundation.test_continuation import ready
from tools.probe_stage5_rpc import SyntheticHandler, SyntheticProvider
from zaratustra.foundation import (
    ALL_ACTIONS,
    AssignAttemptRequest,
    CreateGrantRequest,
    CreateResourceRequest,
    CreateWorkRequest,
    ExecutionSnapshot,
    FoundationError,
    GrantState,
    OutputContract,
    PublishAttemptOutputRequest,
    ResourceState,
    ReviseResourceRequest,
    RevokeGrantRequest,
    WorkState,
    apply_operation,
    authorize_local,
    read_execution,
    read_receipt,
)
from zaratustra.pi_adapter import Bridge
from zaratustra.pi_adapter.assigned import (
    EXECUTOR_VERSION,
    AssignedConfig,
    deliver_outbox,
    run_assigned,
)


class DropFirstHandler(SyntheticHandler):
    def do_POST(self) -> None:
        server = self.server
        if isinstance(server, DropFirstProvider) and not server.digests:
            import hashlib

            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size)
            with server.guard:
                server.digests.append(hashlib.sha256(body).hexdigest().upper())
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        super().do_POST()


class DropFirstProvider(SyntheticProvider):
    def __init__(self) -> None:
        ThreadingHTTPServer.__init__(self, ("127.0.0.1", 0), DropFirstHandler)
        self.digests: list[str] = []
        self.guard = threading.Lock()


def host(case: Path, failpoint: str) -> int:
    data = json.loads(case.read_text(encoding="utf-8"))
    config = AssignedConfig(
        space=Path(data["space"]),
        workspace=Path(data["workspace"]),
        pi_cli=Path(data["pi_cli"]),
        pi_runtime=Path(data["pi_runtime"]),
        node="node",
        provider_profile="local-completions",
        provider_base_url=data["provider_url"],
        provider_id="zara-synthetic",
        model_id="synthetic-model",
        context_window=4096,
        max_tokens=512,
        reserve_units=1000,
        limit_units=10000,
        offline=True,
    )
    owner = authorize_local(
        config.space, actor=data.get("actor", "owner"), source_ref="synthetic-host"
    )
    if failpoint == "before_claim":
        import zaratustra.pi_adapter.assigned as assigned

        def crash_before_claim(*_args: object, **_kwargs: object) -> str:
            os._exit(90)

        assigned._execute_under_lock = crash_before_claim
    elif failpoint == "after_claim":
        import zaratustra.pi_adapter.assigned as assigned

        def crash_after_claim(*_args: object, **_kwargs: object) -> object:
            os._exit(91)

        vars(assigned)["BridgeServer"] = crash_after_claim
    try:
        print(run_assigned(config, owner, UUID(data["attempt_id"])), flush=True)
    except BaseException as error:
        print(f"{type(error).__name__}: {error}", flush=True)
        return 1
    return 0


def make_case(
    output: Path,
    name: str,
    provider_url: str,
    pi_cli: Path,
    pi_runtime: Path,
    *,
    actor: str = "owner",
    version: str = EXECUTOR_VERSION,
) -> tuple[Path, dict[str, str]]:
    case_dir = output / name
    case_dir.mkdir()
    root, workspace, space_id, _, work_id, resource_id = ready(case_dir)
    owner = authorize_local(root, actor="owner", source_ref="synthetic-parent")
    apply_operation(
        root,
        ReviseResourceRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            resource_id=resource_id,
            work_id=work_id,
            expected_revision=1,
            state=ResourceState(label="Fictional directory", root=workspace, limit_units=10000),
        ),
        owner,
    )
    grant_id = uuid4() if actor != "owner" else None
    if grant_id is not None:
        apply_operation(
            root,
            CreateGrantRequest(
                operation_id=uuid4(),
                space_id=space_id,
                actor="owner",
                grant_id=grant_id,
                state=GrantState(grantee=actor, actions=tuple(ALL_ACTIONS)),
            ),
            owner,
        )
    attempt_id, session_id = uuid4(), uuid4()
    apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            expected_work_revision=1,
            resource_id=resource_id,
            expected_resource_revision=2,
            session_id=session_id,
            executor_version=version,
        ),
        owner,
    )
    data = dict(
        space=str(root),
        workspace=str(workspace),
        space_id=str(space_id),
        work_id=str(work_id),
        attempt_id=str(attempt_id),
        session_id=str(session_id),
        pi_cli=str(pi_cli),
        pi_runtime=str(pi_runtime),
        provider_url=provider_url,
        actor=actor,
        grant_id=str(grant_id) if grant_id else "",
    )
    case_file = case_dir / "case.json"
    case_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return case_file, data


def start(case: Path, failpoint: str = "none") -> subprocess.Popen[bytes]:
    log = case.parent / f"host-{failpoint}-{uuid4().hex[:8]}.log"
    stream = log.open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tools.probe_stage5_faults",
            "--host",
            str(case),
            "--failpoint",
            failpoint,
        ],
        stdout=stream,
        stderr=subprocess.STDOUT,
    )
    stream.close()
    return process


def exited(process: subprocess.Popen[bytes], timeout: float = 35) -> int:
    return process.wait(timeout=timeout)


def wait_for_question(
    data: dict[str, str], provider: SyntheticProvider, timeout: float = 35
) -> object:
    owner = authorize_local(Path(data["space"]), actor="owner", source_ref="synthetic-parent")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = read_execution(Path(data["space"]), UUID(data["work_id"]), owner)
        open_waits = [item for item in snapshot.waits if item.status == "open"]
        if open_waits and len(provider.digests) == 1:
            return open_waits[0]
        time.sleep(0.1)
    raise TimeoutError("Ordinary Pi RPC did not save one question")


def answer(
    data: dict[str, str], wait_id: UUID, *, actor: str = "owner", deliver: bool = True
) -> bool:
    root = Path(data["space"])
    responder = authorize_local(root, actor=actor, source_ref="synthetic-parent")
    callback = (lambda outbox_id: deliver_outbox(root, responder, outbox_id)) if deliver else None
    bridge = Bridge(root, responder, Path(data["workspace"]), 10000, deliver_answer=callback)
    session = uuid4()
    bridge.connect(session)
    bridge.select(
        session,
        read_execution(root, UUID(data["work_id"]), responder).activity.activity_id,
        UUID(data["work_id"]),
    )
    first = bridge.answer_wait(session, wait_id, "Code A")
    second = bridge.answer_wait(session, wait_id, "Code A")
    return first == second


def snapshot(data: dict[str, str]) -> ExecutionSnapshot:
    root = Path(data["space"])
    owner = authorize_local(root, actor="owner", source_ref="synthetic-parent")
    return read_execution(root, UUID(data["work_id"]), owner)


def competing_resource(data: dict[str, str]) -> str:
    root = Path(data["space"])
    owner = authorize_local(root, actor="owner", source_ref="synthetic-parent")
    current = snapshot(data)
    work_id, resource_id = uuid4(), uuid4()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=current.activity.activity_id,
                goal="Competing fictional Work",
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            work_id=work_id,
            resource_id=resource_id,
            state=ResourceState(
                label="Same exclusive directory", root=Path(data["workspace"]), limit_units=10000
            ),
        ),
        owner,
    )
    try:
        apply_operation(
            root,
            AssignAttemptRequest(
                operation_id=uuid4(),
                space_id=owner.space_id,
                actor="owner",
                attempt_id=uuid4(),
                work_id=work_id,
                expected_work_revision=1,
                resource_id=resource_id,
                expected_resource_revision=1,
                session_id=uuid4(),
                executor_version=EXECUTOR_VERSION,
            ),
            owner,
        )
    except FoundationError as error:
        return error.code
    raise AssertionError("Conflicting resource was assigned")


def independent_resource(data: dict[str, str]) -> str:
    root = Path(data["space"])
    owner = authorize_local(root, actor="owner", source_ref="synthetic-parent")
    current = snapshot(data)
    work_id, resource_id, attempt_id = uuid4(), uuid4(), uuid4()
    other_workspace = root.parent / f"independent-{work_id}"
    other_workspace.mkdir()
    apply_operation(
        root,
        CreateWorkRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            work_id=work_id,
            state=WorkState(
                activity_id=current.activity.activity_id,
                goal="Independent fictional Work",
                expected_outputs=(OutputContract(slot="summary", media_type="text/plain"),),
            ),
        ),
        owner,
    )
    apply_operation(
        root,
        CreateResourceRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            work_id=work_id,
            resource_id=resource_id,
            state=ResourceState(
                label="Different fictional directory", root=other_workspace, limit_units=10000
            ),
        ),
        owner,
    )
    receipt = apply_operation(
        root,
        AssignAttemptRequest(
            operation_id=uuid4(),
            space_id=owner.space_id,
            actor="owner",
            attempt_id=attempt_id,
            work_id=work_id,
            expected_work_revision=1,
            resource_id=resource_id,
            expected_resource_revision=1,
            session_id=uuid4(),
            executor_version=EXECUTOR_VERSION,
        ),
        owner,
    )
    return str(receipt.result["attempt_id"])


def run(output: Path, pi_cli: Path, pi_runtime: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    provider = SyntheticProvider()
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    reports: dict[str, object] = {}
    try:
        base = f"http://127.0.0.1:{provider.server_port}/v1"
        case, data = make_case(output, "checkpoint", base, pi_cli, pi_runtime)
        first = start(case, "before_claim")
        assert exited(first) == 90
        assert not provider.digests
        second = start(case)
        question = wait_for_question(data, provider)
        assert answer(data, question.wait_id)  # type: ignore[attr-defined]
        assert exited(second, 50) == 0
        state = snapshot(data)
        assert len(provider.digests) == 2 and state.work.state.status == "proposed"
        reports["commit_checkpoint_restart"] = dict(
            first_exit=90,
            provider_calls=2,
            invocations=[x.status for x in state.invocations],
            assignment=state.assignments[0].status,
            work=state.work.state.status,
            duplicate_answer_one_receipt=True,
        )
        provider.digests.clear()
        case, data = make_case(output, "claim", base, pi_cli, pi_runtime)
        first = start(case, "after_claim")
        assert exited(first) == 91
        owner = authorize_local(Path(data["space"]), actor="owner", source_ref="synthetic-parent")
        claim = read_receipt(
            Path(data["space"]), uuid5(UUID(data["attempt_id"]), "rpc-launch-claim"), owner
        )
        second = start(case)
        assert exited(second) != 0
        state = snapshot(data)
        assert state.assignments[0].status == "unknown" and not provider.digests
        assert competing_resource(data) == "resource_busy"
        other_attempt = independent_resource(data)
        reports["claim_before_pi_crash"] = dict(
            first_exit=91,
            claim_receipt=str(claim.operation_id),
            provider_calls=0,
            assignment=state.assignments[0].status,
            held_units=state.held_units,
            conflicting_assignment="resource_busy",
            independent_attempt=other_attempt,
        )
        provider.digests.clear()
        case, data = make_case(output, "live", base, pi_cli, pi_runtime)
        first = start(case)
        question = wait_for_question(data, provider)
        first.kill()
        assert exited(first) != 0
        assert answer(data, question.wait_id)  # type: ignore[attr-defined]
        second = start(case)
        assert exited(second) != 0
        state = snapshot(data)
        assert state.assignments[0].status == "unknown" and len(provider.digests) == 1
        assert state.waits[0].status == "answered" and state.waits[0].remainder
        owner = authorize_local(Path(data["space"]), actor="owner", source_ref="synthetic-parent")
        try:
            apply_operation(
                Path(data["space"]),
                PublishAttemptOutputRequest(
                    operation_id=uuid4(),
                    space_id=owner.space_id,
                    actor="owner",
                    attempt_id=UUID(data["attempt_id"]),
                    work_id=UUID(data["work_id"]),
                    session_id=UUID(data["session_id"]),
                    slot="summary",
                    media_type="text/plain",
                    content=b"late fictional result",
                ),
                owner,
            )
        except FoundationError as error:
            late_result = error.code
        else:
            raise AssertionError("Late result changed current Work")
        assert late_result == "attempt_not_ready"
        assert competing_resource(data) == "resource_busy"
        reports["live_process_restart_and_late_result"] = dict(
            first_exit="killed",
            provider_calls=1,
            assignment=state.assignments[0].status,
            wait=state.waits[0].status,
            remainder=state.waits[0].remainder,
            late_result=late_result,
            conflicting_assignment="resource_busy",
        )
        provider.digests.clear()
        case, data = make_case(output, "live-overlap", base, pi_cli, pi_runtime)
        overlap_first = start(case)
        overlap_second: subprocess.Popen[bytes] | None = None
        try:
            question = wait_for_question(data, provider)
            overlap_second = start(case)
            time.sleep(3)
            state = snapshot(data)
            assert len(provider.digests) == 1
            if state.assignments[0].status == "unknown":
                assert competing_resource(data) == "resource_busy"
                overlap_outcome = "unknown_fenced"
            else:
                assert state.assignments[0].status in ("waiting", "ready")
                assert answer(data, question.wait_id)  # type: ignore[attr-defined]
                assert exited(overlap_first, 50) == 0
                assert exited(overlap_second, 50) == 0
                overlap_outcome = "one_continuation"
            reports["live_host_overlap"] = dict(
                provider_calls=len(provider.digests),
                assignment=snapshot(data).assignments[0].status,
                outcome=overlap_outcome,
            )
        finally:
            for process in (overlap_first, overlap_second):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
        provider.digests.clear()
        before_version = len(provider.digests)
        case, data = make_case(
            output, "version", base, pi_cli, pi_runtime, version="incompatible-executor-v2"
        )
        assert exited(start(case)) != 0
        state = snapshot(data)
        assert state.assignments[0].status == "assigned"
        assert len(provider.digests) == before_version
        reports["incompatible_version"] = dict(
            assignment=state.assignments[0].status,
            provider_calls=len(provider.digests) - before_version,
            blocked="executor_version",
        )
        provider.digests.clear()
        before_revoke = len(provider.digests)
        case, data = make_case(output, "revoked", base, pi_cli, pi_runtime, actor="runner")
        runner = start(case)
        question = wait_for_question(data, provider)
        owner = authorize_local(Path(data["space"]), actor="owner", source_ref="synthetic-parent")
        assert answer(data, question.wait_id, actor="runner", deliver=False)  # type: ignore[attr-defined]
        apply_operation(
            Path(data["space"]),
            RevokeGrantRequest(
                operation_id=uuid4(),
                space_id=owner.space_id,
                actor="owner",
                grant_id=UUID(data["grant_id"]),
                expected_revision=1,
            ),
            owner,
        )
        deliver_outbox(Path(data["space"]), owner)
        assert exited(runner, 50) != 0
        state = snapshot(data)
        assert len(provider.digests) == before_revoke + 1
        assert not state.outputs and state.work.state.status == "proposed"
        assert competing_resource(data) == "resource_busy"
        reports["revoked_before_resume"] = dict(
            provider_calls=len(provider.digests) - before_revoke,
            wait=state.waits[0].status,
            assignment=state.assignments[0].status,
            outputs=len(state.outputs),
            conflicting_assignment="resource_busy",
        )
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)
    drop = DropFirstProvider()
    drop_thread = threading.Thread(target=drop.serve_forever, daemon=True)
    drop_thread.start()
    try:
        case, data = make_case(
            output, "lost-http", f"http://127.0.0.1:{drop.server_port}/v1", pi_cli, pi_runtime
        )
        assert exited(start(case), 50) != 0
        state = snapshot(data)
        assert len(drop.digests) == 1 and state.held_units == 1000
        assert state.invocations[0].status == "unknown" and not state.outputs
        assert state.assignments[0].status == "unknown"
        assert competing_resource(data) == "resource_busy"
        assert exited(start(case), 35) != 0
        assert len(drop.digests) == 1
        reports["lost_http_response"] = dict(
            provider_calls=1,
            invocation=state.invocations[0].status,
            held_units=state.held_units,
            work=state.work.state.status,
            assignment=state.assignments[0].status,
            conflicting_assignment="resource_busy",
            restart_provider_calls=len(drop.digests),
        )
    finally:
        drop.shutdown()
        drop.server_close()
        drop_thread.join(timeout=5)
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pi-cli", type=Path)
    parser.add_argument("--pi-runtime", type=Path)
    parser.add_argument("--host", type=Path)
    parser.add_argument("--failpoint", default="none")
    args = parser.parse_args()
    if args.host is not None:
        return host(args.host, args.failpoint)
    if args.output is None or args.pi_cli is None or args.pi_runtime is None:
        parser.error("Supply output, Pi CLI and Pi runtime")
    report = run(args.output.resolve(), args.pi_cli.resolve(), args.pi_runtime.resolve())
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
