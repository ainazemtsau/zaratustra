"""Authorized, test-only Codex Luna receiver. Not an installed product adapter.

Core reserves finite executor invocations. Provider sends/retries inside official
Codex are not exactly observable and are not represented as measured API calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from zaratustra_app import Coordinator, Sleep
from zaratustra_core import Core


def obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def array(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


TEXT = {"type": "string"}
INT = {"type": "integer"}
REF = obj(
    {"id": TEXT, "revision": INT, "role": {"enum": ["exact", "must_be_current"], "type": "string"}}
)
SOURCE = obj({"sequence": INT, "index": INT, "sha256": TEXT})
PROGRESS = obj(
    {
        "format": {"type": "string", "enum": ["sleep-progress/v1"]},
        "work_id": TEXT,
        "method_ref": REF,
        "scope": TEXT,
        "source_high_watermark": INT,
        "enumeration_cursor": array(INT),
        "enumerated_source_refs": array(SOURCE),
        "selected_source_refs": array(SOURCE),
        "delivered_manifest_refs": array(obj({"attempt_id": TEXT, "sha256": TEXT})),
        "analysis_result_refs": array(REF),
        "unexplored_coverage_position": TEXT,
        "applied_receipts": array(TEXT),
        "proposed_changes": array(TEXT),
        "remaining_refs": array(SOURCE),
        "return_conditions": array(TEXT),
        "consumed_resource": INT,
        "unresolved_calls": array(TEXT),
        "stop_reason": TEXT,
        "continuation": TEXT,
    }
)
SCHEMA = obj(
    {
        "state": {"type": "string", "enum": ["ready", "completed"]},
        "text": TEXT,
        "edits": array(
            obj(
                {
                    "id": TEXT,
                    "kind": {"type": "string", "enum": ["memory", "method"]},
                    "key": TEXT,
                    "scope": TEXT,
                    "text": TEXT,
                    "expected_revision": INT,
                    "source_refs": array(REF),
                    "application": {"type": "string", "enum": ["active", "proposal", "withdrawn"]},
                }
            )
        ),
        "analyses": array(
            obj(
                {
                    "id": TEXT,
                    "scope": TEXT,
                    "expected_revision": INT,
                    "content": TEXT,
                    "sources": array(SOURCE),
                }
            )
        ),
        "progress": {"anyOf": [PROGRESS, {"type": "null"}]},
        "progress_record_revision": INT,
    }
)
DISABLED = [
    "shell_tool",
    "hooks",
    "apps",
    "plugins",
    "remote_plugin",
    "multi_agent",
    "browser_use",
    "computer_use",
    "image_generation",
    "shell_snapshot",
    "unbounded_connection_retries",
]


class CodexLunaExecutor:
    """Explicit official logged-in CLI, no credential extraction or provider fallback."""

    resource_upper = 1
    tool_handler: Any = None

    def __init__(self, root: Path, evidence: Path, *, invocation_cap: int = 2):
        self.root, self.evidence = root.resolve(), evidence.resolve()
        self.invocation_cap, self.invocations = invocation_cap, 0

    def run(self, context: dict[str, Any], action: str) -> bytes:
        if self.invocations >= self.invocation_cap:
            raise RuntimeError("bounded Codex invocation limit exhausted")
        self.invocations += 1
        destination = self.evidence / ("invocation-" + str(self.invocations))
        destination.mkdir(parents=True, exist_ok=False)
        schema = destination / "schema.json"
        answer = destination / "answer.json"
        schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
        cwd = self.root / ("receiver-" + str(self.invocations))
        cwd.mkdir(parents=True, exist_ok=False)
        command = shutil.which("codex.cmd") or shutil.which("codex")
        if command is None:
            raise RuntimeError("required official Codex CLI unavailable")
        argv = [
            command,
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--model",
            "gpt-6-luna",
            "--sandbox",
            "read-only",
            "--json",
            "--color",
            "never",
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(answer),
            "-C",
            str(cwd),
            "-c",
            'forced_login_method="chatgpt"',
            "-c",
            'web_search="disabled"',
            "-c",
            "project_doc_max_bytes=0",
        ]
        for feature in DISABLED:
            argv.extend(["--disable", feature])
        argv.append("-")
        prompt = (
            "You are the executor of this ordinary Zaratustra Work. Follow its exact "
            "Method instructions using the actual supplied source bytes. No external tools. "
            "Return the structured answer from the supplied schema. This test receiver "
            "losslessly maps edits.text to free-text Change.body, analyses to ordinary data "
            "sleep-analysis/v1 records, and progress to the existing progress record. "
            "Put ALL analysis records in analyses, never as a text edit. Reference those "
            "analysis IDs as exact objects in progress.analysis_result_refs. Edits are only "
            "free-text memory/Method changes. Event sequence gaps can be source-less commands, "
            "and are not evidence that a source was omitted or remains unexplored. "
            "For access or ordinary Work use progress=null and analyses=[] when not needed. "
            "For Sleep supply complete progress with exact reference OBJECTS, not ID strings. "
            "Apply the complete Method; retain all required progress fields. "
            "Use data/memory/method exactrefs from the context. Your content and questions "
            "must come from your analysis, not assumed fixture expectations. "
            "Resource units in this test profile are Codex CLI invocations; unknown "
            "provider retries/usage are not zero. context:\n"
            + json.dumps(context, ensure_ascii=False)
        )
        (destination / "prompt.txt").write_text(prompt, encoding="utf-8")
        manifest = {
            "argv": argv,
            "action_id": action,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "resource_unit": "codex_exec",
            "invocation_cap": self.invocation_cap,
            "physical_provider_sends": "unknown",
            "deadline_seconds": 240,
        }
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        result = subprocess.run(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=240,
            cwd=cwd,
        )
        (destination / "stdout.jsonl").write_text(result.stdout, encoding="utf-8")
        (destination / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        (destination / "exit.json").write_text(
            json.dumps({"returncode": result.returncode}), encoding="utf-8"
        )
        if result.returncode != 0:
            raise RuntimeError("Official Codex CLI failed; retained output at " + str(destination))
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        forbidden = [
            event
            for event in events
            if event.get("item", {}).get("type") not in {None, "agent_message", "reasoning"}
        ]
        if forbidden:
            raise RuntimeError("Unexpected tool event invalidates semantic profile")
        return answer.read_bytes()

    @staticmethod
    def decode(raw: bytes) -> dict[str, Any]:
        """Processing occurs AFTER Core retains the exact terminal, including invalid bytes."""
        parsed = json.loads(raw)
        changes = []
        expected = {}
        for analysis in parsed["analyses"]:
            changes.append(
                {
                    "id": analysis["id"],
                    "kind": "data",
                    "key": analysis["id"],
                    "scope": analysis["scope"],
                    "body": {
                        "format": "sleep-analysis/v1",
                        "sources": analysis["sources"],
                        "content": analysis["content"],
                    },
                }
            )
            expected[analysis["id"]] = analysis["expected_revision"]
        for edit in parsed["edits"]:
            changes.append(
                {
                    "id": edit["id"],
                    "kind": edit["kind"],
                    "key": edit["key"],
                    "scope": edit["scope"],
                    "body": edit["text"],
                    "source_refs": edit["source_refs"],
                    "application": edit["application"],
                }
            )
            expected[edit["id"]] = edit["expected_revision"]
        if parsed["progress"] is not None:
            progress = parsed["progress"]
            progress_id = progress["work_id"] + ":progress"
            changes.append(
                {
                    "id": progress_id,
                    "kind": "data",
                    "key": "sleep-progress:" + progress["work_id"],
                    "scope": progress["scope"],
                    "body": progress,
                }
            )
            expected[progress_id] = parsed["progress_record_revision"]
        output = {
            "state": parsed["state"],
            "text": parsed["text"],
            "changes": changes,
            "expected_heads": expected,
        }
        return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--phase", choices=["access", "sleep"], required=True)
    args = parser.parse_args()
    root, evidence = args.root.resolve(), args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    core, token = Core.initialize(root / "space")
    owner = core.connect(token)
    changes: list[dict[str, Any]] = [
        {
            "id": "profile",
            "kind": "profile",
            "key": "codex-luna-evaluation",
            "body": {
                "test_only": True,
                "model": "gpt-6-luna",
                "resource_unit": "codex_exec",
                "exact_physical_provider_sends": "unknown",
            },
        },
        {
            "id": "practice",
            "kind": "method",
            "key": "exhibit-label",
            "body": (
                "Draft an informative exhibit label using current memory and supplied facts. "
                "Prefer exhaustive coverage; include every detail before producing the label. "
                "Return ordinary JSON {state:'completed',text:<usable label>}. No acceptance"
                " claims."
            ),
        },
        {
            "id": "memory",
            "kind": "memory",
            "key": "label-length",
            "body": (
                "Early planning assumption: labels should be 180–200 words; not yet "
                "confirmed by curator."
            ),
        },
        {
            "id": "facts",
            "kind": "data",
            "key": "specimen",
            "body": (
                "Fictional exhibit: night-blooming cactus, flowers open after sunset and "
                "close next morning. "
                "In this indoor trial only 3 of 12 buds opened. No evidence establishing its"
                " wild pollinator."
            ),
        },
        {
            "id": "ordinary",
            "kind": "data",
            "key": "routine",
            "body": (
                "Routine visitor observation: the first sentence and large-print species "
                "name were read; "
                "the provenance appendix was usually skipped. No complaint was filed."
            ),
        },
        {
            "id": "success",
            "kind": "data",
            "key": "success",
            "body": (
                "Trial A: a 42-word draft with one clear observation was approved by the "
                "fictional curator. "
                "The curator asked to keep future display labels 35–50 words, moving "
                "detailed notes off-label."
            ),
        },
        {
            "id": "error",
            "kind": "data",
            "key": "error",
            "body": (
                "Trial B: a 190-word label was returned unread because it did not fit the display. "
                "A short Trial C also failed: it asserted a wild pollinator unsupported by "
                "observations. "
                "Length alone therefore did not establish accuracy. No further negative "
                "trials exist."
            ),
        },
    ]
    for change in changes:
        owner.call(
            "apply_changes", {"changes": [change]}, uuid4().hex, expected_heads={change["id"]: 0}
        )
    client = core.connect(
        core.grant(
            token,
            "semantic-executor",
            [
                "read",
                "apply_changes",
                "open_work",
                "prepare_attempt",
                "claim_dispatch",
                "observe_attempt",
                "commit_outcome",
                "control_work",
                "reserve_tool",
                "write:memory:space",
                "write:method:space",
            ],
            origin="host",
        )
    )
    receiver = CodexLunaExecutor(root, evidence, invocation_cap=2)
    coordinator = Coordinator(client)
    outcome: dict[str, Any]
    try:
        if args.phase == "access":
            method = {
                "id": "access",
                "kind": "method",
                "key": "access",
                "body": (
                    'Return ONLY JSON {"state":"completed","text":"access established"}. '
                    "This fictional access check is not a usefulness evaluation."
                ),
            }
            owner.call(
                "apply_changes", {"changes": [method]}, "access:seed", expected_heads={"access": 0}
            )
            client.call(
                "open_work",
                {
                    "id": "access",
                    "conversation": "access",
                    "goal": "Verify access",
                    "method_ref": {"id": "access", "revision": 1},
                    "inputs": [],
                    "call_limit": 1,
                    "continuation_policy": "durable",
                },
                "access:open",
            )
            prepared = coordinator.prepare(
                "access", "access-attempt", {"id": "profile", "revision": 1}
            )
            coordinator.dispatch("access-attempt", prepared["generation"], receiver)
            outcome = coordinator.recover("access-attempt", decoder=receiver.decode)
        else:
            sleep = Sleep(client)
            sleep.start(work_id="sleep", call_limit=2, portion=32)
            outcome = sleep.run("sleep", {"id": "profile", "revision": 1}, receiver)
        status = {
            "success": True,
            "outcome": outcome,
            "semantic_verdict": "requires independent review",
        }
    except Exception as error:
        status = {"success": False, "error_type": type(error).__name__, "error": str(error)}
    (evidence / "snapshot.json").write_text(
        json.dumps(coordinator.snapshot(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (evidence / "status.json").write_text(
        json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False))
    return 0 if status["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
