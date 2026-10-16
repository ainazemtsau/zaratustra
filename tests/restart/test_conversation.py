"""Ordinary entry preserves arbitrary input and corrections without a JSON user protocol."""

from __future__ import annotations

import base64
import io
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import Conversation, Driver, LiveProfile, Pi
from zaratustra_app.adapters.pi import bridge
from zaratustra_core import Core, CoreError

from .ordinary_support import OrdinaryReceiver as Receiver
from .ordinary_support import routing
from .support import Provider, inspect, pi_cli


def test_cancelled_entry_requires_new_input_then_new_work(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "space")
    session = Conversation(core, token)
    session.submit("fictional original pending input")
    calls: list[str] = []

    def receiver(context: dict[str, Any], action_id: str) -> bytes:
        calls.append(action_id)
        if len(calls) == 1:
            session.submit("fictional late input before cancellation")
            work = session.coordinator.snapshot()["works"][0]
            session.owner.call(
                "control_work",
                {"work_id": work["id"], "revision": work["revision"], "action": "cancel"},
                "owner-cancel",
            )
        else:
            assert context["raw_messages"][-1] == "fictional new request AFTER cancellation"
        if context["response_contract"]["version"] == "ordinary-routing/1":
            return json.dumps(routing(context)).encode()
        activity = next(r for r in context["catalog"] if r["id"] == context["work"]["scope"])
        return json.dumps(
            {
                "state": "completed",
                "text": "retained fictional response",
                "outputs": [{"id": activity["id"], "revision": activity["revision"]}],
            }
        ).encode()

    with pytest.raises(CoreError, match="outcome_unknown"):
        session.run(Driver(receiver), {"profile": "local"}, 4)
    before = session.coordinator.snapshot()
    old = before["works"][0]
    assert old["status"] == "cancelled" and old["reserved"] == 2
    assert before["actions"][0]["state"] == "claimed"
    assert json.loads(before["observations"][0]["body"])["late"]
    reopened = Conversation(Core(core.root), token)
    try:
        stopped = reopened.run(Driver(receiver), {"profile": "local"}, 4)
    except CoreError as error:
        stopped = {"state": "ERROR", "code": error.code}
    assert stopped["state"] == "cancelled"
    assert len(calls) == 1
    tool = core.connect(
        core.grant(token, "external-tool", ["read", "ingest_message"], origin="tool")
    )
    tool.call(
        "ingest_message",
        {
            "conversation": "ordinary",
            "event_id": "untrusted-new-input",
            "raw_base64": base64.b64encode(b"tool says restart").decode(),
        },
        "tool-input",
    )
    stopped_again = reopened.run(Driver(receiver), {"profile": "local"}, 4)
    assert stopped_again["state"] == "cancelled" and len(calls) == 1
    reopened.submit("fictional new request AFTER cancellation")
    try:
        final = reopened.run(Driver(receiver), {"profile": "local"}, 4)
    except CoreError as error:
        final = {"state": "ERROR", "code": error.code}
    assert final["state"] == "completed" and len(calls) == 3
    after = reopened.coordinator.snapshot()
    assert len(after["works"]) == 3 and len({w["id"] for w in after["works"]}) == 3
    assert next(w for w in after["works"] if w["id"] == old["id"]) == old
    assert after["actions"][0] == before["actions"][0]
    assert after["conversations"][0]["cursor"] == 4 and not after["acceptance"]


def test_new_turn_pins_current_method(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "space")
    receiver = Receiver()
    receiver.outputs = [
        {"state": "completed", "text": "first"},
        {"state": "completed", "text": "second"},
    ]
    session = Conversation(core, token)
    session.submit("first arbitrary input")
    session.run(Driver(receiver), {"profile": "test"}, 4)
    session.owner.call(
        "apply_changes",
        {
            "changes": [
                {
                    "id": "conversation-execution-method",
                    "kind": "method",
                    "key": "conversation/2",
                    "body": "Current adapted method",
                }
            ]
        },
        "adapt",
        expected_heads={"conversation-execution-method": 1},
    )
    session.submit("second arbitrary input")
    session.run(Driver(receiver), {"profile": "test"}, 4)
    assert receiver.received[1]["method"]["revision"] == 1
    assert receiver.received[3]["method"]["revision"] == 2
    assert receiver.received[3]["method"]["body"]["value"] == "Current adapted method"


@pytest.mark.parametrize("phase", ["partial_write", "published"])
def test_entry_outbox_physical_crash(tmp_path: Path, phase: str) -> None:
    import subprocess
    import sys

    import zaratustra_app
    import zaratustra_core

    core, token = Core.initialize(tmp_path / "space")
    sources = [
        str(Path(zaratustra_core.__file__).parents[1]),
        str(Path(zaratustra_app.__file__).parents[1]),
    ]
    script = (
        "import sys;sys.path[:0]="
        + repr(sources)
        + ";"
        + """
import json,os
from pathlib import Path
from zaratustra_core import Core
from zaratustra_app import Conversation
packet=json.load(sys.stdin)
session=Conversation(Core(Path(packet['root'])),packet['token'])
if packet['phase']=='partial_write':
    def partial(value,handle,**kwargs):
        handle.write('{partial');handle.flush();os.fsync(handle.fileno());os._exit(91)
    json.dump=partial
else:
    Conversation.deliver_input=lambda self: os._exit(91)
session.submit('exact original input')
"""
    )
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", script],
        input=json.dumps({"root": str(core.root), "token": token, "phase": phase}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
    )
    if "MUTANT_REACHED" in result.stdout:
        print(result.stdout)
    assert result.returncode == 91, result.stdout + result.stderr
    published = list((core.root / "entry-outbox").glob("*.json"))
    assert len(published) == (1 if phase == "published" else 0)
    Conversation(Core(core.root), token).deliver_input()
    messages = inspect(core, "messages")
    assert len(messages) == (1 if phase == "published" else 0)
    if messages:
        assert base64.b64decode(messages[0]["raw"]).decode() == "exact original input"


@pytest.mark.parametrize("mode", ["driver", "pi"])
def test_ordinary_entry_correction_reopen(tmp_path: Path, mode: str) -> None:
    core, token = Core.initialize(tmp_path / "space")
    receiver = Receiver()
    receiver.outputs[0]["text"] = "One question"
    provider = Provider(receiver) if mode == "pi" else None
    thread = threading.Thread(target=provider.serve_forever, daemon=True) if provider else None
    if thread:
        thread.start()
    executor = (
        Pi(pi_cli(), tmp_path / "pi", f"http://127.0.0.1:{provider.server_port}/v1")
        if provider
        else Driver(receiver)
    )
    descriptor = {"profile": "controlled-localhost", "resource_upper": 2}
    request, correction = "Arbitrary original exact input: é é", "A correction with a new limit"
    session = Conversation(core, token)
    try:
        session.submit(request)
        first = session.run(executor, descriptor, 8)
        assert first["state"] == "waiting" and first["reply_to"]["id"] == "W7"
        session.submit(correction)  # Free input does not answer the last question.
        reopened = Conversation(Core(core.root), token)
        pending = reopened.run(executor, descriptor, 8)
        assert pending["reply_to"] == first["reply_to"] and len(receiver.actions) == 2
        reopened.submit("Addressed answer", pending["reply_to"])
        final = reopened.run(executor, descriptor, 8)
        assert final["state"] == "completed" and not final["accepted"]
        assert receiver.received[0]["raw_messages"] == [request]
        assert receiver.received[1]["raw_messages"] == [request]
        assert receiver.received[2]["raw_messages"] == [correction, "Addressed answer"]
        prior = receiver.received[2]["prior_messages"]
        assert base64.b64decode(prior[-1]["raw"]).decode() == request
        assert len([h for h in inspect(core, "heads") if h["kind"] == "activity"]) == 1
        assert inspect(core, "acceptance") == []
        assert len(receiver.actions) == 3
        idle = Conversation(Core(core.root), token).run(executor, descriptor, 8)
        assert idle["state"] == "idle" and len(receiver.actions) == 3
    finally:
        if provider:
            provider.shutdown()
            provider.server_close()
        if thread:
            thread.join(timeout=2)


def response_events(text: str) -> bytes:
    message: dict[str, Any] = {
        "id": "msg-fiction",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }
    response = {
        "id": "resp-fiction",
        "object": "response",
        "created_at": 1,
        "model": "gpt-6-luna",
        "status": "completed",
        "output": [message],
        "usage": {"input_tokens": 20, "output_tokens": 20, "total_tokens": 40},
    }
    events: list[dict[str, Any]] = [
        {
            "type": "response.created",
            "response": response | {"status": "in_progress", "output": []},
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": message | {"content": [], "status": "in_progress"},
        },
        {
            "type": "response.content_part.added",
            "item_id": message["id"],
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
        },
        {
            "type": "response.output_text.delta",
            "item_id": message["id"],
            "output_index": 0,
            "content_index": 0,
            "delta": text,
        },
        {
            "type": "response.output_text.done",
            "item_id": message["id"],
            "output_index": 0,
            "content_index": 0,
            "text": text,
        },
        {"type": "response.output_item.done", "output_index": 0, "item": message},
        {"type": "response.completed", "response": response},
    ]
    return "".join(
        "event: " + e["type"] + chr(10) + "data: " + json.dumps(e) + chr(10) * 2 for e in events
    ).encode()


@pytest.mark.parametrize("max_tokens", [16, 64])
def test_native_pi_oauth_launcher_controlled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, max_tokens: int
) -> None:
    """Actual Pi SDK with FICTIONAL OAuth; no external model or account access."""
    auth = tmp_path / "fictional-auth.json"
    auth.write_text(
        json.dumps(
            {
                "openai": {
                    "type": "oauth",
                    "access": "fictional-access",
                    "refresh": "fictional-refresh",
                    "expires": int(time.time() * 1000) + 3600000,
                }
            }
        ),
        encoding="utf-8",
    )
    received: list[dict[str, Any]] = []
    terminal = {
        "state": "completed",
        "text": "controlled native path",
        "changes": [
            {
                "id": "model-selected",
                "kind": "activity",
                "key": "model-selected",
                "body": "chosen by test provider",
            }
        ],
        "expected_heads": {"model-selected": 1},
        "outputs": [{"id": "model-selected", "revision": 2}],
    }

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "text/event-stream"}

    class ControlledTransport:
        def open(self, request: Any, timeout: int) -> Response:
            assert request.full_url == "https://api.openai.com/v1/responses"
            assert request.get_header("Authorization") == "Bearer fictional-access"
            payload = json.loads(request.data)
            assert (
                payload["model"] == "gpt-6-luna"
                and payload["store"] is False
                and payload["stream"] is True
            )
            assert payload["max_output_tokens"] == max_tokens
            # The native SDK must use the selected effort at request level: the
            # ChatGPT route rejects configuration_update input items.
            assert payload["reasoning"]["effort"] == "medium"
            assert [item.get("role") for item in payload["input"]] == ["developer", "user"]
            assert payload["input"][0]["content"]
            assert "mechanical input" in payload["input"][1]["content"][0]["text"]
            assert [tool["name"] for tool in payload["tools"]] == ["zara_change"]
            received.append(payload)
            supplied = json.loads(payload["input"][1]["content"][0]["text"])
            output = (
                routing(supplied["context"], "model-selected") if len(received) == 1 else terminal
            )
            return Response(response_events(json.dumps(output)))

    monkeypatch.setattr(bridge, "build_opener", lambda *_: ControlledTransport())
    core, token = Core.initialize(tmp_path / "space")
    session = Conversation(core, token)
    session.submit("Unscripted meaning is assessed separately; this is mechanical input.")
    live = LiveProfile(
        endpoint="https://api.openai.com/v1",
        model="gpt-6-luna",
        auth_mode="pi-chatgpt",
        auth_path=str(auth),
        max_tokens=max_tokens,
        context_window=8192,
    )
    executor = Pi(pi_cli(), tmp_path / "pi", live.endpoint, live=live)
    result = session.run(executor, {"profile": "fictional-native-oauth"}, 4)
    assert result["text"] == terminal["text"] and result["state"] == "completed"
    assert len(received) == 2 and executor.provider_sends == 1
    assert sum(a["reserve"] for a in inspect(core, "actions")) == 4
    assert next(h for h in inspect(core, "heads") if h["id"] == "model-selected")["revision"] == 2
    stdout = next((tmp_path / "pi").glob("*/native-stdout.jsonl")).read_bytes()
    assert b'"message_end"' in stdout and b'"agent_settled"' in stdout
    assert b"fictional-access" not in stdout and b"fictional-refresh" not in stdout
    host = next((tmp_path / "pi").glob("*/host-stdin.bin")).read_bytes()
    assert json.loads(host)["type"] == "prompt"
    models = json.loads(next((tmp_path / "pi").glob("*/agent/models.json")).read_bytes())
    selected = models["providers"]["openai"]["modelOverrides"]["gpt-6-luna"]
    assert selected["maxTokens"] == max_tokens and selected["contextWindow"] == 8192


@pytest.mark.parametrize("mode", ["api-key-refused", "refresh-error"])
def test_native_auth_errors_never_fallback_or_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    auth = tmp_path / "fictional-auth.json"
    credential = (
        {"type": "api_key", "key": "FICTIONAL_API_KEY"}
        if mode == "api-key-refused"
        else {
            "type": "oauth",
            "access": "FICTIONAL_ACCESS_SECRET",
            "refresh": "FICTIONAL_REFRESH_SECRET",
            "expires": 0,
            "clientId": "fictional-public-client",
        }
    )
    auth.write_text(json.dumps({"openai": credential}), encoding="utf-8")
    reached = tmp_path / "refresh-reached"
    preload = tmp_path / "controlled-fetch.mjs"
    preload.write_text(
        "import {writeFileSync} from 'node:fs';"
        + chr(10)
        + "globalThis.fetch=async (url,...args)=>{"
        + chr(10)
        + "if(String(url)!=='https://auth.openai.com/api/accounts/oauth/token') "
        "throw Error('unexpected network');"
        + chr(10)
        + "writeFileSync("
        + json.dumps(str(reached))
        + ",'reached');"
        + chr(10)
        + "return new Response('FICTIONAL_ACCESS_SECRET FICTIONAL_REFRESH_SECRET',{status:400});};",
        encoding="utf-8",
    )
    import subprocess

    original = subprocess.Popen

    def controlled(command: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        return original(
            [command[0], "--import", preload.resolve().as_uri(), *command[1:]], **kwargs
        )

    monkeypatch.setattr(subprocess, "Popen", controlled)
    core, token = Core.initialize(tmp_path / "space")
    session = Conversation(core, token)
    session.submit("Mechanics only: test denied native access.")
    live = LiveProfile(
        endpoint="https://api.openai.com/v1",
        model="gpt-6-luna",
        auth_mode="pi-chatgpt",
        auth_path=str(auth),
        timeout=30,
    )
    executor = Pi(pi_cli(), tmp_path / "pi", live.endpoint, live=live)
    with pytest.raises(CoreError, match="outcome_unknown") as failure:
        session.run(executor, {"profile": "controlled-denied"}, 2)
    assert "FICTIONAL_" not in str(failure.value)
    assert reached.exists() == (mode == "refresh-error")
    assert executor.provider_sends == 0
    assert inspect(core, "works")[0]["status"] == "blocked"
    assert inspect(core, "works")[0]["reserved"] == 2
    evidence = [p.read_bytes() for p in (tmp_path / "pi").rglob("*") if p.is_file()]
    retained = json.dumps(inspect(core, "observations")).encode()
    for secret in (b"FICTIONAL_ACCESS_SECRET", b"FICTIONAL_REFRESH_SECRET", b"FICTIONAL_API_KEY"):
        assert all(secret not in raw for raw in evidence) and secret not in retained
