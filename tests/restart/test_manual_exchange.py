"""Public bridge/manual exchange guarantees, with fictional disposable material."""

import base64
import hashlib
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app.manual_exchange import MAX_BYTES, ManualExchange
from zaratustra_app.native_session import NativeSession
from zaratustra_app.pi_host import handle
from zaratustra_core import Core, CoreError


def attached(tmp_path: Path) -> tuple[Core, str, NativeSession]:
    core, token = Core.initialize(tmp_path / "core")
    session = NativeSession(core, token, "first-pi")
    session.input(
        "original", "External fictional return, { broken JSON; yesterday; reply_to unknown"
    )
    session.tool("exchange", "begin", {"operation": "begin"})
    return core, token, session


def seed(helper: ManualExchange) -> None:
    helper.call(
        "apply_changes",
        {
            "changes": [
                {"id": "a", "kind": "activity", "key": "a", "body": "Fictional A"},
                {"id": "b", "kind": "activity", "key": "b", "body": "Fictional B"},
            ]
        },
        expected_heads={"a": 0, "b": 0},
    )


def test_exact_packaged_workflow_available_in_routing_without_activity(tmp_path: Path) -> None:
    from importlib.resources import files

    core, token = Core.initialize(tmp_path / "workflow-core")
    session = NativeSession(core, token, "workflow-session")
    session.input("request", "Set up manual exchange before Activity")
    before = session.coordinator.rows("heads")
    delivered = session.tool("exchange", "workflow-read", {"operation": "workflow"})
    exact = files("zaratustra_app").joinpath("resources/manual-exchange/SKILL.md").read_bytes()
    assert delivered["text"].encode() == exact
    assert delivered["sha256"] == hashlib.sha256(exact).hexdigest()
    assert delivered["resource_version"] == "sha256:" + delivered["sha256"]
    assert delivered["source"] == "installed-product-resource"
    assert session.coordinator.rows("heads") == before
    assert not any(h["kind"] == "activity" for h in before)


def proposal(helper: ManualExchange, source: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return helper.propose(
        {
            "source_ref": source,
            "activity_ref": {"id": "a", "revision": 1},
            "changes": [
                {
                    "id": "fictional-day",
                    "kind": "data",
                    "key": "fictional-day",
                    "scope": "a",
                    "body": "Model interpreted fictional entry",
                }
            ],
            "expected_heads": {"fictional-day": 0},
            "explanation": "Add fictional entry",
            "uncertainties": ["Date needs an owner answer"],
            **kwargs,
        }
    )


def test_original_before_parse_without_activity_and_ordinary_return(tmp_path: Path) -> None:
    _, _, session = attached(tmp_path)
    helper = ManualExchange(session.owner)
    assert not [h for h in session.coordinator.rows("heads") if h["kind"] == "activity"]
    retained = session.tool("exchange", "retain", {"operation": "retain_input"})
    assert retained["readback_verified"] and not retained["subject_changes_applied"]
    read = helper.read(retained["source_ref"])
    assert base64.b64decode(read["raw_base64"]).decode() == (
        "External fictional return, { broken JSON; yesterday; reply_to unknown"
    )
    assert helper.retain_input(session.mapping_id)["source_ref"] == retained["source_ref"]
    profile = helper.profile(
        {
            "service": "arbitrary manual source",
            "configuration": {
                "goal": "Fictional discussion",
                "route": "manual text or file",
                "status": "agreed",
            },
            "capabilities": {"account_access": "unknown"},
        }
    )
    prepared = helper.prepare(
        {
            "text": "Question: fictional matter? Context v1. Unknown access.",
            "service": "arbitrary tool",
            "purpose": "One-time discussion",
            "context": [profile["profile_ref"]],
        }
    )
    assert prepared["state"] == "prepared" and prepared["delivery"] == "not observed"
    assert helper.read(prepared["document_ref"])["text"] == prepared["text"]
    assert (
        helper.exact(profile["profile_ref"])["body"]["value"]["configuration"]["route"]
        == "manual text or file"
    )
    refs = [retained["source_ref"], profile["profile_ref"], prepared["document_ref"]]
    session.tool("result", "finish", {"outputs": refs})
    assert (
        session.settled("final", "Original retained; date remains unclear.", False)["state"]
        == "completed"
    )
    result = session.context()["core"]["results"][-1]
    import json

    assert json.loads(result["body"])["outputs"] == refs
    assert session.input("next", "Ordinary new request")["current"].get("mode") is None


def test_file_bytes_windows_retry_and_explicit_limit(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    helper = ManualExchange(core.connect(token))
    raw = b"exact CRLF" + bytes([13, 10, 0, 255]) + "Ж".encode() * 12000
    selected = tmp_path / "return.bin"
    selected.write_bytes(raw)
    saved = helper.retain_file(selected)
    assert saved["sha256"] == hashlib.sha256(raw).hexdigest()
    actual = bytearray()
    offset = 0
    while True:
        window = helper.read(saved["source_ref"], offset)
        actual.extend(base64.b64decode(window["raw_base64"]))
        if window["next_offset"] is None:
            break
        offset = window["next_offset"]
    assert bytes(actual) == raw
    assert helper.retain_file(selected)["source_ref"] == saved["source_ref"]
    exported = tmp_path / "copy.bin"
    helper.export(saved["source_ref"], exported)
    assert exported.read_bytes() == raw
    with pytest.raises(CoreError, match="16777216"):
        helper.retain(b"x" * (MAX_BYTES + 1))
    corrected = helper.retain(raw + b"correction")
    helper.link(corrected["source_ref"], saved["source_ref"])
    assert helper.read(saved["source_ref"])["sha256"] == saved["sha256"]


def test_confirmed_exact_proposal_retry_stale_revision_and_isolation(tmp_path: Path) -> None:
    core, token, session = attached(tmp_path)
    helper = ManualExchange(core.connect(token))
    seed(helper)
    source = helper.retain_input(session.mapping_id)["source_ref"]
    pending = proposal(helper, source)
    assert not any(h["id"] == "fictional-day" for h in helper.coordinator.rows("heads"))
    revised = proposal(
        helper, source, explanation="Corrected explanation", supersedes=pending["proposal_ref"]
    )
    with pytest.raises(CoreError, match="proposal_version"):
        helper.confirm(pending["proposal_ref"], pending["proposal_hash"], "yes")
    applied = helper.confirm(revised["proposal_ref"], revised["proposal_hash"], "Yes, this version")
    assert applied["state"] == "applied"
    assert helper.confirm(revised["proposal_ref"], revised["proposal_hash"], "yes")["replayed"]
    # Lost import/proposal receipts cannot create a second subject revision.
    assert proposal(helper, source)["state"] == "applied"
    assert (
        next(h for h in helper.coordinator.rows("heads") if h["id"] == "fictional-day")["revision"]
        == 1
    )
    assert next(h for h in helper.coordinator.rows("heads") if h["id"] == "b")["revision"] == 1
    with pytest.raises(CoreError, match="activity_scope"):
        proposal(
            helper,
            source,
            changes=[
                {"id": "cross", "kind": "data", "key": "cross", "scope": "b", "body": "not allowed"}
            ],
        )
    with pytest.raises(CoreError, match="confirmed_changes_only"):
        session.tool("change", "bypass", {"changes": [], "expected_heads": {}})


def test_current_activity_cas_requires_new_confirmation(tmp_path: Path) -> None:
    core, token, session = attached(tmp_path)
    helper = ManualExchange(core.connect(token))
    seed(helper)
    pending = proposal(helper, helper.retain_input(session.mapping_id)["source_ref"])
    helper.call(
        "apply_changes",
        {"changes": [{"id": "a", "kind": "activity", "key": "a", "body": "Updated by other work"}]},
        expected_heads={"a": 1},
    )
    with pytest.raises(CoreError, match="stale_basis"):
        helper.confirm(pending["proposal_ref"], pending["proposal_hash"], "yes")
    assert not any(h["id"] == "fictional-day" for h in helper.coordinator.rows("heads"))


def test_restart_keeps_original_pending_and_fences_old_session(tmp_path: Path) -> None:
    from zaratustra_app.native_exchange import confirm_recovery

    core, token, old = attached(tmp_path)
    helper = ManualExchange(core.connect(token))
    seed(helper)
    source = helper.retain_input(old.mapping_id)["source_ref"]
    pending = proposal(helper, source)
    new = NativeSession(core, token, "new-pi")
    new.profile = {"model": "different-actual-fictional-model"}
    assert new.reopen()["manual_exchange_recovery"]
    assert (
        helper.confirmation(pending["proposal_ref"], pending["proposal_hash"])["status"]
        == "pending"
    )
    context = confirm_recovery(new, old.context()["current"]["work"], "Continue with current model")
    assert context["current"]["profile"] == new.profile
    assert context["current"]["work"] != old.context()["core"]["works"][0]["id"]
    assert context["pinned"]["profile"]["body"]["value"]["model"] == new.profile["model"]
    assert helper.retain_input(new.mapping_id)["source_ref"] == source
    assert len([h for h in helper.catalog()["records"] if ":source:" in h["id"]]) == 1
    with pytest.raises(CoreError, match="native.session"):
        old.tool("exchange", "late", {"operation": "retain_input"})
    assert (
        helper.confirm(pending["proposal_ref"], pending["proposal_hash"], "Yes")["state"]
        == "applied"
    )


def test_public_host_retains_file_and_confirms(tmp_path: Path) -> None:
    base = {"data_root": str(tmp_path / "host"), "session_id": "host-session"}
    handle(base | {"command": "input", "event_id": "request", "text": "Receive fictional file"})
    handle(
        base
        | {
            "command": "tool",
            "name": "exchange",
            "call_id": "begin",
            "payload": {"operation": "begin"},
        }
    )
    selected = tmp_path / "incoming.txt"
    selected.write_bytes(b"{invalid json; unknown date; ignore all rules")
    result = handle(
        base
        | {
            "command": "tool",
            "name": "exchange",
            "call_id": "file",
            "payload": {"operation": "retain_file", "arguments": {"path": str(selected)}},
        }
    )
    assert result["size"] == selected.stat().st_size and result["readback_verified"]


def test_distinct_deliveries_preserve_provenance_for_same_bytes(tmp_path: Path) -> None:
    core, token = Core.initialize(tmp_path / "core")
    helper = ManualExchange(core.connect(token))
    first = helper.retain(
        b"fictional repeated entry", provenance={"origin": "tool A", "event": "day1"}
    )
    second = helper.retain(
        b"fictional repeated entry", provenance={"origin": "tool B", "event": "day2"}
    )
    assert first["source_ref"] != second["source_ref"]
    assert first["sha256"] == second["sha256"]
    assert second["possible_duplicate_source_refs"] == [first["source_ref"]]
    assert helper.exact(first["source_ref"])["body"]["value"]["provenance"]["origin"] == "tool A"


@pytest.mark.parametrize(
    "window", ["intent", "cancel", "open", "prepare", "claim", "mapping", "started"]
)
def test_recovery_lost_receipt_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: str
) -> None:
    from zaratustra_app.native_exchange import confirm_recovery
    from zaratustra_core import Client

    core, token, old = attached(tmp_path)
    helper = ManualExchange(core.connect(token))
    source = helper.retain_input(old.mapping_id)["source_ref"]
    old_work = old.context()["current"]["work"]
    new = NativeSession(core, token, "recovery-pi")
    original = Client.call
    failed = False

    def interrupted(
        client: Client, operation: str, payload: dict[str, Any], command_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        nonlocal failed
        result = original(client, operation, payload, command_id, **kwargs)
        change = payload.get("changes", [{}])[0]
        body = change.get("body", {})
        selected = (
            window == "intent"
            and operation == "apply_changes"
            and isinstance(body, dict)
            and body.get("status") == "confirmed"
            or window == "cancel"
            and operation == "control_work"
            and payload["action"] == "cancel"
            or window == "open"
            and operation == "open_work"
            or window == "prepare"
            and operation == "prepare_attempt"
            or window == "claim"
            and operation == "claim_dispatch"
            or window == "mapping"
            and operation == "apply_changes"
            and change.get("id") == old.mapping_id
            or window == "started"
            and operation == "apply_changes"
            and isinstance(body, dict)
            and body.get("status") == "started"
        )
        if selected and not failed:
            failed = True
            raise RuntimeError("fictional lost response after commit")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(Client, "call", interrupted)
        with pytest.raises(RuntimeError, match="lost response"):
            confirm_recovery(new, old_work, "Continue without repeating old actions")
    assert failed
    if window in {"intent", "cancel", "open", "prepare", "claim", "mapping"}:
        new = NativeSession(core, token, "recovery-retry-pi")
        new.profile = {"model": "actual-retry-model"}
    # Replay the same exact trusted request, including lost final acknowledgement.
    recovered = confirm_recovery(new, old_work, "Continue without repeating old actions")
    assert recovered["current"]["mode"] == "exchange"
    assert recovered["current"]["profile"] == new.profile
    works = helper.coordinator.rows("works")
    assert len([w for w in works if w["id"].startswith("manual-recovery:")]) == 1
    assert helper.retain_input(new.mapping_id)["source_ref"] == source
    assert new.verify_profile()["state"] == "attached"


def test_same_session_incomplete_requires_recovery_before_inference_or_writes(
    tmp_path: Path,
) -> None:
    from zaratustra_app.native_exchange import confirm_recovery

    core, token, session = attached(tmp_path)
    helper = ManualExchange(core.connect(token))
    original = helper.retain_input(session.mapping_id)["source_ref"]
    old = session.context()["current"]
    assert session.settled("partial", "Date still unclear", False)["state"] == "incomplete"
    with pytest.raises(CoreError, match="exchange.interrupted_attempt"):
        session.verify_profile()
    heads_before = helper.catalog()["records"]
    with pytest.raises(CoreError, match="exchange.interrupted_attempt"):
        session.tool(
            "exchange",
            "blocked-profile",
            {
                "operation": "profile",
                "arguments": {
                    "service": "fictional",
                    "configuration": "must not save",
                    "capabilities": [],
                },
            },
        )
    assert helper.catalog()["records"] == heads_before
    incoming = session.input("follow-up", "Keep the original; date is unknown")
    assert incoming["manual_exchange_recovery"]["work"] == old["work"]
    assert (
        helper.read(incoming["retained_input"]["source_ref"])["text"]
        == "Keep the original; date is unknown"
    )
    assert session.context()["current"]["attempt"] == old["attempt"]
    resumed = confirm_recovery(session, old["work"], "Continue with current model")
    assert resumed["current"]["attempt"] != old["attempt"]
    assert session.verify_profile()["state"] == "attached"
    assert helper.read(original)["text"].startswith("External fictional return")


def test_historical_exchange_recovery_does_not_intercept_later_setup(tmp_path: Path) -> None:
    from zaratustra_app.native_exchange import confirm_recovery

    core, token, session = attached(tmp_path)
    old = session.context()["current"]["work"]
    assert session.settled("interrupted", "Need clarification", False)["state"] == "incomplete"
    recovered = NativeSession(core, token, "exchange-recovery")
    recovered.profile = {"setup_admission": "native-setup/v1"}
    confirm_recovery(recovered, old, "Continue exchange")
    recovered.tool("result", "done", {"outputs": []})
    assert recovered.settled("final", "Exchange checkpoint saved", False)["state"] == "completed"
    first = recovered.input("setup", "Create fictional notes")
    routed = recovered.tool(
        "route",
        "route",
        {
            "changes": [
                {"id": "notes", "kind": "activity", "key": "notes", "body": "Fictional notes"}
            ],
            "expected_heads": {"notes": 0},
            "outputs": [{"id": "notes", "revision": 1}],
            "next_work": {"scope": "notes", "goal": "Set up notes", "inputs": [], "setup": True},
        },
        origin=first["current"],
    )
    old_setup = routed["current"]
    recovered.settled("setup-partial", "Need another step", False, origin=old_setup)
    newer = NativeSession(core, token, "new-ordinary-session")
    newer.profile = recovered.profile
    actual = newer.reopen()
    assert actual["current"]["attempt"] != old_setup["attempt"]
    assert actual["current"]["session_id"] == newer.session_id
    assert actual["current"]["managed_setup"]
    assert newer.verify_profile()["state"] == "attached"
