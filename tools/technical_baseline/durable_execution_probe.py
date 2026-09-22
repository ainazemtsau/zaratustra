# mypy: disable-error-code="import-not-found,untyped-decorator,no-any-return"
"""Probe DBOS/SQLite durable execution with disposable subprocesses."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .common import (
    CheckConclusion,
    CheckResult,
    GateReport,
    GateStatus,
    append_jsonl,
    gate_status,
    new_scratch_output,
    read_jsonl,
    sha256_file,
)

CRASH = 91
APP_NAME = "zaratustra-durable-execution-probe"
SENTINEL = "SYNTHETIC-DELETABLE-PAYLOAD-7f93"
EXPECTED_CHECKS = frozenset(
    {
        "executor-readiness",
        "crash-before-domain-commit",
        "domain-commit-checkpoint-lost",
        "outbox-enqueue-retry",
        "durable-wait-duplicate-answer",
        "stale-executor-fencing",
        "current-grant-after-replay",
        "external-effect-response-lost",
        "interrupted-call-reserve",
        "managed-technical-payload-deletion",
        "workflow-code-version-routing",
    }
)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _init_core(base: Path) -> None:
    with _connect(base / "core.sqlite3") as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS receipts(
                operation_id TEXT PRIMARY KEY,
                result TEXT NOT NULL,
                applications INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox(
                event_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                deliveries INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS waits(
                wait_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                answer TEXT,
                continuations INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS attempts(
                attempt_id TEXT PRIMARY KEY,
                current_epoch INTEGER NOT NULL,
                accepted_writes INTEGER NOT NULL DEFAULT 0,
                stale_material INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS grants(
                grant_id TEXT PRIMARY KEY,
                active INTEGER NOT NULL,
                revision INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS effects(
                effect_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                calls INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS resources(
                resource_id TEXT PRIMARY KEY,
                reserved INTEGER NOT NULL,
                consumed INTEGER NOT NULL,
                unknown INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS managed_payloads(
                payload_id TEXT PRIMARY KEY,
                body TEXT NOT NULL
            );
            """
        )


def _query_one(base: Path, statement: str, values: tuple[object, ...] = ()) -> Any:
    with _connect(base / "core.sqlite3") as connection:
        row = connection.execute(statement, values).fetchone()
    return row


def _write(base: Path, callback: Callable[[sqlite3.Connection], Any]) -> Any:
    with _connect(base / "core.sqlite3") as connection:
        connection.execute("BEGIN IMMEDIATE")
        result = callback(connection)
        connection.commit()
        return result


def _crash_once(base: Path, name: str) -> bool:
    marker = base / f"{name}.crashed"
    if marker.exists():
        return False
    marker.write_text("crashed\n", encoding="utf-8", newline="\n")
    return True


def _configure_dbos(base: Path, version: str) -> Any:
    from dbos import DBOS

    executor = (base / "executor.sqlite3").resolve().as_posix()
    DBOS(
        config={
            "name": APP_NAME,
            "system_database_url": f"sqlite:///{executor}",
            "application_version": version,
        }
    )
    return DBOS


def _register_workflows(base: Path, version: str) -> dict[str, Any]:
    from dbos import DBOS

    @DBOS.step(name="fault-domain-operation", retries_allowed=False)
    def fault_domain_operation(case: str) -> str:
        if case == "precommit" and _crash_once(base, "precommit"):
            os._exit(CRASH)

        def operation(connection: sqlite3.Connection) -> tuple[str, bool]:
            existing = connection.execute(
                "SELECT result FROM receipts WHERE operation_id=?", (case,)
            ).fetchone()
            if existing is not None:
                return str(existing[0]), False
            connection.execute(
                "INSERT INTO receipts(operation_id,result,applications) VALUES(?,?,1)",
                (case, f"result-{case}"),
            )
            return f"result-{case}", True

        result, inserted = _write(base, operation)
        if case == "postcommit" and inserted and _crash_once(base, "postcommit"):
            os._exit(CRASH)
        return result

    @DBOS.workflow(name="fault-workflow")
    def fault_workflow(case: str) -> str:
        return fault_domain_operation(case)

    @DBOS.step(name="deliver-outbox", retries_allowed=False)
    def deliver_outbox(event_id: str) -> int:
        def operation(connection: sqlite3.Connection) -> int:
            connection.execute(
                "UPDATE outbox SET state='delivered', deliveries=deliveries+1 "
                "WHERE event_id=? AND state='pending'",
                (event_id,),
            )
            row = connection.execute(
                "SELECT deliveries FROM outbox WHERE event_id=?", (event_id,)
            ).fetchone()
            assert row is not None
            return int(row[0])

        return int(_write(base, operation))

    @DBOS.workflow(name="delivery-workflow")
    def delivery_workflow(event_id: str) -> int:
        return deliver_outbox(event_id)

    @DBOS.step(name="register-wait", retries_allowed=False)
    def register_wait(wait_id: str) -> None:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                "INSERT OR IGNORE INTO waits(wait_id,state) VALUES(?,'pending')", (wait_id,)
            )

        _write(base, operation)

    @DBOS.step(name="continue-wait", retries_allowed=False)
    def continue_wait(wait_id: str, answer: str) -> str:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                "UPDATE waits SET state='answered', answer=?, continuations=continuations+1 "
                "WHERE wait_id=? AND state='pending'",
                (answer, wait_id),
            )

        _write(base, operation)
        return answer

    @DBOS.workflow(name="wait-workflow")
    def wait_workflow(wait_id: str) -> str:
        register_wait(wait_id)
        answer = DBOS.recv("answer", timeout_seconds=30)
        return continue_wait(wait_id, str(answer))

    @DBOS.step(name="write-attempt", retries_allowed=False)
    def write_attempt(attempt_id: str, epoch: int) -> str:
        def operation(connection: sqlite3.Connection) -> str:
            row = connection.execute(
                "SELECT current_epoch FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            assert row is not None
            if int(row[0]) != epoch:
                connection.execute(
                    "UPDATE attempts SET stale_material=stale_material+1 WHERE attempt_id=?",
                    (attempt_id,),
                )
                return "fenced"
            connection.execute(
                "UPDATE attempts SET accepted_writes=accepted_writes+1 WHERE attempt_id=?",
                (attempt_id,),
            )
            return "accepted"

        return str(_write(base, operation))

    @DBOS.workflow(name="attempt-workflow")
    def attempt_workflow(attempt_id: str, epoch: int) -> str:
        return write_attempt(attempt_id, epoch)

    @DBOS.step(name="read-grant", retries_allowed=False)
    def read_grant(grant_id: str) -> bool:
        row = _query_one(base, "SELECT active FROM grants WHERE grant_id=?", (grant_id,))
        return bool(row and row[0])

    @DBOS.step(name="record-grant-effect", retries_allowed=False)
    def record_grant_effect(effect_id: str) -> None:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                "INSERT INTO effects(effect_id,state,calls) VALUES(?,'performed',1) "
                "ON CONFLICT(effect_id) DO UPDATE SET calls=calls+1",
                (effect_id,),
            )

        _write(base, operation)

    @DBOS.workflow(name="grant-workflow")
    def grant_workflow(grant_id: str, wait_id: str) -> str:
        initial = read_grant(grant_id)
        register_wait(wait_id)
        DBOS.recv("wake", timeout_seconds=30)
        current = read_grant(grant_id)
        if initial and current:
            record_grant_effect("grant-effect")
            return "performed"
        return "denied-current"

    @DBOS.step(name="idempotent-external-effect", retries_allowed=False)
    def idempotent_external_effect(effect_id: str) -> str:
        def operation(connection: sqlite3.Connection) -> tuple[str, bool]:
            row = connection.execute(
                "SELECT state FROM effects WHERE effect_id=?", (effect_id,)
            ).fetchone()
            if row is not None:
                return str(row[0]), False
            connection.execute(
                "INSERT INTO effects(effect_id,state,calls) VALUES(?,'confirmed',1)",
                (effect_id,),
            )
            return "confirmed", True

        result, inserted = _write(base, operation)
        if inserted and _crash_once(base, "external-response"):
            os._exit(CRASH)
        return result

    @DBOS.workflow(name="external-workflow")
    def external_workflow(effect_id: str) -> str:
        return idempotent_external_effect(effect_id)

    @DBOS.step(name="unknown-external-effect", retries_allowed=False)
    def unknown_external_effect(effect_id: str, resource_id: str) -> str:
        def begin(connection: sqlite3.Connection) -> bool:
            row = connection.execute(
                "SELECT state FROM effects WHERE effect_id=?", (effect_id,)
            ).fetchone()
            if row is not None:
                return False
            connection.execute(
                "INSERT INTO effects(effect_id,state,calls) VALUES(?,'calling',0)",
                (effect_id,),
            )
            connection.execute(
                "INSERT INTO resources(resource_id,reserved,consumed,unknown) VALUES(?,1,0,0)",
                (resource_id,),
            )
            return True

        should_call = bool(_write(base, begin))
        if not should_call:
            return "unknown-no-retry"

        def uncertain(connection: sqlite3.Connection) -> None:
            connection.execute(
                "UPDATE effects SET state='unknown', calls=1 WHERE effect_id=?", (effect_id,)
            )
            connection.execute("UPDATE resources SET unknown=1 WHERE resource_id=?", (resource_id,))

        _write(base, uncertain)
        if _crash_once(base, "unknown-response"):
            os._exit(CRASH)
        return "unknown-no-retry"

    @DBOS.workflow(name="unknown-workflow")
    def unknown_workflow(effect_id: str, resource_id: str) -> str:
        return unknown_external_effect(effect_id, resource_id)

    @DBOS.step(name="store-payload", retries_allowed=False)
    def store_payload(payload_id: str, body: str) -> str:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                "INSERT INTO managed_payloads(payload_id,body) VALUES(?,?)", (payload_id, body)
            )

        _write(base, operation)
        return payload_id

    @DBOS.workflow(name="payload-workflow")
    def payload_workflow(payload_id: str, body: str) -> str:
        return store_payload(payload_id, body)

    return {
        "fault": fault_workflow,
        "delivery": delivery_workflow,
        "wait": wait_workflow,
        "attempt": attempt_workflow,
        "grant": grant_workflow,
        "external": external_workflow,
        "unknown": unknown_workflow,
        "payload": payload_workflow,
        "version": version,
    }


def _launch(base: Path, version: str) -> tuple[Any, dict[str, Any]]:
    dbos = _configure_dbos(base, version)
    workflows = _register_workflows(base, version)
    dbos.launch()
    return dbos, workflows


def _start(dbos: Any, workflow_id: str, workflow: Any, *args: object) -> Any:
    from dbos import SetWorkflowID

    with SetWorkflowID(workflow_id):
        return dbos.start_workflow(workflow, *args)


def _child(args: argparse.Namespace) -> int:
    base = args.base.resolve()
    _init_core(base)
    dbos, workflows = _launch(base, args.version)
    try:
        if args.action == "ready":
            with sqlite3.connect(base / "executor.sqlite3") as connection:
                migration = connection.execute(
                    "SELECT MAX(version) FROM dbos_migrations"
                ).fetchone()
                table_count = connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'dbos_%'"
                ).fetchone()
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
            print(
                json.dumps(
                    {
                        "migrationVersion": migration[0] if migration else None,
                        "dbosTableCount": table_count[0] if table_count else 0,
                        "journalMode": journal_mode[0] if journal_mode else None,
                    }
                ),
                flush=True,
            )
        elif args.action == "fault":
            handle = _start(dbos, args.workflow_id, workflows["fault"], args.case)
            print(json.dumps({"result": handle.get_result()}), flush=True)
        elif args.action == "dispatch":
            dbos.register_queue("continuations", worker_concurrency=2, global_concurrency=2)
            from dbos import SetWorkflowID

            with SetWorkflowID(args.workflow_id):
                first = dbos.enqueue_workflow("continuations", workflows["delivery"], args.event_id)
            with SetWorkflowID(args.workflow_id):
                second = dbos.enqueue_workflow(
                    "continuations", workflows["delivery"], args.event_id
                )
            print(
                json.dumps({"first": first.get_result(), "second": second.get_result()}),
                flush=True,
            )
        elif args.action in {"start-wait", "start-grant", "start-version"}:
            key = "grant" if args.action == "start-grant" else "wait"
            values: tuple[object, ...]
            if key == "grant":
                values = ("grant-1", args.wait_id)
            else:
                values = (args.wait_id,)
            _start(dbos, args.workflow_id, workflows[key], *values)
            print(json.dumps({"started": args.workflow_id}), flush=True)
            while True:
                time.sleep(1)
        elif args.action in {"recover-wait", "recover-grant"}:
            topic = "wake" if args.action == "recover-grant" else "answer"
            dbos.send(
                args.workflow_id,
                args.answer,
                topic=topic,
                idempotency_key=f"answer:{args.workflow_id}",
            )
            dbos.send(
                args.workflow_id,
                args.answer,
                topic=topic,
                idempotency_key=f"answer:{args.workflow_id}",
            )
            result = dbos.retrieve_workflow(args.workflow_id).get_result()
            print(json.dumps({"result": result}), flush=True)
        elif args.action == "attempt":
            handle = _start(
                dbos,
                args.workflow_id,
                workflows["attempt"],
                args.attempt_id,
                args.epoch,
            )
            print(json.dumps({"result": handle.get_result()}), flush=True)
        elif args.action == "external":
            handle = _start(dbos, args.workflow_id, workflows["external"], args.effect_id)
            print(json.dumps({"result": handle.get_result()}), flush=True)
        elif args.action == "unknown":
            handle = _start(
                dbos,
                args.workflow_id,
                workflows["unknown"],
                args.effect_id,
                args.resource_id,
            )
            print(json.dumps({"result": handle.get_result()}), flush=True)
        elif args.action == "inspect-version":
            status = dbos.get_workflow_status(args.workflow_id)
            print(
                json.dumps(
                    {
                        "status": status.status if status else None,
                        "applicationVersion": status.app_version if status else None,
                        "runningVersion": dbos.application_version,
                    }
                ),
                flush=True,
            )
        elif args.action == "payload-delete":
            handle = _start(
                dbos,
                args.workflow_id,
                workflows["payload"],
                "payload-1",
                SENTINEL,
            )
            handle.get_result()
            dbos.delete_workflow(args.workflow_id)
            _write(
                base,
                lambda connection: connection.execute(
                    "DELETE FROM managed_payloads WHERE payload_id='payload-1'"
                ),
            )
            print(json.dumps({"deleted": True}), flush=True)
        else:
            raise ValueError(f"unknown child action: {args.action}")
        return 0
    finally:
        dbos.destroy(destroy_registry=True, workflow_completion_timeout_sec=1)


def _child_command(base: Path, action: str, **values: object) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "tools.technical_baseline.durable_execution_probe",
        "--child",
        "--base",
        str(base),
        "--action",
        action,
    ]
    for name, value in values.items():
        command.extend((f"--{name.replace('_', '-')}", str(value)))
    return command


def _run_child(
    base: Path,
    action: str,
    *,
    timeout: float = 60,
    **values: object,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        _child_command(base, action, **values),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    (base / f"{action}-{time.time_ns()}.log").write_text(
        f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _wait_for_row(base: Path, statement: str, timeout: float = 45) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = _query_one(base, statement)
        if row is not None:
            return row
        time.sleep(0.1)
    raise TimeoutError(f"row not observed: {statement}")


def _start_pending(base: Path, action: str, **values: object) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        _child_command(base, action, **values),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return process


def _kill_pending(base: Path, process: subprocess.Popen[str], label: str) -> None:
    if process.poll() is None:
        process.kill()
    stdout, stderr = process.communicate(timeout=10)
    (base / f"{label}.log").write_text(
        f"exit={process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}",
        encoding="utf-8",
        newline="\n",
    )


def _observe_then_interrupt(
    base: Path,
    process: subprocess.Popen[str],
    statement: str,
    label: str,
) -> Any:
    try:
        return _wait_for_row(base, statement)
    finally:
        _kill_pending(base, process, label)


def _backup_database(source: Path, destination: Path) -> None:
    with sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True) as source_db:
        with sqlite3.connect(destination) as destination_db:
            source_db.backup(destination_db)


def _scenario_dir(output: Path, name: str, executor_template: Path) -> Path:
    path = output / name
    path.mkdir()
    _backup_database(executor_template, path / "executor.sqlite3")
    _init_core(path)
    return path


def _record_check(output: Path, checks: list[CheckResult], check: CheckResult) -> None:
    checks.append(check)
    append_jsonl(
        output / "scenario-results.jsonl",
        {
            "name": check.name,
            "passed": check.passed,
            "conclusion": check.conclusion,
            "observation": check.observation,
            "evidence": check.evidence,
        },
    )


def _load_recorded_checks(output: Path) -> list[CheckResult]:
    return [
        CheckResult(
            name=str(row["name"]),
            passed=bool(row["passed"]),
            observation=str(row["observation"]),
            evidence=dict(row.get("evidence", {})),
            conclusion=CheckConclusion(str(row["conclusion"])),
        )
        for row in read_jsonl(output / "scenario-results.jsonl")
    ]


def _json_stdout(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    return json.loads(lines[-1]) if lines else {}


def _fencing_contract(
    stale_result: dict[str, Any],
    current_result: dict[str, Any],
    attempt_row: object,
) -> bool:
    return (
        stale_result.get("result") == "fenced"
        and current_result.get("result") == "accepted"
        and attempt_row == (1, 1)
    )


def _vacuum(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        connection.execute("PRAGMA journal_mode=DELETE").fetchone()
        connection.execute("PRAGMA secure_delete=ON").fetchone()
        connection.execute("VACUUM")
        connection.execute("PRAGMA journal_mode=WAL").fetchone()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        connection.close()


def _payload_remnants(files: list[Path], payload: bytes = SENTINEL.encode()) -> list[str]:
    return [path.name for path in files if payload in path.read_bytes()]


def run_probe(output: Path) -> GateReport:
    if sqlite3.sqlite_version_info < (3, 51, 3):
        raise RuntimeError(f"SQLite {sqlite3.sqlite_version} is below the fixed WAL baseline")
    if importlib.metadata.version("dbos") != "3.0.0":
        raise RuntimeError("the durable execution probe requires exact DBOS 3.0.0")
    output = new_scratch_output(output)
    checks: list[CheckResult] = []
    readiness = output / "00-readiness"
    readiness.mkdir()
    _init_core(readiness)
    ready = _run_child(readiness, "ready", timeout=120, version="v1")
    ready_view = _json_stdout(ready)
    readiness_check = CheckResult(
        "executor-readiness",
        ready.returncode == 0
        and int(ready_view.get("migrationVersion", 0)) >= 114
        and int(ready_view.get("dbosTableCount", 0)) > 0,
        "DBOS launched to completion and exposed its completed initial SQLite migrations.",
        ready_view,
        conclusion=(
            CheckConclusion.PASSED
            if ready.returncode == 0
            and int(ready_view.get("migrationVersion", 0)) >= 114
            and int(ready_view.get("dbosTableCount", 0)) > 0
            else CheckConclusion.SETUP_FAILURE
        ),
    )
    _record_check(output, checks, readiness_check)
    if not readiness_check.passed:
        raise RuntimeError(f"DBOS readiness failed: {ready_view!r}; stderr={ready.stderr!r}")
    executor_template = readiness / "executor.sqlite3"

    pre = _scenario_dir(output, "01-precommit", executor_template)
    first = _run_child(pre, "fault", version="v1", workflow_id="wf-pre", case="precommit")
    before = _query_one(pre, "SELECT COUNT(*) FROM receipts")[0]
    second = _run_child(pre, "fault", version="v1", workflow_id="wf-pre", case="precommit")
    row = _query_one(pre, "SELECT applications FROM receipts WHERE operation_id='precommit'")
    _record_check(
        output,
        checks,
        CheckResult(
            "crash-before-domain-commit",
            first.returncode == CRASH and before == 0 and second.returncode == 0 and row == (1,),
            "The crash exposed no partial receipt; DBOS recovered the pending workflow once.",
        ),
    )

    post = _scenario_dir(output, "02-postcommit", executor_template)
    first = _run_child(post, "fault", version="v1", workflow_id="wf-post", case="postcommit")
    committed = _query_one(
        post, "SELECT result,applications FROM receipts WHERE operation_id='postcommit'"
    )
    second = _run_child(post, "fault", version="v1", workflow_id="wf-post", case="postcommit")
    after = _query_one(
        post, "SELECT result,applications FROM receipts WHERE operation_id='postcommit'"
    )
    _record_check(
        output,
        checks,
        CheckResult(
            "domain-commit-checkpoint-lost",
            first.returncode == CRASH
            and committed == ("result-postcommit", 1)
            and second.returncode == 0
            and after == committed,
            "DBOS replayed the lost step; the domain receipt prevented a second mutation.",
        ),
    )

    outbox = _scenario_dir(output, "03-outbox", executor_template)
    _write(
        outbox,
        lambda connection: connection.execute(
            "INSERT INTO outbox(event_id,state) VALUES('event-1','pending')"
        ),
    )
    pending = _query_one(outbox, "SELECT state,deliveries FROM outbox WHERE event_id='event-1'")
    dispatched = _run_child(
        outbox,
        "dispatch",
        version="v1",
        workflow_id="delivery-1",
        event_id="event-1",
    )
    delivered = _query_one(outbox, "SELECT state,deliveries FROM outbox WHERE event_id='event-1'")
    _record_check(
        output,
        checks,
        CheckResult(
            "outbox-enqueue-retry",
            pending == ("pending", 0)
            and dispatched.returncode == 0
            and _json_stdout(dispatched) == {"first": 1, "second": 1}
            and delivered == ("delivered", 1),
            "A stable DBOS workflow ID deduplicated repeated enqueue after an outbox gap.",
        ),
    )

    wait = _scenario_dir(output, "04-wait", executor_template)
    process = _start_pending(
        wait,
        "start-wait",
        version="v1",
        workflow_id="wait-workflow-1",
        wait_id="wait-1",
    )
    _observe_then_interrupt(
        wait,
        process,
        "SELECT state FROM waits WHERE wait_id='wait-1'",
        "interrupted-wait",
    )
    recovered = _run_child(
        wait,
        "recover-wait",
        version="v1",
        workflow_id="wait-workflow-1",
        answer="synthetic-answer",
    )
    wait_row = _query_one(
        wait, "SELECT state,answer,continuations FROM waits WHERE wait_id='wait-1'"
    )
    _record_check(
        output,
        checks,
        CheckResult(
            "durable-wait-duplicate-answer",
            recovered.returncode == 0 and wait_row == ("answered", "synthetic-answer", 1),
            "The DBOS notification survived process replacement and duplicate send continued once.",
        ),
    )

    fencing = _scenario_dir(output, "05-fencing", executor_template)
    _write(
        fencing,
        lambda connection: connection.execute(
            "INSERT INTO attempts(attempt_id,current_epoch) VALUES('attempt-1',2)"
        ),
    )
    stale = _run_child(
        fencing,
        "attempt",
        version="v1",
        workflow_id="attempt-old",
        attempt_id="attempt-1",
        epoch=1,
    )
    current = _run_child(
        fencing,
        "attempt",
        version="v1",
        workflow_id="attempt-current",
        attempt_id="attempt-1",
        epoch=2,
    )
    attempt_row = _query_one(
        fencing,
        "SELECT accepted_writes,stale_material FROM attempts WHERE attempt_id='attempt-1'",
    )
    _record_check(
        output,
        checks,
        CheckResult(
            "stale-executor-fencing",
            _fencing_contract(_json_stdout(stale), _json_stdout(current), attempt_row),
            "DBOS ran independent workflows; the domain epoch fenced the stale writer.",
        ),
    )

    grant = _scenario_dir(output, "06-grant", executor_template)
    _write(
        grant,
        lambda connection: connection.execute(
            "INSERT INTO grants(grant_id,active,revision) VALUES('grant-1',1,1)"
        ),
    )
    process = _start_pending(
        grant,
        "start-grant",
        version="v1",
        workflow_id="grant-workflow-1",
        wait_id="grant-wait-1",
    )
    try:
        _wait_for_row(grant, "SELECT state FROM waits WHERE wait_id='grant-wait-1'")
        _write(
            grant,
            lambda connection: connection.execute(
                "UPDATE grants SET active=0,revision=2 WHERE grant_id='grant-1'"
            ),
        )
    finally:
        _kill_pending(grant, process, "interrupted-grant")
    denied = _run_child(
        grant,
        "recover-grant",
        version="v1",
        workflow_id="grant-workflow-1",
        answer="wake",
    )
    grant_effect = _query_one(grant, "SELECT calls FROM effects WHERE effect_id='grant-effect'")
    _record_check(
        output,
        checks,
        CheckResult(
            "current-grant-after-replay",
            _json_stdout(denied).get("result") == "denied-current" and grant_effect is None,
            "A fresh domain check after the durable wait rejected the revoked Grant.",
        ),
    )

    external = _scenario_dir(output, "07-external-idempotency", executor_template)
    first = _run_child(
        external,
        "external",
        version="v1",
        workflow_id="external-workflow-1",
        effect_id="effect-1",
    )
    second = _run_child(
        external,
        "external",
        version="v1",
        workflow_id="external-workflow-1",
        effect_id="effect-1",
    )
    effect_row = _query_one(external, "SELECT state,calls FROM effects WHERE effect_id='effect-1'")
    _record_check(
        output,
        checks,
        CheckResult(
            "external-effect-response-lost",
            first.returncode == CRASH and second.returncode == 0 and effect_row == ("confirmed", 1),
            "DBOS replayed the step and the external idempotency key established one effect.",
        ),
    )

    unknown = _scenario_dir(output, "08-unknown-resource", executor_template)
    first = _run_child(
        unknown,
        "unknown",
        version="v1",
        workflow_id="unknown-workflow-1",
        effect_id="unknown-effect-1",
        resource_id="resource-1",
    )
    second = _run_child(
        unknown,
        "unknown",
        version="v1",
        workflow_id="unknown-workflow-1",
        effect_id="unknown-effect-1",
        resource_id="resource-1",
    )
    unknown_effect = _query_one(
        unknown, "SELECT state,calls FROM effects WHERE effect_id='unknown-effect-1'"
    )
    resource = _query_one(
        unknown,
        "SELECT reserved,consumed,unknown FROM resources WHERE resource_id='resource-1'",
    )
    _record_check(
        output,
        checks,
        CheckResult(
            "interrupted-call-reserve",
            first.returncode == CRASH
            and _json_stdout(second).get("result") == "unknown-no-retry"
            and unknown_effect == ("unknown", 1)
            and resource == (1, 0, 1),
            "The domain effect ledger blocked blind replay and retained the resource reserve.",
        ),
    )

    deletion = _scenario_dir(output, "09-deletion", executor_template)
    deleted = _run_child(
        deletion,
        "payload-delete",
        version="v1",
        workflow_id="payload-workflow-1",
    )
    _vacuum(deletion / "core.sqlite3")
    _vacuum(deletion / "executor.sqlite3")
    files = list(deletion.glob("*.sqlite3*")) + list(deletion.glob("*.log"))
    first_remnants = _payload_remnants(files)
    time.sleep(0.25)
    second_remnants = _payload_remnants(files)
    _record_check(
        output,
        checks,
        CheckResult(
            "managed-technical-payload-deletion",
            deleted.returncode == 0 and not first_remnants and not second_remnants,
            "DBOS delete plus closed-database checkpoint/VACUUM removed the synthetic payload.",
            {
                "firstClosedScan": first_remnants,
                "secondClosedScan": second_remnants,
            },
        ),
    )

    version = _scenario_dir(output, "10-version", executor_template)
    process = _start_pending(
        version,
        "start-version",
        version="v1",
        workflow_id="version-workflow-1",
        wait_id="version-wait-1",
    )
    _observe_then_interrupt(
        version,
        process,
        "SELECT state FROM waits WHERE wait_id='version-wait-1'",
        "interrupted-version-v1",
    )
    inspected = _run_child(
        version,
        "inspect-version",
        version="v2",
        workflow_id="version-workflow-1",
    )
    view = _json_stdout(inspected)
    finished = _run_child(
        version,
        "recover-wait",
        version="v1",
        workflow_id="version-workflow-1",
        answer="version-answer",
    )
    _record_check(
        output,
        checks,
        CheckResult(
            "workflow-code-version-routing",
            view.get("status") == "PENDING"
            and view.get("applicationVersion") == "v1"
            and view.get("runningVersion") == "v2"
            and finished.returncode == 0,
            "The v2 process left the open v1 workflow visible and unreplayed; v1 completed it.",
            view,
        ),
    )

    status = gate_status(checks, EXPECTED_CHECKS)
    report = GateReport(
        gate="durable-execution",
        status=status,
        checks=tuple(checks),
        versions={
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "dbos": importlib.metadata.version("dbos"),
            "platform": sys.platform,
            "probeSha256": sha256_file(Path(__file__)),
        },
        commands=(
            "fixed-python -m tools.technical_baseline.durable_execution_probe "
            "--output _scratch/<new>",
        ),
        untested=(
            "power loss, filesystem corruption and non-local filesystems",
            "multi-host DBOS operation and DBOS Conductor",
            "production Core schema, real providers and real external effects",
        ),
        notes=(
            "DBOS supplied checkpoints, startup recovery, notifications, durable queue, "
            "stable workflow identity and application-version routing.",
            "The fixture supplied receipts, outbox, current-rights checks, epoch fencing, "
            "resource reservations and unknown-effect policy.",
            "DBOS SQLite used its shipped IMMEDIATE transactions, busy timeout and foreign "
            "keys; it did not enable WAL itself.",
        ),
    )
    report.write(output / "durable-execution.json")
    return report


def run_targeted_failed_probe(output: Path) -> GateReport:
    """Repeat only scenarios 9 and 10 after their diagnosed stand defects."""

    if sqlite3.sqlite_version_info < (3, 51, 3):
        raise RuntimeError(f"SQLite {sqlite3.sqlite_version} is below the fixed WAL baseline")
    if importlib.metadata.version("dbos") != "3.0.0":
        raise RuntimeError("the durable execution probe requires exact DBOS 3.0.0")
    output = new_scratch_output(output)
    checks: list[CheckResult] = []
    readiness = output / "00-readiness"
    readiness.mkdir()
    _init_core(readiness)
    ready = _run_child(readiness, "ready", timeout=120, version="v1")
    ready_view = _json_stdout(ready)
    readiness_ok = (
        ready.returncode == 0
        and int(ready_view.get("migrationVersion", 0)) >= 114
        and int(ready_view.get("dbosTableCount", 0)) > 0
    )
    readiness_check = CheckResult(
        "executor-readiness",
        readiness_ok,
        "DBOS launched to completion before the targeted scenarios.",
        ready_view,
        conclusion=(CheckConclusion.PASSED if readiness_ok else CheckConclusion.SETUP_FAILURE),
    )
    _record_check(output, checks, readiness_check)
    if not readiness_ok:
        raise RuntimeError(f"DBOS readiness failed: {ready_view!r}; stderr={ready.stderr!r}")
    executor_template = readiness / "executor.sqlite3"

    deletion = _scenario_dir(output, "09-deletion", executor_template)
    deleted = _run_child(
        deletion,
        "payload-delete",
        version="v1",
        workflow_id="payload-workflow-1",
    )
    _vacuum(deletion / "core.sqlite3")
    _vacuum(deletion / "executor.sqlite3")
    files = list(deletion.glob("*.sqlite3*")) + list(deletion.glob("*.log"))
    first_remnants = _payload_remnants(files)
    time.sleep(0.25)
    second_remnants = _payload_remnants(files)
    _record_check(
        output,
        checks,
        CheckResult(
            "managed-technical-payload-deletion",
            deleted.returncode == 0 and not first_remnants and not second_remnants,
            "A closed checkpoint, secure VACUUM and two stable byte scans removed the payload.",
            {
                "deleteExitCode": deleted.returncode,
                "firstClosedScan": first_remnants,
                "secondClosedScan": second_remnants,
            },
        ),
    )

    version = _scenario_dir(output, "10-version", executor_template)
    process = _start_pending(
        version,
        "start-version",
        version="v1",
        workflow_id="version-workflow-1",
        wait_id="version-wait-1",
    )
    _observe_then_interrupt(
        version,
        process,
        "SELECT state FROM waits WHERE wait_id='version-wait-1'",
        "interrupted-version-v1",
    )
    inspected = _run_child(
        version,
        "inspect-version",
        version="v2",
        workflow_id="version-workflow-1",
    )
    view = _json_stdout(inspected)
    finished = _run_child(
        version,
        "recover-wait",
        version="v1",
        workflow_id="version-workflow-1",
        answer="version-answer",
    )
    _record_check(
        output,
        checks,
        CheckResult(
            "workflow-code-version-routing",
            inspected.returncode == 0
            and view.get("status") == "PENDING"
            and view.get("applicationVersion") == "v1"
            and view.get("runningVersion") == "v2"
            and finished.returncode == 0,
            "The v2 process inspected but did not replay the open v1 workflow; v1 completed it.",
            {
                **view,
                "inspectExitCode": inspected.returncode,
                "completionExitCode": finished.returncode,
            },
        ),
    )

    expected = frozenset(
        {
            "executor-readiness",
            "managed-technical-payload-deletion",
            "workflow-code-version-routing",
        }
    )
    report = GateReport(
        gate="durable-execution-targeted-9-10",
        status=gate_status(checks, expected),
        checks=tuple(checks),
        versions={
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "dbos": importlib.metadata.version("dbos"),
            "platform": sys.platform,
            "probeSha256": sha256_file(Path(__file__)),
        },
        commands=(
            "fixed-python -m tools.technical_baseline.durable_execution_probe "
            "--targeted-failed --output _scratch/<new>",
        ),
        untested=("scenarios 1-8 were not repeated; use the preserved full-run evidence",),
        notes=(
            "This targeted repeat followed the full run's diagnosed scenario 9 and 10 "
            "stand failures.",
        ),
    )
    report.write(output / "durable-execution-targeted.json")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--base", type=Path)
    parser.add_argument("--action")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--workflow-id", default="workflow-1")
    parser.add_argument("--case", default="precommit")
    parser.add_argument("--event-id", default="event-1")
    parser.add_argument("--wait-id", default="wait-1")
    parser.add_argument("--answer", default="answer")
    parser.add_argument("--attempt-id", default="attempt-1")
    parser.add_argument("--epoch", type=int, default=1)
    parser.add_argument("--effect-id", default="effect-1")
    parser.add_argument("--resource-id", default="resource-1")
    parser.add_argument("--targeted-failed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.child:
        if args.base is None or args.action is None:
            raise SystemExit("--child requires --base and --action")
        return _child(args)
    if args.output is None:
        raise SystemExit("--output is required")
    try:
        report = (
            run_targeted_failed_probe(args.output)
            if args.targeted_failed
            else run_probe(args.output)
        )
    except Exception as error:  # pragma: no cover - exercised only by the live probe
        output = args.output.resolve()
        checks = _load_recorded_checks(output) if output.exists() else []
        readiness_passed = any(
            check.name == "executor-readiness" and check.passed for check in checks
        )
        conclusion = (
            CheckConclusion.INSUFFICIENT_OBSERVATION
            if readiness_passed and isinstance(error, (TimeoutError, subprocess.TimeoutExpired))
            else CheckConclusion.SETUP_FAILURE
        )
        completion = CheckResult(
            "probe-completion",
            False,
            f"The live stand stopped before all scenarios completed: {error!r}",
            {
                "errorType": type(error).__name__,
                "completedScenarios": [check.name for check in checks],
            },
            conclusion=conclusion,
        )
        if output.exists():
            _record_check(output, checks, completion)
        else:
            checks.append(completion)
        expected = (
            frozenset(
                {
                    "executor-readiness",
                    "managed-technical-payload-deletion",
                    "workflow-code-version-routing",
                }
            )
            if args.targeted_failed
            else EXPECTED_CHECKS
        )
        report = GateReport(
            gate="durable-execution",
            status=gate_status(checks, expected),
            checks=tuple(checks),
            versions={
                "python": sys.version.split()[0],
                "sqlite": sqlite3.sqlite_version,
                "dbos": importlib.metadata.version("dbos"),
                "platform": sys.platform,
                "probeSha256": sha256_file(Path(__file__)),
            },
            commands=(
                "fixed-python -m tools.technical_baseline.durable_execution_probe "
                "--output _scratch/<new>",
            ),
            untested=("remaining live scenarios after the bounded stand failure",),
            notes=(
                "Completed scenario results were durably appended before later work began.",
                "Setup failure and insufficient observation are not DBOS contract violations.",
            ),
        )
        if output.exists():
            report.write(output / "durable-execution.json")
    print(json.dumps({"gate": report.gate, "status": report.status}, ensure_ascii=False))
    return 0 if report.status == GateStatus.POSITIVE else 1


if __name__ == "__main__":
    raise SystemExit(main())
