"""Bounded, explicitly invoked ordinary Pi trial through an existing subscription.

Only fictional spaces are created. This is a behavioural observation, not a
deterministic model-quality test. No credentials are read or included in evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import UUID

import zaratustra.foundation as core
from zaratustra.pi_adapter import Bridge, BridgeServer, read_pi_runtime
from zaratustra.pi_adapter.__main__ import _prepare_space
from zaratustra.pi_adapter.activity_setup import SetupCoordinator
from zaratustra.pi_adapter.assigned import AssignedConfig
from zaratustra.pi_adapter.procedures import ProcedureCoordinator
from zaratustra.pi_adapter.skills import activity_setup_skill
from zaratustra.pi_adapter.workflows import WorkflowCoordinator

DETAILS = (
    "Это вымышленная проверка. Мне 29 лет, женщина, рост 164 см, последнее "
    "измерение веса 72 кг сегодня. Хочу постепенно снизить вес и стать сильнее. "
    "Диагнозов, лекарств, травм, болей и пищевых ограничений нет. Есть две гантели "
    "и коврик дома; могу заниматься три раза по 30 минут, сейчас только гуляю. "
    "Готовлю на одного, обычные доступные продукты и умеренный бюджет. "
    "Предлагаемый горизонт 12 недель подходит; меню и планы на неделю, готовка "
    "на два дня. Подробный дневник еды, тренировок и веса, запись датированными "
    "событиями. Сохраняю когда удобно, иногда дважды за день, иногда за два дня. "
    "Недельный обзор в воскресенье и анализ календарного месяца. Часовой пояс "
    "UTC, неделя с понедельника, начать со следующего понедельника. "
    "Планы и анализ готовит ассистент, существенные изменения согласует со мной. "
    "Не нужны внешний сервис, публикация или исследование сейчас. "
    "Начать хочу с основания, дневника и записи первого события; персональная "
    "программа может быть отдельной следующей работой."
)
SCENARIOS = (
    ("short", "Хочу похудеть и стать сильнее. Помоги создать Activity Trial Short."),
    ("detailed", "Создай новую Activity Trial Detailed. " + DETAILS),
    (
        "forwarded",
        "Создай новую Activity Trial Forwarded. Ниже мои прежние ответы; используй "
        "их, не требуй повторить всю анкету. Старые предложения не переноси.\n" + DETAILS,
    ),
)


class Conversation:
    """One native Pi RPC session, with the ordinary installed Core extension."""

    def __init__(
        self,
        directory: Path,
        root: Path,
        working: Path,
        runtime: Path,
        subscription: Path,
        model: str,
        reasoning: str,
        *,
        resume: Path | None = None,
        remaining_sends: int = 40,
        coordination_timeout: int = 1800,
    ) -> None:
        self.coordination_timeout = coordination_timeout
        authority = core.authorize_local(root, actor="owner", source_ref="fictional-real-trial")
        actual = read_pi_runtime(runtime)
        self.bridge = Bridge(root, authority, working)
        config = AssignedConfig(
            space=root,
            workspace=working,
            pi_cli=actual.cli,
            pi_runtime=runtime,
            node=shutil.which("node") or "node",
            provider_profile="codex-sse",
            provider_base_url="https://chatgpt.com/backend-api",
            provider_id="openai-codex",
            model_id=model,
            thinking=reasoning,
            context_window=None,
            max_tokens=None,
            subscription_agent_dir=subscription,
            reserve_units=1000,
            limit_units=None,
            offline=False,
            disable_tools=True,
        )
        self.bridge.setup_controller = SetupCoordinator(self.bridge, config)
        self.bridge.procedure_controller = ProcedureCoordinator(self.bridge, config)
        self.bridge.workflow_controller = WorkflowCoordinator(self.bridge, config)
        self.server = BridgeServer(self.bridge)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        extension = directory / "extension.ts"
        if not extension.exists():
            shutil.copyfile(
                Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts"))), extension
            )
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
        }
        environment.update(
            {
                "PI_CODING_AGENT_DIR": str(subscription),
                "PI_SKIP_VERSION_CHECK": "1",
                "PI_TELEMETRY": "0",
                "ZARA_CORE_ENDPOINT": f"http://127.0.0.1:{self.server.server_port}",
                "ZARA_CORE_TOKEN": self.bridge.token,
                "ZARA_RESERVE_UNITS": "1000",
                "ZARA_PROVIDER_PROFILE": "codex-sse",
                "ZARA_PROVIDER_BASE_URL": "https://chatgpt.com/backend-api",
                "ZARA_PROVIDER_ORIGIN": "https://chatgpt.com",
                "ZARA_TRIAL_MAX_SENDS": str(remaining_sends),
                "ZARA_TRIAL_MAX_TOTAL_SENDS": str(remaining_sends),
                "ZARA_TRIAL_HTTP_TRACE_DIR": str(directory / "http"),
            }
        )
        command = [
            config.node,
            str(actual.cli),
            "--mode",
            "rpc",
            "--provider",
            "openai-codex",
            "--model",
            model,
            "--thinking",
            reasoning,
            "--extension",
            str(extension),
            "--no-extensions",
            "--no-context-files",
            "--no-skills",
            "--skill",
            str(activity_setup_skill()),
            "--no-prompt-templates",
            "--no-themes",
            "--no-approve",
            "--tools",
            "zara_activity,zara_workflow,zara_memory,zara_data,zara_binding",
            "--session-dir",
            str(root / ".zara-core" / "pi-sessions"),
        ]
        if resume is not None:
            command.extend(["--session", str(resume)])
        self.process = subprocess.Popen(
            command,
            cwd=working,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.evidence = directory / "rpc.jsonl"
        self.errors = bytearray()
        self.prompts = 0

        def read_events() -> None:
            assert self.process.stdout is not None
            for line in self.process.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    self.events.put(event)

        def read_errors() -> None:
            error_stream = self.process.stderr
            assert error_stream is not None
            for chunk in iter(lambda: error_stream.read(4096), b""):
                self.errors.extend(chunk)
                if len(self.errors) > 16384:
                    del self.errors[:-16384]

        threading.Thread(target=read_events, daemon=True).start()
        threading.Thread(target=read_errors, daemon=True).start()

    def send(self, value: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n")
        self.process.stdin.flush()

    def prompt(self, text: str) -> list[dict[str, Any]]:
        self.prompts += 1
        self.send({"id": f"prompt-{self.prompts}", "type": "prompt", "message": text})
        observed: list[dict[str, Any]] = []
        deadline = time.monotonic() + 360
        with self.evidence.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"trial_user": text}, ensure_ascii=False) + "\n")
            while time.monotonic() < deadline:
                try:
                    event = self.events.get(timeout=0.25)
                except queue.Empty:
                    if self.process.poll() is not None:
                        raise RuntimeError("Native Pi exited before its turn completed") from None
                    continue
                observed.append(event)
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
                stream.flush()
                if event.get("type") == "extension_ui_request":
                    method = event.get("method")
                    # RPC also emits display-only status/widget/notification events.
                    if method not in ("confirm", "select", "input", "editor"):
                        continue
                    if method != "confirm":
                        raise RuntimeError("The fictional trial requires an unplanned UI choice")
                    # Only creation of these fictional activities is authorized.
                    title = str(event.get("title", ""))
                    if title != "Создать и настроить эту Activity?":
                        raise RuntimeError(f"Unexpected confirmation: {title}")
                    self.send(
                        {"type": "extension_ui_response", "id": event["id"], "confirmed": True}
                    )
                if event.get("type") == "agent_end":
                    return observed
                if event.get("type") == "response" and event.get("success") is False:
                    raise RuntimeError(str(event.get("error", event)))
        raise TimeoutError("Native Pi did not complete within the bounded turn timeout")

    def settle_setup(self, setup_id: Any) -> Any:
        deadline = time.monotonic() + self.coordination_timeout
        read_attempts = 0
        while time.monotonic() < deadline:
            controller = self.bridge.setup_controller
            if controller.thread is None or not controller.thread.is_alive():
                try:
                    return core.read_activity_setup(
                        self.bridge.path, setup_id, self.bridge.authority
                    )
                except core.FoundationError as error:
                    read_attempts += 1
                    if (
                        read_attempts >= 3
                        or error.code not in ("busy", "storage")
                        or "locked" not in str(error)
                    ):
                        raise
                    # Retry a fresh public read only. The coordinator and its
                    # current Attempt continue untouched; no effect is replayed.
                    time.sleep(0.05 * read_attempts)
                    continue
            time.sleep(0.25)
        raise TimeoutError("Activity coordination did not reach a saved boundary")

    def close(self) -> None:
        for controller in (
            self.bridge.setup_controller,
            self.bridge.procedure_controller,
            self.bridge.workflow_controller,
        ):
            controller.close()
        if self.process.poll() is None:
            try:
                self.send({"id": "abort", "type": "abort"})
                assert self.process.stdin is not None
                self.process.stdin.close()
                self.process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=10)
        self.server.shutdown()
        self.server.server_close()


def run_probe(
    directory: Path,
    runtime: Path,
    subscription: Path,
    model: str,
    reasoning: str,
    *,
    prior_sends: int = 0,
    coordination_timeout: int = 1800,
    resume_trial: bool = False,
) -> dict[str, Any]:
    previous_report: dict[str, Any] = {}
    if resume_trial:
        previous_report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        if previous_report["prior_trial_sends"] != prior_sends:
            raise ValueError("Resume must preserve the prior trial send allowance")
    else:
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "http").mkdir()
    root, working = directory / "space", directory / "work"
    if not resume_trial:
        root.mkdir()
        working.mkdir()
    authority = _prepare_space(root, "owner", create=not resume_trial)
    remaining_sends = 40 - prior_sends
    os.environ["ZARA_TRIAL_MAX_TOTAL_SENDS"] = str(remaining_sends)
    os.environ["ZARA_TRIAL_HTTP_TRACE_DIR"] = str(directory / "http")
    report: dict[str, Any] = {
        "model": model,
        "provider": "openai-codex",
        "profile": "codex-sse",
        "reasoning": reasoning,
        "maximum_actual_sends": 40,
        "prior_trial_sends": prior_sends,
        "maximum_new_sends": remaining_sends,
        "fictional_only": True,
        "owner_acceptance": False,
        "resumed_trial": resume_trial,
        "scenarios": [],
        "status": "incomplete",
    }
    conversation: Conversation | None = None
    try:
        for key, text in SCENARIOS:
            prior_case = next(
                (item for item in previous_report.get("scenarios", []) if item["case"] == key), None
            )
            session: Path | None = None
            if prior_case is not None:
                setup_id = UUID(prior_case["setup_id"])
                state = core.read_activity_setup(root, setup_id, authority)
                if state.state.phase == "ready":
                    prior_case.update(
                        final_phase=state.state.phase,
                        reviews_started=state.state.reviews_started,
                        first_action=state.state.result,
                    )
                    report["scenarios"].append(prior_case)
                    continue
                sessions = sorted(
                    (root / ".zara-core" / "pi-sessions").rglob("*.jsonl"),
                    key=lambda path: path.stat().st_mtime,
                )
                if not sessions:
                    raise RuntimeError("The interrupted trial has no saved native session")
                session = sessions[-1]
            before = {view.setup_id for view in core.list_activity_setups(root, authority)}
            conversation = Conversation(
                directory,
                root,
                working,
                runtime,
                subscription,
                model,
                reasoning,
                resume=session,
                remaining_sends=remaining_sends,
                coordination_timeout=coordination_timeout,
            )
            conversation.prompt(
                text
                if prior_case is None
                else "Продолжи прежнюю настройку после закрытия окна. "
                "Используй уже сохранённые ответы; неизвестные отправки не повторяй."
            )
            if prior_case is None:
                created = [
                    view
                    for view in core.list_activity_setups(root, authority)
                    if view.setup_id not in before
                ]
                if len(created) != 1:
                    raise RuntimeError("One ordinary request did not create exactly one setup")
                setup_id = created[0].setup_id
            state = conversation.settle_setup(setup_id)
            item: dict[str, Any] = prior_case or {
                "case": key,
                "setup_id": str(setup_id),
                "boundaries": [],
            }
            report["scenarios"].append(item)
            if (
                key == "short"
                and state.state.phase == "needs_input"
                and not item.get("clarification_preserved_wait")
            ):
                previous = state.state
                conversation.prompt("Почему всё остановилось? Я не понимаю, что дальше.")
                state = conversation.settle_setup(setup_id)
                if (
                    state.state.question != previous.question
                    or state.state.input_version != previous.input_version
                ):
                    raise RuntimeError("A clarification silently changed the pending answer")
                item["clarification_preserved_wait"] = True
                conversation.close()
                sessions = sorted(
                    (root / ".zara-core" / "pi-sessions").rglob("*.jsonl"),
                    key=lambda path: path.stat().st_mtime,
                )
                if not sessions:
                    raise RuntimeError("Native Pi did not retain the session for reopening")
                conversation = Conversation(
                    directory,
                    root,
                    working,
                    runtime,
                    subscription,
                    model,
                    reasoning,
                    resume=sessions[-1],
                    remaining_sends=remaining_sends,
                    coordination_timeout=coordination_timeout,
                )
                item["reopened"] = True
            for _ in range(3):
                state = conversation.settle_setup(setup_id)
                item["boundaries"].append(state.model_dump(mode="json"))
                if state.state.phase in ("ready", "cancelled", "needs_attention"):
                    break
                conversation.prompt(
                    DETAILS
                    if state.state.phase == "needs_input"
                    else "Продолжай настройку; объясни текущий следующий шаг."
                )
            state = conversation.settle_setup(setup_id)
            item["final_phase"] = state.state.phase
            item["reviews_started"] = state.state.reviews_started
            item["first_action"] = state.state.result
            conversation.close()
            conversation = None
            if state.state.phase != "ready":
                raise RuntimeError(
                    f"Case {key} stopped at {state.state.phase}; inspect retained evidence"
                )
        report["status"] = "completed"
    except Exception as error:
        report["obstacle"] = f"{type(error).__name__}: {error}"
    finally:
        if conversation is not None:
            conversation.close()
        traces = sorted((directory / "http").glob("*.json"))
        report["recorded_http_requests"] = len(traces)
        report["total_trial_sends"] = prior_sends + len(traces)
        report["http_metadata"] = [json.loads(path.read_text(encoding="utf-8")) for path in traces]
        # Independent evidence read; product mutations still use the public Core.
        import sqlite3

        database = root / ".zara-core" / "core.sqlite3"
        with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT invocation_id,stage,usage_units FROM knowledge_delivery"
            ).fetchall()
        sent_rows = [row for row in rows if row[1] != "prepared"]
        report["accounted_sends"] = len(sent_rows)
        report["prepared_contexts"] = [row[0] for row in rows if row[1] == "prepared"]
        report["usage_units"] = sum(row[2] or 0 for row in rows)
        report["unresolved_invocations"] = [row[0] for row in sent_rows if row[1] != "answered"]
        report["delivered_manifests"] = []
        report["verification_errors"] = []
        for metadata in report["http_metadata"]:
            invocation = metadata["invocation_id"]
            body = (directory / "http" / f"{invocation}.body").read_bytes()
            delivery = core.read_context_delivery(root, UUID(invocation), authority)
            if (
                sha256(body).hexdigest().upper() != metadata["request_sha256"]
                or delivery["request_sha256"] != metadata["request_sha256"]
                or delivery["request_bytes"] != len(body)
            ):
                report["verification_errors"].append(f"Request/manifest mismatch: {invocation}")
            report["delivered_manifests"].append(delivery)
        if report["status"] == "completed":
            if (
                not (len(traces) == len(sent_rows) <= remaining_sends)
                or report["unresolved_invocations"]
            ):
                report["verification_errors"].append("Incomplete send accounting")
        if report["verification_errors"]:
            report["status"] = "incomplete"
        report["schema"] = core.read_space(root).schema_version
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--pi-runtime", required=True, type=Path)
    parser.add_argument("--subscription-agent-dir", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning", required=True)
    parser.add_argument("--prior-sends", type=int, default=0)
    parser.add_argument("--coordination-timeout", type=int, default=1800)
    parser.add_argument("--resume-trial", action="store_true")
    parser.add_argument("--authorized-subscription-trial", action="store_true")
    args = parser.parse_args()
    if not args.authorized_subscription_trial:
        parser.error("This real subscription trial requires explicit owner authorization")
    if not 0 <= args.prior_sends < 40 or args.coordination_timeout < 1:
        parser.error("Prior sends must leave a positive part of forty; timeout must be positive")
    report = run_probe(
        args.directory.resolve(),
        args.pi_runtime.resolve(),
        args.subscription_agent_dir.resolve(),
        args.model,
        args.reasoning,
        prior_sends=args.prior_sends,
        coordination_timeout=args.coordination_timeout,
        resume_trial=args.resume_trial,
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in ("scenarios", "http_metadata", "delivered_manifests")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
