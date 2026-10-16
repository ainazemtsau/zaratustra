"""Reached D failures; each targets a specific externally observed invariant."""

from pathlib import Path

import pytest

from .test_negative_controls import API, M
from .test_negative_controls import test_seeded_defect_is_killed as run_seed

STORAGE = "core/src/zaratustra_core/storage.py"
MAINTENANCE = "core/src/zaratustra_core/maintenance.py"
SEEDS: list[tuple[str, str, list[tuple[str, str]], str]] = [
    (
        "D-goal-prose-capped-as-identifier",
        "core/src/zaratustra_core/shapes.py",
        [
            ("    goal: NonEmptyText", "    goal: Id"),
            (
                "    except ValidationError as exc:",
                "    except ValidationError as exc:"
                + chr(10)
                + '        if any(error["loc"][-1] == "goal" for error in exc.errors()):'
                + chr(10)
                + "            "
                + M,
            ),
        ],
        "test_prose_fields.py::test_long_goal_c8_handoff_keeps_exact_prose",
    ),
    (
        "D-question-prose-capped-as-identifier",
        "core/src/zaratustra_core/shapes.py",
        [
            ("    question: NonEmptyText", "    question: Id"),
            (
                "    except ValidationError as exc:",
                "    except ValidationError as exc:"
                + chr(10)
                + '        if any(error["loc"][-1] == "question" for error in exc.errors()):'
                + chr(10)
                + "            "
                + M,
            ),
        ],
        "test_prose_fields.py::test_long_wait_question_is_prose_and_replay_is_send_free",
    ),
    (
        "D-known-core-refusal-escapes-cli",
        "app/src/zaratustra_app/cli.py",
        [
            (
                "    except CoreError as error:",
                "    except CoreError as error:"
                + chr(10)
                + "        "
                + M
                + chr(10)
                + "        raise",
            )
        ],
        "test_prose_fields.py::test_cli_known_invalid_retains_terminal_without_resend",
    ),
    (
        "D-model-tool-independent-budget",
        API,
        [('                    fail("denied", "tool.initial_work")', "                    " + M)],
        "test_work_handoff.py::test_correlated_c3_initial_work_is_atomically_refused",
    ),
    (
        "D-tool-initial-work-reserved-before-denial",
        "app/src/zaratustra_app/coordinator.py",
        [
            (
                '                raise CoreError("denied", "native_tool.initial_work")',
                "                " + M,
            )
        ],
        "test_work_handoff.py::test_active_model_tool_cannot_mint_independent_budget[sleep]",
    ),
    (
        "D-handoff-cursor-consumed-early",
        API,
        [
            (
                '(processed, attempt["conversation"], cursor),',
                "(" + M + ' or attempt["cutoff"], attempt["conversation"], cursor),',
            )
        ],
        "test_work_handoff.py::test_handoff_preserves_raw_input_then_scoped_result",
    ),
    (
        "D-handoff-child-published-partially",
        API,
        [
            (
                '        if state == "ready":'
                + chr(10)
                + '            self._intent(db, "prepare", body["id"], {})',
                "        if continuation is not None:"
                + chr(10)
                + "            "
                + M
                + chr(10)
                + "            db.commit()"
                + chr(10)
                + '        if state == "ready":'
                + chr(10)
                + '            self._intent(db, "prepare", body["id"], {})',
            )
        ],
        "test_work_handoff.py::test_physical_loss_inside_child_creation_rolls_back_handoff",
    ),
    (
        "D-handoff-final-replayed-as-new",
        API,
        [
            (
                "            if old:"
                + chr(10)
                + '                if old["fingerprint"] != digest(p):'
                + chr(10)
                + '                    fail("idempotency_conflict", "result_slot")',
                "            if old and ("
                + M
                + " or False):"
                + chr(10)
                + '                if old["fingerprint"] != digest(p):'
                + chr(10)
                + '                    fail("idempotency_conflict", "result_slot")',
            )
        ],
        "test_work_handoff.py::test_handoff_preserves_raw_input_then_scoped_result",
    ),
    (
        "D-handoff-budget-reset",
        API,
        [('if child["call_limit"] > remaining:', "if (" + M + " or False):")],
        "test_work_handoff.py::test_bad_handoff_rolls_back_every_boundary[budget]",
    ),
    (
        "D-routing-orphan-tool-publication",
        "app/src/zaratustra_app/coordinator.py",
        [
            (
                '                raise CoreError("denied", "ordinary.routing_atomic_handoff")',
                "                " + M,
            )
        ],
        "test_ordinary_activity.py::test_discovery_tool_cannot_publish_orphan_activity",
    ),
    (
        "D-scoped-memory-dropped",
        "app/src/zaratustra_app/coordinator.py",
        [
            (
                'head["scope"] not in {"space", scope}',
                'head["scope"] not in ({"space"} if (' + M + ' or True) else {"space", scope})',
            )
        ],
        "test_ordinary_activity.py::test_scoped_execution_pins_only_applicable_memory",
    ),
    (
        "D-addressed-reply-rerouted",
        "app/src/zaratustra_app/conversation.py",
        [("                and not dispatched", "                and (" + M + " or True)")],
        "test_ordinary_activity.py::test_addressed_reply_stays_in_existing_scoped_work",
    ),
    (
        "D-handoff-reopen-rediscovery",
        "app/src/zaratustra_app/conversation.py",
        [("        if active:", "        if active and (" + M + " or False):")],
        "test_ordinary_activity.py::test_handoff_reopen_uses_retained_terminal[after]",
    ),
    (
        "D-native-profile-cap-below-floor",
        "app/src/zaratustra_app/executor_port.py",
        [
            (
                'if self.auth_mode == "pi-chatgpt" and 0 < self.max_tokens < 16:',
                "if (" + M + " or False):",
            )
        ],
        "test_ordinary_activity.py::test_native_cap_below_sdk_floor_refused_before_runtime[1]",
    ),
    (
        "D-native-chatgpt-effort-compat-omitted",
        "app/src/zaratustra_app/executor_port.py",
        [
            (
                '"compat": {"supportsMidConvoEffort": False}',
                '"compat": {"supportsMidConvoEffort": (' + M + " or True)}",
            )
        ],
        "test_conversation.py::test_native_pi_oauth_launcher_controlled",
    ),
    (
        "D-pinned-reference-closure-skipped",
        MAINTENANCE,
        [("        verify_references(db, path)", "        " + M)],
        "test_backup_references.py::test_rehashed_pinned_reference_corruption_refused[profile_ref]",
    ),
    (
        "D-declared-reference-admission-skipped",
        API,
        [
            (
                '                    self._exact(db, ref | {"role": "exact"})',
                "                    " + M,
            )
        ],
        "test_schema_references.py::test_dangling_schema_ref_rejects_entire_bundle[refs-commit_outcome]",
    ),
    (
        "D-pinned-json-types-conflated",
        "core/src/zaratustra_core/backup_refs.py",
        [
            (
                "        return digest(left) == digest(right)",
                "        " + M + chr(10) + "        return left == right",
            )
        ],
        "test_backup_references.py::test_pinned_json_boolean_is_not_integer",
    ),
    (
        "D-cancelled-ID-reused",
        "app/src/zaratustra_app/conversation.py",
        [
            (
                '                work_id = base_id + ":after-cancel:" + str(successor)',
                "                " + M + chr(10) + "                break",
            )
        ],
        "test_conversation.py::test_cancelled_entry_requires_new_input_then_new_work",
    ),
    (
        "D-cancelled-blind-restart",
        "app/src/zaratustra_app/conversation.py",
        [
            (
                "if boundary >= cursor and not any(",
                "if (" + M + " or False) and not any(",
            )
        ],
        "test_conversation.py::test_cancelled_entry_requires_new_input_then_new_work",
    ),
    (
        "D-outbox-published-partial",
        "app/src/zaratustra_app/conversation.py",
        [
            (
                '        staging = pending.with_suffix(".staging")',
                "        " + M + chr(10) + "        staging = pending",
            )
        ],
        "test_conversation.py::test_entry_outbox_physical_crash[partial_write]",
    ),
    (
        "D-database-hash-ignored",
        MAINTENANCE,
        [
            (
                'or hashlib.sha256(database).hexdigest() != manifest["database_sha256"]',
                "or (" + M + " or False)",
            )
        ],
        "test_maintenance.py::test_corrupt_partial_backups_refused[valid_database_change]",
    ),
    (
        "D-logical-integrity-skipped",
        MAINTENANCE,
        [
            (
                "def integrity(path: Path) -> None:",
                "def integrity(path: Path) -> None:"
                + chr(10)
                + "    "
                + M
                + chr(10)
                + "    return",
            )
        ],
        "test_maintenance.py::test_rehashed_incoherent_backup_refused[orphan_head]",
    ),
    (
        "D-ref-before-durable",
        API,
        [
            (
                '                durable(self.root / "artifacts" / sha256, raw)',
                "                "
                + M
                + chr(10)
                + '                db.execute("INSERT INTO artifacts VALUES(?,?,?)", '
                '(sha256, len(raw), p["content_type"]))'
                + chr(10)
                + "                db.commit()"
                + chr(10)
                + '                durable(self.root / "artifacts" / sha256, raw)',
            )
        ],
        "test_maintenance.py::test_staging_physical_crash[stage_sync]",
    ),
    (
        "D-ignore-artifact-integrity",
        STORAGE,
        [
            (
                "if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha256:",
                "if (" + M + " or False):",
            )
        ],
        "test_maintenance.py::test_corrupt_partial_backups_refused[bytes]",
    ),
    (
        "D-incomplete-inventory",
        MAINTENANCE,
        [
            (
                'if rows != manifest["artifacts"] or original != manifest["source"]:',
                "if (" + M + " or False):",
            )
        ],
        "test_maintenance.py::test_corrupt_partial_backups_refused[manifest]",
    ),
    (
        "D-retain-old-credentials",
        MAINTENANCE,
        [
            (
                '            db.execute("DELETE FROM credentials")',
                "            " + M,
            )
        ],
        "test_maintenance.py::test_backup_complete_new_epoch_quarantine",
    ),
    (
        "D-retain-old-epoch",
        MAINTENANCE,
        [
            (
                '"UPDATE meta SET instance=?,space=?,epoch=epoch+1"',
                '"UPDATE meta SET instance=?,space=?,epoch=epoch+0"',
            ),
            (
                "        token = secrets.token_urlsafe(32)",
                "        " + M + chr(10) + "        token = secrets.token_urlsafe(32)",
            ),
        ],
        "test_maintenance.py::test_backup_complete_new_epoch_quarantine",
    ),
    (
        "D-allow-quarantine-writes",
        API,
        [
            (
                '                fail("denied", "quarantined")',
                "                " + M,
            )
        ],
        "test_maintenance.py::test_backup_complete_new_epoch_quarantine",
    ),
    (
        "D-maintenance-fence-only-late",
        MAINTENANCE,
        [
            ("from contextlib import closing", "from contextlib import closing, nullcontext"),
            ("with exclusion(core.root):", "with (" + M + " or nullcontext()):"),
        ],
        "test_maintenance.py::test_backup_crash_and_maintenance_excludes_writer[backup_hold_inventory]",
    ),
    (
        "D-diagnostics-body-leak",
        API,
        [
            (
                '                "excluded": ["conversation_text", "record_bodies", '
                '"credentials", "paths"],',
                '                "leak": ('
                + M
                + ' or db.execute("SELECT body FROM records LIMIT 1").fetchone()[0]),'
                + chr(10)
                + '                "excluded": ["conversation_text", "record_bodies", '
                '"credentials", "paths"],',
            )
        ],
        "test_maintenance.py::test_artifact_bytes_refs_and_diagnostics",
    ),
]


@pytest.mark.parametrize("seed", SEEDS, ids=[s[0] for s in SEEDS])
def test_delivery_defect_is_killed(
    tmp_path: Path, seed: tuple[str, str, list[tuple[str, str]], str]
) -> None:
    run_seed(tmp_path, seed)
    assert (tmp_path / "mutant" / seed[1]).is_file()
