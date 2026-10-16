"""Seeded behavioral defects: valid source, reached injection, independent assertion failure."""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
API = "core/src/zaratustra_core/api.py"
TYPES = "core/src/zaratustra_core/types.py"
COORD = "app/src/zaratustra_app/coordinator.py"
M = 'print("MUTANT_REACHED", flush=True)'
# Each seed removes a concrete guarantee, rather than corrupting syntax/builds.
SEEDS: list[tuple[str, str, list[tuple[str, str]], str]] = [
    (
        "G1-legacy-dependency",
        API,
        [
            (
                "from __future__ import annotations",
                "from __future__ import annotations" + chr(10) + M + chr(10) + "import zaratustra",
            )
        ],
        "test_isolation.py::test_import_without_legacy_or_pi",
    ),
    (
        "C0-wire-order",
        TYPES,
        [("sort_keys=True", "sort_keys=(" + M + " or False)")],
        "test_contract.py::test_wire_vectors",
    ),
    (
        "G2-native-callback-no-effect",
        COORD,
        [
            (
                "executor.tool_handler = tool_handler",
                "executor.tool_handler = lambda *_: (" + M + ', {"outcome":"committed"})[1]',
            )
        ],
        "test_trace.py::test_fixed_trace[pi]",
    ),
    (
        "G3-stale-write",
        API,
        [
            ("if (head[0] if head else 0) != revision:", "if (" + M + " or False):"),
            ('if expected.get(change["id"]) != current:', "if (" + M + " or False):"),
        ],
        "test_contract.py::test_cas_identity_exact",
    ),
    (
        "G4-lost-input-intent",
        API,
        [
            (
                '        db.execute("INSERT OR REPLACE INTO intents VALUES(?,?,?)", '
                "(kind, subject, dumps(body)))",
                '        if kind == "input":'
                + chr(10)
                + "            "
                + M
                + chr(10)
                + "            return"
                + chr(10)
                + '        db.execute("INSERT OR REPLACE INTO intents VALUES(?,?,?)", '
                "(kind, subject, dumps(body)))",
            )
        ],
        "test_contract.py::test_ingest_idempotency_intent",
    ),
    (
        "G5-drop-original-input",
        COORD,
        [
            ("context = dict(pinned)", M + chr(10) + "        context = dict(pinned)"),
            ('for m in pinned["messages"]', 'for m in pinned["messages"][:-1]'),
        ],
        "test_trace.py::test_fixed_trace[driver]",
    ),
    (
        "G6-lost-late-continuation",
        API,
        [("if high > processed:", "if (" + M + " or False):")],
        "test_trace.py::test_fixed_trace[driver]",
    ),
    (
        "G6-skipped-M19",
        API,
        [
            (
                'or p["message_sequences"] != [m["seq"] for m in messages]',
                "or (" + M + " or False)",
            ),
            ('if p["manifest"] != expected_manifest:', "if (" + M + " or False):"),
        ],
        "test_contract.py::test_missing_m19_cannot_prepare_cutoff20",
    ),
    (
        "G7-ignore-late-fence",
        API,
        [('body["late"] = fenced', M + chr(10) + '            body["late"] = False')],
        "test_contract.py::test_late_fencing",
    ),
    (
        "G8-replay-claim-resend",
        COORD,
        [
            ('attempt_id + ":claim:" + str(uuid4())', 'attempt_id + ":claim"'),
            (
                'action_id = attempt_id + ":action"',
                M + chr(10) + '        action_id = attempt_id + ":action"',
            ),
        ],
        "test_contract.py::test_no_blind_resend_after_claim",
    ),
    (
        "G9-ignore-revocation",
        API,
        [
            (
                'if "*" not in permissions and permission not in permissions:',
                "if (" + M + " or False):",
            )
        ],
        "test_contract.py::test_revocation_and_foreign_receipt",
    ),
    (
        "G9-generic-grant",
        API,
        [('if change["kind"] not in SUBJECTS:', "if (" + M + " or False):")],
        "test_contract.py::test_forbidden_delta_atomic[apply_changes]",
    ),
    (
        "G9-C8-generic-grant",
        API,
        [('if change["kind"] not in SUBJECTS:', "if (" + M + " or False):")],
        "test_contract.py::test_forbidden_delta_atomic[commit_outcome]",
    ),
    (
        "G10-drop-retained-bytes",
        API,
        [
            (
                "body = dict(p)",
                "body = dict(p)"
                + chr(10)
                + "            "
                + M
                + chr(10)
                + '            body["raw_base64"] = ""',
            )
        ],
        "test_contract.py::test_retained_terminal_bytes",
    ),
    (
        "G10-lose-tool-receipt",
        API,
        [
            (
                "UPDATE tool_calls SET receipt=? WHERE attempt=? AND native_id=?",
                "UPDATE tool_calls SET receipt=? WHERE 0 AND attempt=? AND native_id=?",
            ),
            (
                'refs = self._changes(db, p["changes"], req.expected_heads, actor)',
                M
                + chr(10)
                + '            refs = self._changes(db, p["changes"], req.expected_heads, actor)',
            ),
        ],
        "test_contract.py::test_tool_before_terminal_recovery",
    ),
    (
        "G11-wrong-question-revision",
        API,
        [('or wait["revision"] != reply["revision"]', "or (" + M + " or False)")],
        "test_contract.py::test_exact_question_no_acceptance",
    ),
]

SEEDS.extend(
    [
        (
            "G4-early-ingress-commit",
            API,
            [
                (
                    'self._intent(db, "input", conversation, {"high_watermark": seq})',
                    M
                    + chr(10)
                    + "            db.commit()"
                    + chr(10)
                    + '            self._intent(db, "input", conversation, '
                    '{"high_watermark": seq})',
                )
            ],
            "test_crashes.py::test_ingest_crash_atomic[ingest_mid]",
        ),
        (
            "G6-early-outcome-commit",
            API,
            [
                (
                    '            for ref in p.get("outputs", []):',
                    "            "
                    + M
                    + chr(10)
                    + "            db.commit()"
                    + chr(10)
                    + '            for ref in p.get("outputs", []):',
                )
            ],
            "test_crashes.py::test_outcome_crash_atomic[outcome_mid]",
        ),
        (
            "G7-allow-old-generation-publication",
            API,
            [
                (
                    'if generation != work["generation"] or attempt["generation"] != generation:',
                    "if (" + M + " or False):",
                ),
                (
                    'if work["status"] != "running" or attempt["status"] '
                    'not in {"prepared", "claimed"}:',
                    "if (" + M + " or False):",
                ),
            ],
            "test_contract.py::test_old_generation_cannot_publish_current",
        ),
        (
            "G8-accept-changed-command-intent",
            API,
            [('if old["fingerprint"] != fingerprint:', "if (" + M + " or False):")],
            "test_contract.py::test_ingest_idempotency_intent",
        ),
    ]
)


SEEDS.extend(
    [
        (
            "F1-skip-whole-declaration",
            "core/src/zaratustra_core/formats.py",
            [("    validate_schema(schema, path)", "    " + M)],
            "test_binding_findings.py::test_declaration_rejected_atomically",
        ),
        (
            "F2-ignore-active-wait-binding",
            API,
            [
                (
                    'binding = loads(wait["body"])',
                    M + chr(10) + '                binding = loads(wait["body"])',
                ),
                (
                    "if (" + chr(10) + "                    work is None",
                    "if False and (" + chr(10) + "                    work is None",
                ),
            ],
            "test_binding_findings.py::test_old_wait_cannot_unblock_current_question",
        ),
    ]
)


@pytest.mark.parametrize("seed", SEEDS, ids=[s[0] for s in SEEDS])
def test_seeded_defect_is_killed(
    tmp_path: Path, seed: tuple[str, str, list[tuple[str, str]], str]
) -> None:
    name, source_path, replacements, node = seed
    tree = tmp_path / "mutant"
    for package in ("core", "app"):
        shutil.copytree(ROOT / "packages" / package / "src", tree / package / "src")
    path = tree / source_path
    original = path.read_text(encoding="utf-8")
    changed = original
    for before, after in replacements:
        assert before in changed, "stale mutation anchor: " + name
        changed = changed.replace(before, after)
    compile(changed, str(path), "exec")
    path.write_text(changed, encoding="utf-8")
    prefix = [str(tree / "core" / "src"), str(tree / "app" / "src"), str(ROOT)]
    script = (
        "import sys;sys.path[:0]="
        + repr(prefix)
        + ";import pytest;raise SystemExit(pytest.main(sys.argv[1:]))"
    )
    env = os.environ.copy()
    env.pop("ZARA_RESTART_EVIDENCE", None)
    run = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            script,
            str(ROOT / "tests" / "restart" / node),
            "--basetemp",
            str(tmp_path / "run"),
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    report: dict[str, Any] = {
        "seed": name,
        "test": node,
        "returncode": run.returncode,
        "injection_reached": "MUTANT_REACHED" in run.stdout,
        "behavioral_failure": "AssertionError" in run.stdout
        or "DID NOT RAISE" in run.stdout
        or any(line.startswith("E") and "assert " in line for line in run.stdout.splitlines()),
        "stdout": run.stdout,
        "stderr": run.stderr,
        "diff": "".join(
            difflib.unified_diff(
                original.splitlines(True),
                changed.splitlines(True),
                fromfile=source_path,
                tofile=source_path + ".mutant",
            )
        ),
    }
    destination = os.environ.get("ZARA_RESTART_NEGATIVES")
    if destination:
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (name + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    assert run.returncode == 1, report
    assert report["injection_reached"], report
    assert report["behavioral_failure"], report
    assert "SyntaxError" not in run.stdout and "ImportError" not in run.stdout, report
