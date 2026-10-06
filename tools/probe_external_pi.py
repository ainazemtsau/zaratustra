"""Installed workflow and adapter roundtrip through real Pi, synthetic localhost only."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from tests.zaratustra.foundation.test_binding import _apply, _ready
from tools.probe_knowledge_pi import Provider, apply, run_process, source
from zaratustra.foundation import (
    ClaimState,
    CreateActivityRequest,
    CreateWorkRequest,
    HandoffState,
    KnowledgeRef,
    OutputContract,
    SourceState,
    WorkState,
    read_knowledge,
    read_work,
    upgrade_knowledge_space,
)
from zaratustra.pi_adapter import Bridge, external_workflow_skill


def _user_texts(request: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for message in request["messages"]:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.extend(str(part["text"]) for part in content if "text" in part)
    return texts


def _integration(operation: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "_tool": "zara_integration",
        "mode": "apply",
        "adapter": "manual",
        "operation": operation,
        "contract_version": 1,
        "arguments": arguments,
    }


def _last_result(body: dict[str, Any]) -> dict[str, Any]:
    tool = [message for message in body["messages"] if message.get("role") == "tool"][-1]
    content = tool["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content)
    return cast(dict[str, Any], json.loads(content))


def run_probe(directory: Path, runtime: Path) -> dict[str, object]:
    root, space, owner, activity, _ = _ready(directory)
    upgrade_knowledge_space(root, owner)
    work = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateWorkRequest,
        work_id=work,
        state=WorkState(
            activity_id=activity,
            goal="An unrelated fictional Work is not accepted by intake",
            expected_outputs=(OutputContract(slot="result", media_type="text/plain"),),
        ),
    )
    other_activity = uuid4()
    _apply(
        root,
        space,
        owner,
        CreateActivityRequest,
        activity_id=other_activity,
        state={"title": "Fictional independent notes", "goal": "Use fictional articles"},
    )
    capability_id, setup_claim_id, article_id = (uuid4() for _ in range(3))
    capability = {
        **source("Fictional Chat accepts pasted text; project support is unknown."),
        "connection": "fictional-external-research",
        "scope_activity_id": str(activity),
    }
    capability_ref = {"record_id": str(capability_id), "revision": 1}
    document = "Fictional Chat setup: discuss chosen ideas freely.\nUse the supplied context.\n"
    article = "Fictional article\r\n\nЦитата: α 🙂\nFree prose without an import schema.\n"
    returned = "\ufeff Returned idea; {invalid JSON; no date\r\nИдея 🙂\n"
    setup_ref: dict[str, object] = {}

    def retain_setup_pointer(body: dict[str, Any]) -> dict[str, object]:
        prepared = _last_result(body)
        assert prepared["stage"] == "prepared" and prepared["sent"] is False
        setup_ref.update(record_id=prepared["record_id"], revision=prepared["revision"])
        return apply(
            setup_claim_id,
            {
                "kind": "claim",
                "proposition": "Fictional Chat setup prepared; not sent or installed",
                "epistemic_kind": "observed",
                "status": "current",
                "scope_activity_id": str(activity),
                "evidence": [dict(setup_ref)],
                "interpretation_basis": "Exact prepared document, not external observation",
            },
        )

    def return_text(_body: dict[str, Any]) -> dict[str, object]:
        return _integration(
            "retain_text",
            {
                "activity_id": str(activity),
                "origin": "Fictional Chat",
                "content_text": returned,
                "reply_to": dict(setup_ref),
            },
        )

    skill = external_workflow_skill()
    first = Provider(
        [
            {"_tool": "zara_integration", "mode": "catalog"},
            {
                "_tool": "zara_integration",
                "mode": "contract",
                "adapter": "manual",
                "operation": "prepare_document",
            },
            apply(capability_id, capability),
            _integration(
                "prepare_document",
                {
                    "activity_id": str(activity),
                    "external_tool": "Fictional Chat",
                    "document_text": document,
                    "expected_return": "The user's chosen result",
                    "context": [capability_ref],
                },
            ),
            retain_setup_pointer,
            apply(
                article_id,
                {
                    **source(article),
                    "connection": "fictional-article",
                    "scope_activity_id": str(other_activity),
                    "locator": "https://example.invalid/fictional-article",
                    "limitations": ["Supplied text; no network request"],
                },
            ),
            return_text,
        ]
    )
    first_events = run_process(
        directory,
        runtime,
        Bridge(root, owner, directory),
        first,
        prompt="/skill:zaratustra-external Set up fictional discussion and retain the materials.",
        skills=(skill,),
    )
    # Full native resource delivery, not a semantic quality assertion.
    skill_body = skill.read_text(encoding="utf-8").split("---", 2)[2].strip()
    assert any(skill_body in text for text in _user_texts(first.requests[0]))
    setup_id = UUID(str(setup_ref["record_id"]))
    setup = read_knowledge(root, setup_id, owner)
    assert isinstance(setup.state, HandoffState) and setup.state.document == document.encode()
    assert setup.state.status == "prepared" and setup.state.transfer_source is None
    assert KnowledgeRef(record_id=capability_id, revision=1) in setup.state.included
    claim = read_knowledge(root, setup_claim_id, owner)
    assert isinstance(claim.state, ClaimState) and claim.state.scope_activity_id == activity
    saved_article = read_knowledge(root, article_id, owner)
    assert isinstance(saved_article.state, SourceState)
    assert saved_article.state.content == article.encode()
    assert saved_article.state.scope_activity_id == other_activity
    results = [
        json.loads(cast(dict[str, Any], event["result"])["content"][0]["text"])
        for event in first_events
        if event.get("type") == "tool_execution_end" and event.get("toolName") == "zara_integration"
    ]
    imports = [result for result in results if result.get("stage") == "retained"]
    assert len(imports) == 1 and "content_text" not in imports[0]
    return_id = UUID(imports[0]["record_id"])
    saved_return = read_knowledge(root, return_id, owner)
    assert isinstance(saved_return.state, SourceState)
    assert saved_return.state.content == returned.encode()
    assert saved_return.state.derived_from == (KnowledgeRef(record_id=setup_id, revision=1),)
    second = Provider(
        [
            {"mode": "search", "query": "Fictional Chat", "limit": 10},
            {"mode": "open", "record_id": str(setup_claim_id), "revision": 1},
            _integration("read_document", dict(setup_ref)),
            _integration("read_document", {"record_id": str(return_id), "revision": 1}),
            {"mode": "open", "record_id": str(article_id), "revision": 1},
            _integration("product_context", {}),
        ]
    )
    resumed = run_process(
        directory,
        runtime,
        Bridge(root, owner, directory),
        second,
        prompt="/skill:zaratustra-external Resume the saved setup and read the originals.",
        skills=(skill,),
    )
    assert any(skill_body in text for text in _user_texts(second.requests[0]))
    replies = [
        json.loads(cast(dict[str, Any], event["result"])["content"][0]["text"])
        for event in resumed
        if event.get("type") == "tool_execution_end" and isinstance(event.get("result"), dict)
    ]
    for record_id, expected in ((setup_id, document), (return_id, returned), (article_id, article)):
        opened = [reply for reply in replies if reply.get("record_id") == str(record_id)]
        assert len(opened) == 1 and opened[0]["content_text"] == expected
        assert opened[0]["next_offset"] is None
    assert read_work(root, work, owner).state.acceptance is None
    assert read_work(root, work, owner).state.linked_outputs == ()
    return {
        "skill": str(skill),
        "pi_processes": 2,
        "synthetic_localhost_calls": first.calls + second.calls,
        "real_model_calls": 0,
        "skill_body_delivered": True,
        "installed_adapter_tools_executed": True,
        "source_bytes_equal_after_restart": True,
        "source_backed_handoff_reply": True,
        "separate_activity_scope_preserved": True,
        "handoff_status": "prepared",
        "work_accepted": False,
        "limitation": "Synthetic tool choices; live account setup/model judgement not tested",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-runtime", required=True, type=Path)
    args = parser.parse_args()
    scratch = Path.cwd() / "_scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="external-pi-", dir=scratch) as temporary:
        result = run_probe(Path(temporary), args.pi_runtime.resolve())
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
